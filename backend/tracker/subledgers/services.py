import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from decimal import Decimal
from django.db.models import Q
from django.apps import apps
from django.apps import apps
from django.db.models import Q
from decimal import Decimal
from .candidate_matcher_helpers import (
    resolve_bank_hint,
    build_date_range_filter,
    get_bank_paired_row_identifiers,
)

if TYPE_CHECKING:
    from tracker.models import JournalEntry
    from tracker.models.subledger import AssetSubLedger, AssetTransactionMapping


class AssetCandidateMatcher:

    # ---------------------------------------------------------
    # STATIC HELPER METHODS
    # ---------------------------------------------------------

    @staticmethod
    def parse_date_safely(val, default=None):
        """Safely normalize strings, datetimes, or dates into datetime.date."""
        if not val:
            return default
        if isinstance(val, date) and not isinstance(val, datetime):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, str):
            clean_str = val.strip()
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(clean_str, fmt).date()
                except ValueError:
                    continue
        return default

    @staticmethod
    def normalize_text(text):
        """Sanitize remarks and keywords for case-insensitive matching."""
        if not text:
            return ""
        return re.sub(r"[^a-zA-Z0-9]", "", str(text)).lower()

    @staticmethod
    def normalize_subcategory(sub_name):
        """Strip taxonomy arrow notation dynamically (e.g. 'Asset ➔ Gold' -> 'Gold')."""
        if not sub_name:
            return ""
        tokens = re.split(r"[➔\->/]+", str(sub_name))
        return tokens[-1].strip()

    @staticmethod
    def inspect_asset_stream(asset_obj):
        """Determine if asset represents an inflow/credit or outflow/debit stream."""
        if not asset_obj or not asset_obj.asset_category:
            return False

        cat_type = getattr(asset_obj.asset_category, "category_type", "").upper()
        cat_code = getattr(asset_obj.asset_category, "code", "").upper()
        return cat_type == "INCOME" or "INCOME" in cat_code or "RENT" in cat_code

    @staticmethod
    def extract_asset_keywords(asset_obj, fallback_keywords=None):
        """Derive search keywords from vendor defaults or cleaned asset codes/names."""
        if fallback_keywords:
            return [kw for kw in fallback_keywords if kw]

        if not asset_obj:
            return []

        # 1. Vendor defaults
        if asset_obj.vendor:
            if getattr(asset_obj.vendor, "default_keywords", None):
                return asset_obj.vendor.default_keywords
            if getattr(asset_obj.vendor, "name", None):
                return [asset_obj.vendor.name]

        # 2. Asset name cleanup (strip leading prefixes like FD#, AST-, etc.)
        if asset_obj.name:
            clean_token = re.sub(
                r"^(FD#?|AST-|SBI FD|Asset)\s*", "", asset_obj.name, flags=re.I
            ).strip()
            if len(clean_token) >= 4:
                return [clean_token]

        return []

    @staticmethod
    def build_vector_filter(is_income_stream):
        """Return credit > 0 for income or debit > 0 for expenditure/assets."""
        return {"credit__gt": 0} if is_income_stream else {"debit__gt": 0}

    @staticmethod
    def calculate_match_score(
        has_subcategory, matched_count, is_amount_matched, base_unmapped_score=70
    ):
        """Calculate dynamic confidence probability score."""
        score = base_unmapped_score if has_subcategory else 0
        if matched_count > 0:
            score += min(20 + (matched_count * 10), 30)
        if is_amount_matched:
            score += 30
        return min(score, 100)

    @staticmethod
    def _resolve_remarks(remarks):
        """Helper to extract a clean string narration from remarks dictionary or fallback."""
        if isinstance(remarks, dict):
            return (
                remarks.get("display_text")
                or remarks.get("narration")
                or remarks.get("payee")
                or ""
            )
        return str(remarks or "")

    @classmethod
    def find_candidate_rows(
        cls,
        document_date=None,
        target_amount=None,
        account_id=99,
        keywords=None,
        day_window=1825,
        amount_tolerance_pct=Decimal("0.05"),
        asset_id=None,
        to_date=None,
        subcategory=None,
        unmapped_only=False,
        max_results=200,
        bank_account_hint=None,
    ):
        JournalEntry = apps.get_model("ledger", "JournalEntry")
        StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
        AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
        AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")
        Account = apps.get_model("ledger", "Account")

        doc_date = cls.parse_date_safely(document_date)
        parsed_to_date = cls.parse_date_safely(to_date)

        # ---------------------------------------------------------------------
        # 1. Asset Folio Inspection & Scope
        # ---------------------------------------------------------------------
        asset_obj = None
        is_income_stream = False
        is_cash_domain = False

        if asset_id:
            try:
                asset_obj = AssetSubLedger.objects.select_related(
                    "asset_category", "vendor", "linked_gl_account"
                ).get(id=asset_id)
                is_income_stream = cls.inspect_asset_stream(asset_obj)

                if not subcategory and asset_obj.linked_gl_account:
                    subcategory = asset_obj.linked_gl_account

                cat_code = str(getattr(asset_obj, "category", "")).upper()
                gl_head = ""
                if hasattr(asset_obj.linked_gl_account, "subcategory"):
                    gl_head = str(asset_obj.linked_gl_account.subcategory).lower()
                else:
                    gl_head = str(asset_obj.linked_gl_account or "").lower()

                is_cash_domain = (
                    "CASH" in cat_code
                    or "FLOAT" in cat_code
                    or "petty cash" in gl_head
                    or "float" in gl_head
                )

                # Auto-lock bank account hint ONLY for cash floats if not explicitly passed
                if (
                    is_cash_domain
                    and not bank_account_hint
                    and isinstance(asset_obj.metadata_payload, dict)
                ):
                    raw_hint = str(
                        asset_obj.metadata_payload.get("bank_account_hint", "")
                    ).strip()
                    digits = re.findall(r"\d+", raw_hint)
                    if digits:
                        bank_account_hint = digits[-1]
                    elif raw_hint:
                        bank_account_hint = raw_hint

            except Exception as e:
                print(f"⚠️ [CANDIDATE MATCHER] Asset inspection failed: {e}")

        # ---------------------------------------------------------------------
        # 2. Keywords Normalization
        # ---------------------------------------------------------------------
        search_terms = []
        if keywords:
            if isinstance(keywords, str):
                search_terms = [k.strip() for k in keywords.split(",") if k.strip()]
            elif isinstance(keywords, list):
                search_terms = [str(k).strip() for k in keywords if str(k).strip()]

        if not search_terms and asset_obj:
            extracted = cls.extract_asset_keywords(asset_obj) or []
            if not is_cash_domain or not bank_account_hint:
                search_terms = extracted

        # ---------------------------------------------------------------------
        # 3. Target Amount Bounds Calculation
        # ---------------------------------------------------------------------
        has_target_amount = (
            target_amount is not None and Decimal(str(target_amount)) > 0
        )
        min_amount, max_amount = None, None
        if has_target_amount:
            target_amt = Decimal(str(target_amount))
            min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
            max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

        # =====================================================================
        # PHASE 1: DIRECT LOOKUP FOR BOUND TRANSACTIONS (THIS ASSET)
        # =====================================================================
        mapped_entries = []
        seen_row_ids = set()
        seen_journal_ids = set()

        if asset_id and not unmapped_only:
            bound_mappings = list(
                AssetTransactionMapping.objects.filter(asset_id=asset_id)
                .exclude(row_identifier__isnull=True)
                .values("id", "row_identifier")
            )

            if bound_mappings:
                mapping_map = {m["row_identifier"]: m["id"] for m in bound_mappings}
                bound_row_ids = list(mapping_map.keys())

                bound_entries = list(
                    JournalEntry.objects.filter(row_identifier__in=bound_row_ids)
                )

                bound_narrations = dict(
                    StatementStagingLine.objects.filter(
                        row_identifier__in=bound_row_ids
                    ).values_list("row_identifier", "narration")
                )

                asset_code_val = (
                    getattr(asset_obj, "asset_code", "") if asset_obj else ""
                )
                asset_name_val = getattr(asset_obj, "name", "") if asset_obj else ""

                for entry in bound_entries:
                    seen_row_ids.add(entry.row_identifier)
                    seen_journal_ids.add(str(entry.id))
                    mapping_id = mapping_map.get(entry.row_identifier)

                    ssot_narration = bound_narrations.get(
                        entry.row_identifier, cls._resolve_remarks(entry.remarks)
                    )

                    mapped_entries.append(
                        {
                            "journal_id": str(entry.id),
                            "row_identifier": entry.row_identifier,
                            "account_id": entry.account_id,
                            "transaction_date": entry.transaction_date.strftime(
                                "%Y-%m-%d"
                            ),
                            "date_offset_days": 0,
                            "debit": float(entry.debit),
                            "credit": float(entry.credit),
                            "remarks": ssot_narration,
                            "matched_keywords": search_terms,
                            "probability_score": 100,
                            "is_mapped": True,
                            "is_mapped_to_this_asset": True,
                            "mapping_info": {
                                "mapping_id": str(mapping_id) if mapping_id else None,
                                "asset_id": str(asset_id),
                                "asset_code": asset_code_val,
                                "asset_name": asset_name_val,
                            },
                        }
                    )

        # =====================================================================
        # PHASE 2: SEARCH VIA STAGING (SSOT) & JOURNAL ENTRY (STAGE 3)
        # =====================================================================
        # 1. Base Node 99 Query
        unmapped_query = JournalEntry.objects.filter(account_id=account_id or 99)

        # 2. Reclassification Rules & Directional Vector
        if is_cash_domain:
            # 🎯 FOR CASH FLOATS:
            # A) Only pull unclassified items
            unmapped_query = unmapped_query.filter(
                Q(is_reclassified=False)
                | Q(is_reclassified=0)
                | Q(is_reclassified__isnull=True)
            ).filter(
                Q(evaluation_matrix_snapshot__resolved_subcategory__isnull=True)
                | Q(evaluation_matrix_snapshot__resolved_subcategory="")
                | Q(evaluation_matrix_snapshot__resolved_subcategory="Suspense Account")
                | Q(evaluation_matrix_snapshot__resolved_subcategory__icontains="Cash")
                | Q(evaluation_matrix_snapshot__resolved_subcategory__icontains="Float")
            )
            # B) 🎯 CRITICAL: ONLY INCOMING MONEY (TOP-UPS / INFLOWS) ARE CREDITS ON NODE 99
            # Everyday expenses (seafood, tea, fuel) are DEBITS on Node 99 and are excluded here!
            unmapped_query = unmapped_query.filter(credit__gt=0, debit=0)
        else:
            # For General Subledgers / Workbench
            clean_sub = cls.normalize_subcategory(subcategory)
            if clean_sub and not search_terms:
                unmapped_query = unmapped_query.filter(
                    Q(
                        evaluation_matrix_snapshot__resolved_subcategory__iexact=clean_sub
                    )
                    | Q(
                        evaluation_matrix_snapshot__target_subcategory__iexact=clean_sub
                    )
                    | Q(evaluation_matrix_snapshot__resolved_category__iexact=clean_sub)
                    | Q(
                        evaluation_matrix_snapshot__resolved_subcategory__iexact="Suspense Account"
                    )
                    | Q(evaluation_matrix_snapshot__isnull=True)
                )

            # Normal directional vector for other subledgers
            vector_filter = cls.build_vector_filter(is_income_stream)
            unmapped_query = unmapped_query.filter(**vector_filter)

        # 3. Date Range Filter
        if doc_date:
            start_date = doc_date - timedelta(days=day_window)
            if parsed_to_date:
                end_date = parsed_to_date
            elif day_window >= 1825:
                end_date = date.today()
            else:
                end_date = doc_date + timedelta(days=day_window)

            unmapped_query = unmapped_query.filter(
                transaction_date__gte=start_date,
                transaction_date__lte=end_date,
            )

        # 4. Amount Bounds Filter (applied to credits for cash float top-ups)
        if has_target_amount and min_amount is not None and max_amount is not None:
            if is_cash_domain:
                unmapped_query = unmapped_query.filter(
                    credit__gte=min_amount, credit__lte=max_amount
                )
            else:
                unmapped_query = unmapped_query.filter(
                    (Q(debit__gte=min_amount) & Q(debit__lte=max_amount))
                    | (Q(credit__gte=min_amount) & Q(credit__lte=max_amount))
                )

        # ---------------------------------------------------------------------
        # 5. Bank Account Isolation via JournalEntry Pairing Leg
        # ---------------------------------------------------------------------
        if bank_account_hint:
            clean_hint = str(bank_account_hint).strip()
            acc_query = Q(account_number__icontains=clean_hint) | Q(
                name__icontains=clean_hint
            )
            if clean_hint.isdigit():
                acc_query |= Q(id=int(clean_hint))

            target_acc_ids = list(
                Account.objects.filter(acc_query).values_list("id", flat=True)
            )

            if target_acc_ids:
                # Find all row_identifiers where the REAL bank leg belongs to the target account
                paired_row_ids = list(
                    JournalEntry.objects.filter(account_id__in=target_acc_ids)
                    .exclude(account_id=99)
                    .values_list("row_identifier", flat=True)
                )
                unmapped_query = unmapped_query.filter(
                    row_identifier__in=paired_row_ids
                )
            else:
                unmapped_query = unmapped_query.none()

        # 6. Keywords Search via Staging SSOT
        if search_terms:
            staging_kw_q = Q()
            for term in search_terms:
                staging_kw_q |= Q(narration__icontains=term)

            matched_row_ids = list(
                StatementStagingLine.objects.filter(staging_kw_q).values_list(
                    "row_identifier", flat=True
                )
            )
            remarks_q = Q(row_identifier__in=matched_row_ids)
            for term in search_terms:
                remarks_q |= Q(remarks__icontains=term)
            unmapped_query = unmapped_query.filter(remarks_q)

        # ---------------------------------------------------------------------
        # 7. Fetch Candidates Slice
        # ---------------------------------------------------------------------
        candidate_entries = list(
            unmapped_query.order_by("-transaction_date")[:max_results]
        )
        candidate_row_ids = [
            e.row_identifier for e in candidate_entries if e.row_identifier
        ]

        # ---------------------------------------------------------------------
        # 8. Batch Hydrate SSOT Narrations & Existing Mappings
        # ---------------------------------------------------------------------
        staging_narrations_map = (
            dict(
                StatementStagingLine.objects.filter(
                    row_identifier__in=candidate_row_ids
                ).values_list("row_identifier", "narration")
            )
            if candidate_row_ids
            else {}
        )

        all_mappings = (
            {
                m.row_identifier: m
                for m in AssetTransactionMapping.objects.filter(
                    row_identifier__in=candidate_row_ids
                ).select_related("asset")
            }
            if candidate_row_ids
            else {}
        )

        # ---------------------------------------------------------------------
        # 9. Batch Hydrate Pairing Bank Account Metadata (Name + Last 4)
        # ---------------------------------------------------------------------
        pairing_legs = (
            JournalEntry.objects.filter(row_identifier__in=candidate_row_ids)
            .exclude(account_id=99)
            .values("row_identifier", "account_id")
        )
        row_to_bank_id = {p["row_identifier"]: p["account_id"] for p in pairing_legs}

        all_bank_ids = set(row_to_bank_id.values())
        account_lookup = {}
        if all_bank_ids:
            for acc in Account.objects.filter(id__in=all_bank_ids):
                acc_num = str(getattr(acc, "account_number", "") or "")
                last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
                account_lookup[acc.id] = {
                    "bank_name": getattr(acc, "name", "Bank"),
                    "bank_last4": last4,
                    "account_id": acc.id,
                }

        # ---------------------------------------------------------------------
        # 10. Assembly
        # ---------------------------------------------------------------------
        unmapped_candidates = []
        target_asset_str = str(asset_id or "")

        for entry in candidate_entries:
            if (
                entry.row_identifier in seen_row_ids
                or str(entry.id) in seen_journal_ids
            ):
                continue

            ssot_narration = staging_narrations_map.get(
                entry.row_identifier, cls._resolve_remarks(entry.remarks)
            )

            matched_keywords_found = [
                term for term in search_terms if term.lower() in ssot_narration.lower()
            ]

            is_amount_matched = False
            if has_target_amount and min_amount is not None and max_amount is not None:
                is_amount_matched = (
                    min_amount <= entry.debit <= max_amount
                    or min_amount <= entry.credit <= max_amount
                )

            clean_sub_val = cls.normalize_subcategory(subcategory)
            score = cls.calculate_match_score(
                has_subcategory=bool(clean_sub_val),
                matched_count=len(matched_keywords_found),
                is_amount_matched=is_amount_matched,
            )

            date_offset = (entry.transaction_date - doc_date).days if doc_date else 0
            mapping = all_mappings.get(entry.row_identifier)
            is_bound = mapping is not None
            is_this_asset = is_bound and str(mapping.asset_id) == target_asset_str

            mapping_info = None
            if is_bound and mapping.asset:
                mapping_info = {
                    "mapping_id": str(mapping.id),
                    "asset_id": str(mapping.asset.id),
                    "asset_code": mapping.asset.asset_code,
                    "asset_name": mapping.asset.name,
                }

            bank_id = row_to_bank_id.get(entry.row_identifier)
            bank_meta = account_lookup.get(bank_id, {})

            unmapped_candidates.append(
                {
                    "journal_id": str(entry.id),
                    "row_identifier": entry.row_identifier,
                    "account_id": entry.account_id,
                    "bank_account_id": bank_id,
                    "bank_name": bank_meta.get("bank_name"),
                    "bank_last4": bank_meta.get("bank_last4"),
                    "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
                    "date_offset_days": date_offset,
                    "debit": float(entry.debit),
                    "credit": float(entry.credit),
                    "remarks": ssot_narration,
                    "matched_keywords": matched_keywords_found,
                    "probability_score": score,
                    "is_mapped": is_bound,
                    "is_mapped_to_this_asset": is_this_asset,
                    "mapping_info": mapping_info,
                }
            )

        return mapped_entries + unmapped_candidates

    # @classmethod
    # def find_candidate_rows(
    #     cls,
    #     document_date=None,
    #     target_amount=None,
    #     account_id=99,
    #     keywords=None,
    #     day_window=1825,
    #     amount_tolerance_pct=Decimal("0.05"),
    #     asset_id=None,
    #     to_date=None,
    #     subcategory=None,
    #     unmapped_only=False,
    #     max_results=200,
    #     bank_account_hint=None,
    # ):

    #     JournalEntry = apps.get_model("ledger", "JournalEntry")
    #     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
    #     AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
    #     AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")
    #     Account = apps.get_model("ledger", "Account")

    #     doc_date = cls.parse_date_safely(document_date)
    #     parsed_to_date = cls.parse_date_safely(to_date)

    #     # ---------------------------------------------------------------------
    #     # 1. Asset Folio Inspection & Scope
    #     # ---------------------------------------------------------------------
    #     asset_obj = None
    #     is_income_stream = False
    #     is_cash_domain = False

    #     if asset_id:
    #         try:
    #             asset_obj = AssetSubLedger.objects.select_related(
    #                 "asset_category", "vendor", "linked_gl_account"
    #             ).get(id=asset_id)
    #             is_income_stream = cls.inspect_asset_stream(asset_obj)

    #             if not subcategory and asset_obj.linked_gl_account:
    #                 subcategory = asset_obj.linked_gl_account

    #             cat_code = str(getattr(asset_obj, "category", "")).upper()
    #             gl_head = ""
    #             if hasattr(asset_obj.linked_gl_account, "subcategory"):
    #                 gl_head = str(asset_obj.linked_gl_account.subcategory).lower()
    #             else:
    #                 gl_head = str(asset_obj.linked_gl_account or "").lower()

    #             is_cash_domain = (
    #                 "CASH" in cat_code
    #                 or "FLOAT" in cat_code
    #                 or "petty cash" in gl_head
    #                 or "float" in gl_head
    #             )

    #             bank_account_hint = resolve_bank_hint(
    #                 asset_obj, bank_account_hint, is_cash_domain
    #             )
    #         except Exception as e:
    #             print(f"⚠️ [CANDIDATE MATCHER] Asset inspection failed: {e}")

    #     # ---------------------------------------------------------------------
    #     # 2. Keywords Normalization
    #     # ---------------------------------------------------------------------
    #     search_terms = []
    #     if keywords:
    #         if isinstance(keywords, str):
    #             search_terms = [k.strip() for k in keywords.split(",") if k.strip()]
    #         elif isinstance(keywords, list):
    #             search_terms = [str(k).strip() for k in keywords if str(k).strip()]

    #     if not search_terms and asset_obj:
    #         extracted = cls.extract_asset_keywords(asset_obj) or []
    #         if not is_cash_domain or not bank_account_hint:
    #             search_terms = extracted

    #     # ---------------------------------------------------------------------
    #     # 3. Target Amount Bounds Calculation
    #     # ---------------------------------------------------------------------
    #     has_target_amount = (
    #         target_amount is not None and Decimal(str(target_amount)) > 0
    #     )
    #     min_amount, max_amount = None, None
    #     if has_target_amount:
    #         target_amt = Decimal(str(target_amount))
    #         min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
    #         max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

    #     # =====================================================================
    #     # PHASE 1: DIRECT LOOKUP FOR BOUND TRANSACTIONS (THIS ASSET)
    #     # =====================================================================
    #     mapped_entries = []
    #     seen_row_ids = set()
    #     seen_journal_ids = set()

    #     if asset_id and not unmapped_only:
    #         bound_mappings = list(
    #             AssetTransactionMapping.objects.filter(asset_id=asset_id)
    #             .exclude(row_identifier__isnull=True)
    #             .values("id", "row_identifier")
    #         )

    #         if bound_mappings:
    #             mapping_map = {m["row_identifier"]: m["id"] for m in bound_mappings}
    #             bound_row_ids = list(mapping_map.keys())

    #             bound_entries = list(
    #                 JournalEntry.objects.filter(row_identifier__in=bound_row_ids)
    #             )

    #             bound_narrations = dict(
    #                 StatementStagingLine.objects.filter(
    #                     row_identifier__in=bound_row_ids
    #                 ).values_list("row_identifier", "narration")
    #             )

    #             asset_code_val = (
    #                 getattr(asset_obj, "asset_code", "") if asset_obj else ""
    #             )
    #             asset_name_val = getattr(asset_obj, "name", "") if asset_obj else ""

    #             for entry in bound_entries:
    #                 seen_row_ids.add(entry.row_identifier)
    #                 seen_journal_ids.add(str(entry.id))
    #                 mapping_id = mapping_map.get(entry.row_identifier)

    #                 ssot_narration = bound_narrations.get(
    #                     entry.row_identifier,
    #                     cls._resolve_remarks(entry.remarks),
    #                 )

    #                 mapped_entries.append(
    #                     {
    #                         "journal_id": str(entry.id),
    #                         "row_identifier": entry.row_identifier,
    #                         "account_id": entry.account_id,
    #                         "transaction_date": entry.transaction_date.strftime(
    #                             "%Y-%m-%d"
    #                         ),
    #                         "date_offset_days": 0,
    #                         "debit": float(entry.debit),
    #                         "credit": float(entry.credit),
    #                         "remarks": ssot_narration,
    #                         "matched_keywords": search_terms,
    #                         "probability_score": 100,
    #                         "is_mapped": True,
    #                         "is_mapped_to_this_asset": True,
    #                         "mapping_info": {
    #                             "mapping_id": str(mapping_id) if mapping_id else None,
    #                             "asset_id": str(asset_id),
    #                             "asset_code": asset_code_val,
    #                             "asset_name": asset_name_val,
    #                         },
    #                     }
    #                 )

    #     # =====================================================================
    #     # PHASE 2: SEARCH VIA STAGING (SSOT) & JOURNAL ENTRY (STAGE 3)
    #     # =====================================================================
    #     # 1. Base Node 99 Query
    #     unmapped_query = JournalEntry.objects.filter(account_id=account_id or 99)

    #     # 2. Strict Reclassification Rules
    #     if is_cash_domain:
    #         # For Cash Floats: Exclude items already reclassified to other non-cash expense categories
    #         unmapped_query = unmapped_query.filter(
    #             Q(is_reclassified=False)
    #             | Q(is_reclassified=0)
    #             | Q(is_reclassified__isnull=True)
    #         ).filter(
    #             Q(evaluation_matrix_snapshot__resolved_subcategory__isnull=True)
    #             | Q(evaluation_matrix_snapshot__resolved_subcategory="")
    #             | Q(evaluation_matrix_snapshot__resolved_subcategory="Suspense Account")
    #             | Q(evaluation_matrix_snapshot__resolved_subcategory__icontains="Cash")
    #             | Q(evaluation_matrix_snapshot__resolved_subcategory__icontains="Float")
    #         )
    #     else:
    #         # For General Subledgers / Workbench
    #         clean_sub = cls.normalize_subcategory(subcategory)
    #         if clean_sub and not search_terms:
    #             unmapped_query = unmapped_query.filter(
    #                 Q(
    #                     evaluation_matrix_snapshot__resolved_subcategory__iexact=clean_sub
    #                 )
    #                 | Q(
    #                     evaluation_matrix_snapshot__target_subcategory__iexact=clean_sub
    #                 )
    #                 | Q(evaluation_matrix_snapshot__resolved_category__iexact=clean_sub)
    #                 | Q(
    #                     evaluation_matrix_snapshot__resolved_subcategory__iexact="Suspense Account"
    #                 )
    #                 | Q(evaluation_matrix_snapshot__isnull=True)
    #             )

    #     # 3. Date Range Filter
    #     date_filter = build_date_range_filter(doc_date, parsed_to_date, day_window)
    #     if date_filter != Q():
    #         unmapped_query = unmapped_query.filter(date_filter)

    #     # 4. Amount Bounds Filter
    #     if has_target_amount and min_amount is not None and max_amount is not None:
    #         unmapped_query = unmapped_query.filter(
    #             (Q(debit__gte=min_amount) & Q(debit__lte=max_amount))
    #             | (Q(credit__gte=min_amount) & Q(credit__lte=max_amount))
    #         )
    #     else:
    #         vector_filter = cls.build_vector_filter(is_income_stream)
    #         unmapped_query = unmapped_query.filter(**vector_filter)

    #     # ---------------------------------------------------------------------
    #     # 5. Staging & Bank Account Filtering via JournalEntry Pairing Leg
    #     # ---------------------------------------------------------------------
    #     if bank_account_hint:
    #         Account = apps.get_model("ledger", "Account")
    #         clean_hint = str(bank_account_hint).strip()

    #         # Match by ID or account number
    #         acc_query = Q(account_number__icontains=clean_hint) | Q(
    #             name__icontains=clean_hint
    #         )
    #         if clean_hint.isdigit():
    #             acc_query |= Q(id=int(clean_hint))

    #         target_acc_ids = list(
    #             Account.objects.filter(acc_query).values_list("id", flat=True)
    #         )

    #         if target_acc_ids:
    #             # Get row_identifiers where the paired bank leg is in target_acc_ids
    #             paired_row_ids = list(
    #                 JournalEntry.objects.filter(account_id__in=target_acc_ids)
    #                 .exclude(account_id=99)
    #                 .values_list("row_identifier", flat=True)
    #             )
    #             unmapped_query = unmapped_query.filter(
    #                 row_identifier__in=paired_row_ids
    #             )
    #         else:
    #             unmapped_query = unmapped_query.none()

    #     if search_terms:
    #         staging_kw_q = Q()
    #         for term in search_terms:
    #             staging_kw_q |= Q(narration__icontains=term)

    #         matched_row_ids = list(
    #             StatementStagingLine.objects.filter(staging_kw_q).values_list(
    #                 "row_identifier", flat=True
    #             )
    #         )
    #         remarks_q = Q(row_identifier__in=matched_row_ids)
    #         for term in search_terms:
    #             remarks_q |= Q(remarks__icontains=term)
    #         unmapped_query = unmapped_query.filter(remarks_q)

    #     # ---------------------------------------------------------------------
    #     # 6. Fetch Candidates Slice
    #     # ---------------------------------------------------------------------
    #     candidate_entries = list(
    #         unmapped_query.order_by("-transaction_date")[:max_results]
    #     )
    #     candidate_row_ids = [
    #         e.row_identifier for e in candidate_entries if e.row_identifier
    #     ]

    #     # ---------------------------------------------------------------------
    #     # 7. Hydrate SSOT Narrations & Existing Subledger Mappings
    #     # ---------------------------------------------------------------------
    #     staging_narrations_map = (
    #         dict(
    #             StatementStagingLine.objects.filter(
    #                 row_identifier__in=candidate_row_ids
    #             ).values_list("row_identifier", "narration")
    #         )
    #         if candidate_row_ids
    #         else {}
    #     )

    #     all_mappings = (
    #         {
    #             m.row_identifier: m
    #             for m in AssetTransactionMapping.objects.filter(
    #                 row_identifier__in=candidate_row_ids
    #             ).select_related("asset")
    #         }
    #         if candidate_row_ids
    #         else {}
    #     )

    #     # ---------------------------------------------------------------------
    #     # 8. Hydrate Pairing Bank Account Metadata (Name + Last 4)
    #     # ---------------------------------------------------------------------
    #     pairing_legs = (
    #         JournalEntry.objects.filter(row_identifier__in=candidate_row_ids)
    #         .exclude(account_id=99)
    #         .values("row_identifier", "account_id")
    #     )
    #     row_to_bank_id = {p["row_identifier"]: p["account_id"] for p in pairing_legs}

    #     all_bank_ids = set(row_to_bank_id.values())
    #     account_lookup = {}
    #     if all_bank_ids:
    #         for acc in Account.objects.filter(id__in=all_bank_ids):
    #             acc_num = str(getattr(acc, "account_number", "") or "")
    #             last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
    #             account_lookup[acc.id] = {
    #                 "bank_name": getattr(acc, "name", "Bank"),
    #                 "bank_last4": last4,
    #                 "account_id": acc.id,
    #             }

    #     # ---------------------------------------------------------------------
    #     # 9. Assembly
    #     # ---------------------------------------------------------------------
    #     unmapped_candidates = []
    #     target_asset_str = str(asset_id or "")

    #     for entry in candidate_entries:
    #         if (
    #             entry.row_identifier in seen_row_ids
    #             or str(entry.id) in seen_journal_ids
    #         ):
    #             continue

    #         ssot_narration = staging_narrations_map.get(
    #             entry.row_identifier, cls._resolve_remarks(entry.remarks)
    #         )

    #         matched_keywords_found = [
    #             term for term in search_terms if term.lower() in ssot_narration.lower()
    #         ]

    #         is_amount_matched = False
    #         if has_target_amount and min_amount is not None and max_amount is not None:
    #             is_amount_matched = (
    #                 min_amount <= entry.debit <= max_amount
    #                 or min_amount <= entry.credit <= max_amount
    #             )

    #         clean_sub_val = cls.normalize_subcategory(subcategory)
    #         score = cls.calculate_match_score(
    #             has_subcategory=bool(clean_sub_val),
    #             matched_count=len(matched_keywords_found),
    #             is_amount_matched=is_amount_matched,
    #         )

    #         date_offset = (entry.transaction_date - doc_date).days if doc_date else 0
    #         mapping = all_mappings.get(entry.row_identifier)
    #         is_bound = mapping is not None
    #         is_this_asset = is_bound and str(mapping.asset_id) == target_asset_str

    #         mapping_info = None
    #         if is_bound and mapping.asset:
    #             mapping_info = {
    #                 "mapping_id": str(mapping.id),
    #                 "asset_id": str(mapping.asset.id),
    #                 "asset_code": mapping.asset.asset_code,
    #                 "asset_name": mapping.asset.name,
    #             }

    #         # Resolve bank badge info from pairing leg
    #         bank_id = row_to_bank_id.get(entry.row_identifier)
    #         bank_meta = account_lookup.get(bank_id, {})

    #         unmapped_candidates.append(
    #             {
    #                 "journal_id": str(entry.id),
    #                 "row_identifier": entry.row_identifier,
    #                 "account_id": entry.account_id,
    #                 "bank_account_id": bank_id,
    #                 "bank_name": bank_meta.get("bank_name"),
    #                 "bank_last4": bank_meta.get("bank_last4"),
    #                 "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
    #                 "date_offset_days": date_offset,
    #                 "debit": float(entry.debit),
    #                 "credit": float(entry.credit),
    #                 "remarks": ssot_narration,
    #                 "matched_keywords": matched_keywords_found,
    #                 "probability_score": score,
    #                 "is_mapped": is_bound,
    #                 "is_mapped_to_this_asset": is_this_asset,
    #                 "mapping_info": mapping_info,
    #             }
    #         )

    #     return mapped_entries + unmapped_candidates


