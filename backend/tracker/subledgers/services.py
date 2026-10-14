import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from decimal import Decimal
from django.db.models import Q
from django.apps import apps

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
    ):
        from django.apps import apps
        from django.db.models import Q
        from datetime import date, timedelta
        from decimal import Decimal

        JournalEntry = apps.get_model("ledger", "JournalEntry")
        StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
        AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
        AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")

        doc_date = cls.parse_date_safely(document_date)
        parsed_to_date = cls.parse_date_safely(to_date)

        # -------------------------------------------------------------------------
        # 1. Asset Folio Inspection
        # -------------------------------------------------------------------------
        asset_obj = None
        is_income_stream = False
        if asset_id:
            try:
                asset_obj = AssetSubLedger.objects.select_related(
                    "asset_category", "vendor"
                ).get(id=asset_id)
                is_income_stream = cls.inspect_asset_stream(asset_obj)

                if not subcategory and getattr(asset_obj, "linked_gl_account", None):
                    subcategory = asset_obj.linked_gl_account
            except Exception as e:
                print(f"⚠️ [CANDIDATE MATCHER] Asset inspection failed: {e}")

        # -------------------------------------------------------------------------
        # 2. Keywords Resolution
        # -------------------------------------------------------------------------
        search_terms = []
        if keywords:
            if isinstance(keywords, str):
                search_terms = [k.strip() for k in keywords.split(",") if k.strip()]
            elif isinstance(keywords, list):
                search_terms = [str(k).strip() for k in keywords if str(k).strip()]

        if not search_terms and asset_obj:
            search_terms = cls.extract_asset_keywords(asset_obj) or []

        # -------------------------------------------------------------------------
        # 3. Target Amount Bounds (Covers Debit & Credit)
        # -------------------------------------------------------------------------
        has_target_amount = (
            target_amount is not None and Decimal(str(target_amount)) > 0
        )
        target_amt = Decimal(str(target_amount)) if has_target_amount else None
        min_amount = (
            target_amt * (Decimal("1") - amount_tolerance_pct)
            if has_target_amount
            else None
        )
        max_amount = (
            target_amt * (Decimal("1") + amount_tolerance_pct)
            if has_target_amount
            else None
        )

        # =========================================================================
        # PHASE 1: DIRECT LOOKUP FOR BOUND TRANSACTIONS (THIS ASSET)
        # =========================================================================
        mapped_entries = []
        seen_row_ids = set()
        seen_journal_ids = set()

        if asset_id and not unmapped_only:
            bound_mappings = AssetTransactionMapping.objects.filter(
                asset_id=asset_id
            ).exclude(row_identifier__isnull=True)

            bound_row_ids = list(
                bound_mappings.values_list("row_identifier", flat=True)
            )
            if bound_row_ids:
                bound_entries = JournalEntry.objects.filter(
                    row_identifier__in=bound_row_ids
                )
                mapping_map = {m.row_identifier: m for m in bound_mappings}

                # Pre-fetch raw SSOT narrations for bound lines
                bound_narrations = dict(
                    StatementStagingLine.objects.filter(
                        row_identifier__in=bound_row_ids
                    ).values_list("row_identifier", "narration")
                )

                for entry in bound_entries:
                    m_obj = mapping_map.get(entry.row_identifier)
                    seen_row_ids.add(entry.row_identifier)
                    seen_journal_ids.add(str(entry.id))

                    ssot_narration = bound_narrations.get(
                        entry.row_identifier, entry.remarks
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
                                "mapping_id": str(m_obj.id) if m_obj else None,
                                "asset_id": str(asset_id),
                                "asset_code": (
                                    getattr(asset_obj, "asset_code", "")
                                    if asset_obj
                                    else ""
                                ),
                                "asset_name": (
                                    getattr(asset_obj, "name", "") if asset_obj else ""
                                ),
                            },
                        }
                    )

        # =========================================================================
        # PHASE 2: SEARCH VIA RAW STATEMENT STAGING (SSOT) + JOURNAL ENTRY (STAGE 3)
        # =========================================================================
        staging_matched_row_ids = set()

        # If user searched terms, find all matching row_identifiers from the raw bank statement SSOT
        if search_terms:
            staging_kw_q = Q()
            for term in search_terms:
                staging_kw_q |= Q(narration__icontains=term)

            staging_matched_row_ids = set(
                StatementStagingLine.objects.filter(staging_kw_q).values_list(
                    "row_identifier", flat=True
                )
            )

        # Query Node 99 Journal entries
        unmapped_query = JournalEntry.objects.filter(account_id=account_id or 99)

        # Date filtering
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

        # Amount filtering (debit or credit)
        if has_target_amount and min_amount is not None and max_amount is not None:
            unmapped_query = unmapped_query.filter(
                (Q(debit__gte=min_amount) & Q(debit__lte=max_amount))
                | (Q(credit__gte=min_amount) & Q(credit__lte=max_amount))
            )
        else:
            vector_filter = cls.build_vector_filter(is_income_stream)
            unmapped_query = unmapped_query.filter(**vector_filter)

        # Subcategory filtering: Only apply if NO explicit keyword search was made
        clean_sub = cls.normalize_subcategory(subcategory)
        if clean_sub and not search_terms:
            unmapped_query = unmapped_query.filter(
                Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=clean_sub)
                | Q(evaluation_matrix_snapshot__target_subcategory__iexact=clean_sub)
                | Q(evaluation_matrix_snapshot__resolved_category__iexact=clean_sub)
                | Q(
                    evaluation_matrix_snapshot__resolved_subcategory__iexact="Suspense Account"
                )
                | Q(evaluation_matrix_snapshot__isnull=True)
            )

        # If keywords were specified, include matches from either StatementStagingLine or JournalEntry.remarks
        if search_terms:
            remarks_q = Q(row_identifier__in=staging_matched_row_ids)
            for term in search_terms:
                remarks_q |= Q(remarks__icontains=term)
            unmapped_query = unmapped_query.filter(remarks_q)

        candidate_entries = list(
            unmapped_query.order_by("-transaction_date")[:max_results]
        )
        candidate_row_ids = [
            e.row_identifier for e in candidate_entries if e.row_identifier
        ]

        # Hydrate the candidate list with the raw narration from StatementStagingLine (SSOT)
        staging_narrations_map = dict(
            StatementStagingLine.objects.filter(
                row_identifier__in=candidate_row_ids
            ).values_list("row_identifier", "narration")
        )

        # Look up cross-asset lock bindings
        all_mappings = {
            m.row_identifier: m
            for m in AssetTransactionMapping.objects.filter(
                row_identifier__in=candidate_row_ids
            ).select_related("asset")
        }

        unmapped_candidates = []
        for entry in candidate_entries:
            if (
                entry.row_identifier in seen_row_ids
                or str(entry.id) in seen_journal_ids
            ):
                continue

            # Resolve true narration from SSOT (fallback to remarks)
            ssot_narration = staging_narrations_map.get(entry.row_identifier)
            if not ssot_narration:
                raw_remarks = entry.remarks
                if isinstance(raw_remarks, dict):
                    ssot_narration = (
                        raw_remarks.get("display_text")
                        or raw_remarks.get("narration")
                        or ""
                    )
                else:
                    ssot_narration = str(raw_remarks or "")

            entry_debit = Decimal(str(entry.debit or 0))
            entry_credit = Decimal(str(entry.credit or 0))

            matched_keywords_found = [
                term for term in search_terms if term.lower() in ssot_narration.lower()
            ]

            is_amount_matched = False
            if has_target_amount and min_amount is not None and max_amount is not None:
                if (min_amount <= entry_debit <= max_amount) or (
                    min_amount <= entry_credit <= max_amount
                ):
                    is_amount_matched = True

            score = cls.calculate_match_score(
                has_subcategory=bool(clean_sub),
                matched_count=len(matched_keywords_found),
                is_amount_matched=is_amount_matched,
            )

            date_offset = (entry.transaction_date - doc_date).days if doc_date else 0
            mapping = all_mappings.get(entry.row_identifier)
            is_bound = mapping is not None
            is_this_asset = is_bound and str(mapping.asset_id) == str(asset_id or "")

            unmapped_candidates.append(
                {
                    "journal_id": str(entry.id),
                    "row_identifier": entry.row_identifier,
                    "account_id": entry.account_id,
                    "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
                    "date_offset_days": date_offset,
                    "debit": float(entry.debit),
                    "credit": float(entry.credit),
                    "remarks": ssot_narration,
                    "matched_keywords": matched_keywords_found,
                    "probability_score": score,
                    "is_mapped": is_bound,
                    "is_mapped_to_this_asset": is_this_asset,
                    "mapping_info": (
                        {
                            "mapping_id": str(mapping.id),
                            "asset_id": str(mapping.asset.id),
                            "asset_code": mapping.asset.asset_code,
                            "asset_name": mapping.asset.name,
                        }
                        if is_bound
                        else None
                    ),
                }
            )

        return mapped_entries + unmapped_candidates
