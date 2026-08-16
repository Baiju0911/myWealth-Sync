from datetime import date, datetime, timedelta
from decimal import Decimal
from django.db import models

import json
import re


class AssetCandidateMatcher:

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Extracts narration/payee from dict/JSON string if needed,
        then strips all non-alphanumeric characters and converts to UPPERCASE.
        """
        if not text:
            return ""

        if isinstance(text, dict):
            text = f"{text.get('narration', '')} {text.get('payee', '')}"
        elif isinstance(text, str) and text.strip().startswith("{"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    text = f"{data.get('narration', '')} {data.get('payee', '')}"
            except Exception:
                pass

        return re.sub(r"[^A-Za-z0-9]", "", str(text)).upper()

    @staticmethod
    def tokenize_text(text: str) -> set:
        """
        Splits text into clean, individual alphanumeric uppercase words/tokens.
        Useful for precise word-boundary matching.
        """
        if not text:
            return set()

        if isinstance(text, dict):
            text = f"{text.get('narration', '')} {text.get('payee', '')}"
        elif isinstance(text, str) and text.strip().startswith("{"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    text = f"{data.get('narration', '')} {data.get('payee', '')}"
            except Exception:
                pass

        tokens = re.findall(r"[A-Za-z0-9]+", str(text).upper())
        return set(tokens)

    @staticmethod
    def find_candidate_rows(
        document_date,
        target_amount=None,
        account_id=None,
        keywords=None,
        day_window=30,
        amount_tolerance_pct=Decimal("0.05"),
        asset_id=None,
        to_date=None,
    ):
        from tracker.models import JournalEntry
        from tracker.models.subledger import AssetSubLedger, AssetTransactionMapping

        # 🎯 Normalize document_date safely to a datetime.date instance
        if isinstance(document_date, str):
            try:
                doc_date = datetime.strptime(document_date, "%Y-%m-%d").date()
            except ValueError:
                doc_date = date.today()
        elif isinstance(document_date, datetime):
            doc_date = document_date.date()
        elif isinstance(document_date, date):
            doc_date = document_date
        else:
            doc_date = date.today()

        if isinstance(to_date, str):
            try:
                parsed_to_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            except ValueError:
                parsed_to_date = None
        elif isinstance(to_date, datetime):
            parsed_to_date = to_date.date()
        elif isinstance(to_date, date):
            parsed_to_date = to_date
        else:
            parsed_to_date = None

        # 🎯 AUTO-KEYWORD INHERITANCE FROM LINKED VENDOR
        if asset_id and not keywords:
            try:
                asset_obj = AssetSubLedger.objects.select_related("vendor").get(
                    id=asset_id
                )
                if asset_obj.vendor:
                    if asset_obj.vendor.default_keywords:
                        keywords = asset_obj.vendor.default_keywords
                    elif asset_obj.vendor.name:
                        keywords = [asset_obj.vendor.name]
            except Exception as e:
                print(f"⚠️ [CANDIDATE MATCHER] Failed to inherit vendor keywords: {e}")

        print("\n==================================================")
        print(f"🔍 [DEBUG CANDIDATES] STARTING MATCH FOR ASSET: {asset_id}")
        print(
            f"📥 Keywords: {keywords} | Target Amount: {target_amount} | Horizon Days: {day_window}"
        )
        print("==================================================")

        mapped_entries = []
        seen_row_ids = set()
        seen_journal_ids = set()

        # =========================================================================
        # PHASE 1: DIRECT LOOKUP FOR BOUND DATA (EXCLUDE ZERO-DEBIT COUNTERPARTS)
        # =========================================================================
        if asset_id:
            bound_mappings = AssetTransactionMapping.objects.filter(
                asset_id=asset_id
            ).exclude(row_identifier__isnull=True)

            bound_row_ids = list(
                bound_mappings.values_list("row_identifier", flat=True)
            )

            if bound_row_ids:
                bound_staging_entries = JournalEntry.objects.filter(
                    row_identifier__in=bound_row_ids, debit__gt=0
                )
                mapping_map = {m.row_identifier: m for m in bound_mappings}

                print("\n--- PHASE 1 BOUND ROWS PRINT ---")
                for idx, entry in enumerate(bound_staging_entries, 1):
                    m_obj = mapping_map.get(entry.row_identifier)

                    seen_row_ids.add(entry.row_identifier)
                    seen_journal_ids.add(str(entry.id))

                    raw_remarks_str = str(entry.remarks or "")[:60]
                    print(
                        f"[{idx:02d}] BOUND | Date: {entry.transaction_date} | "
                        f"Debit: {entry.debit:10.2f} | ID: {entry.id} | "
                        f"RowID: {entry.row_identifier[:12]}... | "
                        f"Remarks: {raw_remarks_str}"
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
                            "remarks": entry.remarks,
                            "probability_score": 100,
                            "is_mapped": True,
                            "is_mapped_to_this_asset": True,
                            "mapping_info": {
                                "mapping_id": str(m_obj.id) if m_obj else None,
                                "asset_id": str(asset_id),
                            },
                        }
                    )

        print(f"\n📌 Phase 1 Total Bound Rows (Debits Only): {len(mapped_entries)}")

        # =========================================================================
        # PHASE 2: UNMAPPED POOL MATCHING (TIGHTENED SCORING)
        # =========================================================================
        start_date = doc_date - timedelta(days=day_window)
        end_date = (
            parsed_to_date
            if parsed_to_date
            else (doc_date + timedelta(days=day_window))
        )

        all_mapped_row_ids = set(
            AssetTransactionMapping.objects.exclude(
                row_identifier__isnull=True
            ).values_list("row_identifier", flat=True)
        )
        all_mapped_row_ids.update(seen_row_ids)

        unmapped_query = JournalEntry.objects.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date,
            debit__gt=0,
        )

        if account_id:
            unmapped_query = unmapped_query.filter(account_id=account_id)

        if all_mapped_row_ids:
            unmapped_query = unmapped_query.exclude(
                row_identifier__in=list(all_mapped_row_ids)
            )

        has_target_amount = (
            target_amount is not None and Decimal(str(target_amount)) > 0
        )

        target_amt = None
        min_amount = None
        max_amount = None
        if has_target_amount:
            target_amt = Decimal(str(target_amount))
            min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
            max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

        clean_keywords = []
        keyword_token_sets = []
        if keywords:
            for kw in keywords:
                norm_kw = AssetCandidateMatcher.normalize_text(kw)
                tokens = AssetCandidateMatcher.tokenize_text(kw)
                if norm_kw:
                    clean_keywords.append(norm_kw)
                if tokens:
                    keyword_token_sets.append(tokens)

        exclude_self_kw = ["INTRAACCOUNT", "OWNACCOUNTTFR", "SELFTRANSFER"]

        unmapped_candidates = []
        print("\n--- PHASE 2 UNMAPPED CANDIDATES PRINT ---")
        idx_p2 = 0

        for entry in unmapped_query.iterator():
            if (
                entry.row_identifier in seen_row_ids
                or str(entry.id) in seen_journal_ids
            ):
                continue

            eval_snapshot = entry.evaluation_matrix_snapshot or {}
            if isinstance(eval_snapshot, str):
                try:
                    eval_snapshot = json.loads(eval_snapshot)
                except Exception:
                    eval_snapshot = {}

            res_cat = eval_snapshot.get("resolved_category", "")
            res_sub = eval_snapshot.get("resolved_subcategory", "")

            if res_sub == "Self Inter-Account" or res_cat == "Income":
                continue

            norm_remarks = AssetCandidateMatcher.normalize_text(entry.remarks)

            if any(skw in norm_remarks for skw in exclude_self_kw):
                continue

            # KEYWORD MATCHING
            matched_count = 0
            entry_tokens = AssetCandidateMatcher.tokenize_text(entry.remarks)

            if clean_keywords:
                for norm_kw, kw_tokens in zip(clean_keywords, keyword_token_sets):
                    if kw_tokens and kw_tokens.issubset(entry_tokens):
                        matched_count += 1
                        continue

                    stem = norm_kw.rstrip("S")
                    if norm_kw in norm_remarks or (
                        len(stem) >= 4 and stem in norm_remarks
                    ):
                        matched_count += 1

            # AMOUNT MATCHING
            entry_debit = Decimal(str(entry.debit or 0))
            is_amount_matched = False
            if has_target_amount and min_amount and max_amount:
                if min_amount <= entry_debit <= max_amount:
                    is_amount_matched = True

            # HARD GUARDRAIL: Skip if neither keyword nor amount matches
            if clean_keywords or has_target_amount:
                if matched_count == 0 and not is_amount_matched:
                    continue

            # PROBABILITY SCORE CALCULATION
            score = 0

            if matched_count > 0:
                score += min(30 + (matched_count * 10), 50)

            if is_amount_matched:
                diff = abs(entry_debit - target_amt)
                if diff == Decimal("0"):
                    score += 40
                else:
                    score += 25

            date_diff = abs((entry.transaction_date - doc_date).days)
            if date_diff == 0:
                score += 10
            elif date_diff <= 7:
                score += 5

            seen_row_ids.add(entry.row_identifier)
            seen_journal_ids.add(str(entry.id))
            idx_p2 += 1

            raw_remarks_str = str(entry.remarks or "")[:60]
            print(
                f"[{idx_p2:02d}] UNMAPPED | Score: {score}% | Date: {entry.transaction_date} | "
                f"Debit: {entry.debit:10.2f} | ID: {entry.id} | "
                f"RowID: {entry.row_identifier[:12]}... | "
                f"Remarks: {raw_remarks_str}"
            )

            unmapped_candidates.append(
                {
                    "journal_id": str(entry.id),
                    "row_identifier": entry.row_identifier,
                    "account_id": entry.account_id,
                    "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
                    "date_offset_days": (entry.transaction_date - doc_date).days,
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
            key=lambda x: (x["probability_score"], -abs(x["date_offset_days"])),
            reverse=True,
        )

        total_final = len(mapped_entries) + len(sorted_unmapped)
        print("\n==================================================")
        print(
            f"📊 Phase 1 Bound (Debits): {len(mapped_entries)} | Phase 2 Unmapped: {len(sorted_unmapped)}"
        )
        print(f"✅ TOTAL CLEAN CANDIDATES: {total_final}")
        print("==================================================\n")

        return mapped_entries + sorted_unmapped


# from datetime import date, datetime, timedelta
# from decimal import Decimal
# from datetime import timedelta
# from django.db import models

# import json
# import re


# class AssetCandidateMatcher:

#     @staticmethod
#     def normalize_text(text: str) -> str:
#         """
#         Extracts narration/payee from dict/JSON string if needed,
#         then strips all non-alphanumeric characters and converts to UPPERCASE.
#         """
#         if not text:
#             return ""