# working before adding pettyCash logic
# @classmethod
# def find_candidate_rows(
#     cls,
#     document_date=None,
#     target_amount=None,
#     account_id=99,
#     keywords=None,
#     day_window=1825,
#     amount_tolerance_pct=Decimal("0.05"),
#     asset_id=None,
#     to_date=None,
#     subcategory=None,
#     unmapped_only=False,
#     max_results=200,

# ):
#     from django.apps import apps
#     from django.db.models import Q
#     from datetime import date, timedelta
#     from decimal import Decimal

#     JournalEntry = apps.get_model("ledger", "JournalEntry")
#     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
#     AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
#     AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")

#     doc_date = cls.parse_date_safely(document_date)
#     parsed_to_date = cls.parse_date_safely(to_date)

#     # -------------------------------------------------------------------------
#     # 1. Asset Folio Inspection
#     # -------------------------------------------------------------------------
#     asset_obj = None
#     is_income_stream = False
#     if asset_id:
#         try:
#             asset_obj = AssetSubLedger.objects.select_related(
#                 "asset_category", "vendor"
#             ).get(id=asset_id)
#             is_income_stream = cls.inspect_asset_stream(asset_obj)

#             if not subcategory and getattr(asset_obj, "linked_gl_account", None):
#                 subcategory = asset_obj.linked_gl_account
#         except Exception as e:
#             print(f"⚠️ [CANDIDATE MATCHER] Asset inspection failed: {e}")

