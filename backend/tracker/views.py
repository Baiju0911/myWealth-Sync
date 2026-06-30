##########################

# S:\_BaijSoft\myWealth-Sync\backend\tracker\views.py
import csv
import datetime
import decimal
import json
import logging
import pprint

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from pypdf import PdfReader

# 🔌 Django REST Framework Tools
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

# from .parsers.utils import MatchWrapper, generate_row_fingerprint

from rest_framework.views import APIView

from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status

# from .parsers.raw_extractor import extract_raw_preview
import os
from django.core.files.storage import default_storage
from .parsers.parsers_v1.utils.normalizer import format_to_two_digits


from .models import (
    Account,
    Bank,
    BankCredential,
    BankLayoutSchema,
    JournalEntry,
    Permission,
    Role,
    TransactionHeader,
    StatementStagingLine,
    StatementIngestRegistry,
    UserStatementTemplate,
)
from .serializers import AccountSerializer, BankCredentialSerializer
from .parsers.SBI_format import process_SBI_pdf_statement
from .parsers.SIB_format import process_SIB_pdf_statement
from .parsers.FED_format import process_FED_pdf_statement
from .parsers.unified_csv_format import process_unified_csv_statement
from .parsers.raw_extractor import extract_spatial_preview, match_statement_template
from .parsers.universal_format import (
    UniversalStatementParser,
)
from .parsers.utils import generate_row_fingerprint


from .parsers.parsers_v1.utils import validator
from .parsers.parsers_v1.utils.normalizer import parse_meta_decimal
from .parsers.parsers_v1.utils.normalizer import sanitize_transaction_dates_via_template
from .parsers.parsers_v1.utils.validator import process_and_filter_rows
from .parsers.parsers_v1.orchestrator import process_bank_statement

# If you decide to pull in the resolver/profiler/registry/validator modules later:
# from .parsers.parsers_v1.profiler import create_profile
# from .parsers.parsers_v1.resolver import resolve_strategy
# from .parsers.parsers_v1.strategies import registry
# from .parsers.parsers_v1.utils import validator

logger = logging.getLogger(__name__)

User = get_user_model()

# ==========================================
# 1. SYSTEM STRUCTURAL METADATA ENDPOINTS
# ==========================================


class SystemConfigView(APIView):
    """
    Exposes global system constants to the frontend app.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        account_types = [
            {"key": item[0], "label": item[1]} for item in settings.ACCOUNT_TYPES
        ]
        transaction_statuses = [
            {"key": item[0], "label": item[1]}
            for item in settings.TRANSACTION_STATUS_CHOICES
        ]
        return Response(
            {
                "account_types": account_types,
                "transaction_statuses": transaction_statuses,
                "currency": "INR",
                "precision_decimal_places": 2,
            }
        )


# ==========================================
# 2. ACCOUNT CONTROL LAYER (CRUD & SUFFIX INTEGRATION)
# ==========================================


class AccountListCreateView(APIView):
    """
    Adapter Endpoint to manage structural multi-account assets and configurations.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        """
        📥 GET: Fetch full array payloads for active financial nodes
        """
        accounts = Account.objects.all()
        # Enforce detailed representation straight from your pre-configured serializer block
        serializer = AccountSerializer(accounts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        🚀 POST: Provision a new Master Ledger Account Node
        """
        bank_id = request.data.get("bank_id")
        name = request.data.get("name")
        account_type = request.data.get("account_type", "ASSET")
        ifsc_code = request.data.get("ifsc_code", "").strip().upper()
        branch_name = request.data.get("branch_name", "")
        address = request.data.get("address", "")

        # 🔗 COMPATIBILITY LINK: Extracts 'account_number' but checks old 'account_suffix' as a fallback
        account_number = request.data.get("account_number") or request.data.get(
            "account_suffix", ""
        )

        # 🧩 SAFE CONTEXT GENERATION: Execute a get_or_create query directly over matching attributes
        account, created = Account.objects.get_or_create(
            bank_id=bank_id,
            name=name,
            defaults={
                "account_type": account_type,
                "account_number": account_number,
                "ifsc_code": ifsc_code,
                "branch_name": branch_name,
                "address": address,
            },
        )

        serializer = AccountSerializer(account)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AccountDetailView(APIView):
    """
    ✏️ ADAPTER CORE: Manages isolated updates to individual records, squashing 405 errors.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, pk=None):
        """
        💾 PUT: Modify and lock detailed metadata configuration rows (IFSC, Branch, Suffix)
        """
        account = get_object_or_404(Account, id=pk)

        # Hydrate text parameters from active inputs or retain fallback values
        account.name = request.data.get("name", account.name)
        account.account_type = request.data.get("account_type", account.account_type)
        account.ifsc_code = (
            request.data.get("ifsc_code", account.ifsc_code).strip().upper()
        )
        account.branch_name = request.data.get("branch_name", account.branch_name)
        account.address = request.data.get("address", account.address)

        # Check both modern and legacy variables for the 4-digit token
        account.account_number = (
            request.data.get("account_number")
            or request.data.get("account_suffix")
            or account.account_number
        )

        account.save()

        serializer = AccountSerializer(account)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        """
        🗑️ DELETE: Purge account records cleanly from the system registry
        """
        account = get_object_or_404(Account, id=pk)
        account.delete()
        return Response(
            {"message": "Account node removed cleanly"}, status=status.HTTP_200_OK
        )


# ==========================================
# 3. DOUBLE-ENTRY TRANSACTION QUEUE HANDLING
# ==========================================