#         if isinstance(text, dict):
#             text = f"{text.get('narration', '')} {text.get('payee', '')}"
#         elif isinstance(text, str) and text.strip().startswith("{"):
#             try:
#                 data = json.loads(text)
#                 if isinstance(data, dict):
#                     text = f"{data.get('narration', '')} {data.get('payee', '')}"
#             except Exception:
#                 pass

#         return re.sub(r"[^A-Za-z0-9]", "", str(text)).upper()

#     @staticmethod
#     def tokenize_text(text: str) -> set:
#         """
#         Splits text into clean, individual alphanumeric uppercase words/tokens.
#         Useful for precise word-boundary matching.
#         """
#         if not text:
#             return set()

#         if isinstance(text, dict):
#             text = f"{text.get('narration', '')} {text.get('payee', '')}"
#         elif isinstance(text, str) and text.strip().startswith("{"):
#             try:
#                 data = json.loads(text)
#                 if isinstance(data, dict):
#                     text = f"{data.get('narration', '')} {data.get('payee', '')}"
#             except Exception:
#                 pass

#         # Split on non-alphanumeric boundaries
#         tokens = re.findall(r"[A-Za-z0-9]+", str(text).upper())
#         return set(tokens)

#     # @staticmethod
#     # def find_candidate_rows(
#     #     document_date,
#     #     target_amount=None,
#     #     account_id=None,
#     #     keywords=None,
#     #     day_window=30,
#     #     amount_tolerance_pct=Decimal("0.05"),
#     #     asset_id=None,
#     #     to_date=None,
#     # ):
#     #     from tracker.models import JournalEntry
#     #     from tracker.models.subledger import AssetTransactionMapping