#     # -------------------------------------------------------------------------
#     # 2. Keywords Resolution
#     # -------------------------------------------------------------------------
#     search_terms = []
#     if keywords:
#         if isinstance(keywords, str):
#             search_terms = [k.strip() for k in keywords.split(",") if k.strip()]
#         elif isinstance(keywords, list):
#             search_terms = [str(k).strip() for k in keywords if str(k).strip()]

#     if not search_terms and asset_obj:
#         search_terms = cls.extract_asset_keywords(asset_obj) or []

#     # -------------------------------------------------------------------------
#     # 3. Target Amount Bounds (Covers Debit & Credit)
#     # -------------------------------------------------------------------------
#     has_target_amount = (
#         target_amount is not None and Decimal(str(target_amount)) > 0
#     )
#     target_amt = Decimal(str(target_amount)) if has_target_amount else None
#     min_amount = (
#         target_amt * (Decimal("1") - amount_tolerance_pct)
#         if has_target_amount
#         else None
#     )
#     max_amount = (
#         target_amt * (Decimal("1") + amount_tolerance_pct)
#         if has_target_amount
#         else None
#     )

#     # =========================================================================
#     # PHASE 1: DIRECT LOOKUP FOR BOUND TRANSACTIONS (THIS ASSET)
#     # =========================================================================
#     mapped_entries = []
#     seen_row_ids = set()
#     seen_journal_ids = set()

