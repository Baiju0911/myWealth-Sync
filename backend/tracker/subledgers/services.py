from datetime import timedelta
from decimal import Decimal
from django.db import models

from tracker.models import JournalEntry  # Lazy import
from tracker.models.subledger import AssetTransactionMapping


class AssetCandidateMatcher:
    """
    Implements sliding window candidate matching (±5 to ±10 days)
    for binding bank/journal entries to asset sub-ledgers.
    """

    @staticmethod
    def find_candidate_rows(
        document_date,
        target_amount=None,
        account_id=None,
        keywords=None,
        day_window=10,
        amount_tolerance_pct=Decimal("0.05"),
        asset_id=None,  # 👈 Make sure this receives the asset PK/UUID
    ):
        from tracker.models import JournalEntry
        from tracker.models.subledger import AssetTransactionMapping

        mapped_entries = []

        # =========================================================================
        # PHASE 1: DIRECT LOOKUP BY ROW_IDENTIFIER FOR BOUND DATA (PRIORITY)
        # =========================================================================
        if asset_id:
            # 1. Pull bound row_identifiers from mapping table for THIS asset
            bound_mappings = AssetTransactionMapping.objects.filter(
                asset_id=asset_id
            ).exclude(row_identifier__isnull=True)

            bound_row_ids = list(
                bound_mappings.values_list("row_identifier", flat=True)
            )

            if bound_row_ids:
                # 2. Fetch corresponding staging journal entries DIRECTLY by row_identifier
                #    (Completely bypasses document_date, target_amount, and keywords!)
                bound_staging_entries = JournalEntry.objects.filter(
                    row_identifier__in=bound_row_ids, account_id=99
                )

                mapping_map = {m.row_identifier: m for m in bound_mappings}

                for entry in bound_staging_entries:
                    m_obj = mapping_map.get(entry.row_identifier)
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
                            "remarks": entry.remarks,
                            "probability_score": 100,  # Bound entries get 100% score
                            "is_mapped": True,
                            "is_mapped_to_this_asset": True,
                            "mapping_info": {
                                "mapping_id": str(m_obj.id) if m_obj else None,
                                "asset_id": asset_id,
                            },
                        }
                    )

        # =========================================================================
        # PHASE 2: SEARCH UNMAPPED POOL WITH USER FILTERS (DATE, AMOUNT, KEYWORDS)
        # =========================================================================
        start_date = document_date - timedelta(days=day_window)
        end_date = document_date + timedelta(days=day_window)

        # Get all mapped row_identifiers across the whole system to exclude them
        all_mapped_row_ids = AssetTransactionMapping.objects.exclude(
            row_identifier__isnull=True
        ).values_list("row_identifier", flat=True)

        unmapped_query = JournalEntry.objects.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date,
            account_id=99,
            debit__gt=0,
        ).exclude(row_identifier__in=all_mapped_row_ids)

        # Apply amount and keyword filters ONLY to unmapped rows
        has_target_amount = (
            target_amount is not None and Decimal(str(target_amount)) > 0
        )
        if has_target_amount:
            target_amt = Decimal(str(target_amount))
            min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
            max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)
            unmapped_query = unmapped_query.filter(
                debit__range=(min_amount, max_amount)
            )
        elif keywords and len(keywords) > 0 and any(kw.strip() for kw in keywords):
            keyword_q = models.Q()
            for kw in keywords:
                if kw and kw.strip():
                    keyword_q |= models.Q(remarks__icontains=kw.strip())
            unmapped_query = unmapped_query.filter(keyword_q)

        # Exclude internal self-transfers
        exclude_self_transfer_keywords = ["TFR", "TRANSFER", "SELF", "INTRA"]
        for self_kw in exclude_self_transfer_keywords:
            unmapped_query = unmapped_query.exclude(remarks__icontains=self_kw)

        unmapped_candidates = []
        for entry in unmapped_query:
            score = 20
            date_diff = abs((entry.transaction_date - document_date).days)
            if date_diff == 0:
                score += 30
            elif date_diff <= 3:
                score += 20
            elif date_diff <= 7:
                score += 15

            raw_remarks = str(entry.remarks or "").upper()
            if keywords:
                matched_count = sum(
                    1 for kw in keywords if kw and kw.strip().upper() in raw_remarks
                )
                if matched_count > 0:
                    score += min(20 + (matched_count * 5), 30)

            unmapped_candidates.append(
                {
                    "journal_id": str(entry.id),
                    "row_identifier": entry.row_identifier,
                    "account_id": entry.account_id,
                    "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
                    "date_offset_days": (entry.transaction_date - document_date).days,
                    "debit": float(entry.debit),
                    "credit": float(entry.credit),
                    "remarks": entry.remarks,
                    "probability_score": min(score, 100),
                    "is_mapped": False,
                    "is_mapped_to_this_asset": False,
                    "mapping_info": None,
                }
            )

        sorted_unmapped = sorted(
            unmapped_candidates,
            key=lambda x: (x["transaction_date"], x["probability_score"]),
            reverse=True,
        )

        # =========================================================================
        # PHASE 3: COMBINE (BOUND DATA ALWAYS ON TOP)
        # =========================================================================
        return mapped_entries + sorted_unmapped

    # @staticmethod
    # def find_candidate_rows(
    #     document_date,
    #     target_amount=None,
    #     account_id=None,
    #     keywords=None,
    #     day_window=10,
    #     amount_tolerance_pct=Decimal("0.05"),
    #     asset_id=None,
    # ):
    #     from tracker.models import JournalEntry
    #     from tracker.models.subledger import AssetTransactionMapping

    #     # ------------------------------------------------------------------
    #     # STEP 1: ALWAYS FETCH ALREADY-BOUND ROWS FOR THIS ASSET (BY UUID)
    #     # ------------------------------------------------------------------
    #     mapped_entries = []
    #     already_mapped_lookup = {}

    #     # Fetch all mappings across all assets to know ownership
    #     all_mappings = AssetTransactionMapping.objects.exclude(
    #         row_identifier__isnull=True
    #     ).select_related("asset")

    #     for m in all_mappings:
    #         already_mapped_lookup[m.row_identifier] = {
    #             "mapping_id": str(m.id),
    #             "asset_id": m.asset_id,
    #             "asset_code": m.asset.asset_code if m.asset else None,
    #             "asset_name": m.asset.name if m.asset else None,
    #         }

    #     # If an asset_id is provided, pull its staging rows directly via UUIDs
    #     if asset_id:
    #         bound_row_ids = [
    #             m.row_identifier for m in all_mappings if m.asset_id == int(asset_id)
    #         ]

    #         # DIRECT LOOKUP IN STAGING BY UUID (Ignores date & keyword filters!)
    #         bound_staging_entries = JournalEntry.objects.filter(
    #             row_identifier__in=bound_row_ids, account_id=99
    #         )

    #         for entry in bound_staging_entries:
    #             mapping_info = already_mapped_lookup.get(entry.row_identifier)
    #             mapped_entries.append(
    #                 {
    #                     "journal_id": str(entry.id),
    #                     "row_identifier": entry.row_identifier,
    #                     "account_id": entry.account_id,
    #                     "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
    #                     "date_offset_days": 0,
    #                     "debit": float(entry.debit),
    #                     "credit": float(entry.credit),
    #                     "remarks": entry.remarks,
    #                     "probability_score": 100,  # 100% since it's already bound
    #                     "is_mapped": True,
    #                     "is_mapped_to_this_asset": True,
    #                     "mapping_info": mapping_info,
    #                 }
    #             )

    #     # ------------------------------------------------------------------
    #     # STEP 2: SEARCH FOR NEW UNMAPPED CANDIDATES (USES DATE & KEYWORDS)
    #     # ------------------------------------------------------------------
    #     start_date = document_date - timedelta(days=day_window)
    #     end_date = document_date + timedelta(days=day_window)

    #     # Exclude rows already mapped anywhere
    #     unmapped_query = JournalEntry.objects.filter(
    #         transaction_date__gte=start_date,
    #         transaction_date__lte=end_date,
    #         account_id=99,
    #         debit__gt=0,
    #     ).exclude(row_identifier__in=already_mapped_lookup.keys())

    #     # Apply amount / keyword filters to unmapped pool only
    #     has_target_amount = (
    #         target_amount is not None and Decimal(str(target_amount)) > 0
    #     )
    #     if has_target_amount:
    #         target_amt = Decimal(str(target_amount))
    #         min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
    #         max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)
    #         unmapped_query = unmapped_query.filter(
    #             debit__range=(min_amount, max_amount)
    #         )
    #     elif keywords and len(keywords) > 0 and any(kw.strip() for kw in keywords):
    #         keyword_q = models.Q()
    #         for kw in keywords:
    #             if kw and kw.strip():
    #                 keyword_q |= models.Q(remarks__icontains=kw.strip())
    #         unmapped_query = unmapped_query.filter(keyword_q)

    #     # Exclude self-transfers
    #     exclude_self_transfer_keywords = ["TFR", "TRANSFER", "SELF", "INTRA"]
    #     for self_kw in exclude_self_transfer_keywords:
    #         unmapped_query = unmapped_query.exclude(remarks__icontains=self_kw)

    #     unmapped_candidates = []
    #     for entry in unmapped_query:
    #         score = 20
    #         date_diff = abs((entry.transaction_date - document_date).days)
    #         if date_diff == 0:
    #             score += 30
    #         elif date_diff <= 3:
    #             score += 20
    #         elif date_diff <= 7:
    #             score += 15

    #         raw_remarks = str(entry.remarks or "").upper()
    #         if keywords:
    #             matched_count = sum(
    #                 1 for kw in keywords if kw and kw.strip().upper() in raw_remarks
    #             )
    #             if matched_count > 0:
    #                 score += min(20 + (matched_count * 5), 30)

    #         unmapped_candidates.append(
    #             {
    #                 "journal_id": str(entry.id),
    #                 "row_identifier": entry.row_identifier,
    #                 "account_id": entry.account_id,
    #                 "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
    #                 "date_offset_days": (entry.transaction_date - document_date).days,
    #                 "debit": float(entry.debit),
    #                 "credit": float(entry.credit),
    #                 "remarks": entry.remarks,
    #                 "probability_score": min(score, 100),
    #                 "is_mapped": False,
    #                 "is_mapped_to_this_asset": False,
    #                 "mapping_info": None,
    #             }
    #         )

    #     # ------------------------------------------------------------------
    #     # STEP 3: COMBINE (BOUND ROWS FIRST, THEN SORTED UNMAPPED CANDIDATES)
    #     # ------------------------------------------------------------------
    #     sorted_unmapped = sorted(
    #         unmapped_candidates,
    #         key=lambda x: (x["transaction_date"], x["probability_score"]),
    #         reverse=True,
    #     )

    #     # Mapped rows always stay at top
    #     return mapped_entries + sorted_unmapped

    # @staticmethod
    # def find_candidate_rows(
    #     document_date,
    #     target_amount=None,
    #     account_id=None,
    #     keywords=None,
    #     day_window=10,
    #     amount_tolerance_pct=Decimal("0.05"),
    #     asset_id=None,  # 👈 Pass current asset_id if available
    # ):
    #     from tracker.models import JournalEntry
    #     from tracker.models.subledger import AssetTransactionMapping

    #     start_date = document_date - timedelta(days=day_window)
    #     end_date = document_date + timedelta(days=day_window)

    #     # 1. Base query for Node 99 debits
    #     query = JournalEntry.objects.filter(
    #         transaction_date__gte=start_date,
    #         transaction_date__lte=end_date,
    #         account_id=99,
    #         debit__gt=0,
    #     )

    #     # 2. Get map of ALL currently bound rows & which asset owns them
    #     mappings = AssetTransactionMapping.objects.exclude(
    #         row_identifier__isnull=True
    #     ).select_related("asset")

    #     mapped_lookup = {
    #         m.row_identifier: {
    #             "mapping_id": str(m.id),
    #             "asset_id": m.asset_id,
    #             "asset_code": m.asset.asset_code if m.asset else None,
    #             "asset_name": m.asset.name if m.asset else None,
    #         }
    #         for m in mappings
    #     }

    #     # 3. Apply Amount / Keyword Filters
    #     has_target_amount = (
    #         target_amount is not None and Decimal(str(target_amount)) > 0
    #     )
    #     if has_target_amount:
    #         target_amt = Decimal(str(target_amount))
    #         min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
    #         max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)
    #         query = query.filter(debit__range=(min_amount, max_amount))
    #     elif keywords and len(keywords) > 0 and any(kw.strip() for kw in keywords):
    #         keyword_q = models.Q()
    #         for kw in keywords:
    #             if kw and kw.strip():
    #                 keyword_q |= models.Q(remarks__icontains=kw.strip())
    #         query = query.filter(keyword_q)

    #     # 4. Exclude self-transfers
    #     exclude_self_transfer_keywords = ["TFR", "TRANSFER", "SELF", "INTRA"]
    #     for self_kw in exclude_self_transfer_keywords:
    #         query = query.exclude(remarks__icontains=self_kw)

    #     candidates = []

    #     # 5. Process entries and attach mapping metadata
    #     for entry in query:
    #         row_id = entry.row_identifier
    #         mapping_info = mapped_lookup.get(row_id)

    #         # Determine binding state
    #         is_mapped = mapping_info is not None
    #         is_mapped_to_this_asset = is_mapped and (
    #             asset_id is not None and mapping_info["asset_id"] == int(asset_id)
    #         )

    #         # Score calculation
    #         score = 0
    #         entry_val = entry.debit

    #         if has_target_amount:
    #             target_amt = Decimal(str(target_amount))
    #             if entry_val == target_amt:
    #                 score += 50
    #             elif abs(entry_val - target_amt) <= (target_amt * Decimal("0.02")):
    #                 score += 40
    #             else:
    #                 score += 25
    #         else:
    #             score += 20

    #         date_diff = abs((entry.transaction_date - document_date).days)
    #         if date_diff == 0:
    #             score += 30
    #         elif date_diff <= 3:
    #             score += 20
    #         elif date_diff <= 7:
    #             score += 15
    #         else:
    #             score += 10

    #         raw_remarks = str(entry.remarks or "").upper()
    #         if keywords and len(keywords) > 0:
    #             matched_count = sum(
    #                 1 for kw in keywords if kw and kw.strip().upper() in raw_remarks
    #             )
    #             if matched_count > 0:
    #                 score += min(20 + (matched_count * 5), 30)

    #         candidate_data = {
    #             "journal_id": str(entry.id),
    #             "row_identifier": row_id,
    #             "account_id": entry.account_id,
    #             "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
    #             "date_offset_days": (entry.transaction_date - document_date).days,
    #             "debit": float(entry.debit),
    #             "credit": float(entry.credit),
    #             "remarks": entry.remarks,
    #             "probability_score": min(score, 100),
    #             # 🎯 Binding Flags for Frontend UI
    #             "is_mapped": is_mapped,
    #             "is_mapped_to_this_asset": is_mapped_to_this_asset,
    #             "mapping_info": mapping_info,  # Contains mapping_id, asset_id, asset_name if bound
    #         }

    #         candidates.append(candidate_data)

    #     sorted_candidates = sorted(
    #         candidates,
    #         key=lambda x: (
    #             x["is_mapped_to_this_asset"],
    #             x["transaction_date"],
    #             x["probability_score"],
    #         ),
    #         reverse=True,
    #     )

    #     return sorted_candidates

    # @staticmethod
    # def find_candidate_rows(
    #     document_date,
    #     target_amount=None,
    #     account_id=None,
    #     keywords=None,
    #     day_window=10,
    #     amount_tolerance_pct=Decimal("0.05"),
    # ):
    #     from tracker.models import JournalEntry
    #     from tracker.models.subledger import AssetTransactionMapping

    #     print("\n--------------------------------------------------")
    #     print("🔍 [MATCHER SERVICE] RUNNING CLEANED OUTFLOW MATCHER")
    #     print(f"• Document Date : {document_date} ({type(document_date)})")
    #     print(f"• Target Amount : {target_amount} ({type(target_amount)})")
    #     print(f"• Account ID    : 99 (Node 99 Target)")
    #     print(f"• Keywords      : {keywords}")
    #     print(f"• Day Window    : ±{day_window} days")
    #     print("--------------------------------------------------")

    #     # 1. Date window boundaries (±N days)
    #     start_date = document_date - timedelta(days=day_window)
    #     end_date = document_date + timedelta(days=day_window)

    #     # 🎯 TARGET NODE 99: Outflows only (debit > 0)
    #     query = JournalEntry.objects.filter(
    #         transaction_date__gte=start_date,
    #         transaction_date__lte=end_date,
    #         account_id=99,
    #         debit__gt=0,
    #     )

    #     # 2. Exclude transactions already mapped to an asset
    #     already_mapped_rows = AssetTransactionMapping.objects.exclude(
    #         row_identifier__isnull=True
    #     ).values_list("row_identifier", flat=True)

    #     query = query.exclude(row_identifier__in=already_mapped_rows)

    #     # 3. Optional Amount filtering / Keyword Pre-Filtering + Self-Transfer Exclusion
    #     has_target_amount = (
    #         target_amount is not None and Decimal(str(target_amount)) > 0
    #     )
    #     if has_target_amount:
    #         target_amt = Decimal(str(target_amount))
    #         min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
    #         max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

    #         query = query.filter(debit__range=(min_amount, max_amount))
    #         print(f"🎯 Filtered by Amount Range: ₹{min_amount} - ₹{max_amount}")
    #     elif keywords and len(keywords) > 0 and any(kw.strip() for kw in keywords):
    #         keyword_q = models.Q()
    #         for kw in keywords:
    #             if kw and kw.strip():
    #                 keyword_q |= models.Q(remarks__icontains=kw.strip())
    #         query = query.filter(keyword_q)
    #         print(f"🎯 SQL Pre-Filtered by Keywords: {keywords}")
    #     else:
    #         print(
    #             "🎯 No active keywords provided; querying all unmapped outflows in date window."
    #         )

    #     # 🎯 4. Exclude self-transfers and internal account movements based on narration keywords
    #     exclude_self_transfer_keywords = ["TFR", "TRANSFER", "SELF", "INTRA"]
    #     for self_kw in exclude_self_transfer_keywords:
    #         query = query.exclude(remarks__icontains=self_kw)

    #     print(
    #         f"📊 [MATCHER SERVICE] Cleaned Query Returned: {query.count()} row(s) after excluding self-transfers & credits."
    #     )

    #     candidates = []

    #     # 5. Score calculation loop
    #     for entry in query:
    #         score = 0
    #         entry_val = entry.debit

    #         # Score based on Amount accuracy
    #         if has_target_amount:
    #             target_amt = Decimal(str(target_amount))
    #             if entry_val == target_amt:
    #                 score += 50
    #             elif abs(entry_val - target_amt) <= (target_amt * Decimal("0.02")):
    #                 score += 40
    #             else:
    #                 score += 25
    #         else:
    #             score += 20

    #         # Score based on Date proximity
    #         date_diff = abs((entry.transaction_date - document_date).days)
    #         if date_diff == 0:
    #             score += 30
    #         elif date_diff <= 3:
    #             score += 20
    #         elif date_diff <= 7:
    #             score += 15
    #         else:
    #             score += 10

    #         # Score based on Keyword matches
    #         raw_remarks = str(entry.remarks or "").upper()
    #         if keywords and len(keywords) > 0:
    #             matched_count = 0
    #             for kw in keywords:
    #                 if kw and kw.strip().upper() in raw_remarks:
    #                     matched_count += 1

    #             if matched_count > 0:
    #                 score += min(20 + (matched_count * 5), 30)

    #         candidate_data = {
    #             "journal_id": str(entry.id),
    #             "row_identifier": entry.row_identifier,
    #             "account_id": entry.account_id,
    #             "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
    #             "date_offset_days": (entry.transaction_date - document_date).days,
    #             "debit": float(entry.debit),
    #             "credit": float(entry.credit),
    #             "remarks": entry.remarks,
    #             "probability_score": min(score, 100),
    #         }

    #         print(
    #             f"   ➔ Row ID: {entry.row_identifier[:10]}... | Date: {candidate_data['transaction_date']} "
    #             f"| Debit: ₹{entry_val} | Score: {candidate_data['probability_score']}%"
    #         )

    #         candidates.append(candidate_data)

    #     sorted_candidates = sorted(
    #         candidates,
    #         key=lambda x: (x["transaction_date"], x["probability_score"]),
    #         reverse=False,
    #     )

    #     print("\n📋 [MATCHER SERVICE] FINAL SORTED CANDIDATES RETURNED:")
    #     print(f"Total Clean Candidates Returned: {len(sorted_candidates)}")
    #     print("--------------------------------------------------\n")

    #     return sorted_candidates

    # @staticmethod
    # def find_candidate_rows(
    #     document_date,
    #     target_amount=None,
    #     account_id=None,
    #     keywords=None,
    #     day_window=10,
    #     amount_tolerance_pct=Decimal("0.05"),  # Default 5% tolerance
    # ):
    #     from tracker.models import JournalEntry  # Lazy import
    #     from tracker.models.subledger import (
    #         AssetTransactionMapping,
    #     )  # Corrected subledger path

    #     print("\n--------------------------------------------------")
    #     print("🔍 [MATCHER SERVICE] RUNNING CANDIDATE MATCHER")
    #     print(f"• Document Date : {document_date} ({type(document_date)})")
    #     print(f"• Target Amount : {target_amount} ({type(target_amount)})")
    #     print(f"• Account ID    : {account_id}")
    #     print(f"• Keywords      : {keywords}")
    #     print(f"• Day Window    : ±{day_window} days")
    #     print("--------------------------------------------------")

    #     # 1. Date window boundaries
    #     start_date = document_date - timedelta(days=day_window)
    #     end_date = document_date + timedelta(days=day_window)

    #     query = JournalEntry.objects.filter(
    #         transaction_date__gte=start_date,
    #         transaction_date__lte=end_date,
    #     )

    #     # 2. Filter by specific account if passed
    #     if account_id:
    #         query = query.filter(account_id=account_id)

    #     # 3. Exclude transactions already mapped to an asset
    #     already_mapped_rows = AssetTransactionMapping.objects.exclude(
    #         row_identifier__isnull=True
    #     ).values_list("row_identifier", flat=True)

    #     query = query.exclude(row_identifier__in=already_mapped_rows)

    #     # 4. Optional Amount filtering
    #     has_target_amount = (
    #         target_amount is not None and Decimal(str(target_amount)) > 0
    #     )
    #     if has_target_amount:
    #         target_amt = Decimal(str(target_amount))
    #         min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
    #         max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

    #         query = query.filter(
    #             models.Q(debit__range=(min_amount, max_amount))
    #             | models.Q(credit__range=(min_amount, max_amount))
    #         )

    #     print(f"📊 [MATCHER SERVICE] DB Filter Returned: {query.count()} row(s)")

    #     candidates = []

    #     # 5. Score calculation loop
    #     for entry in query:
    #         score = 0
    #         entry_val = entry.debit if entry.debit > 0 else entry.credit

    #         # Score based on Amount accuracy
    #         if has_target_amount:
    #             target_amt = Decimal(str(target_amount))
    #             if entry_val == target_amt:
    #                 score += 50
    #             elif abs(entry_val - target_amt) <= (target_amt * Decimal("0.02")):
    #                 score += 40  # Within 2% difference
    #             else:
    #                 score += 25
    #         else:
    #             score += 20  # Base score when searching without amount target

    #         # Score based on Date proximity
    #         date_diff = abs((entry.transaction_date - document_date).days)
    #         if date_diff == 0:
    #             score += 30
    #         elif date_diff <= 3:
    #             score += 20
    #         elif date_diff <= 7:
    #             score += 15
    #         else:
    #             score += 10

    #         # Score based on Keyword matches
    #         raw_remarks = str(entry.remarks or "").upper()
    #         if keywords:
    #             matched_count = 0
    #             for kw in keywords:
    #                 if kw and kw.strip().upper() in raw_remarks:
    #                     matched_count += 1

    #             if matched_count > 0:
    #                 score += min(20 + (matched_count * 5), 30)

    #         candidate_data = {
    #             "journal_id": str(entry.id),
    #             "row_identifier": entry.row_identifier,
    #             "account_id": entry.account_id,
    #             "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
    #             "date_offset_days": (entry.transaction_date - document_date).days,
    #             "debit": float(entry.debit),
    #             "credit": float(entry.credit),
    #             "remarks": entry.remarks,
    #             "probability_score": min(score, 100),
    #         }

    #         print(
    #             f"   ➔ Row ID: {entry.row_identifier} | Date: {candidate_data['transaction_date']} "
    #             f"| Amount: ₹{entry_val} | Score: {candidate_data['probability_score']}%"
    #         )

    #         candidates.append(candidate_data)

    #     sorted_candidates = sorted(
    #         candidates, key=lambda x: x["probability_score"], reverse=True
    #     )

    #     print("\n📋 [MATCHER SERVICE] FINAL SORTED CANDIDATES RETURNED:")
    #     print(f"{sorted_candidates}")
    #     print("--------------------------------------------------\n")

    #     return sorted_candidates