#     #     print("\n==================================================")
#     #     print(f"🔍 [DEBUG CANDIDATES] STARTING MATCH FOR ASSET: {asset_id}")
#     #     print(f"📥 Keywords: {keywords} | Horizon Days: {day_window}")
#     #     print("==================================================")

#     #     mapped_entries = []
#     #     seen_row_ids = set()
#     #     seen_journal_ids = set()

#     #     # =========================================================================
#     #     # PHASE 1: DIRECT LOOKUP FOR BOUND DATA (EXCLUDE ZERO-DEBIT COUNTERPARTS)
#     #     # =========================================================================
#     #     if asset_id:
#     #         bound_mappings = AssetTransactionMapping.objects.filter(
#     #             asset_id=asset_id
#     #         ).exclude(row_identifier__isnull=True)

#     #         bound_row_ids = list(
#     #             bound_mappings.values_list("row_identifier", flat=True)
#     #         )

#     #         if bound_row_ids:
#     #             bound_staging_entries = JournalEntry.objects.filter(
#     #                 row_identifier__in=bound_row_ids, debit__gt=0
#     #             )
#     #             mapping_map = {m.row_identifier: m for m in bound_mappings}

#     #             print("\n--- PHASE 1 BOUND ROWS PRINT ---")
#     #             for idx, entry in enumerate(bound_staging_entries, 1):
#     #                 m_obj = mapping_map.get(entry.row_identifier)