#     if asset_id and not unmapped_only:
#         bound_mappings = AssetTransactionMapping.objects.filter(
#             asset_id=asset_id
#         ).exclude(row_identifier__isnull=True)

#         bound_row_ids = list(
#             bound_mappings.values_list("row_identifier", flat=True)
#         )
#         if bound_row_ids:
#             bound_entries = JournalEntry.objects.filter(
#                 row_identifier__in=bound_row_ids
#             )
#             mapping_map = {m.row_identifier: m for m in bound_mappings}

#             # Pre-fetch raw SSOT narrations for bound lines
#             bound_narrations = dict(
#                 StatementStagingLine.objects.filter(
#                     row_identifier__in=bound_row_ids
#                 ).values_list("row_identifier", "narration")
#             )

#             for entry in bound_entries:
#                 m_obj = mapping_map.get(entry.row_identifier)
#                 seen_row_ids.add(entry.row_identifier)
#                 seen_journal_ids.add(str(entry.id))

#                 ssot_narration = bound_narrations.get(
#                     entry.row_identifier, entry.remarks
#                 )

#                 mapped_entries.append(
#                     {
#                         "journal_id": str(entry.id),
#                         "row_identifier": entry.row_identifier,
#                         "account_id": entry.account_id,
#                         "transaction_date": entry.transaction_date.strftime(
#                             "%Y-%m-%d"
#                         ),
#                         "date_offset_days": 0,
#                         "debit": float(entry.debit),
#                         "credit": float(entry.credit),
#                         "remarks": ssot_narration,
#                         "matched_keywords": search_terms,
#                         "probability_score": 100,
#                         "is_mapped": True,
#                         "is_mapped_to_this_asset": True,
#                         "mapping_info": {
#                             "mapping_id": str(m_obj.id) if m_obj else None,
#                             "asset_id": str(asset_id),
#                             "asset_code": (
#                                 getattr(asset_obj, "asset_code", "")
#                                 if asset_obj
#                                 else ""
#                             ),
#                             "asset_name": (
#                                 getattr(asset_obj, "name", "") if asset_obj else ""
#                             ),
#                         },
#                     }
#                 )

