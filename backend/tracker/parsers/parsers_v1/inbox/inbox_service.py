import os
import re
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
import fitz  # PyMuPDF
from django.utils import timezone
from django.db import transaction
from django.apps import apps

from tracker.models import (
    Account,
    Bank,
    BankCredential,
    DocumentInboxItem,
    StatementIngestRegistry,
    StatementStagingLine,
    UserStatementTemplate,
)
from tracker.parsers.parsers_v1.orchestrator import process_bank_statement
from tracker.parsers.parsers_v1.utils import validator

logger = logging.getLogger(__name__)


class DocumentKeychainResolver:
    """
    Decodes statement metadata dynamically by cross-referencing
    decrypted document text against registered Database Entities.
    Zero hardcoded bank logic.
    """

    @classmethod
    def get_aggregated_passwords(
        cls, preferred_account: Optional[Account] = None
    ) -> List[str]:
        keychain: List[str] = []

        if preferred_account:
            pref_cred = BankCredential.objects.filter(account=preferred_account).first()
            if pref_cred and isinstance(pref_cred.password_vault, list):
                keychain.extend(
                    [str(p).strip() for p in pref_cred.password_vault if str(p).strip()]
                )

        all_creds = BankCredential.objects.exclude(account=preferred_account)
        for cred in all_creds:
            if isinstance(cred.password_vault, list):
                for pwd in cred.password_vault:
                    clean_pwd = str(pwd).strip()
                    if clean_pwd and clean_pwd not in keychain:
                        keychain.append(clean_pwd)

        return keychain

    @classmethod
    def unlock_document(cls, file_path: str, initial_hint: str = "") -> Tuple[str, str]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF statement not found at: {file_path}")

        doc = fitz.open(file_path)
        working_password = ""

        if doc.is_encrypted:
            preferred_acc = (
                Account.objects.filter(account_number__endswith=initial_hint).first()
                if initial_hint
                else None
            )
            keychain = cls.get_aggregated_passwords(preferred_acc)

            success = False
            for pwd in keychain:
                if doc.authenticate(pwd) > 0:
                    working_password = pwd
                    success = True
                    break

            if not success:
                doc.close()
                raise PermissionError(
                    "Decryption failed. No matching password found in platform keychain."
                )

        page_0 = doc[0]
        header_text = page_0.get_text("text")
        doc.close()

        return working_password, header_text

    @classmethod
    def identify_account_from_text(
        cls, header_text: str, fallback_hint: str = "", fallback_bank_name: str = ""
    ) -> Optional[Account]:
        upper_text = header_text.upper()
        clean_doc_stream = re.sub(r"[\s\-\:\.\/]", "", upper_text)

        all_accounts = list(Account.objects.select_related("bank").all())

        # PASS 1: Exact continuous Account Number match
        for acc in all_accounts:
            if acc.account_number:
                clean_acc_num = re.sub(
                    r"[\s\-\:\.]", "", str(acc.account_number)
                ).upper()
                if len(clean_acc_num) >= 6 and clean_acc_num in clean_doc_stream:
                    return acc

        # PASS 2: Institutional Bank Marker + Account Suffix Match
        for acc in all_accounts:
            if not acc.account_number:
                continue

            clean_acc_str = str(acc.account_number).strip()
            acc_suffix = (
                clean_acc_str[-4:] if len(clean_acc_str) >= 4 else clean_acc_str
            )
            bank_obj = getattr(acc, "bank", None)

            markers = []
            if bank_obj:
                if bank_obj.display_name:
                    markers.append(bank_obj.display_name.upper())
                if bank_obj.code:
                    markers.append(bank_obj.code.upper())
                if hasattr(bank_obj, "ifsc_prefix") and bank_obj.ifsc_prefix:
                    markers.append(bank_obj.ifsc_prefix.upper())

            bank_matched = any(m in upper_text for m in markers if m)
            suffix_matched = (acc_suffix in upper_text) or (
                acc_suffix == str(fallback_hint).strip()
            )

            if bank_matched and suffix_matched:
                return acc

        # PASS 3: Fallback Hint Match
        if fallback_hint:
            clean_hint = str(fallback_hint).strip()
            query = Account.objects.filter(account_number__endswith=clean_hint)
            if fallback_bank_name:
                query = query.filter(
                    bank__display_name__icontains=fallback_bank_name
                ) | query.filter(bank__code__icontains=fallback_bank_name)
            acc = query.first()
            if acc:
                return acc

        return None