#     #                 seen_row_ids.add(entry.row_identifier)
#     #                 seen_journal_ids.add(str(entry.id))

#     #                 raw_remarks_str = str(entry.remarks or "")[:60]
#     #                 print(
#     #                     f"[{idx:02d}] BOUND | Date: {entry.transaction_date} | "
#     #                     f"Debit: {entry.debit:10.2f} | ID: {entry.id} | "
#     #                     f"RowID: {entry.row_identifier[:12]}... | "
#     #                     f"Remarks: {raw_remarks_str}"
#     #                 )

#     #                 mapped_entries.append(
#     #                     {
#     #                         "journal_id": str(entry.id),
#     #                         "row_identifier": entry.row_identifier,
#     #                         "account_id": entry.account_id,
#     #                         "transaction_date": entry.transaction_date.strftime(
#     #                             "%Y-%m-%d"
#     #                         ),
#     #                         "date_offset_days": 0,
#     #                         "debit": float(entry.debit),
#     #                         "credit": float(entry.credit),
#     #                         "remarks": entry.remarks,
#     #                         "probability_score": 100,
#     #                         "is_mapped": True,
#     #                         "is_mapped_to_this_asset": True,
#     #                         "mapping_info": {
#     #                             "mapping_id": str(m_obj.id) if m_obj else None,
#     #                             "asset_id": asset_id,
#     #                         },
#     #                     }
#     #                 )

#     #     print(f"\n📌 Phase 1 Total Bound Rows (Debits Only): {len(mapped_entries)}")

#     #     # =========================================================================
#     #     # PHASE 2: UNMAPPED POOL MATCHING (OPTIMIZED)
#     #     # =========================================================================
#     #     start_date = document_date
#     #     end_date = to_date if to_date else (document_date + timedelta(days=day_window))

#     #     all_mapped_row_ids = set(
#     #         AssetTransactionMapping.objects.exclude(
#     #             row_identifier__isnull=True
#     #         ).values_list("row_identifier", flat=True)
#     #     )
#     #     all_mapped_row_ids.update(seen_row_ids)

#     #     # Base DB Query - Select only necessary fields if needed
#     #     unmapped_query = JournalEntry.objects.filter(
#     #         transaction_date__gte=start_date,
#     #         transaction_date__lte=end_date,
#     #         debit__gt=0,
#     #     )

#     #     if account_id:
#     #         unmapped_query = unmapped_query.filter(account_id=account_id)

#     #     # Exclude already bound rows at database level
#     #     if all_mapped_row_ids:
#     #         unmapped_query = unmapped_query.exclude(
#     #             row_identifier__in=list(all_mapped_row_ids)
#     #         )