#     # =========================================================================
#     # PHASE 2: SEARCH VIA RAW STATEMENT STAGING (SSOT) + JOURNAL ENTRY (STAGE 3)
#     # =========================================================================
#     staging_matched_row_ids = set()

#     # If user searched terms, find all matching row_identifiers from the raw bank statement SSOT
#     if search_terms:
#         staging_kw_q = Q()
#         for term in search_terms:
#             staging_kw_q |= Q(narration__icontains=term)

#         staging_matched_row_ids = set(
#             StatementStagingLine.objects.filter(staging_kw_q).values_list(
#                 "row_identifier", flat=True
#             )
#         )

#     # Query Node 99 Journal entries
#     unmapped_query = JournalEntry.objects.filter(account_id=account_id or 99)

#     # Date filtering
#     if doc_date:
#         start_date = doc_date - timedelta(days=day_window)
#         if parsed_to_date:
#             end_date = parsed_to_date
#         elif day_window >= 1825:
#             end_date = date.today()
#         else:
#             end_date = doc_date + timedelta(days=day_window)

#         unmapped_query = unmapped_query.filter(
#             transaction_date__gte=start_date,
#             transaction_date__lte=end_date,
#         )

#     # Amount filtering (debit or credit)
#     if has_target_amount and min_amount is not None and max_amount is not None:
#         unmapped_query = unmapped_query.filter(
#             (Q(debit__gte=min_amount) & Q(debit__lte=max_amount))
#             | (Q(credit__gte=min_amount) & Q(credit__lte=max_amount))
#         )
#     else:
#         vector_filter = cls.build_vector_filter(is_income_stream)
#         unmapped_query = unmapped_query.filter(**vector_filter)