class TransactionListCreateView(APIView):
    """
    Fallback historical review view list.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        mock_user = User.objects.first() or User.objects.create_user(
            email="testowner@wealth.com", password="TestPassword123"
        )
        headers = TransactionHeader.objects.filter(user=mock_user).prefetch_related(
            "entries__account"
        )

        serialized_list = []
        for h in headers:
            lines = [
                {"account_name": e.account.name, "amount": float(e.amount)}
                for e in h.entries.all()
            ]
            serialized_list.append(
                {
                    "id": str(h.id),
                    "date": h.date,
                    "description": h.narration,
                    "source": h.source,
                    "upi_rrn": h.upi_rrn,
                    "lines": lines,
                }
            )
        return Response(serialized_list, status=status.HTTP_200_OK)


class BulkTransactionSyncView(APIView):
    """
    Smart mobile payload translator adapter to double-entry rows.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        owner_role, _ = Role.objects.get_or_create(name="PLATFORM_OWNER")
        mock_user = User.objects.first()
        if not mock_user:
            mock_user = User.objects.create_user(
                email="testowner@wealth.com",
                password="TestPassword123",
                role=owner_role,
            )
        elif not mock_user.role:
            mock_user.role = owner_role
            mock_user.save()

        perm, _ = Permission.objects.get_or_create(codename="CAN_UPLOAD_STATEMENT")
        owner_role.permissions.add(perm)

        payload = request.data
        transactions_to_process = payload if isinstance(payload, list) else [payload]

        try:
            with transaction.atomic():
                for item in transactions_to_process:
                    description = item.get("description", "QR Scan Transfer Inflow")
                    timestamp_str = item.get(
                        "timestamp", datetime.datetime.now().isoformat()
                    )
                    parsed_date = datetime.datetime.fromisoformat(
                        timestamp_str.replace("Z", "")
                    ).date()

                    raw_narration = ""
                    header = TransactionHeader.objects.create(
                        user=mock_user,
                        date=parsed_date,
                        narration=raw_narration,
                        source="QR_SCAN_MOBILE",
                        upi_rrn=item.get("upi_rrn", None),
                        merchant_vpa=item.get("merchant_vpa", None),
                        scanned_by=item.get("scanned_by", "Handheld App Mobile Client"),
                    )

                    incoming_lines = item.get("lines", [])
                    if incoming_lines:
                        for line in incoming_lines:
                            account_name = line.get(
                                "account_name", "Expenses:Unclassified"
                            )
                            debit = decimal.Decimal(str(line.get("debit_amount", 0.00)))
                            credit = decimal.Decimal(
                                str(line.get("credit_amount", 0.00))
                            )
                            net_amount = debit - credit

                            # 🎯 GLOBAL STRUCTURAL REFIX: Removed 'user=mock_user' field filter parameter
                            account, _ = Account.objects.get_or_create(
                                name=account_name,
                                defaults={
                                    "account_type": (
                                        "EXPENSE"
                                        if "Expense" in account_name
                                        else "ASSET"
                                    )
                                },
                            )

                            JournalEntry.objects.create(
                                transaction=header, account=account, amount=net_amount
                            )
                    else:
                        fallback_amt = decimal.Decimal(str(item.get("amount", 0.00)))
                        if fallback_amt > 0:
                            # 🎯 GLOBAL STRUCTURAL REFIX: Removed 'user=mock_user' field filter parameter
                            exp_acc, _ = Account.objects.get_or_create(
                                name="Expenses:General",
                                defaults={"account_type": "EXPENSE"},
                            )
                            asset_acc, _ = Account.objects.get_or_create(
                                name="Assets:Liquid Wallet",
                                defaults={"account_type": "ASSET"},
                            )

                            JournalEntry.objects.create(
                                transaction=header, account=exp_acc, amount=fallback_amt
                            )
                            JournalEntry.objects.create(
                                transaction=header,
                                account=asset_acc,
                                amount=-fallback_amt,
                            )

            return Response(
                {
                    "status": "SUCCESS",
                    "message": "Successfully translated and synchronized offline queue items to MySQL!",
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {
                    "status": "ERROR",
                    "message": f"Database processing exception: {str(e)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ==========================================
# 4. CREDENTIAL VAULT VIEWS & PARSING PIPELINE
# ==========================================


class BankCredentialViewSet(viewsets.ModelViewSet):
    serializer_class = BankCredentialSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return BankCredential.objects.filter(user=self.request.user)
        test_user = User.objects.filter(email="testowner@wealth.com").first()
        return (
            BankCredential.objects.filter(user=test_user)
            if test_user
            else BankCredential.objects.none()
        )

    def _get_target_user(self):
        """Helper to safely determine user ownership across auth and local testing contexts"""
        if self.request.user.is_authenticated:
            return self.request.user
        return User.objects.filter(email="testowner@wealth.com").first()

    def create(self, request, *args, **kwargs):
        # 📥 Copy the inbound request dictionary data matrix defensively
        payload_data = request.data.copy()

        # 🛡️ ALIGN DATA PROPERTY KEYS FOR THE SERIALIZER
        if "account_id" in payload_data and "account" not in payload_data:
            payload_data["account"] = payload_data["account_id"]

        # 🎯 THE JSON ARRAY FIX: Reconstruct raw text into a list block array structure
        raw_pass = payload_data.get("statement_password") or payload_data.get(
            "password_vault"
        )

        if raw_pass:
            if isinstance(raw_pass, str) and raw_pass.strip():
                payload_data["password_vault"] = [raw_pass.strip()]
            elif isinstance(raw_pass, list):
                payload_data["password_vault"] = raw_pass

        # print(f"📥 [NORMALIZED VAULT INPUT PAYLOAD]: {payload_data}")  # 🔍 DEBUG ENGINE

        serializer = self.get_serializer(data=payload_data)
        serializer.is_valid(raise_exception=True)

        target_account = serializer.validated_data.get("account")
        incoming_passwords = serializer.validated_data.get("password_vault", [])

        print(
            f"📦 [PARSED VALIDATED DATA ARRAY]: Account: {target_account.id if target_account else 'None'}, Vault Array: {incoming_passwords}"
        )

        target_user = self._get_target_user()
        existing_credential = BankCredential.objects.filter(
            account=target_account
        ).first()

        # 🔄 BRANCH A: THE EDIT ROUTE (Existing Profile Found)
        if existing_credential:
            print(
                f"🔄 [VAULT MATCH FOUND] Row ID: {existing_credential.id}. Executing merge loop..."
            )
            current_vault = existing_credential.password_vault
            if not isinstance(current_vault, list):
                current_vault = []

            for raw_pwd in reversed(incoming_passwords):
                pwd_string = str(raw_pwd).strip()
                if not pwd_string or pwd_string in current_vault:
                    if pwd_string in current_vault:
                        current_vault.remove(pwd_string)
                current_vault.insert(0, pwd_string)

            existing_credential.password_vault = current_vault[:5]
            if target_user:
                existing_credential.user = target_user

            existing_credential.save()

            # Use serializer to return clean output format
            return Response(
                self.get_serializer(existing_credential).data, status=status.HTTP_200_OK
            )

        # 🚀 BRANCH B: THE NEW ROUTE FIXED!
        # Instead of calling super().create(), we save the validated serializer data explicitly
        # and pass the password_vault list directly into the database commit layer.
        serializer.save(user=target_user, password_vault=incoming_passwords)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        """
        🛡️ THE INTEGRITY SHIELD:
        Forces both user assignment AND the normalized password vault array
        directly into the database insert statement, preventing serializer drops!
        """
        target_user = self._get_target_user()

        # 🎯 SNATCH the validated vault array directly from the serializer context
        validated_vault = serializer.validated_data.get("password_vault", [])

        # If the serializer stripped it out, fallback to pulling it right from our request data modification
        if not validated_vault:
            raw_val = serializer.initial_data.get("password_vault")
            if isinstance(raw_val, list):
                validated_vault = raw_val

        # Force save both variables straight to the database layer
        serializer.save(user=target_user, password_vault=validated_vault)


# ──────────────────────────────────────────────────────────────────────────
# 🛡️ THE URL DISPATCHER ANCHOR: RESTORES THE COMMIT DISCOVERABILITY WORKSPACE
# ──────────────────────────────────────────────────────────────────────────


class StatementStagingCommitView1(APIView):
    """
    🔒 CORE TRANSACTION COMMIT ENGINE (PRODUCTION RECTIFIED):
    Maps, validates, and atomically commits both registry headers and transactional children blocks.
    Defensively handles incoming date parameters across string, integer, and object datatypes safely.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        preview_dataset = request.data.get("preview_dataset", [])
        meta_summary = request.data.get("meta_summary", {})

        fallback_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = (
            request.data.get("file_name") or f"STATEMENT_UPLOAD_{fallback_time}.PDF"
        )

        if not account_id or not preview_dataset:
            return Response(
                {
                    "message": "Required parameters missing or empty payload array received."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)

        # 1. Extract financial balances safely
        op_bal = parse_meta_decimal(meta_summary, "openingBalance", "opening_balance")
        cl_bal = parse_meta_decimal(meta_summary, "closingBalance", "closing_balance")
        tot_dr = parse_meta_decimal(meta_summary, "totalDebit", "total_debit")
        tot_cr = parse_meta_decimal(meta_summary, "totalCredit", "total_credit")

        # 2. Extract Document Range Signatures Safely
        report_from_date = None
        report_to_date = None

        if preview_dataset:
            try:
                first_date = preview_dataset[0].get("post_date") or preview_dataset[
                    0
                ].get("date")
                if first_date:
                    if isinstance(first_date, (datetime.date, datetime.datetime)):
                        report_from_date = (
                            first_date
                            if isinstance(first_date, datetime.date)
                            else first_date.date()
                        )
                    else:
                        clean_first_str = str(first_date).split("T")[0].strip()
                        report_from_date = datetime.datetime.strptime(
                            clean_first_str, "%d-%m-%Y"
                        ).date()

                last_date = preview_dataset[-1].get("post_date") or preview_dataset[
                    -1
                ].get("date")
                if last_date:
                    if isinstance(last_date, (datetime.date, datetime.datetime)):
                        report_to_date = (
                            last_date
                            if isinstance(last_date, datetime.date)
                            else last_date.date()
                        )
                    else:
                        clean_last_str = str(last_date).split("T")[0].strip()
                        report_to_date = datetime.datetime.strptime(
                            clean_last_str, "%d-%m-%Y"
                        ).date()
            except Exception as date_range_err:
                print(f"⚠️ Metadata range parsing fell back: {str(date_range_err)}")
                report_from_date = datetime.date.today()
                report_to_date = datetime.date.today()

        # Dynamic extension tracking extraction
        raw_file_type = meta_summary.get("fileType") or meta_summary.get("file_type")
        if not raw_file_type or str(raw_file_type).strip().upper() in [
            "UNKNOWN",
            "NONE",
            "",
        ]:
            _, file_extension = os.path.splitext(str(file_name).lower())
            if file_extension in [".xls", ".xlsx"]:
                clean_file_type = "EXCEL"
            elif file_extension == ".csv":
                clean_file_type = "CSV"
            else:
                clean_file_type = "PDF"
        else:
            clean_file_type = str(raw_file_type).strip().upper()[:10]

        # ─── 🏛️ STEP 3: CONSTRUCT LIVE DATABASE METADATA DICTIONARY ───
        db_records = StatementStagingLine.objects.filter(account_id=account.id).values(
            "row_identifier",
            "narration",
            "cheque_ref_number",
            "raw_statement_date",
            "amount",
            "running_balance",
            "credit",
            "debit",
        )

        existing_hashes = set()
        database_lookup_dict = {}
        for r in db_records:
            h_key = r["row_identifier"]
            existing_hashes.add(h_key)
            database_lookup_dict[h_key] = r

        try:
            # Run core deduplication filtering pass using raw stream inputs
            tx_pool, duplicate_skip_count = process_and_filter_rows(
                preview_dataset,
                account,
                account.bank,
                existing_hashes,
                database_lookup_dict,
            )

            with transaction.atomic():
                # ─── TABLE 1 WRITER: Full Registry Header Write ───
                registry_entry = StatementIngestRegistry.objects.create(
                    account=account,
                    file_name=file_name,
                    file_type=clean_file_type,
                    vault_decrypted=meta_summary.get("decrypted")
                    or meta_summary.get("vault_decrypted", False),
                    report_from_date=report_from_date,
                    report_to_date=report_to_date,
                    opening_balance=op_bal,
                    closing_balance=cl_bal,
                    total_debit_amount=tot_dr,
                    total_credit_amount=tot_cr,
                    total_row_count=len(preview_dataset),
                    debit_line_count=meta_summary.get("debitLineCount")
                    or meta_summary.get("debit_line_count", 0),
                    credit_line_count=meta_summary.get("creditLineCount")
                    or meta_summary.get("credit_line_count", 0),
                    skipped_duplicate_count=duplicate_skip_count,
                    source_channel="WEB_DASHBOARD",
                )

                # ─── 🏛️ STEP 5: TWO-WAY SPLIT UPSERT LOGIC CHANNELING ───
                create_pool = []
                update_records_count = 0

                for tx in tx_pool:
                    action_intent = tx.pop("pipeline_action", "INSERT")
                    tx.pop("status", None)
                    tx.pop("id", None)
                    tx.pop(
                        "value_date", None
                    )  # 🎯 Drop the extra field safe shield check

                    # Defensive type shield check
                    raw_date_token = tx.get("raw_statement_date")
                    if isinstance(raw_date_token, (datetime.date, datetime.datetime)):
                        db_date = (
                            raw_date_token
                            if isinstance(raw_date_token, datetime.date)
                            else raw_date_token.date()
                        )
                    elif (
                        isinstance(raw_date_token, str)
                        and len(raw_date_token.strip()) >= 8
                    ):
                        try:
                            clean_tx_str = raw_date_token.split("T")[0].strip()
                            db_date = datetime.datetime.strptime(
                                clean_tx_str, "%d-%m-%Y"
                            ).date()
                        except (ValueError, TypeError):
                            db_date = datetime.date.today()
                    else:
                        db_date = datetime.date.today()

                    if action_intent == "UPDATE_ENRICHMENT":
                        target_uuid = tx.get("row_identifier")
                        StatementStagingLine.objects.filter(
                            account_id=account.id, row_identifier=target_uuid
                        ).update(
                            narration=tx.get("narration"),
                            cheque_ref_number=tx.get("cheque_ref_number"),
                            uploaded_at=datetime.datetime.now(),  # Refreshes the upload timestamp
                        )
                        update_records_count += 1
                    else:
                        create_pool.append(
                            StatementStagingLine(
                                account=account,
                                bank=account.bank,
                                ingest_registry=registry_entry,
                                routing_status="COMMITTED",
                                raw_statement_date=db_date,  # Only map fields aligned to our model definitions
                                narration=tx.get("narration"),
                                amount=tx.get("amount"),
                                running_balance=tx.get("running_balance"),
                                debit=tx.get("debit"),
                                credit=tx.get("credit"),
                                bank_transaction_id=tx.get("bank_transaction_id"),
                                cheque_ref_number=tx.get("cheque_ref_number"),
                                row_identifier=tx.get("row_identifier"),
                            )
                        )

                if create_pool:
                    StatementStagingLine.objects.bulk_create(create_pool)

            return Response(
                {
                    "status": "SUCCESS",
                    "registry_id": str(registry_entry.id),
                    "message": f"Sync run complete. Saved {len(create_pool)} new rows, enriched & updated {update_records_count} transactions, skipped {duplicate_skip_count} unchanged duplicates.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as batch_err:
            print(f"❌ RECONCILIATION DATA COMMIT CRASHED: {str(batch_err)}")
            return Response(
                {"message": f"Ledger write failure: {str(batch_err)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StatementStagingCommitView(APIView):
    """
    🔒 CORE TRANSACTION COMMIT ENGINE (PRODUCTION RECTIFIED):
    Maps, validates, and atomically commits both registry headers and transactional children blocks.
    Defensively handles timezone alignment natively across all query paths.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        preview_dataset = request.data.get("preview_dataset", [])
        meta_summary = request.data.get("meta_summary", {})

        # Use timezone-aware generation for fallback text strings if needed
        fallback_time = timezone.now().strftime("%Y-%m-%d_%H-%M")
        file_name = (
            request.data.get("file_name") or f"STATEMENT_UPLOAD_{fallback_time}.PDF"
        )

        if not account_id or not preview_dataset:
            return Response(
                {
                    "message": "Required parameters missing or empty payload array received."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)

        # 1. Extract financial balances safely
        op_bal = parse_meta_decimal(meta_summary, "openingBalance", "opening_balance")
        cl_bal = parse_meta_decimal(meta_summary, "closingBalance", "closing_balance")
        tot_dr = parse_meta_decimal(meta_summary, "totalDebit", "total_debit")
        tot_cr = parse_meta_decimal(meta_summary, "totalCredit", "total_credit")

        # 2. Extract Document Range Signatures Safely
        report_from_date = None
        report_to_date = None

        if preview_dataset:
            try:
                first_date = preview_dataset[0].get("post_date") or preview_dataset[
                    0
                ].get("date")
                if first_date:
                    if isinstance(first_date, (datetime.date, datetime.datetime)):
                        report_from_date = (
                            first_date
                            if isinstance(first_date, datetime.date)
                            else first_date.date()
                        )
                    else:
                        clean_first_str = str(first_date).split("T")[0].strip()
                        report_from_date = datetime.datetime.strptime(
                            clean_first_str, "%d-%m-%Y"
                        ).date()

                last_date = preview_dataset[-1].get("post_date") or preview_dataset[
                    -1
                ].get("date")
                if last_date:
                    if isinstance(last_date, (datetime.date, datetime.datetime)):
                        report_to_date = (
                            last_date
                            if isinstance(last_date, datetime.date)
                            else last_date.date()
                        )
                    else:
                        clean_last_str = str(last_date).split("T")[0].strip()
                        report_to_date = datetime.datetime.strptime(
                            clean_last_str, "%d-%m-%Y"
                        ).date()
            except Exception as date_range_err:
                print(f"⚠️ Metadata range parsing fell back: {str(date_range_err)}")
                report_from_date = timezone.now().date()
                report_to_date = timezone.now().date()

        raw_file_type = meta_summary.get("fileType") or meta_summary.get("file_type")
        if not raw_file_type or str(raw_file_type).strip().upper() in [
            "UNKNOWN",
            "NONE",
            "",
        ]:
            _, file_extension = os.path.splitext(str(file_name).lower())
            if file_extension in [".xls", ".xlsx"]:
                clean_file_type = "EXCEL"
            elif file_extension == ".csv":
                clean_file_type = "CSV"
            else:
                clean_file_type = "PDF"
        else:
            clean_file_type = str(raw_file_type).strip().upper()[:10]

        # ─── 🏛️ STEP 3: CONSTRUCT LIVE DATABASE METADATA DICTIONARY ───
        db_records = StatementStagingLine.objects.filter(account_id=account.id).values(
            "row_identifier",
            "narration",
            "cheque_ref_number",
            "raw_statement_date",
            "amount",
            "running_balance",
            "credit",
            "debit",
        )

        existing_hashes = set()
        database_lookup_dict = {}
        for r in db_records:
            h_key = r["row_identifier"]
            existing_hashes.add(h_key)
            database_lookup_dict[h_key] = r

        try:
            # Run core deduplication filtering pass using raw stream inputs
            tx_pool, duplicate_skip_count = process_and_filter_rows(
                preview_dataset,
                account,
                account.bank,
                existing_hashes,
                database_lookup_dict,
            )

            with transaction.atomic():
                # ─── TABLE 1 WRITER: Full Registry Header Write ───
                registry_entry = StatementIngestRegistry.objects.create(
                    account=account,
                    file_name=file_name,
                    file_type=clean_file_type,
                    vault_decrypted=meta_summary.get("decrypted")
                    or meta_summary.get("vault_decrypted", False),
                    report_from_date=report_from_date,
                    report_to_date=report_to_date,
                    opening_balance=op_bal,
                    closing_balance=cl_bal,
                    total_debit_amount=tot_dr,
                    total_credit_amount=tot_cr,
                    total_row_count=len(preview_dataset),
                    debit_line_count=meta_summary.get("debitLineCount")
                    or meta_summary.get("debit_line_count", 0),
                    credit_line_count=meta_summary.get("creditLineCount")
                    or meta_summary.get("credit_line_count", 0),
                    skipped_duplicate_count=duplicate_skip_count,
                    source_channel="WEB_DASHBOARD",
                )

                # ─── 🏛️ STEP 5: TWO-WAY SPLIT UPSERT LOGIC CHANNELING ───
                create_pool = []
                update_records_count = 0

                for tx in tx_pool:
                    action_intent = tx.pop("pipeline_action", "INSERT")
                    tx.pop("status", None)
                    tx.pop("id", None)
                    tx.pop("value_date", None)

                    raw_date_token = tx.get("raw_statement_date")
                    if isinstance(raw_date_token, (datetime.date, datetime.datetime)):
                        db_date = (
                            raw_date_token
                            if isinstance(raw_date_token, datetime.date)
                            else raw_date_token.date()
                        )
                    elif (
                        isinstance(raw_date_token, str)
                        and len(raw_date_token.strip()) >= 8
                    ):
                        try:
                            clean_tx_str = raw_date_token.split("T")[0].strip()
                            db_date = datetime.datetime.strptime(
                                clean_tx_str, "%d-%m-%Y"
                            ).date()
                        except (ValueError, TypeError):
                            db_date = timezone.now().date()
                    else:
                        db_date = timezone.now().date()

                    if action_intent == "UPDATE_ENRICHMENT":
                        target_uuid = tx.get("row_identifier")
                        StatementStagingLine.objects.filter(
                            account_id=account.id, row_identifier=target_uuid
                        ).update(
                            narration=tx.get("narration"),
                            cheque_ref_number=tx.get("cheque_ref_number"),
                            uploaded_at=timezone.now(),  # 🎯 FIXED: Timezone-aware timestamp clears runtime warnings!
                        )
                        update_records_count += 1
                    else:
                        create_pool.append(
                            StatementStagingLine(
                                account=account,
                                bank=account.bank,
                                ingest_registry=registry_entry,
                                routing_status="COMMITTED",
                                raw_statement_date=db_date,
                                narration=tx.get("narration"),
                                amount=tx.get("amount"),
                                running_balance=tx.get("running_balance"),
                                debit=tx.get("debit"),
                                credit=tx.get("credit"),
                                bank_transaction_id=tx.get("bank_transaction_id"),
                                cheque_ref_number=tx.get("cheque_ref_number"),
                                row_identifier=tx.get("row_identifier"),
                                # auto_now_add=True handles uploaded_at cleanly here
                            )
                        )

                if create_pool:
                    StatementStagingLine.objects.bulk_create(create_pool)

            return Response(
                {
                    "status": "SUCCESS",
                    "registry_id": str(registry_entry.id),
                    "message": f"Sync run complete. Saved {len(create_pool)} new rows, enriched & updated {update_records_count} transactions, skipped {duplicate_skip_count} unchanged duplicates.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as batch_err:
            print(f"❌ RECONCILIATION DATA COMMIT CRASHED: {str(batch_err)}")
            return Response(
                {"message": f"Ledger write failure: {str(batch_err)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ==========================================
# 5. CORE MASTER INSTITUTION VIEWS
# ==========================================


class BankSerializer(serializers.ModelSerializer):
    account_count = serializers.IntegerField(read_only=True)
    credential_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Bank
        fields = ["id", "code", "display_name", "account_count", "credential_count"]


class BankViewSet(viewsets.ModelViewSet):
    """
    🏦 Master Institutional Core Engine
    """

    serializer_class = BankSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Bank.objects.annotate(
            account_count=Count("accounts", distinct=True),
            credential_count=Count("accounts__credential", distinct=True),
        ).order_by("-id")


class UpdateBankCredentialVaultView(APIView):
    """
    🔐 IDEMPOTENT VAULT KEYCHAIN UPDATER:
    Handles appending new passwords to an existing account's vault.
    If no vault exists yet for the account, it seamlessly instantiates one.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        new_password = request.data.get("new_password", "").strip()

        if not account_id or not new_password:
            return Response(
                {
                    "message": "Required parameters missing: account_id and new_password."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)

        # 🎯 THE FIX: Get existing record or prepare to create a net-new one
        credential, created = BankCredential.objects.get_or_create(
            account=account,
            defaults={
                "user": request.user if request.user.is_authenticated else None,
                "password_vault": [],
            },
        )

        current_vault = (
            credential.password_vault
            if isinstance(credential.password_vault, list)
            else []
        )

        # 🛡️ THE APPENDING SHIELD LOGIC:
        if new_password in current_vault:
            # If the password is already in the list, just float it to the front (Index 0)
            current_vault.remove(new_password)

        # Push the newest password to index 0 so the parser tries it first!
        current_vault.insert(0, new_password)

        # Keep the history manageable (cap at the last 5 historical passwords)
        credential.password_vault = current_vault[:5]
        credential.save()

        return Response(
            {
                "status": "SUCCESS",
                "message": "Password successfully added to the front of the account vault keychain.",
                "vault_depth": len(credential.password_vault),
            },
            status=status.HTTP_200_OK,
        )


########### Template UI


class StatementPreviewAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        account_id = request.data.get("account_id")

        if not uploaded_file or not account_id:
            return Response(
                {"error": "Required fields (file or account_id) missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 🏛️ Pull the exact account and credentials profile from your DB tables
            account = get_object_or_404(Account, id=account_id)
            credential = BankCredential.objects.filter(account=account).first()

            # Extract your database list matrix pool safely
            password_pool = (
                credential.password_vault
                if credential and isinstance(credential.password_vault, list)
                else []
            )

            # 🔥 Pass the memory buffer file stream straight to your utility
            spatial_matrix = extract_spatial_preview(
                uploaded_file, password_pool, max_rows=15
            )

            # 🟢 FIXED: Cleaned up structural logic verification checks safely
            if (
                spatial_matrix
                and isinstance(spatial_matrix, list)
                and len(spatial_matrix) > 0
                and isinstance(spatial_matrix[0], list)
                and len(spatial_matrix[0]) > 0
            ):
                first_token_text = spatial_matrix[0][0].get("text", "")

                if (
                    "❌ DECRYPTION FAILURE:" in first_token_text
                    or "🔒 LOCKED:" in first_token_text
                ):
                    return Response(
                        {"error": first_token_text},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )

            return Response(
                {
                    "status": "REQUIRES_MAPPING",
                    "file_name": uploaded_file.name,
                    "raw_matrix": spatial_matrix,  # Forwards coordinates matrix to React
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AvailableTemplatesListView(APIView):
    """
    📋 METADATA BLUEPRINT SERIALIZER VIEW:
    Serves full geometric coordinates from unpacked explicit table fields back
    to the frontend configuration engine UI seamlessly.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        templates = UserStatementTemplate.objects.all().order_by("template_name")
        payload = []

        for t in templates:
            # Check if signature properties contain a valid layout footprint
            sig = t.signature_json or "{}"
            is_universal = bool(t.matching_keyword) or "UNIVERSAL_GEOMETRY" in sig

            try:
                meta = json.loads(sig) if isinstance(sig, str) else sig
            except Exception:
                meta = {}

            # Construct clean, column-driven bounds dict map for your frontend template state
            payload.append(
                {
                    "id": t.id,
                    "template_name": t.template_name,
                    "is_universal": is_universal,
                    "matching_keyword": t.matching_keyword
                    or meta.get("matching_keyword", ""),
                    "bounds": {
                        "date_max": t.date_x,
                        "value_date_max": t.narration_x,
                        "trantype_max": t.debit_x,
                        "cheque_max": t.credit_x,
                        "particulars_max": t.debit_x,  # Consistent frontend variable mirroring mappings
                        "withdrawals_max": t.debit_x,
                        "deposits_max": t.credit_x,
                        "balance_max": t.balance_x,
                        "header_lines_to_skip": t.header_lines_to_skip,
                        "footer_lines_to_skip": t.footer_lines_to_skip,
                        "y_tolerance": t.y_tolerance,
                    },
                }
            )

        return Response(payload, status=status.HTTP_200_OK)


class StatementTemplateSaveAPIView(APIView):
    """
    💾 DETERMINISTIC CONFIGURATION WRITER:
    Binds coordinate geometry parameters and processing engine switches
    directly to native columns on ledger_userstatementtemplate.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        template_name = request.data.get("templateName")
        account_id = request.data.get("accountId")
        bounds_config = request.data.get("boundsConfig", {})

        # ─── 🟢 EXPLICIT MODE AND FORMAT INJECTIONS FROM THE UI ───
        has_separate_cols = request.data.get("hasSeparateColumns", True)
        target_date_format = request.data.get("dateFormat", "%d-%m-%Y")

        if not template_name or not account_id or not bounds_config:
            return Response(
                {"error": "Required blueprint mapping metadata fields are missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = get_object_or_404(Account, id=account_id)

            target_user = (
                request.user
                if request.user and not request.user.is_anonymous
                else get_user_model().objects.first()
            )

            # Unpack incoming UI parameters into absolute geometric floats
            d_x = float(bounds_config.get("date_max", 10.0))
            n_x = float(bounds_config.get("value_date_max", 18.0))
            deb_x = float(bounds_config.get("withdrawals_max", 52.0))
            cred_x = float(bounds_config.get("deposits_max", 60.0))
            bal_x = float(bounds_config.get("balance_max", 98.0))

            # Set up default heuristics for bank profiles dynamically
            is_sbi = "SBI" in template_name.upper()
            keyword = "SBI" if is_sbi else "FED"
            y_tol = 3.0 if is_sbi else 2.5
            h_skip = 5 if is_sbi else 4
            f_skip = 2 if is_sbi else 3

            # Catch-all container payload for unmapped future params
            extended_meta = {
                "UNIVERSAL_GEOMETRY": True,
                "indicator_max": int(bounds_config.get("indicator_max", 100)),
            }

            # 🔒 ATOMIC ATTACHMENT WRITER: Persist clean data fields straight to schema columns
            template, created = UserStatementTemplate.objects.update_or_create(
                account=account,
                defaults={
                    "user": target_user,
                    "template_name": template_name.strip(),
                    "matching_keyword": keyword,
                    # 📐 Native Bounding Box Coordinates
                    "date_x": d_x,
                    "narration_x": n_x,
                    "debit_x": deb_x,
                    "credit_x": cred_x,
                    "balance_x": bal_x,
                    # Fallback structural index properties
                    "date_index": int(bounds_config.get("date_max", 10)),
                    "narration_index": int(bounds_config.get("value_date_max", 18)),
                    "debit_index": int(bounds_config.get("trantype_max", 52)),
                    "credit_index": int(bounds_config.get("cheque_max", 60)),
                    "balance_index": 0,
                    # Operational Switches
                    "has_separate_dr_cr_columns": bool(has_separate_cols),
                    "date_format": target_date_format.strip(),
                    "y_tolerance": y_tol,
                    "multiline_enabled": True,
                    "header_lines_to_skip": h_skip,
                    "footer_lines_to_skip": f_skip,
                    # Store clean payloads safely inside the escaping JSON field
                    "signature_json": json.dumps(extended_meta),
                    "header_signature": json.dumps(
                        {
                            "UNIVERSAL_GEOMETRY": True,
                            "withdrawals_max": deb_x,
                            "deposits_max": cred_x,
                            "balance_max": bal_x,
                        }
                    ),
                },
            )

            return Response(
                {
                    "status": "synchronized",
                    "template_name": template.template_name,
                    "mode_assigned": (
                        "Strategy A (Flat)"
                        if template.has_separate_dr_cr_columns
                        else "Strategy B (Stacked Machine)"
                    ),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Blueprint persistence runtime error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StatementIngestRouterDynamicView(APIView):
    """
    🚀 DYNAMIC INGESTION ROUTER INTERFACE:
    Identifies document type layers over an automated matching engine,
    instantiating our coordinate-aware parser core to deliver clean,
    deduplicated ledger datasets directly to the frontend interface.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        account_id = request.data.get("account_id")

        if not uploaded_file or not account_id:
            return Response(
                {
                    "error": "Missing required ingestion payload: file or account_id block."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # ─── STEP 1: RESOLVE FILE GEOMETRY OVER THE ROUTER ───
            routing_match = match_statement_template(uploaded_file, account_id)

            if routing_match.get("type") == "UNKNOWN":
                return Response(
                    {
                        "status": "REQUIRES_MAPPING",
                        "message": "No registered schema model blueprint found for this statement signature layout.",
                        "file_name": uploaded_file.name,
                    },
                    status=status.HTTP_200_OK,
                )

            # ─── STEP 2: PARSE PDF STATEMENTS WITH OUR COORDINATE CORE ───
            if routing_match.get("type") == "UNIVERSAL_PDF":
                # Instantiating the exact UniversalStatementParser class we perfected
                processor = UniversalStatementParser(uploaded_file, account_id)
                result = processor.execute_full_parse()

                if not result.get("success"):
                    return Response(
                        {
                            "error": result.get(
                                "error_message", "Parsing execution error."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                inner_data = result.get("data", {})
                formatted_transactions = inner_data.get("preview_dataset", [])

                # Return the completely self-calculated, pristine dataset metrics
                return Response(
                    {
                        "status": "PARSED_SUCCESS",
                        "applied_template": routing_match["template"].template_name,
                        "transactions": formatted_transactions,
                        "total_debit": inner_data.get("calculated_debit", 0.0),
                        "total_credit": inner_data.get("calculated_credit", 0.0),
                        "opening_balance": inner_data.get("calculated_opening", 0.0),
                        "closing_balance": inner_data.get("calculated_closing", 0.0),
                        "debit_line_count": inner_data.get("debit_line_count", 0),
                        "credit_line_count": inner_data.get("credit_line_count", 0),
                        "audit_passed": inner_data.get("audit_passed", True),
                    },
                    status=status.HTTP_200_OK,
                )

            # ─── STEP 3: FALLBACK COMPATIBILITY FOR CSV STREAMS ───
            elif routing_match.get("type") == "CSV":
                return Response(
                    {
                        "status": "PARSED_SUCCESS",
                        "applied_template": routing_match["template"].template_name,
                        "transactions": [],
                        "total_debit": 0.0,
                        "total_credit": 0.0,
                        "opening_balance": 0.0,
                        "closing_balance": 0.0,
                    },
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            return Response(
                {
                    "error": f"Automated ledger router validation engine trace crash: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


##################################


class StatementBulkIngestPipelineView(APIView):
    """
    📡 PIPELINE INGESTION VIEW CONTROLLER (PRODUCTION ALIGNED):
    Loads historical deduplication hashes up front, processes document layouts,
    normalizes string variations, and triggers inline narration enrichment checks
    before emitting the payload grid to the front-end dashboard preview.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("statement_file")
        account_id = request.data.get("account_id")

        if not uploaded_file or not account_id:
            return Response(
                {"status": "ERROR", "message": "Required parameters are missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account = Account.objects.get(id=account_id)

            # ─── 🚀 STEP A: INTERCEPT EXTENSION FIRST ───
            original_filename = getattr(uploaded_file, "name", "bank_statement.pdf")
            file_extension = os.path.splitext(original_filename)[1].lower()
            is_tabular = file_extension in [".csv", ".txt", ".xlsx", ".xls"]

            # ─── 🎯 STEP B: STRATEGY-AWARE DATABASE TEMPLATE RESOLUTION ───
            if is_tabular:
                template_obj = UserStatementTemplate.objects.filter(
                    template_name="UNIVERSAL"
                ).first()
                if not template_obj:
                    template_obj = UserStatementTemplate.objects.filter(
                        account_id=account_id
                    ).first()
            else:
                template_obj = (
                    UserStatementTemplate.objects.filter(account_id=account_id)
                    .exclude(parser_strategy_code="UNIVERSAL_CSV_FLOW")
                    .first()
                )

            if not template_obj:
                template_obj = UserStatementTemplate.objects.filter(
                    account_id=account_id
                ).first()

            if not template_obj:
                return Response(
                    {
                        "status": "ERROR",
                        "message": "No parsing template linked to this account context profile.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            credential_record = BankCredential.objects.filter(
                account_id=account_id
            ).first()
            password_vault_data = (
                credential_record.password_vault if credential_record else "[]"
            )

            # Pull historical database verification metrics
            db_records = StatementStagingLine.objects.filter(
                account_id=account.id
            ).values(
                "row_identifier",
                "narration",
                "cheque_ref_number",
                "raw_statement_date",
                "amount",
                "running_balance",
                "credit",
                "debit",
            )

            existing_hashes = set()
            database_lookup_dict = {}
            for r in db_records:
                h_key = r["row_identifier"]
                existing_hashes.add(h_key)
                database_lookup_dict[h_key] = r

            # Process layout coordinates
            processed_bundle, op_bal, system_noise = process_bank_statement(
                uploaded_file=uploaded_file,
                template_obj=template_obj,
                account_id=account_id,
                existing_database_hashes=existing_hashes,
                password_vault=password_vault_data,
            )

            export_filename = f"{os.path.splitext(original_filename)[0]}.csv"
            intermediate_txns = []
            ocr_confidence_score = 100.0
            active_strategy = getattr(
                template_obj, "parser_strategy_code", "UNIVERSAL_CSV_FLOW"
            )

            if (
                isinstance(processed_bundle, dict)
                and "transactions_list" in processed_bundle
            ):
                intermediate_txns = processed_bundle.get("transactions_list", [])
                ocr_confidence_score = processed_bundle.get("confidence_score", 0.0)
                active_strategy = processed_bundle.get(
                    "fallback_engine_executed", "PaddleOCR_v1"
                )
            elif isinstance(processed_bundle, str):
                return Response(
                    {
                        "status": "SUCCESS",
                        "export_filename": export_filename,
                        "raw_csv_stream": processed_bundle,
                        "preview_dataset": [],
                        "opening_balance": op_bal,
                        "closing_balance": op_bal,
                        "count": 0,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                intermediate_txns = processed_bundle

            if (
                "sanitize_transaction_dates_via_template" in locals()
                or "sanitize_transaction_dates_via_template" in globals()
            ):
                intermediate_txns = sanitize_transaction_dates_via_template(
                    intermediate_txns, template_obj
                )

            # Generate baseline payload matrix layout maps
            payload = validator.run_final_math(
                intermediate_txns,
                op_bal,
                template_obj=template_obj,
                account_id=account_id,
                export_filename=export_filename,
            )

            preview_dataset = payload.get("preview_dataset", [])

            # ─── 🎯 RUN DUAL ENRICHMENT PROCESSING PASS ───
            # This mutates the values inside preview_dataset array elements inline
            _, _ = validator.process_and_filter_rows(
                preview_dataset=preview_dataset,
                account=account,
                bank=account.bank if hasattr(account, "bank") else None,
                existing_hashes=existing_hashes,
                database_lookup_dict=database_lookup_dict,
            )

            # Re-generate diagnostic CSV strings using the updated values
            raw_csv_lines = [
                f"#FILENAME:{export_filename}",
                "Date ~ Narration ~ Debit ~ Credit ~ Running Bal ~ Record Status",
            ]
            for row in preview_dataset:
                p_narr_escaped = (
                    str(row["narration_description"]).replace('"', '""').strip()
                )
                raw_csv_lines.append(
                    f'{row["post_date"]} ~ "{p_narr_escaped}" ~ {row["debit"]} ~ {row["credit"]} ~ {row["balance"]} ~ {row["status"]}'
                )

            # Re-sync payload array structures
            payload["preview_dataset"] = preview_dataset
            payload["generated_raw_csv_stream"] = "\n".join(raw_csv_lines)

            return Response(
                {
                    "status": "SUCCESS",
                    "strategy_processed": active_strategy,
                    "engine_strategy_executed": active_strategy,
                    "confidence_score": ocr_confidence_score,
                    "system_noise_records_cleared": (
                        len(system_noise) if system_noise else 0
                    ),
                    "export_filename": export_filename,
                    "raw_csv_stream": payload.get("generated_raw_csv_stream", ""),
                    **payload,  # Unpacks the correctly synchronized array references out to the React table grid
                },
                status=status.HTTP_200_OK,
            )

        except Account.DoesNotExist:
            return Response(
                {"status": "ERROR", "message": "Account context not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            print(f"❌ PIPELINE INGEST PREVIEW CRASHED: {str(e)}")
            return Response(
                {"status": "ERROR", "message": f"Pipeline execution crash: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