#     #     # ⚡ OPTIMIZATION 1: Database-Level Keyword Pre-Filtering
#     #     # Reduces incoming record count drastically before Python processing
#     #     has_target_amount = (
#     #         target_amount is not None and Decimal(str(target_amount)) > 0
#     #     )

#     #     if keywords and not has_target_amount:
#     #         phrase_q = models.Q()
#     #         for kw in keywords:
#     #             # Extract clean tokens >= 3 characters for DB LIKE filter
#     #             words = re.findall(r"[A-Za-z0-9]{3,}", kw)
#     #             if words:
#     #                 word_q = models.Q()
#     #                 for w in words:
#     #                     word_q &= models.Q(remarks__icontains=w)
#     #                 phrase_q |= word_q

#     #         if len(phrase_q) > 0:
#     #             unmapped_query = unmapped_query.filter(phrase_q)

#     #     # Prepare normalized keywords & token sets for Python matcher
#     #     clean_keywords = []
#     #     keyword_token_sets = []
#     #     if keywords:
#     #         for kw in keywords:
#     #             norm_kw = AssetCandidateMatcher.normalize_text(kw)
#     #             tokens = AssetCandidateMatcher.tokenize_text(kw)
#     #             if norm_kw:
#     #                 clean_keywords.append(norm_kw)
#     #             if tokens:
#     #                 keyword_token_sets.append(tokens)

#     #     exclude_self_kw = [
#     #         "INTRAACCOUNT",
#     #         "OWNACCOUNTTFR",
#     #         "SELFTRANSFER",
#     #     ]

#     #     target_amt = None
#     #     min_amount = None
#     #     max_amount = None
#     #     if has_target_amount:
#     #         target_amt = Decimal(str(target_amount))
#     #         min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
#     #         max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

#     #     unmapped_candidates = []
#     #     print("\n--- PHASE 2 UNMAPPED CANDIDATES PRINT ---")
#     #     idx_p2 = 0

#     #     # Execute Query with Iterator to conserve memory on large querysets
#     #     for entry in unmapped_query.iterator():
#     #         if (
#     #             entry.row_identifier in seen_row_ids
#     #             or str(entry.id) in seen_journal_ids
#     #         ):
#     #             continue

#     #         # 🎯 FIX 1: Python-Level Rule Classification Exclusion Guardrail
#     #         # Handles stringified or JSON-typed snapshots reliably
#     #         eval_snapshot = entry.evaluation_matrix_snapshot or {}
#     #         if isinstance(eval_snapshot, str):
#     #             try:
#     #                 eval_snapshot = json.loads(eval_snapshot)
#     #             except Exception:
#     #                 eval_snapshot = {}

#     #         res_cat = eval_snapshot.get("resolved_category", "")
#     #         res_sub = eval_snapshot.get("resolved_subcategory", "")

#     #         # Exclude cleared self-transfers and income records instantly
#     #         if res_sub == "Self Inter-Account" or res_cat == "Income":
#     #             continue

#     #         norm_remarks = AssetCandidateMatcher.normalize_text(entry.remarks)

#     #         # Exclude based on hardcoded self-transfer keywords
#     #         if any(skw in norm_remarks for skw in exclude_self_kw):
#     #             continue

#     #         # 🎯 FIX 2: Dual-Strategy Keyword Matching (Tokenized + Normalized)
#     #         score = 20
#     #         matched_count = 0
#     #         entry_tokens = AssetCandidateMatcher.tokenize_text(entry.remarks)

#     #         if clean_keywords:
#     #             for norm_kw, kw_tokens in zip(clean_keywords, keyword_token_sets):
#     #                 # Strategy A: Exact Word Token Match (Highest Precision)
#     #                 if kw_tokens and kw_tokens.issubset(entry_tokens):
#     #                     matched_count += 1
#     #                     continue

#     #                 # Strategy B: Compact Normalized Match (Handles space/hyphen differences)
#     #                 stem = norm_kw.rstrip("S")
#     #                 if norm_kw in norm_remarks or (
#     #                     len(stem) >= 4 and stem in norm_remarks
#     #                 ):
#     #                     matched_count += 1

#     #             if matched_count == 0 and not has_target_amount:
#     #                 continue