#     # Subcategory filtering: Only apply if NO explicit keyword search was made
#     clean_sub = cls.normalize_subcategory(subcategory)
#     if clean_sub and not search_terms:
#         unmapped_query = unmapped_query.filter(
#             Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=clean_sub)
#             | Q(evaluation_matrix_snapshot__target_subcategory__iexact=clean_sub)
#             | Q(evaluation_matrix_snapshot__resolved_category__iexact=clean_sub)
#             | Q(
#                 evaluation_matrix_snapshot__resolved_subcategory__iexact="Suspense Account"
#             )
#             | Q(evaluation_matrix_snapshot__isnull=True)
#         )

#     # If keywords were specified, include matches from either StatementStagingLine or JournalEntry.remarks
#     if search_terms:
#         remarks_q = Q(row_identifier__in=staging_matched_row_ids)
#         for term in search_terms:
#             remarks_q |= Q(remarks__icontains=term)
#         unmapped_query = unmapped_query.filter(remarks_q)

#     candidate_entries = list(
#         unmapped_query.order_by("-transaction_date")[:max_results]
#     )
#     candidate_row_ids = [
#         e.row_identifier for e in candidate_entries if e.row_identifier
#     ]

#     # Hydrate the candidate list with the raw narration from StatementStagingLine (SSOT)
#     staging_narrations_map = dict(
#         StatementStagingLine.objects.filter(
#             row_identifier__in=candidate_row_ids
#         ).values_list("row_identifier", "narration")
#     )