class InboxStatementService:
    @classmethod
    def preview_inbox_item(cls, inbox_item_id: str) -> Dict[str, Any]:
        inbox_item = DocumentInboxItem.objects.filter(id=inbox_item_id).first()
        if not inbox_item:
            raise ValueError(f"DocumentInboxItem {inbox_item_id} not found.")

        file_path = inbox_item.file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Attachment file not found at: {file_path}")

        working_password, header_text = DocumentKeychainResolver.unlock_document(
            file_path=file_path,
            initial_hint=inbox_item.account_hint or "",
        )

        account = DocumentKeychainResolver.identify_account_from_text(
            header_text=header_text,
            fallback_hint=inbox_item.account_hint or "",
            fallback_bank_name=inbox_item.bank_name or "",
        )

        if not account:
            extracted_snippet = (
                " ".join(header_text.split()[:40]) if header_text else ""
            )
            return {
                "status": "ACCOUNT_REGISTRATION_REQUIRED",
                "inbox_item_id": str(inbox_item.id),
                "filename": inbox_item.filename or os.path.basename(file_path),
                "detected_bank_hint": inbox_item.bank_name or "Unknown Institution",
                "detected_account_hint": inbox_item.account_hint or "N/A",
                "message": (
                    f"This document could not be mapped to any registered account. "
                    f"Detected hint: '{inbox_item.account_hint}' ({inbox_item.bank_name}). "
                    f"Please register or link this account in settings to proceed."
                ),
                "header_snippet": extracted_snippet,
                "preview_dataset": [],
                "count": 0,
            }

        clean_acc = str(account.account_number).strip()
        actual_suffix = clean_acc[-4:] if len(clean_acc) >= 4 else clean_acc
        if inbox_item.account_hint != actual_suffix:
            inbox_item.account_hint = actual_suffix
            inbox_item.save(update_fields=["account_hint"])

        if working_password:
            cred, _ = BankCredential.objects.get_or_create(
                account=account, defaults={"password_vault": []}
            )
            vault = cred.password_vault if isinstance(cred.password_vault, list) else []
            if working_password in vault:
                vault.remove(working_password)
            vault.insert(0, working_password)
            cred.password_vault = vault[:5]
            cred.save(update_fields=["password_vault"])

        template_obj = (
            UserStatementTemplate.objects.filter(account=account)
            .exclude(parser_strategy_code="UNIVERSAL_CSV_FLOW")
            .first()
        ) or UserStatementTemplate.objects.filter(account=account).first()

        db_records = list(
            StatementStagingLine.objects.filter(account_id=account.id).values(
                "row_identifier",
                "narration",
                "cheque_ref_number",
                "raw_statement_date",
                "amount",
                "running_balance",
                "credit",
                "debit",
            )
        )
        existing_hashes = {
            r["row_identifier"] for r in db_records if r["row_identifier"]
        }
        database_lookup_dict = {
            r["row_identifier"]: r for r in db_records if r["row_identifier"]
        }

        with open(file_path, "rb") as file_handle:
            processed_bundle, op_bal, system_noise = process_bank_statement(
                uploaded_file=file_handle,
                template_obj=template_obj,
                account_id=str(account.id),
                existing_database_hashes=existing_hashes,
                password_vault=[working_password] if working_password else [],
            )

        intermediate_txns = (
            processed_bundle.get("transactions_list", [])
            if isinstance(processed_bundle, dict)
            else processed_bundle
        )

        export_filename = inbox_item.filename or os.path.basename(file_path)

        payload = validator.run_final_math(
            intermediate_txns,
            op_bal,
            template_obj=template_obj,
            account_id=str(account.id),
            export_filename=export_filename,
        )

        preview_dataset = payload.get("preview_dataset", [])

        _, _ = validator.process_and_filter_rows(
            preview_dataset=preview_dataset,
            account=account,
            bank=account.bank if hasattr(account, "bank") else None,
            existing_hashes=existing_hashes,
            database_lookup_dict=database_lookup_dict,
        )

        active_strategy = getattr(
            template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW"
        ).upper()

        return {
            "status": "SUCCESS",
            "inbox_item_id": str(inbox_item.id),
            "account_id": str(account.id),
            "account_name": account.name,
            "applied_template": (
                template_obj.template_name if template_obj else "UNIVERSAL"
            ),
            "strategy_processed": active_strategy,
            "preview_dataset": preview_dataset,
            "opening_balance": payload.get("opening_balance", op_bal),
            "closing_balance": payload.get("closing_balance", 0.0),
            "total_debit": payload.get("total_debit", 0.0),
            "total_credit": payload.get("total_credit", 0.0),
            "count": len(preview_dataset),
        }

    @classmethod
    def commit_inbox_item(
        cls,
        inbox_item_id: str,
        preview_dataset: List[Dict[str, Any]],
        meta_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        inbox_item = DocumentInboxItem.objects.filter(id=inbox_item_id).first()
        if not inbox_item:
            raise ValueError(f"DocumentInboxItem {inbox_item_id} not found.")

        account = DocumentKeychainResolver.identify_account_from_text(
            header_text="",
            fallback_hint=inbox_item.account_hint or "",
            fallback_bank_name=inbox_item.bank_name or "",
        )
        if not account:
            raise ValueError("Target account could not be resolved for commit.")

        create_pool: List[StatementStagingLine] = []
        update_count = 0
        now_ts = timezone.now()

        with transaction.atomic():
            registry = StatementIngestRegistry.objects.create(
                account=account,
                file_name=inbox_item.filename or os.path.basename(inbox_item.file_path),
                file_type="PDF",
                vault_decrypted=True,
                report_from_date=inbox_item.period_start or now_ts.date(),
                report_to_date=inbox_item.period_end or now_ts.date(),
                opening_balance=Decimal(str(meta_summary.get("openingBalance", 0.0))),
                closing_balance=Decimal(str(meta_summary.get("closingBalance", 0.0))),
                total_debit_amount=Decimal(str(meta_summary.get("totalDebit", 0.0))),
                total_credit_amount=Decimal(str(meta_summary.get("totalCredit", 0.0))),
                total_row_count=len(preview_dataset),
                source_channel="DOCUMENT_INBOX",
            )

            for tx in preview_dataset:
                action = tx.get("pipeline_action", "INSERT")
                row_id = tx.get("row_identifier")

                original_narr = str(
                    tx.get("narration") or tx.get("narration_description") or ""
                ).strip()

                if action in ["UPDATE", "UPDATE_ENRICHMENT", "EXISTING"] and row_id:
                    StatementStagingLine.objects.filter(
                        account_id=account.id, row_identifier=row_id
                    ).update(uploaded_at=now_ts)
                    update_count += 1

                elif action == "INSERT":
                    # 🔍 DIAGNOSTIC LOG FOR ROW 0
                    if len(create_pool) == 0:
                        logger.warning(f"🔍 [DEBUG TX KEYS]: {list(tx.keys())}")
                        logger.warning(
                            f"🔍 [DEBUG RAW_DATE VALUES]: "
                            f"raw_statement_date={repr(tx.get('raw_statement_date'))}, "
                            f"post_date={repr(tx.get('post_date'))}, "
                            f"date={repr(tx.get('date'))}, "
                            f"value_date={repr(tx.get('value_date'))}"
                        )

                    # Exhaustive check across all potential strategy date keys
                    raw_date = (
                        tx.get("raw_statement_date")
                        or tx.get("post_date")
                        or tx.get("date")
                        or tx.get("value_date")
                        or tx.get("txn_date")
                    )

                    parsed_date = None

                    # 1. Date or Datetime objects
                    if hasattr(raw_date, "date"):
                        parsed_date = raw_date.date()
                    elif isinstance(raw_date, timezone.datetime) or hasattr(
                        raw_date, "strftime"
                    ):
                        parsed_date = raw_date

                    # 2. String Dates with broad format parsing
                    elif (
                        isinstance(raw_date, str)
                        and raw_date.strip()
                        and raw_date.strip() != "-"
                    ):
                        clean_d = raw_date.strip().replace("/", "-")
                        for fmt in (
                            "%Y-%m-%d",
                            "%d-%m-%Y",
                            "%d-%m-%y",
                            "%d-%b-%Y",
                            "%d-%b-%y",
                            "%d-%B-%Y",
                        ):
                            try:
                                parsed_date = timezone.datetime.strptime(
                                    clean_d, fmt
                                ).date()
                                break
                            except (ValueError, TypeError):
                                continue

                    # 3. Fallback: Statement period start date before defaulting to today
                    if not parsed_date:
                        parsed_date = inbox_item.period_start or now_ts.date()

                    debit_val = (
                        Decimal(str(tx.get("debit")))
                        if tx.get("debit") and tx.get("debit") != "-"
                        else None
                    )
                    credit_val = (
                        Decimal(str(tx.get("credit")))
                        if tx.get("credit") and tx.get("credit") != "-"
                        else None
                    )

                    amt_val = Decimal(str(tx.get("amount", 0.0)))
                    if amt_val == Decimal("0.00") or amt_val is None:
                        if debit_val and debit_val > 0:
                            amt_val = debit_val
                        elif credit_val and credit_val > 0:
                            amt_val = credit_val

                    create_pool.append(
                        StatementStagingLine(
                            account=account,
                            bank=account.bank if hasattr(account, "bank") else None,
                            ingest_registry=registry,
                            raw_statement_date=parsed_date,
                            narration=original_narr,
                            amount=amt_val,
                            running_balance=Decimal(str(tx.get("balance", 0.0))),
                            debit=debit_val,
                            credit=credit_val,
                            row_identifier=row_id,
                            cheque_ref_number=tx.get("cheque_ref_number"),
                            is_enriched_from_live=0,
                            live_upi_rrn=None,
                            live_metadata={},
                        )
                    )

            if create_pool:
                StatementStagingLine.objects.bulk_create(create_pool)

            inbox_item.status = "COMPLETED"
            inbox_item.save(update_fields=["status", "updated_at"])

        return {
            "status": "SUCCESS",
            "registry_id": str(registry.id),
            "inserted_lines": len(create_pool),
            "updated_lines": update_count,
        }


class BatchRevokeService:
    @classmethod
    @transaction.atomic
    def revoke_inbox_registry(cls, registry_id: str) -> Dict[str, Any]:
        """
        One-click atomic rollback:
        Unwinds an entire committed statement batch by StatementIngestRegistry ID,
        safely purging WIP matrix items, subledger mappings, journal entries,
        and resetting the DocumentInboxItem status back to 'INBOX'.
        """
        registry = StatementIngestRegistry.objects.filter(id=registry_id).first()
        if not registry:
            raise ValueError(f"StatementIngestRegistry '{registry_id}' not found.")

        # Dynamically load related models with resilient app fallbacks
        def resolve_model(model_name: str):
            for app_label in ("ledger", "tracker"):
                try:
                    return apps.get_model(app_label, model_name)
                except LookupError:
                    continue
            return None

        JournalEntry = resolve_model("JournalEntry")
        AssetTransactionMapping = resolve_model("AssetTransactionMapping")
        WipEvaluationMatrix = resolve_model("WipEvaluationMatrix")

        # 1. Fetch related staging IDs and row identifiers
        staging_lines = StatementStagingLine.objects.filter(ingest_registry=registry)
        staging_ids = list(staging_lines.values_list("id", flat=True))
        row_ids = [
            str(r).strip()
            for r in staging_lines.values_list("row_identifier", flat=True)
            if r
        ]

        counts = {
            "staging_deleted": len(staging_ids),
            "wip_deleted": 0,
            "journal_entries_deleted": 0,
            "subledger_mappings_deleted": 0,
        }

        # 2. Delete WIP evaluation records (Linked via staging_line_id)
        if staging_ids and WipEvaluationMatrix:
            try:
                deleted = WipEvaluationMatrix.objects.filter(
                    staging_line_id__in=staging_ids
                ).delete()
                counts["wip_deleted"] = deleted[0] if deleted else 0
            except Exception as e:
                logger.warning(f"Error purging WipEvaluationMatrix: {e}")

        # 3. Delete Subledger Mappings (Linked via row_identifier)
        if row_ids and AssetTransactionMapping:
            try:
                deleted = AssetTransactionMapping.objects.filter(
                    row_identifier__in=row_ids
                ).delete()
                counts["subledger_mappings_deleted"] = deleted[0] if deleted else 0
            except Exception as e:
                logger.warning(f"Error purging AssetTransactionMapping: {e}")

        # 4. Delete Journal Entries (Linked via row_identifier)
        if row_ids and JournalEntry:
            try:
                deleted = JournalEntry.objects.filter(
                    row_identifier__in=row_ids
                ).delete()
                counts["journal_entries_deleted"] = deleted[0] if deleted else 0
            except Exception as e:
                logger.warning(f"Error purging JournalEntry: {e}")

        # 5. Delete Statement Staging Lines
        staging_lines.delete()

        # 6. Reset DocumentInboxItem status back to 'INBOX'
        clean_file_basename = os.path.basename(str(registry.file_name or "")).strip()
        inbox_item = DocumentInboxItem.objects.filter(
            filename__iexact=clean_file_basename
        ).first()

        if not inbox_item and registry.file_name:
            inbox_item = DocumentInboxItem.objects.filter(
                filename__icontains=clean_file_basename
            ).first()

        if inbox_item:
            inbox_item.status = "INBOX"
            inbox_item.updated_at = timezone.now()
            inbox_item.save(update_fields=["status", "updated_at"])

        # 7. Delete the registry record itself
        registry.delete()

        logger.info(f"✅ Revoked batch {registry_id} ({clean_file_basename}): {counts}")

        return {
            "status": "SUCCESS",
            "message": f"Successfully revoked registry batch '{registry_id}'",
            "details": counts,
        }


# import os
# import re
# import logging
# from decimal import Decimal
# from typing import Dict, Any, List, Optional, Tuple
# import fitz  # PyMuPDF
# from django.utils import timezone
# from django.db import transaction

# from tracker.models import (
#     Account,
#     Bank,
#     BankCredential,
#     DocumentInboxItem,
#     StatementIngestRegistry,
#     StatementStagingLine,
#     UserStatementTemplate,
# )
# from tracker.models.emailModels import RawEmailPayload
# from tracker.parsers.parsers_v1.orchestrator import process_bank_statement
# from tracker.parsers.parsers_v1.utils import validator
# from tracker.parsers.utils import generate_live_collision_hash  # SSOT Hash

# logger = logging.getLogger(__name__)


# class DocumentKeychainResolver:
#     """
#     Decodes statement metadata dynamically by cross-referencing
#     decrypted document text against registered Database Entities.
#     Zero hardcoded bank logic.
#     """

#     @classmethod
#     def get_aggregated_passwords(
#         cls, preferred_account: Optional[Account] = None
#     ) -> List[str]:
#         keychain: List[str] = []

#         if preferred_account:
#             pref_cred = BankCredential.objects.filter(account=preferred_account).first()
#             if pref_cred and isinstance(pref_cred.password_vault, list):
#                 keychain.extend(
#                     [str(p).strip() for p in pref_cred.password_vault if str(p).strip()]
#                 )

#         all_creds = BankCredential.objects.exclude(account=preferred_account)
#         for cred in all_creds:
#             if isinstance(cred.password_vault, list):
#                 for pwd in cred.password_vault:
#                     clean_pwd = str(pwd).strip()
#                     if clean_pwd and clean_pwd not in keychain:
#                         keychain.append(clean_pwd)

#         return keychain

#     @classmethod
#     def unlock_document(cls, file_path: str, initial_hint: str = "") -> Tuple[str, str]:
#         if not os.path.exists(file_path):
#             raise FileNotFoundError(f"PDF statement not found at: {file_path}")

#         doc = fitz.open(file_path)
#         working_password = ""

#         if doc.is_encrypted:
#             preferred_acc = (
#                 Account.objects.filter(account_number__endswith=initial_hint).first()
#                 if initial_hint
#                 else None
#             )
#             keychain = cls.get_aggregated_passwords(preferred_acc)

#             success = False
#             for pwd in keychain:
#                 if doc.authenticate(pwd) > 0:
#                     working_password = pwd
#                     success = True
#                     break

#             if not success:
#                 doc.close()
#                 raise PermissionError(
#                     "Decryption failed. No matching password found in platform keychain."
#                 )

#         page_0 = doc[0]
#         header_text = page_0.get_text("text")
#         doc.close()

#         return working_password, header_text

#     @classmethod
#     def identify_account_from_text(
#         cls, header_text: str, fallback_hint: str = "", fallback_bank_name: str = ""
#     ) -> Optional[Account]:
#         upper_text = header_text.upper()
#         clean_doc_stream = re.sub(r"[\s\-\:\.\/]", "", upper_text)

#         all_accounts = list(Account.objects.select_related("bank").all())

#         # PASS 1: Exact continuous Account Number match
#         for acc in all_accounts:
#             if acc.account_number:
#                 clean_acc_num = re.sub(
#                     r"[\s\-\:\.]", "", str(acc.account_number)
#                 ).upper()
#                 if len(clean_acc_num) >= 6 and clean_acc_num in clean_doc_stream:
#                     return acc

#         # PASS 2: Institutional Bank Marker + Account Suffix Match
#         for acc in all_accounts:
#             if not acc.account_number:
#                 continue

#             clean_acc_str = str(acc.account_number).strip()
#             acc_suffix = (
#                 clean_acc_str[-4:] if len(clean_acc_str) >= 4 else clean_acc_str
#             )
#             bank_obj = getattr(acc, "bank", None)

#             markers = []
#             if bank_obj:
#                 if bank_obj.display_name:
#                     markers.append(bank_obj.display_name.upper())
#                 if bank_obj.code:
#                     markers.append(bank_obj.code.upper())
#                 if hasattr(bank_obj, "ifsc_prefix") and bank_obj.ifsc_prefix:
#                     markers.append(bank_obj.ifsc_prefix.upper())

#             bank_matched = any(m in upper_text for m in markers if m)
#             suffix_matched = (acc_suffix in upper_text) or (
#                 acc_suffix == str(fallback_hint).strip()
#             )

#             if bank_matched and suffix_matched:
#                 return acc

#         # PASS 3: Fallback Hint Match
#         if fallback_hint:
#             clean_hint = str(fallback_hint).strip()
#             query = Account.objects.filter(account_number__endswith=clean_hint)
#             if fallback_bank_name:
#                 query = query.filter(
#                     bank__display_name__icontains=fallback_bank_name
#                 ) | query.filter(bank__code__icontains=fallback_bank_name)
#             acc = query.first()
#             if acc:
#                 return acc

#         return None


# class InboxStatementService:
#     @classmethod
#     def preview_inbox_item(cls, inbox_item_id: str) -> Dict[str, Any]:
#         inbox_item = DocumentInboxItem.objects.filter(id=inbox_item_id).first()
#         if not inbox_item:
#             raise ValueError(f"DocumentInboxItem {inbox_item_id} not found.")

#         file_path = inbox_item.file_path
#         if not os.path.exists(file_path):
#             raise FileNotFoundError(f"Attachment file not found at: {file_path}")

#         working_password, header_text = DocumentKeychainResolver.unlock_document(
#             file_path=file_path,
#             initial_hint=inbox_item.account_hint or "",
#         )

#         account = DocumentKeychainResolver.identify_account_from_text(
#             header_text=header_text,
#             fallback_hint=inbox_item.account_hint or "",
#             fallback_bank_name=inbox_item.bank_name or "",
#         )

#         if not account:
#             extracted_snippet = (
#                 " ".join(header_text.split()[:40]) if header_text else ""
#             )
#             return {
#                 "status": "ACCOUNT_REGISTRATION_REQUIRED",
#                 "inbox_item_id": str(inbox_item.id),
#                 "filename": inbox_item.filename or os.path.basename(file_path),
#                 "detected_bank_hint": inbox_item.bank_name or "Unknown Institution",
#                 "detected_account_hint": inbox_item.account_hint or "N/A",
#                 "message": (
#                     f"This document could not be mapped to any registered account. "
#                     f"Detected hint: '{inbox_item.account_hint}' ({inbox_item.bank_name}). "
#                     f"Please register or link this account in settings to proceed."
#                 ),
#                 "header_snippet": extracted_snippet,
#                 "preview_dataset": [],
#                 "count": 0,
#             }

#         clean_acc = str(account.account_number).strip()
#         actual_suffix = clean_acc[-4:] if len(clean_acc) >= 4 else clean_acc
#         if inbox_item.account_hint != actual_suffix:
#             inbox_item.account_hint = actual_suffix
#             inbox_item.save(update_fields=["account_hint"])

#         if working_password:
#             cred, _ = BankCredential.objects.get_or_create(
#                 account=account, defaults={"password_vault": []}
#             )
#             vault = cred.password_vault if isinstance(cred.password_vault, list) else []
#             if working_password in vault:
#                 vault.remove(working_password)
#             vault.insert(0, working_password)
#             cred.password_vault = vault[:5]
#             cred.save(update_fields=["password_vault"])

#         template_obj = (
#             UserStatementTemplate.objects.filter(account=account)
#             .exclude(parser_strategy_code="UNIVERSAL_CSV_FLOW")
#             .first()
#         ) or UserStatementTemplate.objects.filter(account=account).first()

#         db_records = list(
#             StatementStagingLine.objects.filter(account_id=account.id).values(
#                 "row_identifier",
#                 "narration",
#                 "cheque_ref_number",
#                 "raw_statement_date",
#                 "amount",
#                 "running_balance",
#                 "credit",
#                 "debit",
#             )
#         )
#         existing_hashes = {
#             r["row_identifier"] for r in db_records if r["row_identifier"]
#         }
#         database_lookup_dict = {
#             r["row_identifier"]: r for r in db_records if r["row_identifier"]
#         }

#         with open(file_path, "rb") as file_handle:
#             processed_bundle, op_bal, system_noise = process_bank_statement(
#                 uploaded_file=file_handle,
#                 template_obj=template_obj,
#                 account_id=str(account.id),
#                 existing_database_hashes=existing_hashes,
#                 password_vault=[working_password] if working_password else [],
#             )

#         intermediate_txns = (
#             processed_bundle.get("transactions_list", [])
#             if isinstance(processed_bundle, dict)
#             else processed_bundle
#         )

#         export_filename = inbox_item.filename or os.path.basename(file_path)

#         payload = validator.run_final_math(
#             intermediate_txns,
#             op_bal,
#             template_obj=template_obj,
#             account_id=str(account.id),
#             export_filename=export_filename,
#         )

#         preview_dataset = payload.get("preview_dataset", [])

#         _, _ = validator.process_and_filter_rows(
#             preview_dataset=preview_dataset,
#             account=account,
#             bank=account.bank if hasattr(account, "bank") else None,
#             existing_hashes=existing_hashes,
#             database_lookup_dict=database_lookup_dict,
#         )

#         # ─── 7. ⚡ SSOT HASH CROSS-REFERENCE (raw_email_payloads) ───
#         try:
#             bank_canonical_name = (
#                 account.bank.display_name or account.bank.name
#                 if account.bank
#                 else "SOUTH INDIAN BANK"
#             )

#             pending_live = list(
#                 RawEmailPayload.objects.filter(status__in=["STAGED", "PENDING"]).values(
#                     "id",
#                     "source",
#                     "headers_json",
#                     "amount",
#                     "created_at",
#                     "email_date",
#                     "decrypted_body",
#                     "account_last4",
#                     "bank_name",
#                     "upi_ref",
#                     "merchant",
#                 )
#             )

#             live_rrn_map: Dict[str, Any] = {}
#             # Hash map stores a list to safely handle duplicate intraday transactions without collisions
#             live_hash_queue_map: Dict[str, List[Any]] = {}

#             for item in pending_live:
#                 headers = item.get("headers_json") or {}
#                 parsed = headers.get("parsed_summary") or {}

#                 # 1. RRN key
#                 rrn = (
#                     item.get("upi_ref")
#                     or headers.get("merge_details", {}).get("matched_rrn")
#                     or parsed.get("upi_ref")
#                 )
#                 if rrn:
#                     live_rrn_map[str(rrn).strip()] = item

#                 # 2. SSOT Collision Hash Key
#                 item_date = item.get("email_date") or item.get("created_at")
#                 item_amt = (
#                     item.get("amount")
#                     if item.get("amount") is not None
#                     else parsed.get("amount")
#                 )
#                 item_acc = (
#                     item.get("account_last4") or parsed.get("account") or actual_suffix
#                 )

#                 hash_key = generate_live_collision_hash(
#                     date_val=item_date,
#                     bank_val=bank_canonical_name,
#                     account_last4=item_acc,
#                     amount_val=item_amt,
#                 )
#                 if hash_key not in live_hash_queue_map:
#                     live_hash_queue_map[hash_key] = []
#                 live_hash_queue_map[hash_key].append(item)

#             # Correlate statement preview rows against live queue
#             for row in preview_dataset:
#                 chq = str(row.get("cheque_ref_number") or "").strip()
#                 narr = str(
#                     row.get("narration_description") or row.get("narration") or ""
#                 ).strip()

#                 matched_live = None
#                 matched_hash_val = None

#                 # Step A: Tier 1 RRN lookup
#                 if chq and chq in live_rrn_map:
#                     matched_live = live_rrn_map[chq]
#                 else:
#                     for rrn, live_item in live_rrn_map.items():
#                         if len(rrn) >= 6 and (rrn in chq or rrn in narr):
#                             matched_live = live_item
#                             break

#                 # Step B: Tier 2 SSOT Hash Collision lookup (if RRN wasn't found)
#                 row_date = str(
#                     row.get("raw_statement_date") or row.get("post_date") or ""
#                 )[:10]
#                 row_amount = row.get("amount") or row.get("debit") or row.get("credit")

#                 row_live_hash = generate_live_collision_hash(
#                     date_val=row_date,
#                     bank_val=bank_canonical_name,
#                     account_last4=actual_suffix,
#                     amount_val=row_amount,
#                 )

#                 if not matched_live and row_live_hash in live_hash_queue_map:
#                     queue = live_hash_queue_map[row_live_hash]
#                     if queue:
#                         matched_live = queue.pop(
#                             0
#                         )  # FIFO match for identical amounts on same date

#                 matched_hash_val = row_live_hash

#                 # Step C: Enrich statement preview row
#                 if matched_live:
#                     headers = matched_live.get("headers_json") or {}
#                     parsed = headers.get("parsed_summary") or {}
#                     rich_narr = (
#                         headers.get("merge_details", {}).get("resolved_narration")
#                         or parsed.get("full_narration")
#                         or matched_live.get("merchant")
#                     )

#                     if rich_narr:
#                         row["narration_description"] = rich_narr
#                         row["narration"] = rich_narr

#                     matched_rrn = (
#                         matched_live.get("upi_ref")
#                         or headers.get("merge_details", {}).get("matched_rrn")
#                         or parsed.get("upi_ref")
#                     )
#                     row["live_upi_rrn"] = matched_rrn
#                     row["is_enriched_from_live"] = True
#                     row["raw_payload_id"] = str(matched_live["id"])
#                     row["live_hash_val"] = matched_hash_val  # Pass SSOT hash forward
#                     row["pipeline_action"] = "UPDATE_ENRICHMENT"
#                     row["status"] = "UPDATE_ENRICHMENT"

#         except Exception as live_err:
#             logger.warning(
#                 f"Live notification cross-reference bypassed: {str(live_err)}"
#             )

#         active_strategy = getattr(
#             template_obj, "parser_strategy_code", "GRID_COLUMN_FLOW"
#         ).upper()

#         return {
#             "status": "SUCCESS",
#             "inbox_item_id": str(inbox_item.id),
#             "account_id": str(account.id),
#             "account_name": account.name,
#             "applied_template": (
#                 template_obj.template_name if template_obj else "UNIVERSAL"
#             ),
#             "strategy_processed": active_strategy,
#             "preview_dataset": preview_dataset,
#             "opening_balance": payload.get("opening_balance", op_bal),
#             "closing_balance": payload.get("closing_balance", 0.0),
#             "total_debit": payload.get("total_debit", 0.0),
#             "total_credit": payload.get("total_credit", 0.0),
#             "count": len(preview_dataset),
#         }

#     @classmethod
#     def commit_inbox_item(
#         cls,
#         inbox_item_id: str,
#         preview_dataset: List[Dict[str, Any]],
#         meta_summary: Dict[str, Any],
#     ) -> Dict[str, Any]:
#         inbox_item = DocumentInboxItem.objects.filter(id=inbox_item_id).first()
#         if not inbox_item:
#             raise ValueError(f"DocumentInboxItem {inbox_item_id} not found.")

#         account = DocumentKeychainResolver.identify_account_from_text(
#             header_text="",
#             fallback_hint=inbox_item.account_hint or "",
#             fallback_bank_name=inbox_item.bank_name or "",
#         )
#         if not account:
#             raise ValueError("Target account could not be resolved for commit.")

#         create_pool: List[StatementStagingLine] = []
#         update_count = 0
#         retired_raw_payload_ids: List[str] = []

#         with transaction.atomic():
#             registry = StatementIngestRegistry.objects.create(
#                 account=account,
#                 file_name=inbox_item.filename or os.path.basename(inbox_item.file_path),
#                 file_type="PDF",
#                 vault_decrypted=True,
#                 report_from_date=inbox_item.period_start or timezone.now().date(),
#                 report_to_date=inbox_item.period_end or timezone.now().date(),
#                 opening_balance=Decimal(str(meta_summary.get("openingBalance", 0.0))),
#                 closing_balance=Decimal(str(meta_summary.get("closingBalance", 0.0))),
#                 total_debit_amount=Decimal(str(meta_summary.get("totalDebit", 0.0))),
#                 total_credit_amount=Decimal(str(meta_summary.get("totalCredit", 0.0))),
#                 total_row_count=len(preview_dataset),
#                 source_channel="DOCUMENT_INBOX",
#             )

#             for tx in preview_dataset:
#                 action = tx.get("pipeline_action", "INSERT")
#                 row_id = tx.get("row_identifier")
#                 raw_payload_id = tx.get("raw_payload_id")
#                 is_live_enriched = bool(tx.get("is_enriched_from_live", False))
#                 live_rrn = tx.get("live_upi_rrn")
#                 hash_val = tx.get("live_hash_val")

#                 if raw_payload_id:
#                     retired_raw_payload_ids.append(raw_payload_id)

#                 live_meta = {}
#                 if is_live_enriched:
#                     live_meta = {
#                         "hash_val": hash_val,
#                         "raw_payload_id": raw_payload_id,
#                         "enriched_at": timezone.now().isoformat(),
#                     }

#                 if action == "UPDATE_ENRICHMENT" and row_id:
#                     update_fields: Dict[str, Any] = {
#                         "narration": tx.get("narration_description")
#                         or tx.get("narration"),
#                         "cheque_ref_number": tx.get("cheque_ref_number"),
#                         "uploaded_at": timezone.now(),
#                     }
#                     if is_live_enriched:
#                         update_fields["is_enriched_from_live"] = 1
#                         update_fields["routing_status"] = "UPDATE_ENRICHMENT"
#                         if live_rrn:
#                             update_fields["live_upi_rrn"] = live_rrn
#                         if live_meta:
#                             update_fields["live_metadata"] = live_meta

#                     StatementStagingLine.objects.filter(
#                         account_id=account.id, row_identifier=row_id
#                     ).update(**update_fields)
#                     update_count += 1

#                 elif action == "INSERT":
#                     raw_date = tx.get("raw_statement_date") or tx.get("post_date")
#                     parsed_date = (
#                         raw_date
#                         if isinstance(raw_date, timezone.datetime)
#                         or hasattr(raw_date, "strftime")
#                         else timezone.now().date()
#                     )

#                     create_pool.append(
#                         StatementStagingLine(
#                             account=account,
#                             bank=account.bank if hasattr(account, "bank") else None,
#                             ingest_registry=registry,
#                             routing_status=(
#                                 "UPDATE_ENRICHMENT" if is_live_enriched else "PENDING"
#                             ),
#                             raw_statement_date=parsed_date,
#                             narration=tx.get("narration_description")
#                             or tx.get("narration", ""),
#                             amount=Decimal(str(tx.get("amount", 0.0))),
#                             running_balance=Decimal(str(tx.get("balance", 0.0))),
#                             debit=(
#                                 Decimal(str(tx.get("debit")))
#                                 if tx.get("debit") and tx.get("debit") != "-"
#                                 else None
#                             ),
#                             credit=(
#                                 Decimal(str(tx.get("credit")))
#                                 if tx.get("credit") and tx.get("credit") != "-"
#                                 else None
#                             ),
#                             row_identifier=row_id,
#                             cheque_ref_number=tx.get("cheque_ref_number"),
#                             is_enriched_from_live=1 if is_live_enriched else 0,
#                             live_upi_rrn=live_rrn,
#                             live_metadata=live_meta,
#                         )
#                     )

#             if create_pool:
#                 StatementStagingLine.objects.bulk_create(create_pool)

#             if retired_raw_payload_ids:
#                 RawEmailPayload.objects.filter(id__in=retired_raw_payload_ids).update(
#                     status="COMPLETED",
#                     processed_at=timezone.now(),
#                 )
#                 logger.info(
#                     f"✅ Retired {len(retired_raw_payload_ids)} live payloads to status=COMPLETED."
#                 )

#             inbox_item.status = "COMPLETED"
#             inbox_item.save(update_fields=["status", "updated_at"])

#         return {
#             "status": "SUCCESS",
#             "registry_id": str(registry.id),
#             "inserted_lines": len(create_pool),
#             "enriched_lines": update_count,
#             "retired_live_payloads": len(retired_raw_payload_ids),
#         }