#     #         if matched_count > 0:
#     #             score += min(30 + (matched_count * 10), 50)

#     #         # Amount Matching Logic
#     #         if target_amt and min_amount and max_amount:
#     #             entry_debit = Decimal(str(entry.debit))
#     #             if min_amount <= entry_debit <= max_amount:
#     #                 score += 30

#     #         # Proximity Scoring
#     #         date_diff = (entry.transaction_date - document_date).days
#     #         if date_diff == 0:
#     #             score += 20
#     #         elif date_diff <= 30:
#     #             score += 15
#     #         elif date_diff <= 90:
#     #             score += 10

#     #         seen_row_ids.add(entry.row_identifier)
#     #         seen_journal_ids.add(str(entry.id))
#     #         idx_p2 += 1

#     #         raw_remarks_str = str(entry.remarks or "")[:60]
#     #         print(
#     #             f"[{idx_p2:02d}] UNMAPPED | Date: {entry.transaction_date} | "
#     #             f"Debit: {entry.debit:10.2f} | ID: {entry.id} | "
#     #             f"RowID: {entry.row_identifier[:12]}... | "
#     #             f"Remarks: {raw_remarks_str}"
#     #         )

#     #         unmapped_candidates.append(
#     #             {
#     #                 "journal_id": str(entry.id),
#     #                 "row_identifier": entry.row_identifier,
#     #                 "account_id": entry.account_id,
#     #                 "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
#     #                 "date_offset_days": date_diff,
#     #                 "debit": float(entry.debit),
#     #                 "credit": float(entry.credit),
#     #                 "remarks": entry.remarks,
#     #                 "probability_score": min(score, 100),
#     #                 "is_mapped": False,
#     #                 "is_mapped_to_this_asset": False,
#     #                 "mapping_info": None,
#     #             }
#     #         )

#     #     sorted_unmapped = sorted(
#     #         unmapped_candidates,
#     #         key=lambda x: (x["transaction_date"], x["probability_score"]),
#     #         reverse=False,
#     #     )

#     #     total_final = len(mapped_entries) + len(sorted_unmapped)
#     #     print("\n==================================================")
#     #     print(
#     #         f"📊 Phase 1 Bound (Debits): {len(mapped_entries)} | Phase 2 Unmapped: {len(sorted_unmapped)}"
#     #     )
#     #     print(f"✅ TOTAL CLEAN CANDIDATES: {total_final}")
#     #     print("==================================================\n")

#     #     return mapped_entries + sorted_unmapped

#     @staticmethod
#     def find_candidate_rows(
#         document_date,
#         target_amount=None,
#         account_id=None,
#         keywords=None,
#         day_window=30,
#         amount_tolerance_pct=Decimal("0.05"),
#         asset_id=None,
#         to_date=None,
#     ):
#         from tracker.models import JournalEntry
#         from tracker.models.subledger import AssetTransactionMapping

#         print("\n==================================================")
#         print(f"🔍 [DEBUG CANDIDATES] STARTING MATCH FOR ASSET: {asset_id}")
#         print(
#             f"📥 Keywords: {keywords} | Target Amount: {target_amount} | Horizon Days: {day_window}"
#         )
#         print("==================================================")

#         mapped_entries = []
#         seen_row_ids = set()
#         seen_journal_ids = set()

#         # =========================================================================
#         # PHASE 1: DIRECT LOOKUP FOR BOUND DATA (EXCLUDE ZERO-DEBIT COUNTERPARTS)
#         # =========================================================================
#         if asset_id:
#             bound_mappings = AssetTransactionMapping.objects.filter(
#                 asset_id=asset_id
#             ).exclude(row_identifier__isnull=True)

#             bound_row_ids = list(
#                 bound_mappings.values_list("row_identifier", flat=True)
#             )

#             if bound_row_ids:
#                 bound_staging_entries = JournalEntry.objects.filter(
#                     row_identifier__in=bound_row_ids, debit__gt=0
#                 )
#                 mapping_map = {m.row_identifier: m for m in bound_mappings}

#                 print("\n--- PHASE 1 BOUND ROWS PRINT ---")
#                 for idx, entry in enumerate(bound_staging_entries, 1):
#                     m_obj = mapping_map.get(entry.row_identifier)