#     # Look up cross-asset lock bindings
#     all_mappings = {
#         m.row_identifier: m
#         for m in AssetTransactionMapping.objects.filter(
#             row_identifier__in=candidate_row_ids
#         ).select_related("asset")
#     }

#     unmapped_candidates = []
#     for entry in candidate_entries:
#         if (
#             entry.row_identifier in seen_row_ids
#             or str(entry.id) in seen_journal_ids
#         ):
#             continue

#         # Resolve true narration from SSOT (fallback to remarks)
#         ssot_narration = staging_narrations_map.get(entry.row_identifier)
#         if not ssot_narration:
#             raw_remarks = entry.remarks
#             if isinstance(raw_remarks, dict):
#                 ssot_narration = (
#                     raw_remarks.get("display_text")
#                     or raw_remarks.get("narration")
#                     or ""
#                 )
#             else:
#                 ssot_narration = str(raw_remarks or "")

#         entry_debit = Decimal(str(entry.debit or 0))
#         entry_credit = Decimal(str(entry.credit or 0))

#         matched_keywords_found = [
#             term for term in search_terms if term.lower() in ssot_narration.lower()
#         ]

#         is_amount_matched = False
#         if has_target_amount and min_amount is not None and max_amount is not None:
#             if (min_amount <= entry_debit <= max_amount) or (
#                 min_amount <= entry_credit <= max_amount
#             ):
#                 is_amount_matched = True