#                     seen_row_ids.add(entry.row_identifier)
#                     seen_journal_ids.add(str(entry.id))

#                     raw_remarks_str = str(entry.remarks or "")[:60]
#                     print(
#                         f"[{idx:02d}] BOUND | Date: {entry.transaction_date} | "
#                         f"Debit: {entry.debit:10.2f} | ID: {entry.id} | "
#                         f"RowID: {entry.row_identifier[:12]}... | "
#                         f"Remarks: {raw_remarks_str}"
#                     )

#                     mapped_entries.append(
#                         {
#                             "journal_id": str(entry.id),
#                             "row_identifier": entry.row_identifier,
#                             "account_id": entry.account_id,
#                             "transaction_date": entry.transaction_date.strftime(
#                                 "%Y-%m-%d"
#                             ),
#                             "date_offset_days": 0,
#                             "debit": float(entry.debit),
#                             "credit": float(entry.credit),
#                             "remarks": entry.remarks,
#                             "probability_score": 100,
#                             "is_mapped": True,
#                             "is_mapped_to_this_asset": True,
#                             "mapping_info": {
#                                 "mapping_id": str(m_obj.id) if m_obj else None,
#                                 "asset_id": asset_id,
#                             },
#                         }
#                     )

#         print(f"\n📌 Phase 1 Total Bound Rows (Debits Only): {len(mapped_entries)}")

#         # =========================================================================
#         # PHASE 2: UNMAPPED POOL MATCHING (TIGHTENED SCORING)
#         # =========================================================================
#         start_date = (
#             document_date - timedelta(days=day_window)
#             if isinstance(document_date, date)
#             else document_date
#         )
#         end_date = to_date if to_date else (document_date + timedelta(days=day_window))

#         all_mapped_row_ids = set(
#             AssetTransactionMapping.objects.exclude(
#                 row_identifier__isnull=True
#             ).values_list("row_identifier", flat=True)
#         )
#         all_mapped_row_ids.update(seen_row_ids)

#         unmapped_query = JournalEntry.objects.filter(
#             transaction_date__gte=start_date,
#             transaction_date__lte=end_date,
#             debit__gt=0,
#         )

#         if account_id:
#             unmapped_query = unmapped_query.filter(account_id=account_id)

#         if all_mapped_row_ids:
#             unmapped_query = unmapped_query.exclude(
#                 row_identifier__in=list(all_mapped_row_ids)
#             )

#         has_target_amount = (
#             target_amount is not None and Decimal(str(target_amount)) > 0
#         )

#         target_amt = None
#         min_amount = None
#         max_amount = None
#         if has_target_amount:
#             target_amt = Decimal(str(target_amount))
#             min_amount = target_amt * (Decimal("1") - amount_tolerance_pct)
#             max_amount = target_amt * (Decimal("1") + amount_tolerance_pct)

#         # Prepare normalized keywords
#         clean_keywords = []
#         keyword_token_sets = []
#         if keywords:
#             for kw in keywords:
#                 norm_kw = AssetCandidateMatcher.normalize_text(kw)
#                 tokens = AssetCandidateMatcher.tokenize_text(kw)
#                 if norm_kw:
#                     clean_keywords.append(norm_kw)
#                 if tokens:
#                     keyword_token_sets.append(tokens)

#         exclude_self_kw = ["INTRAACCOUNT", "OWNACCOUNTTFR", "SELFTRANSFER"]

#         unmapped_candidates = []
#         print("\n--- PHASE 2 UNMAPPED CANDIDATES PRINT ---")
#         idx_p2 = 0

#         for entry in unmapped_query.iterator():
#             if (
#                 entry.row_identifier in seen_row_ids
#                 or str(entry.id) in seen_journal_ids
#             ):
#                 continue

#             eval_snapshot = entry.evaluation_matrix_snapshot or {}
#             if isinstance(eval_snapshot, str):
#                 try:
#                     eval_snapshot = json.loads(eval_snapshot)
#                 except Exception:
#                     eval_snapshot = {}

#             res_cat = eval_snapshot.get("resolved_category", "")
#             res_sub = eval_snapshot.get("resolved_subcategory", "")

#             if res_sub == "Self Inter-Account" or res_cat == "Income":
#                 continue

#             norm_remarks = AssetCandidateMatcher.normalize_text(entry.remarks)

#             if any(skw in norm_remarks for skw in exclude_self_kw):
#                 continue

#             # 🎯 1. KEYWORD MATCHING
#             matched_count = 0
#             entry_tokens = AssetCandidateMatcher.tokenize_text(entry.remarks)

#             if clean_keywords:
#                 for norm_kw, kw_tokens in zip(clean_keywords, keyword_token_sets):
#                     if kw_tokens and kw_tokens.issubset(entry_tokens):
#                         matched_count += 1
#                         continue

#                     stem = norm_kw.rstrip("S")
#                     if norm_kw in norm_remarks or (
#                         len(stem) >= 4 and stem in norm_remarks
#                     ):
#                         matched_count += 1

#             # 🎯 2. AMOUNT MATCHING
#             entry_debit = Decimal(str(entry.debit or 0))
#             is_amount_matched = False
#             if has_target_amount and min_amount and max_amount:
#                 if min_amount <= entry_debit <= max_amount:
#                     is_amount_matched = True

#             # 🛑 HARD GUARDRAIL: If user specified keywords or amount,
#             # discard rows that match NEITHER keyword NOR amount.
#             if clean_keywords or has_target_amount:
#                 if matched_count == 0 and not is_amount_matched:
#                     continue  # Drops random ₹175 entries instantly!

#             # 🧮 3. PROBABILITY SCORE CALCULATION
#             score = 0

#             # Keyword points (up to 50 pts)
#             if matched_count > 0:
#                 score += min(30 + (matched_count * 10), 50)

#             # Amount points (up to 40 pts)
#             if is_amount_matched:
#                 diff = abs(entry_debit - target_amt)
#                 if diff == Decimal("0"):
#                     score += 40  # Exact amount match
#                 else:
#                     score += 25  # Within tolerance

#             # Proximity points (up to 10 pts)
#             date_diff = (
#                 abs((entry.transaction_date - document_date).days)
#                 if isinstance(document_date, date)
#                 else 0
#             )
#             if date_diff == 0:
#                 score += 10
#             elif date_diff <= 7:
#                 score += 5

#             seen_row_ids.add(entry.row_identifier)
#             seen_journal_ids.add(str(entry.id))
#             idx_p2 += 1

#             raw_remarks_str = str(entry.remarks or "")[:60]
#             print(
#                 f"[{idx_p2:02d}] UNMAPPED | Score: {score}% | Date: {entry.transaction_date} | "
#                 f"Debit: {entry.debit:10.2f} | ID: {entry.id} | "
#                 f"RowID: {entry.row_identifier[:12]}... | "
#                 f"Remarks: {raw_remarks_str}"
#             )

#             unmapped_candidates.append(
#                 {
#                     "journal_id": str(entry.id),
#                     "row_identifier": entry.row_identifier,
#                     "account_id": entry.account_id,
#                     "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
#                     "date_offset_days": (
#                         (entry.transaction_date - document_date).days
#                         if isinstance(document_date, date)
#                         else 0
#                     ),
#                     "debit": float(entry.debit),
#                     "credit": float(entry.credit),
#                     "remarks": entry.remarks,
#                     "probability_score": min(score, 100),
#                     "is_mapped": False,
#                     "is_mapped_to_this_asset": False,
#                     "mapping_info": None,
#                 }
#             )

#         # Sort unmapped candidates by probability score descending
#         sorted_unmapped = sorted(
#             unmapped_candidates,
#             key=lambda x: (x["probability_score"], -abs(x["date_offset_days"])),
#             reverse=True,
#         )

#         total_final = len(mapped_entries) + len(sorted_unmapped)
#         print("\n==================================================")
#         print(
#             f"📊 Phase 1 Bound (Debits): {len(mapped_entries)} | Phase 2 Unmapped: {len(sorted_unmapped)}"
#         )
#         print(f"✅ TOTAL CLEAN CANDIDATES: {total_final}")
#         print("==================================================\n")

#         return mapped_entries + sorted_unmapped