#         score = cls.calculate_match_score(
#             has_subcategory=bool(clean_sub),
#             matched_count=len(matched_keywords_found),
#             is_amount_matched=is_amount_matched,
#         )

#         date_offset = (entry.transaction_date - doc_date).days if doc_date else 0
#         mapping = all_mappings.get(entry.row_identifier)
#         is_bound = mapping is not None
#         is_this_asset = is_bound and str(mapping.asset_id) == str(asset_id or "")

#         unmapped_candidates.append(
#             {
#                 "journal_id": str(entry.id),
#                 "row_identifier": entry.row_identifier,
#                 "account_id": entry.account_id,
#                 "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
#                 "date_offset_days": date_offset,
#                 "debit": float(entry.debit),
#                 "credit": float(entry.credit),
#                 "remarks": ssot_narration,
#                 "matched_keywords": matched_keywords_found,
#                 "probability_score": score,
#                 "is_mapped": is_bound,
#                 "is_mapped_to_this_asset": is_this_asset,
#                 "mapping_info": (
#                     {
#                         "mapping_id": str(mapping.id),
#                         "asset_id": str(mapping.asset.id),
#                         "asset_code": mapping.asset.asset_code,
#                         "asset_name": mapping.asset.name,
#                     }
#                     if is_bound
#                     else None
#                 ),
#             }
#         )

#     return mapped_entries + unmapped_candidates
