# tracker/serviceWIP.py
import hashlib
import json
import re
import copy
from decimal import Decimal
from django.db import transaction
from .models import (
    StatementStagingLine,
    WIPEvaluationMatrix,
    MasterFinancialCategory,
    AccountingRule,
    DirectionalVectorOverride,
)


class WIPIngestionSweeper:
    """
    🎛️ AIR-GAPPED TRANSACTION INITIALIZATION ENGINE
    Sweeps unallocated StatementStagingLines into the WIP Evaluation Sandbox
    using strict deterministic SHA-256 state tracking keys.
    """

    @staticmethod
    def generate_row_hash(date_obj, debit_val, credit_val, balance_val) -> str:
        def clean_num(val) -> str:
            if val is None:
                return "0.00"
            return f"{Decimal(str(val)):.2f}"

        date_str = (
            date_obj.strftime("%Y-%m-%d")
            if hasattr(date_obj, "strftime")
            else str(date_obj)
        )
        data_payload = f"{date_str}|{clean_num(debit_val)}|{clean_num(credit_val)}|{clean_num(balance_val)}"
        return hashlib.sha256(data_payload.encode("utf-8")).hexdigest()

    @classmethod
    def execute_sweep(cls, account_context_id) -> dict:
        metrics = {"scanned": 0, "initialized": 0, "skipped": 0}
        with transaction.atomic():
            staging_queue = StatementStagingLine.objects.filter(
                account_id=account_context_id, routing_status="PENDING"
            ).select_for_update()

            metrics["scanned"] = staging_queue.count()

            existing_wip_hashes = set(
                WIPEvaluationMatrix.objects.filter(
                    account_id=account_context_id
                ).values_list("row_footprint_hash", flat=True)
            )

            wip_insertions = []

            for row in staging_queue:
                dr_clean = row.debit if row.debit is not None else Decimal("0.00")
                cr_clean = row.credit if row.credit is not None else Decimal("0.00")
                bal_clean = (
                    row.running_balance
                    if row.running_balance is not None
                    else Decimal("0.00")
                )

                row_hash = cls.generate_row_hash(
                    row.raw_statement_date, dr_clean, cr_clean, bal_clean
                )

                if row_hash in existing_wip_hashes:
                    metrics["skipped"] += 1
                    continue

                wip_row = WIPEvaluationMatrix(
                    staging_line=row,
                    row_footprint_hash=row_hash,
                    account=row.account,
                    bank=row.bank,
                    raw_statement_date=row.raw_statement_date,
                    narration_normalized=" ".join(
                        row.narration.strip().lower().split()
                    ),
                    debit=dr_clean,
                    credit=cr_clean,
                    confidence_level="ZERO",
                    tier_1_passed=False,
                    tier_2_passed=False,
                    tier_3_passed=False,
                    evaluation_errors=["UNPROCESSED_RUN"],
                )
                wip_insertions.append(wip_row)
                existing_wip_hashes.add(row_hash)

            if wip_insertions:
                WIPEvaluationMatrix.objects.bulk_create(wip_insertions)
                metrics["initialized"] = len(wip_insertions)

        return metrics


class WIPReconciliationEngine:
    """
    ⚡ MULTI-TIER CASCADING RECONCILIATION ENGINE
    Tier 1 (KNOWN_DEFAULT) and Tier 2 (SELF_TRANSFER) executed with sequential early-exit gates.
    """

    @classmethod
    def evaluate_account_queue(cls, account_id: int) -> dict:
        # ─── STEP 1: PRE-COMPILE REFERENCE LOOKUPS AT DB LAYER ───

        # 1a. Load Tier 1 Reference (Known System Defaults)
        t1_categories = MasterFinancialCategory.objects.filter(
            category_type="KNOWN_DEFAULT"
        )
        t1_lookup = []
        for m_cat in t1_categories:
            if isinstance(m_cat.keys, dict):
                k1 = (m_cat.keys.get("key1") or "").strip().lower()
                k2 = (m_cat.keys.get("key2") or "").strip().lower()
                if k1:
                    t1_lookup.append((m_cat, k1, k2))

        # 1b. Load Tier 2 Reference (Self Internal Account Transfers)
        t2_categories = MasterFinancialCategory.objects.filter(
            category_type="SELF_TRANSFER"
        )
        t2_lookup = []
        for m_cat in t2_categories:
            if isinstance(m_cat.keys, dict):
                k1 = (m_cat.keys.get("key1") or "").strip().lower()
                k2 = (m_cat.keys.get("key2") or "").strip().lower()
                if k1:
                    t2_lookup.append((m_cat, k1, k2))

        # ─── STEP 2: LOAD WIP DATA TARGET MATRIX ───
        active_wip_rows = WIPEvaluationMatrix.objects.filter(
            account_id=account_id, is_split_component=False
        ).select_related("staging_line")

        serialized_queue = []

        # ─── STEP 3: TRANSACTION PROCESSING LOOP ───
        for wip_row in active_wip_rows:
            raw_narration = (
                wip_row.staging_line.narration if wip_row.staging_line else ""
            )
            narration_clean = raw_narration.strip().lower()

            try:
                debit_val = float(wip_row.debit or 0)
                credit_val = float(wip_row.credit or 0)
            except (ValueError, TypeError):
                debit_val, credit_val = 0.0, 0.0

            # Baseline Directional Fallback state for Tier 1
            if credit_val > 0:
                s1_cat = "Income"
            else:
                s1_cat = "Expenses"
            s1_sub = "Suspense Account"

            # Isolated, independent registers for Tier 2 values
            s2_cat = "None"
            s2_sub = "None"

            matched_token = "None"
            hit_tier = 0

            # 🛑 PASS A: TIER 1 INDEPENDENT LOOP (No early exit!)
            for cat_inst, k1, k2 in t1_lookup:
                if k1 in narration_clean:
                    if not k2 or (k2 and k2 in narration_clean):
                        s1_cat = cat_inst.act_category
                        s1_sub = (
                            cat_inst.act_subcategory
                            if cat_inst.act_subcategory
                            else cat_inst.act_category
                        )
                        matched_token = k1 if not k2 else f"{k1} + {k2}"
                        hit_tier = 1
                        break  # Only breaks out of Tier 1 keywords, moves to Tier 2 check!

            # 🔄 PASS B: TIER 2 INDEPENDENT LOOP (Always checks!)
            for cat_inst, k1, k2 in t2_lookup:
                if k1 in narration_clean:
                    if not k2 or (k2 and k2 in narration_clean):
                        s2_cat = cat_inst.act_category
                        s2_sub = (
                            cat_inst.act_subcategory
                            if cat_inst.act_subcategory
                            else cat_inst.act_category
                        )
                        # If Tier 1 didn't hit, Tier 2 becomes the primary display driver
                        if hit_tier == 0:
                            matched_token = k1 if not k2 else f"{k1} + {k2}"
                            hit_tier = 2
                        break

            # Append structured payload with cleanly isolated fields
            serialized_queue.append(
                {
                    "wip_id": str(wip_row.id),
                    "date": (
                        wip_row.raw_statement_date.strftime("%Y-%m-%d")
                        if wip_row.raw_statement_date
                        else ""
                    ),
                    "narration": raw_narration,
                    "debit": debit_val,
                    "credit": credit_val,
                    "tier1_metrics": {
                        "active_tier_level": hit_tier,
                        "matched_keyword_token": matched_token,
                        "execution_weight": (
                            100 if hit_tier == 1 else (90 if hit_tier == 2 else 50)
                        ),
                        "confidence_level": (
                            100 if hit_tier == 1 else (95 if hit_tier == 2 else 20)
                        ),
                        "t1_category": s1_cat,
                        "t1_subcategory": s1_sub,
                        "t2_category": s2_cat,
                        "t2_subcategory": s2_sub,
                    },
                }
            )

        return {"workspace_queue": serialized_queue}


# class WIPReconciliationEngine1:
#     """
#     🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE - VERSION 13.0
#     Full-Spectrum Exposure Pipeline (Maximum Operational Visibility)
#     """

#     @classmethod
#     def evaluate_account_queue(cls, account_id: int) -> dict:
#         # ─── BLOCK 1: PRE-COMPILE LOCAL CACHE MEMORY ───
#         master_categories = list(MasterFinancialCategory.objects.all())
#         accounting_rules = list(
#             AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
#         )

#         rules_by_composite_cache = {}
#         suspense_rules_by_vector = {"Debit": None, "Credit": None}

#         for rule in accounting_rules:
#             meta = {}
#             if rule.rule_metadata:
#                 if isinstance(rule.rule_metadata, dict):
#                     meta = rule.rule_metadata
#                 elif isinstance(rule.rule_metadata, str):
#                     try:
#                         meta = json.loads(rule.rule_metadata)
#                     except json.JSONDecodeError:
#                         meta = {}

#             rule_cat = str(meta.get("category") or "").strip()
#             rule_sub = str(meta.get("subcategory") or "").strip()
#             vector = rule.entry_type

#             if rule_cat:
#                 rules_by_composite_cache[
#                     (rule_cat.lower(), rule_sub.lower(), vector)
#                 ] = (rule, meta, rule_cat, rule_sub)

#             if (
#                 "suspense" in rule_sub.lower()
#                 or "suspense" in str(rule.rule_title or "").lower()
#             ):
#                 if not suspense_rules_by_vector[vector]:
#                     suspense_rules_by_vector[vector] = (rule, meta, rule_cat, rule_sub)

#         parsed_keywords = []
#         balance_sheet_map = {}

#         for m_cat in master_categories:
#             if isinstance(m_cat.keys, dict):
#                 k1 = (m_cat.keys.get("key1") or "").strip().lower()
#                 k2 = (m_cat.keys.get("key2") or "").strip().lower()
#             else:
#                 k1, k2 = "", ""
#             parsed_keywords.append((m_cat, k1, k2))

#             cat_item_name = (
#                 str(m_cat.categories_items or m_cat.act_category or "").strip().lower()
#             )
#             if cat_item_name:
#                 balance_sheet_map[cat_item_name] = (
#                     str(m_cat.act_category or "").strip(),
#                     str(m_cat.act_subcategory or "").strip(),
#                     str(m_cat.dashboard_cat or "").strip(),
#                 )

#         active_wip_rows = WIPEvaluationMatrix.objects.filter(
#             account_id=account_id,
#             is_split_component=False,
#         ).select_related("staging_line", "matched_category", "applied_rule")

#         total_high = 0
#         total_medium = 0
#         total_low = 0
#         modified_wip_rows = []
#         serialized_workspace_queue = []

#         # ─── BLOCK 2: THE 4-STOP SEQUENTIAL EVALUATION LOOP ───
#         for wip_row in active_wip_rows:
#             narration_clean = (wip_row.narration_normalized or "").strip().lower()

#             try:
#                 debit_val = float(wip_row.debit or 0)
#                 credit_val = float(wip_row.credit or 0)
#             except (ValueError, TypeError):
#                 debit_val, credit_val = 0.0, 0.0

#             is_credit_flow = credit_val > 0
#             target_vector = "Credit" if is_credit_flow else "Debit"
#             fallback_default_cat = "Income" if is_credit_flow else "Expenses"

#             profile_votes = []

#             # 🧩 STOP 1: KnownDefaultSource (Keywords Pass)
#             s1_cat, s1_sub, s1_score = None, None, 50
#             for cat_inst, k1, k2 in parsed_keywords:
#                 if not k1:
#                     continue

#                 if is_credit_flow and cat_inst.act_category.strip().lower() in [
#                     "expense",
#                     "expenses",
#                     "charity",
#                 ]:
#                     continue
#                 if debit_val > 0 and cat_inst.act_category.strip().lower() in [
#                     "income",
#                     "revenue",
#                 ]:
#                     continue

#                 is_match = False
#                 if len(k1) == 64:
#                     words = re.sub(r"[/:\-_,]", " ", narration_clean).split()
#                     is_match = any(
#                         hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
#                         for w in words
#                     )
#                 elif k1 in narration_clean:
#                     k2_clean = k2.replace(" ", "") if k2 else None
#                     if not k2_clean or (k2_clean in narration_clean.replace(" ", "")):
#                         is_match = True

#                 if is_match:
#                     s1_cat = cat_inst.act_category
#                     s1_sub = (
#                         cat_inst.act_subcategory
#                         if cat_inst.act_subcategory
#                         else cat_inst.act_category
#                     )
#                     s1_score = 100
#                     wip_row.matched_category = cat_inst
#                     break

#             if s1_score == 50:
#                 s1_cat, s1_sub = fallback_default_cat, "Suspense Account"

#             profile_votes.append({"cat": s1_cat, "sub": s1_sub, "score": s1_score})
#             wip_row.t1_category, wip_row.t1_subcategory = s1_cat, s1_sub

#             # 📊 STOP 2: SelfTransfer Source
#             s2_cat, s2_sub, s2_score = None, None, 50
#             if (
#                 "transfer" in narration_clean
#                 or "self" in narration_clean
#                 or "own account" in narration_clean
#             ):
#                 s2_cat = "Transfer"
#                 s2_sub = "Inter-Account Transfer"
#                 s2_score = 100
#             else:
#                 s2_cat, s2_sub = fallback_default_cat, "Suspense Account"

#             profile_votes.append({"cat": s2_cat, "sub": s2_sub, "score": s2_score})
#             wip_row.t2_category, wip_row.t2_subcategory = s2_cat, s2_sub

#             # ⚖️ STOP 3: BalanceSheetSourceRows
#             s3_cat, s3_sub, s3_dash, s3_score = None, None, None, 50
#             lookup_target_key = str(s1_cat or "").strip().lower()

#             if lookup_target_key in balance_sheet_map:
#                 act_c, act_s, dash_c = balance_sheet_map[lookup_target_key]
#                 s3_cat = act_c
#                 s3_sub = act_s if act_s else act_c
#                 s3_dash = dash_c
#                 s3_score = 100
#             else:
#                 s3_cat, s3_sub, s3_dash = (
#                     fallback_default_cat,
#                     "Suspense Account",
#                     "Suspense Dashboard",
#                 )

#             profile_votes.append({"cat": s3_cat, "sub": s3_sub, "score": s3_score})
#             wip_row.t3_category, wip_row.t3_subcategory = s3_cat, s3_sub

#             # 📜 STOP 4: Accounting Rule Book Lookup & Binding
#             s4_cat, s4_sub, s4_score, matched_rule_obj = None, None, 50, None
#             lookup_composite_key = (
#                 str(s1_cat or "").strip().lower(),
#                 str(s1_sub or "").strip().lower(),
#                 target_vector,
#             )

#             if lookup_composite_key in rules_by_composite_cache:
#                 rule_obj, rule_meta, true_cat, true_sub = rules_by_composite_cache[
#                     lookup_composite_key
#                 ]
#                 s4_cat = true_cat
#                 s4_sub = true_sub
#                 s4_score = 100
#                 matched_rule_obj = rule_obj
#             else:
#                 # 🎯 FIX: Intelligently protect the keyword match!
#                 # If an explicit rule doesn't exist, keep the Category & Subcategory from Stop 1
#                 s4_cat = s1_cat
#                 s4_sub = s1_sub
#                 s4_score = 100  # Vote with high weight for the keyword category

#                 # 🤖 ...but bind the dynamic Suspense database rule row object to secure the ledger backend!
#                 suspense_tuple = suspense_rules_by_vector[target_vector]
#                 if suspense_tuple:
#                     rule_obj, _, _, _ = suspense_tuple
#                     matched_rule_obj = rule_obj
#                 else:
#                     matched_rule_obj = None

#             profile_votes.append({"cat": s4_cat, "sub": s4_sub, "score": s4_score})

#             # 🏆 THE WEIGHTED AVERAGE ELECTION
#             candidate_combos = {}
#             for vote in profile_votes:
#                 combo_key = (vote["cat"], vote["sub"])
#                 candidate_combos[combo_key] = (
#                     candidate_combos.get(combo_key, 0) + vote["score"]
#                 )

#             winner_combo = max(candidate_combos, key=candidate_combos.get)
#             resolved_winner_cat, resolved_winner_sub = winner_combo[0], winner_combo[1]

#             total_score_accumulated = sum(v["score"] for v in profile_votes)
#             if total_score_accumulated >= 350:
#                 confidence_level = "HIGH"
#                 total_high += 1
#             elif total_score_accumulated >= 250:
#                 confidence_level = "MEDIUM"
#                 total_medium += 1
#             else:
#                 confidence_level = "LOW"
#                 total_low += 1

#             # 💾 Save State to Row Model Objects
#             wip_row.resolved_category = resolved_winner_cat
#             wip_row.resolved_subcategory = resolved_winner_sub
#             wip_row.confidence_score = int((total_score_accumulated / 400) * 100)
#             wip_row.confidence_level = confidence_level
#             wip_row.evaluation_errors = []

#             wip_row.applied_rule = matched_rule_obj
#             wip_row.tier_1_passed = s1_score == 100
#             wip_row.tier_2_passed = s2_score == 100
#             wip_row.tier_3_passed = matched_rule_obj is not None

#             modified_wip_rows.append(wip_row)

#             # 🎯 EXPOSE ALL STOPS DIRECTLY INSIDE THE FRONTLINE PAYLOAD
#             serialized_workspace_queue.append(
#                 {
#                     "wip_id": str(wip_row.id),
#                     "hash": wip_row.row_footprint_hash,
#                     "date": (
#                         wip_row.raw_statement_date.strftime("%Y-%m-%d")
#                         if wip_row.raw_statement_date
#                         else ""
#                     ),
#                     "narration": wip_row.staging_line.narration,
#                     "debit": debit_val,
#                     "credit": credit_val,
#                     "confidence": confidence_level,
#                     "score": wip_row.confidence_score,
#                     "errors": [],
#                     "routing_status": wip_row.staging_line.routing_status,
#                     # The Full Auditable Pipeline Matrix
#                     "pipeline_trace": {
#                         "stop1_known_default": {
#                             "category": s1_cat,
#                             "subcategory": s1_sub,
#                             "score": s1_score,
#                         },
#                         "stop2_self_transfer": {
#                             "category": s2_cat,
#                             "subcategory": s2_sub,
#                             "score": s2_score,
#                         },
#                         "stop3_balance_sheet": {
#                             "category": s3_cat,
#                             "subcategory": s3_sub,
#                             "score": s3_score,
#                             "dashboard": s3_dash,
#                         },
#                         "stop4_accounting_rule": {
#                             "category": s4_cat,
#                             "subcategory": s4_sub,
#                             "score": s4_score,
#                             "rule_id": rule_obj.id if matched_rule_obj else None,
#                         },
#                     },
#                     "analysis": {
#                         "category_id": (
#                             wip_row.matched_category.id
#                             if wip_row.matched_category
#                             else None
#                         ),
#                         "category_item": (
#                             wip_row.matched_category.categories_items
#                             if wip_row.matched_category
#                             else resolved_winner_cat
#                         ),
#                         "dashboard_cat": (
#                             wip_row.matched_category.dashboard_cat
#                             if wip_row.matched_category
#                             else resolved_winner_cat
#                         ),
#                         "group": resolved_winner_cat,
#                         "subcategory": resolved_winner_sub,
#                         "rule_code": (
#                             matched_rule_obj.rule_code
#                             if matched_rule_obj
#                             else "System Match"
#                         ),
#                         "rule_title": (
#                             matched_rule_obj.rule_title
#                             if matched_rule_obj
#                             else "Classified via Composite Keywords Pipeline"
#                         ),
#                     },
#                 }
#             )

#         # ─── BLOCK 3: ATOMIC DATABASE WRITE BACK ───
#         if modified_wip_rows:
#             with transaction.atomic():
#                 WIPEvaluationMatrix.objects.bulk_update(
#                     modified_wip_rows,
#                     fields=[
#                         "t1_category",
#                         "t1_subcategory",
#                         "t2_category",
#                         "t2_subcategory",
#                         "t3_category",
#                         "t3_subcategory",
#                         "resolved_category",
#                         "resolved_subcategory",
#                         "confidence_score",
#                         "confidence_level",
#                         "evaluation_errors",
#                         "matched_category",
#                         "applied_rule",
#                         "tier_1_passed",
#                         "tier_2_passed",
#                         "tier_3_passed",
#                     ],
#                     batch_size=500,
#                 )
#         return {
#             "serialized_queue": serialized_workspace_queue,
#             "staged_for_bulk_high": total_high,
#             "staged_for_bulk_medium": total_medium,
#             "uncategorized_vault_zero": total_low,
#         }


# class WIPReconciliationEngine5:
#     """
#     🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE - VERSION 12.0
#     Single-Pass Evaluation & Serialization Pipeline (Zero-Latency Architecture)
#     """

#     @classmethod
#     def evaluate_account_queue(cls, account_id: int) -> dict:
#         # ─── BLOCK 1: PRE-COMPILE LOCAL CACHE MEMORY ───
#         master_categories = list(MasterFinancialCategory.objects.all())
#         accounting_rules = list(
#             AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
#         )

#         rules_by_composite_cache = {}
#         suspense_rules_by_vector = {"Debit": None, "Credit": None}

#         for rule in accounting_rules:
#             meta = {}
#             if rule.rule_metadata:
#                 if isinstance(rule.rule_metadata, dict):
#                     meta = rule.rule_metadata
#                 elif isinstance(rule.rule_metadata, str):
#                     try:
#                         meta = json.loads(rule.rule_metadata)
#                     except json.JSONDecodeError:
#                         meta = {}

#             rule_cat = str(meta.get("category") or "").strip()
#             rule_sub = str(meta.get("subcategory") or "").strip()
#             vector = rule.entry_type

#             if rule_cat:
#                 rules_by_composite_cache[
#                     (rule_cat.lower(), rule_sub.lower(), vector)
#                 ] = (rule, meta, rule_cat, rule_sub)

#             if (
#                 "suspense" in rule_sub.lower()
#                 or "suspense" in str(rule.rule_title or "").lower()
#             ):
#                 if not suspense_rules_by_vector[vector]:
#                     suspense_rules_by_vector[vector] = (rule, meta, rule_cat, rule_sub)

#         parsed_keywords = []
#         balance_sheet_map = {}

#         for m_cat in master_categories:
#             if isinstance(m_cat.keys, dict):
#                 k1 = (m_cat.keys.get("key1") or "").strip().lower()
#                 k2 = (m_cat.keys.get("key2") or "").strip().lower()
#             else:
#                 k1, k2 = "", ""
#             parsed_keywords.append((m_cat, k1, k2))

#             cat_item_name = (
#                 str(m_cat.categories_items or m_cat.act_category or "").strip().lower()
#             )
#             if cat_item_name:
#                 balance_sheet_map[cat_item_name] = (
#                     str(m_cat.act_category or "").strip(),
#                     str(m_cat.act_subcategory or "").strip(),
#                     str(m_cat.dashboard_cat or "").strip(),
#                 )

#         active_wip_rows = WIPEvaluationMatrix.objects.filter(
#             account_id=account_id,
#             is_split_component=False,
#         ).select_related("staging_line", "matched_category", "applied_rule")

#         total_high = 0
#         total_medium = 0
#         total_low = 0
#         modified_wip_rows = []

#         # 🎯 THE VELOCITY FIX: Pre-allocate the serialization array here
#         serialized_workspace_queue = []

#         # ─── BLOCK 2: SINGLE-PASS EVALUATION & SERIALIZATION LOOP ───
#         for wip_row in active_wip_rows:
#             narration_clean = (wip_row.narration_normalized or "").strip().lower()

#             try:
#                 debit_val = float(wip_row.debit or 0)
#                 credit_val = float(wip_row.credit or 0)
#             except (ValueError, TypeError):
#                 debit_val, credit_val = 0.0, 0.0

#             is_credit_flow = credit_val > 0
#             target_vector = "Credit" if is_credit_flow else "Debit"
#             fallback_default_cat = "Income" if is_credit_flow else "Expenses"

#             profile_votes = []

#             # STOP 1: KnownDefaultSource
#             s1_cat, s1_sub, s1_score = None, None, 50
#             for cat_inst, k1, k2 in parsed_keywords:
#                 if not k1:
#                     continue

#                 if is_credit_flow and cat_inst.act_category.strip().lower() in [
#                     "expense",
#                     "expenses",
#                     "charity",
#                 ]:
#                     continue
#                 if debit_val > 0 and cat_inst.act_category.strip().lower() in [
#                     "income",
#                     "revenue",
#                 ]:
#                     continue

#                 is_match = False
#                 if len(k1) == 64:
#                     words = re.sub(r"[/:\-_,]", " ", narration_clean).split()
#                     is_match = any(
#                         hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
#                         for w in words
#                     )
#                 elif k1 in narration_clean:
#                     k2_clean = k2.replace(" ", "") if k2 else None
#                     if not k2_clean or (k2_clean in narration_clean.replace(" ", "")):
#                         is_match = True

#                 if is_match:
#                     s1_cat = cat_inst.act_category
#                     s1_sub = (
#                         cat_inst.act_subcategory
#                         if cat_inst.act_subcategory
#                         else cat_inst.act_category
#                     )
#                     s1_score = 100
#                     wip_row.matched_category = cat_inst
#                     break

#             if s1_score == 50:
#                 s1_cat, s1_sub = fallback_default_cat, "Suspense Account"

#             profile_votes.append({"cat": s1_cat, "sub": s1_sub, "score": s1_score})
#             wip_row.t1_category, wip_row.t1_subcategory = s1_cat, s1_sub

#             # STOP 2: SelfTransfer Source
#             s2_cat, s2_sub, s2_score = None, None, 50
#             if (
#                 "transfer" in narration_clean
#                 or "self" in narration_clean
#                 or "own account" in narration_clean
#             ):
#                 s2_cat = "Transfer"
#                 s2_sub = "Inter-Account Transfer"
#                 s2_score = 100
#             else:
#                 s2_cat, s2_sub = fallback_default_cat, "Suspense Account"

#             profile_votes.append({"cat": s2_cat, "sub": s2_sub, "score": s2_score})
#             wip_row.t2_category, wip_row.t2_subcategory = s2_cat, s2_sub

#             # STOP 3: BalanceSheetSourceRows
#             s3_cat, s3_sub, s3_dash, s3_score = None, None, None, 50
#             lookup_target_key = str(s1_cat or "").strip().lower()

#             if lookup_target_key in balance_sheet_map:
#                 act_c, act_s, dash_c = balance_sheet_map[lookup_target_key]
#                 s3_cat = act_c
#                 s3_sub = act_s if act_s else act_c
#                 s3_dash = dash_c
#                 s3_score = 100
#             else:
#                 s3_cat, s3_sub, s3_dash = (
#                     fallback_default_cat,
#                     "Suspense Account",
#                     "Suspense Dashboard",
#                 )

#             profile_votes.append({"cat": s3_cat, "sub": s3_sub, "score": s3_score})
#             wip_row.t3_category, wip_row.t3_subcategory = s3_cat, s3_sub

#             # STOP 4: Accounting Rule Book
#             s4_cat, s4_sub, s4_score, matched_rule_obj = None, None, 50, None
#             lookup_composite_key = (
#                 str(s1_cat or "").strip().lower(),
#                 str(s1_sub or "").strip().lower(),
#                 target_vector,
#             )

#             if lookup_composite_key in rules_by_composite_cache:
#                 rule_obj, rule_meta, true_cat, true_sub = rules_by_composite_cache[
#                     lookup_composite_key
#                 ]
#                 s4_cat = true_cat
#                 s4_sub = true_sub
#                 s4_score = 100
#                 matched_rule_obj = rule_obj
#             else:
#                 suspense_tuple = suspense_rules_by_vector[target_vector]
#                 if suspense_tuple:
#                     rule_obj, rule_meta, true_cat, true_sub = suspense_tuple
#                     s4_cat = true_cat if true_cat else fallback_default_cat
#                     s4_sub = true_sub if true_sub else "Suspense Account"
#                     matched_rule_obj = rule_obj
#                 else:
#                     s4_cat, s4_sub = fallback_default_cat, "Suspense Account"
#                     matched_rule_obj = None

#             profile_votes.append({"cat": s4_cat, "sub": s4_sub, "score": s4_score})

#             # 🏆 THE WEIGHTED AVERAGE ELECTION
#             candidate_combos = {}
#             for vote in profile_votes:
#                 combo_key = (vote["cat"], vote["sub"])
#                 candidate_combos[combo_key] = (
#                     candidate_combos.get(combo_key, 0) + vote["score"]
#                 )

#             winner_combo = max(candidate_combos, key=candidate_combos.get)
#             resolved_winner_cat, resolved_winner_sub = winner_combo[0], winner_combo[1]

#             total_score_accumulated = sum(v["score"] for v in profile_votes)
#             if total_score_accumulated >= 350:
#                 confidence_level = "HIGH"
#                 total_high += 1
#             elif total_score_accumulated >= 250:
#                 confidence_level = "MEDIUM"
#                 total_medium += 1
#             else:
#                 confidence_level = "LOW"
#                 total_low += 1

#             # 💾 Commit to Row
#             wip_row.resolved_category = resolved_winner_cat
#             wip_row.resolved_subcategory = resolved_winner_sub
#             wip_row.confidence_score = int((total_score_accumulated / 400) * 100)
#             wip_row.confidence_level = confidence_level
#             wip_row.evaluation_errors = []

#             wip_row.applied_rule = matched_rule_obj
#             wip_row.tier_1_passed = s1_score == 100
#             wip_row.tier_2_passed = s2_score == 100
#             wip_row.tier_3_passed = matched_rule_obj is not None

#             modified_wip_rows.append(wip_row)

#             # 🎯 BUILD JSON DATA RIGHT HERE IN THE FIRST LOOP (Zero Double-Looping!)
#             serialized_workspace_queue.append(
#                 {
#                     "wip_id": str(wip_row.id),
#                     "hash": wip_row.row_footprint_hash,
#                     "date": (
#                         wip_row.raw_statement_date.strftime("%Y-%m-%d")
#                         if wip_row.raw_statement_date
#                         else ""
#                     ),
#                     "narration": wip_row.staging_line.narration,
#                     "debit": debit_val,
#                     "credit": credit_val,
#                     "confidence": confidence_level,
#                     "score": wip_row.confidence_score,
#                     "errors": [],
#                     "routing_status": wip_row.staging_line.routing_status,
#                     "analysis": {
#                         "category_id": (
#                             wip_row.matched_category.id
#                             if wip_row.matched_category
#                             else None
#                         ),
#                         "category_item": (
#                             wip_row.matched_category.categories_items
#                             if wip_row.matched_category
#                             else resolved_winner_cat
#                         ),
#                         "dashboard_cat": (
#                             wip_row.matched_category.dashboard_cat
#                             if wip_row.matched_category
#                             else resolved_winner_cat
#                         ),
#                         "group": resolved_winner_cat,
#                         "subcategory": resolved_winner_sub,
#                         "rule_code": (
#                             matched_rule_obj.rule_code
#                             if matched_rule_obj
#                             else "System Match"
#                         ),
#                         "rule_title": (
#                             matched_rule_obj.rule_title
#                             if matched_rule_obj
#                             else "Classified via Composite Keywords Pipeline"
#                         ),
#                     },
#                 }
#             )

#         # ─── BLOCK 3: ATOMIC DATABASE WRITE BACK ───
#         if modified_wip_rows:
#             with transaction.atomic():
#                 WIPEvaluationMatrix.objects.bulk_update(
#                     modified_wip_rows,
#                     fields=[
#                         "t1_category",
#                         "t1_subcategory",
#                         "t2_category",
#                         "t2_subcategory",
#                         "t3_category",
#                         "t3_subcategory",
#                         "resolved_category",
#                         "resolved_subcategory",
#                         "confidence_score",
#                         "confidence_level",
#                         "evaluation_errors",
#                         "matched_category",
#                         "applied_rule",
#                         "tier_1_passed",
#                         "tier_2_passed",
#                         "tier_3_passed",
#                     ],
#                     batch_size=500,
#                 )

#         return {
#             "serialized_queue": serialized_workspace_queue,
#             "staged_for_bulk_high": total_high,
#             "staged_for_bulk_medium": total_medium,
#             "uncategorized_vault_zero": total_low,
#         }


# class WIPReconciliationEngine3:
#     """
#     🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE - VERSION 11.0
#     4-Stop Composite Predictive Matrix (Weighted Average Election Architecture)
#     """

#     @classmethod
#     def evaluate_account_queue(cls, account_id: int) -> dict:
#         # ─── BLOCK 1: PRE-COMPILE LOCAL CACHE MEMORY ───
#         master_categories = list(MasterFinancialCategory.objects.all())
#         accounting_rules = list(
#             AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
#         )

#         # Pre-Compile Accounting Rules Book Matrices
#         rules_by_composite_cache = {}
#         suspense_rules_by_vector = {"Debit": None, "Credit": None}

#         for rule in accounting_rules:
#             meta = {}
#             if rule.rule_metadata:
#                 if isinstance(rule.rule_metadata, dict):
#                     meta = rule.rule_metadata
#                 elif isinstance(rule.rule_metadata, str):
#                     try:
#                         meta = json.loads(rule.rule_metadata)
#                     except json.JSONDecodeError:
#                         meta = {}

#             rule_cat = str(meta.get("category") or "").strip()
#             rule_sub = str(meta.get("subcategory") or "").strip()
#             vector = rule.entry_type  # "Debit" or "Credit"

#             # Index using the 3-part composite key signature to prevent row overwriting
#             if rule_cat:
#                 rules_by_composite_cache[
#                     (rule_cat.lower(), rule_sub.lower(), vector)
#                 ] = (rule, meta, rule_cat, rule_sub)

#             # Isolate the explicit dynamic suspense rule rows configured by the user
#             if (
#                 "suspense" in rule_sub.lower()
#                 or "suspense" in str(rule.rule_title or "").lower()
#             ):
#                 if not suspense_rules_by_vector[vector]:
#                     suspense_rules_by_vector[vector] = (rule, meta, rule_cat, rule_sub)

#         # Pre-Compile Keywords Table
#         parsed_keywords = []
#         balance_sheet_map = {}  # Stop 3 lookup cache indexed by category_item

#         for m_cat in master_categories:
#             if isinstance(m_cat.keys, dict):
#                 k1 = (m_cat.keys.get("key1") or "").strip().lower()
#                 k2 = (m_cat.keys.get("key2") or "").strip().lower()
#             else:
#                 k1, k2 = "", ""
#             parsed_keywords.append((m_cat, k1, k2))

#             # Stop 3 indexing mapping: look up target strings via key1 names cleanly
#             cat_item_name = (
#                 str(m_cat.categories_items or m_cat.act_category or "").strip().lower()
#             )
#             if cat_item_name:
#                 balance_sheet_map[cat_item_name] = (
#                     str(m_cat.act_category or "").strip(),
#                     str(m_cat.act_subcategory or "").strip(),
#                     str(m_cat.dashboard_cat or "").strip(),
#                 )

#         # Fetch active WIP database lines using optimal prefetch parameters
#         active_wip_rows = WIPEvaluationMatrix.objects.filter(
#             account_id=account_id,
#             is_split_component=False,
#         ).select_related("staging_line", "matched_category", "applied_rule")

#         total_high = 0
#         total_medium = 0
#         total_low = 0
#         modified_wip_rows = []

#         # ─── BLOCK 2: THE 4-STOP SEQUENTIAL EVALUATION LOOP ───
#         for wip_row in active_wip_rows:
#             narration_clean = (wip_row.narration_normalized or "").strip().lower()

#             try:
#                 debit_val = float(wip_row.debit or 0)
#                 credit_val = float(wip_row.credit or 0)
#             except (ValueError, TypeError):
#                 debit_val, credit_val = 0.0, 0.0

#             is_credit_flow = credit_val > 0
#             target_vector = "Credit" if is_credit_flow else "Debit"
#             fallback_default_cat = "Income" if is_credit_flow else "Expenses"

#             # Instantiate tracking profiles for the 4 separate stops
#             profile_votes = []

#             # 🧩 STOP 1: KnownDefaultSource (Keywords Pass)
#             s1_cat, s1_sub, s1_score = None, None, 50
#             for cat_inst, k1, k2 in parsed_keywords:
#                 if not k1:
#                     continue

#                 # Structural directional validation boundaries
#                 if is_credit_flow and cat_inst.act_category.strip().lower() in [
#                     "expense",
#                     "expenses",
#                     "charity",
#                 ]:
#                     continue
#                 if debit_val > 0 and cat_inst.act_category.strip().lower() in [
#                     "income",
#                     "revenue",
#                 ]:
#                     continue

#                 is_match = False
#                 if len(k1) == 64:  # Cryptographic Token Check
#                     words = re.sub(r"[/:\-_,]", " ", narration_clean).split()
#                     is_match = any(
#                         hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
#                         for w in words
#                     )
#                 elif k1 in narration_clean:
#                     k2_clean = k2.replace(" ", "") if k2 else None
#                     if not k2_clean or (k2_clean in narration_clean.replace(" ", "")):
#                         is_match = True

#                 if is_match:
#                     s1_cat = cat_inst.act_category
#                     s1_sub = (
#                         cat_inst.act_subcategory
#                         if cat_inst.act_subcategory
#                         else cat_inst.act_category
#                     )
#                     s1_score = 100
#                     wip_row.matched_category = cat_inst
#                     break

#             if s1_score == 50:
#                 s1_cat, s1_sub = fallback_default_cat, "Suspense Account"

#             profile_votes.append({"cat": s1_cat, "sub": s1_sub, "score": s1_score})
#             wip_row.t1_category, wip_row.t1_subcategory = s1_cat, s1_sub

#             # 📊 STOP 2: SelfTransfer Source (Intra-Cash Asset Transfers)
#             s2_cat, s2_sub, s2_score = None, None, 50
#             # Context Note: Filter keywords specifically indicating internal wallet/bank balancing strings
#             if (
#                 "transfer" in narration_clean
#                 or "self" in narration_clean
#                 or "own account" in narration_clean
#             ):
#                 s2_cat = "Transfer"
#                 s2_sub = "Inter-Account Transfer"
#                 s2_score = 100
#             else:
#                 s2_cat, s2_sub = fallback_default_cat, "Suspense Account"

#             profile_votes.append({"cat": s2_cat, "sub": s2_sub, "score": s2_score})
#             wip_row.t2_category, wip_row.t2_subcategory = s2_cat, s2_sub

#             # ⚖️ STOP 3: BalanceSheetSourceRows (Meticulous Category Thorough Check)
#             s3_cat, s3_sub, s3_dash, s3_score = None, None, None, 50
#             lookup_target_key = str(s1_cat or "").strip().lower()

#             if lookup_target_key in balance_sheet_map:
#                 act_c, act_s, dash_c = balance_sheet_map[lookup_target_key]
#                 s3_cat = act_c
#                 s3_sub = act_s if act_s else act_c
#                 s3_dash = dash_c
#                 s3_score = 100
#             else:
#                 s3_cat, s3_sub, s3_dash = (
#                     fallback_default_cat,
#                     "Suspense Account",
#                     "Suspense Dashboard",
#                 )

#             profile_votes.append({"cat": s3_cat, "sub": s3_sub, "score": s3_score})
#             wip_row.t3_category, wip_row.t3_subcategory = s3_cat, s3_sub

#             # 📜 STOP 4: Accounting Rule Book Lookup & Binding
#             s4_cat, s4_sub, s4_score, matched_rule_obj = None, None, 50, None
#             lookup_composite_key = (
#                 str(s1_cat or "").strip().lower(),
#                 str(s1_sub or "").strip().lower(),
#                 target_vector,
#             )

#             if lookup_composite_key in rules_by_composite_cache:
#                 rule_obj, rule_meta, true_cat, true_sub = rules_by_composite_cache[
#                     lookup_composite_key
#                 ]
#                 s4_cat = true_cat
#                 s4_sub = true_sub
#                 s4_score = 100
#                 matched_rule_obj = rule_obj
#             else:
#                 # 🎯 THE SELF-SUFFICIENT INTELLIGENCE OVERRIDE:
#                 # If no rule exists, pull your official database Suspense row for this direction vector
#                 suspense_tuple = suspense_rules_by_vector[target_vector]
#                 if suspense_tuple:
#                     rule_obj, rule_meta, true_cat, true_sub = suspense_tuple
#                     # Force Stop 4 to vote for the database-configured Suspense categories
#                     s4_cat = true_cat if true_cat else fallback_default_cat
#                     s4_sub = true_sub if true_sub else "Suspense Account"
#                     matched_rule_obj = rule_obj
#                     s4_score = 100  # Give it full authority to align the row
#                 else:
#                     # Absolute hard fallback if even the database suspense row is missing
#                     s4_cat = fallback_default_cat
#                     s4_sub = "Suspense Account"
#                     matched_rule_obj = None
#                     s4_score = 50

#             profile_votes.append({"cat": s4_cat, "sub": s4_sub, "score": s4_score})

#             # 🏆 THE WEIGHTED AVERAGE ELECTION ARENA
#             # Calculate composite weightings to choose the ultimate display tokens
#             candidate_combos = {}
#             for vote in profile_votes:
#                 combo_key = (vote["cat"], vote["sub"])
#                 candidate_combos[combo_key] = (
#                     candidate_combos.get(combo_key, 0) + vote["score"]
#                 )

#             # Select the combo that earned the highest overall cumulative confidence score
#             winner_combo = max(candidate_combos, key=candidate_combos.get)
#             resolved_winner_cat, resolved_winner_sub = winner_combo[0], winner_combo[1]

#             # Determine aggregate confidence percentages (Max Score: 400 total)
#             total_score_accumulated = sum(v["score"] for v in profile_votes)
#             if total_score_accumulated >= 350:
#                 confidence_level = "HIGH"
#                 total_high += 1
#             elif total_score_accumulated >= 250:
#                 confidence_level = "MEDIUM"
#                 total_medium += 1
#             else:
#                 confidence_level = "LOW"
#                 total_low += 1

#             # 💾 Balance values straight down to database fields
#             wip_row.resolved_category = resolved_winner_cat
#             wip_row.resolved_subcategory = resolved_winner_sub
#             wip_row.confidence_score = int((total_score_accumulated / 400) * 100)
#             wip_row.confidence_level = confidence_level
#             wip_row.evaluation_errors = []

#             wip_row.applied_rule = matched_rule_obj
#             wip_row.tier_1_passed = s1_score == 100
#             wip_row.tier_2_passed = s2_score == 100
#             wip_row.tier_3_passed = matched_rule_obj is not None

#             modified_wip_rows.append(wip_row)

#         # ─── BLOCK 3: ATOMIC DATABASE WRITE BACK ───
#         if modified_wip_rows:
#             with transaction.atomic():
#                 WIPEvaluationMatrix.objects.bulk_update(
#                     modified_wip_rows,
#                     fields=[
#                         "t1_category",
#                         "t1_subcategory",
#                         "t2_category",
#                         "t2_subcategory",
#                         "t3_category",
#                         "t3_subcategory",
#                         "resolved_category",
#                         "resolved_subcategory",
#                         "confidence_score",
#                         "confidence_level",
#                         "evaluation_errors",
#                         "matched_category",
#                         "applied_rule",
#                         "tier_1_passed",
#                         "tier_2_passed",
#                         "tier_3_passed",
#                     ],
#                     batch_size=500,
#                 )

#         return {
#             "processed_rows": modified_wip_rows,
#             "staged_for_bulk_high": total_high,
#             "staged_for_bulk_medium": total_medium,
#             "uncategorized_vault_zero": total_low,
#         }


# class WIPReconciliationEngine1:
#     """
#     🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE - VERSION 9.5
#     Weighted Election Matrix Architecture (Zero-Error Ledger Purity)
#     """

#     @classmethod
#     def evaluate_account_queue(cls, account_id: int) -> dict:
#         # ─── BLOCK 1: PRE-COMPILE LOCAL CACHE MEMORY ───
#         master_categories = list(MasterFinancialCategory.objects.all())
#         accounting_rules = list(
#             AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
#         )

#         # Pre-Compile Accounting Rules & Index them by Metadata Intent
#         rules_by_category_cache = {}
#         suspense_rules_by_vector = {"Debit": None, "Credit": None}

#         for rule in accounting_rules:
#             # Safe Metadata Parsing
#             meta = {}
#             if rule.rule_metadata:
#                 if isinstance(rule.rule_metadata, dict):
#                     meta = rule.rule_metadata
#                 elif isinstance(rule.rule_metadata, str):
#                     try:
#                         meta = json.loads(rule.rule_metadata)
#                     except json.JSONDecodeError:
#                         meta = {}

#             rule_cat = str(meta.get("category") or "").strip()
#             rule_sub = str(meta.get("subcategory") or "").strip()
#             vector = rule.entry_type  # "Debit" or "Credit"

#             # Cache using lowercase keys for safe matching, mapping to original casing parameters
#             if rule_cat:
#                 rules_by_category_cache[(rule_cat.lower(), vector)] = (
#                     rule,
#                     meta,
#                     rule_cat,
#                     rule_sub,
#                 )

#             # Isolate the explicit dynamic suspense rule row
#             if (
#                 "suspense" in rule_sub.lower()
#                 or "suspense" in str(rule.rule_title or "").lower()
#             ):
#                 if not suspense_rules_by_vector[vector]:
#                     suspense_rules_by_vector[vector] = (rule, meta, rule_cat, rule_sub)

#         # Pre-Compile Keyword Token Maps
#         parsed_categories = []
#         for cat in master_categories:
#             if isinstance(cat.keys, dict):
#                 k1 = (cat.keys.get("key1") or "").strip().lower()
#                 k2 = (cat.keys.get("key2") or "").strip().lower()
#             else:
#                 k1, k2 = "", ""
#             parsed_categories.append((cat, k1, k2))

#         # Fetch active WIP records via optimal relational JOIN commands
#         active_wip_rows = WIPEvaluationMatrix.objects.filter(
#             account_id=account_id,
#             is_split_component=False,
#         ).select_related("staging_line", "matched_category", "applied_rule")

#         total_promoted_to_high = 0
#         total_promoted_to_medium = 0
#         total_failed_to_zero = 0
#         modified_wip_rows = []

#         # ─── BLOCK 2: SEQUENTIAL EVALUATION LOOP ───
#         for wip_row in active_wip_rows:
#             narration_clean = (wip_row.narration_normalized or "").strip().lower()

#             try:
#                 debit_val = float(wip_row.debit or 0)
#                 credit_val = float(wip_row.credit or 0)
#             except (ValueError, TypeError):
#                 debit_val, credit_val = 0.0, 0.0

#             is_credit_flow = credit_val > 0
#             target_vector = "Credit" if is_credit_flow else "Debit"

#             # Initialize candidate layers for the weighted election matrix
#             candidates = []
#             wip_row.t1_category, wip_row.t1_subcategory = None, None
#             wip_row.t2_category, wip_row.t2_subcategory = None, None
#             wip_row.t3_category, wip_row.t3_subcategory = None, None

#             # 🧩 TIER 1: KEYWORD EXTRACTOR PASS (Weight: 35)
#             for cat, k1, k2 in parsed_categories:
#                 if not k1:
#                     continue

#                 # Vector directional boundary constraint validations
#                 if is_credit_flow and cat.act_category.strip().lower() in [
#                     "expense",
#                     "expenses",
#                     "charity",
#                 ]:
#                     continue
#                 if debit_val > 0 and cat.act_category.strip().lower() in [
#                     "income",
#                     "revenue",
#                 ]:
#                     continue

#                 is_match = False
#                 if len(k1) == 64:  # SHA-256 Hashing Verification
#                     words = re.sub(r"[/:\-_,]", " ", narration_clean).split()
#                     is_match = any(
#                         hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
#                         for w in words
#                     )
#                 elif k1 in narration_clean:
#                     k2_clean = k2.replace(" ", "") if k2 else None
#                     if not k2_clean or (k2_clean in narration_clean.replace(" ", "")):
#                         is_match = True

#                 if is_match:
#                     candidates.append(
#                         {
#                             "tier": 1,
#                             "category": cat.act_category,
#                             "subcategory": cat.act_subcategory,
#                             "rule_obj": None,
#                             "weight": 35,
#                         }
#                     )
#                     wip_row.t1_category, wip_row.t1_subcategory = (
#                         cat.act_category,
#                         cat.act_subcategory,
#                     )
#                     break

#             # 📊 TIER 2: REPORTING GRID CONTEXT PASS (Weight: 15)
#             if candidates and candidates[-1]["tier"] == 1:
#                 t1_cand = candidates[-1]
#                 matched_cat_instance = next(
#                     (
#                         c
#                         for c, _, _ in parsed_categories
#                         if c.act_category == t1_cand["category"]
#                     ),
#                     None,
#                 )
#                 if (
#                     matched_cat_instance
#                     and matched_cat_instance.dashboard_cat
#                     and matched_cat_instance.dashboard_cat.strip()
#                 ):
#                     candidates.append(
#                         {
#                             "tier": 2,
#                             "category": t1_cand["category"],
#                             "subcategory": t1_cand["subcategory"],
#                             "rule_obj": None,
#                             "weight": 15,
#                         }
#                     )
#                     wip_row.t2_category, wip_row.t2_subcategory = (
#                         t1_cand["category"],
#                         t1_cand["subcategory"],
#                     )

#             # 📜 TIER 3: ACCOUNTING RULES METAMORPHOSIS PASS (Weight: 50)
#             if candidates:
#                 t1_cand = candidates[0]
#                 lookup_key = (t1_cand["category"].strip().lower(), target_vector)

#                 if lookup_key in rules_by_category_cache:
#                     rule_obj, rule_meta, true_cat, true_sub = rules_by_category_cache[
#                         lookup_key
#                     ]
#                     candidates.append(
#                         {
#                             "tier": 3,
#                             "category": true_cat,  # Preserves original casing format from database table row
#                             "subcategory": true_sub,  # Preserves original casing format from database table row
#                             "rule_obj": rule_obj,
#                             "weight": 50,
#                         }
#                     )
#                     wip_row.t3_category, wip_row.t3_subcategory = true_cat, true_sub
#                 else:
#                     # Tweak: Valid keyword matched, but category row entry is completely missing from rule metadata cache maps.
#                     # We leave rule_obj = None to completely prevent rule bleeding out to wrong elements.
#                     wip_row.t3_category = t1_cand["category"]
#                     wip_row.t3_subcategory = (
#                         t1_cand["subcategory"]
#                         if t1_cand["subcategory"]
#                         else t1_cand["category"]
#                     )

#             # 🏆 THE WEIGHTED RESOLUTION ELECTION (Cases 1, 2, 3, and 4)
#             winner_cat, winner_sub, matched_rule_obj = None, None, None
#             final_calculated_score = sum(c["weight"] for c in candidates)

#             if candidates:
#                 # 🥇 Cases 1, 2, 3: Sort by descending weight to let highest ranking tier assign outputs
#                 candidates.sort(key=lambda x: x["weight"], reverse=True)
#                 top_candidate = candidates[0]

#                 winner_cat = top_candidate["category"]
#                 winner_sub = (
#                     top_candidate["subcategory"]
#                     if top_candidate["subcategory"]
#                     else top_candidate["category"]
#                 )

#                 rule_candidate = next(
#                     (c for c in candidates if c["rule_obj"] is not None), None
#                 )
#                 matched_rule_obj = (
#                     rule_candidate["rule_obj"] if rule_candidate else None
#                 )

#                 confidence_level = "HIGH" if final_calculated_score >= 85 else "MEDIUM"
#             else:
#                 # 💥 Case 4: Complete Missing Link Fallback (Dynamic Vector Recalculation -> Suspense Fallback)
#                 confidence_level = "ZERO"
#                 final_calculated_score = 50

#                 suspense_tuple = suspense_rules_by_vector[target_vector]
#                 if suspense_tuple:
#                     rule_obj, rule_meta, true_cat, true_sub = suspense_tuple
#                     matched_rule_obj = rule_obj
#                     winner_cat = (
#                         true_cat
#                         if true_cat
#                         else ("Income" if is_credit_flow else "Expenses")
#                     )
#                     winner_sub = true_sub if true_sub else "Suspense Account"
#                 else:
#                     matched_rule_obj = None
#                     winner_cat = "Income" if is_credit_flow else "Expenses"
#                     winner_sub = "Suspense Account"

#                 wip_row.t3_category, wip_row.t3_subcategory = winner_cat, winner_sub

#             if confidence_level == "HIGH":
#                 total_promoted_to_high += 1
#             elif confidence_level == "MEDIUM":
#                 total_promoted_to_medium += 1
#             else:
#                 total_failed_to_zero += 1

#             # 💾 Commit perfectly balanced values down to data frame cells
#             wip_row.resolved_category = winner_cat
#             wip_row.resolved_subcategory = winner_sub
#             wip_row.confidence_score = final_calculated_score
#             wip_row.confidence_level = confidence_level
#             wip_row.evaluation_errors = []

#             # Retain linked relation identifiers safely
#             wip_row.applied_rule = matched_rule_obj
#             wip_row.tier_1_passed = wip_row.t1_category is not None
#             wip_row.tier_2_passed = wip_row.t2_category is not None
#             wip_row.tier_3_passed = matched_rule_obj is not None

#             modified_wip_rows.append(wip_row)

#         # ─── BLOCK 3: ATOMIC BULK TRANSACTION SAVE ───
#         if modified_wip_rows:
#             with transaction.atomic():
#                 WIPEvaluationMatrix.objects.bulk_update(
#                     modified_wip_rows,
#                     fields=[
#                         "t1_category",
#                         "t1_subcategory",
#                         "t2_category",
#                         "t2_subcategory",
#                         "t3_category",
#                         "t3_subcategory",
#                         "resolved_category",
#                         "resolved_subcategory",
#                         "confidence_score",
#                         "confidence_level",
#                         "evaluation_errors",
#                         "matched_category",
#                         "applied_rule",
#                         "tier_1_passed",
#                         "tier_2_passed",
#                         "tier_3_passed",
#                     ],
#                     batch_size=500,
#                 )

#         return {
#             "processed_rows": modified_wip_rows,
#             "staged_for_bulk_high": total_promoted_to_high,
#             "staged_for_bulk_medium": total_promoted_to_medium,
#             "uncategorized_vault_zero": total_failed_to_zero,
#         }


# class WIPReconciliationEngine2:
#     """
#     🤖 DECISION-TREE AUTOMATED AUTO-CATEGORIZATION ENGINE - VERSION 10.0
#     Composite Subcategory Tracking Matrix (Zero-Overwriting Purity)
#     """

#     @classmethod
#     def evaluate_account_queue(cls, account_id: int) -> dict:
#         # ─── BLOCK 1: PRE-COMPILE LOCAL CACHE MEMORY ───
#         master_categories = list(MasterFinancialCategory.objects.all())
#         accounting_rules = list(
#             AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
#         )

#         # Pre-Compile Accounting Rules & Index them by Multi-Field Metadata Composite Keys
#         rules_by_category_cache = {}
#         suspense_rules_by_vector = {"Debit": None, "Credit": None}

#         for rule in accounting_rules:
#             # Safe Metadata Parsing
#             meta = {}
#             if rule.rule_metadata:
#                 if isinstance(rule.rule_metadata, dict):
#                     meta = rule.rule_metadata
#                 elif isinstance(rule.rule_metadata, str):
#                     try:
#                         meta = json.loads(rule.rule_metadata)
#                     except json.JSONDecodeError:
#                         meta = {}

#             rule_cat = str(meta.get("category") or "").strip()
#             rule_sub = str(meta.get("subcategory") or "").strip()
#             vector = rule.entry_type  # "Debit" or "Credit"

#             # 🎯 THE CRITICAL STRUCTURAL FIX: Include Subcategory in the cache map key to stop rule overwriting!
#             if rule_cat:
#                 rules_by_category_cache[
#                     (rule_cat.lower(), rule_sub.lower(), vector)
#                 ] = (rule, meta, rule_cat, rule_sub)

#             # Isolate the explicit dynamic suspense rule row
#             if (
#                 "suspense" in rule_sub.lower()
#                 or "suspense" in str(rule.rule_title or "").lower()
#             ):
#                 if not suspense_rules_by_vector[vector]:
#                     suspense_rules_by_vector[vector] = (rule, meta, rule_cat, rule_sub)

#         # Pre-Compile Keyword Token Maps
#         parsed_categories = []
#         for cat in master_categories:
#             if isinstance(cat.keys, dict):
#                 k1 = (cat.keys.get("key1") or "").strip().lower()
#                 k2 = (cat.keys.get("key2") or "").strip().lower()
#             else:
#                 k1, k2 = "", ""
#             parsed_categories.append((cat, k1, k2))

#         # Fetch active WIP records via optimal relational JOIN commands
#         active_wip_rows = WIPEvaluationMatrix.objects.filter(
#             account_id=account_id,
#             is_split_component=False,
#         ).select_related("staging_line", "matched_category", "applied_rule")

#         total_promoted_to_high = 0
#         total_promoted_to_medium = 0
#         total_failed_to_zero = 0
#         modified_wip_rows = []

#         # ─── BLOCK 2: SEQUENTIAL EVALUATION LOOP ───
#         for wip_row in active_wip_rows:
#             narration_clean = (wip_row.narration_normalized or "").strip().lower()

#             try:
#                 debit_val = float(wip_row.debit or 0)
#                 credit_val = float(wip_row.credit or 0)
#             except (ValueError, TypeError):
#                 debit_val, credit_val = 0.0, 0.0

#             is_credit_flow = credit_val > 0
#             target_vector = "Credit" if is_credit_flow else "Debit"

#             # Initialize candidate layers for the weighted election matrix
#             candidates = []
#             wip_row.t1_category, wip_row.t1_subcategory = None, None
#             wip_row.t2_category, wip_row.t2_subcategory = None, None
#             wip_row.t3_category, wip_row.t3_subcategory = None, None

#             # 🧩 TIER 1: KEYWORD EXTRACTOR PASS (Weight: 35)
#             for cat, k1, k2 in parsed_categories:
#                 if not k1:
#                     continue

#                 if is_credit_flow and cat.act_category.strip().lower() in [
#                     "expense",
#                     "expenses",
#                     "charity",
#                 ]:
#                     continue
#                 if debit_val > 0 and cat.act_category.strip().lower() in [
#                     "income",
#                     "revenue",
#                 ]:
#                     continue

#                 is_match = False
#                 if len(k1) == 64:  # SHA-256 Check
#                     words = re.sub(r"[/:\-_,]", " ", narration_clean).split()
#                     is_match = any(
#                         hashlib.sha256(w.encode("utf-8")).hexdigest() == k1
#                         for w in words
#                     )
#                 elif k1 in narration_clean:
#                     k2_clean = k2.replace(" ", "") if k2 else None
#                     if not k2_clean or (k2_clean in narration_clean.replace(" ", "")):
#                         is_match = True

#                 if is_match:
#                     candidates.append(
#                         {
#                             "tier": 1,
#                             "category": cat.act_category,
#                             "subcategory": cat.act_subcategory,
#                             "rule_obj": None,
#                             "weight": 35,
#                         }
#                     )
#                     wip_row.t1_category, wip_row.t1_subcategory = (
#                         cat.act_category,
#                         cat.act_subcategory,
#                     )
#                     break

#             # 📊 TIER 2: REPORTING GRID CONTEXT PASS (Weight: 15)
#             if candidates and candidates[-1]["tier"] == 1:
#                 t1_cand = candidates[-1]
#                 matched_cat_instance = next(
#                     (
#                         c
#                         for c, _, _ in parsed_categories
#                         if c.act_category == t1_cand["category"]
#                     ),
#                     None,
#                 )
#                 if (
#                     matched_cat_instance
#                     and matched_cat_instance.dashboard_cat
#                     and matched_cat_instance.dashboard_cat.strip()
#                 ):
#                     candidates.append(
#                         {
#                             "tier": 2,
#                             "category": t1_cand["category"],
#                             "subcategory": t1_cand["subcategory"],
#                             "rule_obj": None,
#                             "weight": 15,
#                         }
#                     )
#                     wip_row.t2_category, wip_row.t2_subcategory = (
#                         t1_cand["category"],
#                         t1_cand["subcategory"],
#                     )

#             # 📜 TIER 3: ACCOUNTING RULES MATAMORPHOSIS PASS (Weight: 50)
#             if candidates:
#                 t1_cand = candidates[0]
#                 t1_sub_lookup = t1_cand["subcategory"] if t1_cand["subcategory"] else ""

#                 # 🎯 COMPOSITE MATCH: Find rule by looking up Category AND Subcategory explicitly
#                 lookup_key = (
#                     t1_cand["category"].strip().lower(),
#                     t1_sub_lookup.strip().lower(),
#                     target_vector,
#                 )

#                 if lookup_key in rules_by_category_cache:
#                     rule_obj, rule_meta, true_cat, true_sub = rules_by_category_cache[
#                         lookup_key
#                     ]
#                     candidates.append(
#                         {
#                             "tier": 3,
#                             "category": true_cat,
#                             "subcategory": true_sub,
#                             "rule_obj": rule_obj,
#                             "weight": 50,
#                         }
#                     )
#                     wip_row.t3_category, wip_row.t3_subcategory = true_cat, true_sub
#                 else:
#                     # Keep keyword category intact; leave rule_obj = None to prevent incorrect fallback bleeding
#                     wip_row.t3_category = t1_cand["category"]
#                     wip_row.t3_subcategory = (
#                         t1_cand["subcategory"]
#                         if t1_cand["subcategory"]
#                         else t1_cand["category"]
#                     )

#             # 🏆 THE WEIGHTED RESOLUTION ELECTION (Cases 1, 2, 3, and 4)
#             winner_cat, winner_sub, matched_rule_obj = None, None, None
#             final_calculated_score = sum(c["weight"] for c in candidates)

#             if candidates:
#                 candidates.sort(key=lambda x: x["weight"], reverse=True)
#                 top_candidate = candidates[0]

#                 winner_cat = top_candidate["category"]
#                 winner_sub = (
#                     top_candidate["subcategory"]
#                     if top_candidate["subcategory"]
#                     else top_candidate["category"]
#                 )

#                 rule_candidate = next(
#                     (c for c in candidates if c["rule_obj"] is not None), None
#                 )
#                 matched_rule_obj = (
#                     rule_candidate["rule_obj"] if rule_candidate else None
#                 )

#                 confidence_level = "HIGH" if final_calculated_score >= 85 else "MEDIUM"
#             else:
#                 # 💥 Case 4: Complete Missing Link Fallback (Dynamic Vector Recalculation -> Suspense Fallback)
#                 confidence_level = "ZERO"
#                 final_calculated_score = 50

#                 suspense_tuple = suspense_rules_by_vector[target_vector]
#                 if suspense_tuple:
#                     rule_obj, rule_meta, true_cat, true_sub = suspense_tuple
#                     matched_rule_obj = rule_obj
#                     winner_cat = (
#                         true_cat
#                         if true_cat
#                         else ("Income" if is_credit_flow else "Expenses")
#                     )
#                     winner_sub = true_sub if true_sub else "Suspense Account"
#                 else:
#                     matched_rule_obj = None
#                     winner_cat = "Income" if is_credit_flow else "Expenses"
#                     winner_sub = "Suspense Account"

#                 wip_row.t3_category, wip_row.t3_subcategory = winner_cat, winner_sub

#             if confidence_level == "HIGH":
#                 total_promoted_to_high += 1
#             elif confidence_level == "MEDIUM":
#                 total_promoted_to_medium += 1
#             else:
#                 total_failed_to_zero += 1

#             # 💾 Commit perfectly balanced values down to data frame cells
#             wip_row.resolved_category = winner_cat
#             wip_row.resolved_subcategory = winner_sub
#             wip_row.confidence_score = final_calculated_score
#             wip_row.confidence_level = confidence_level
#             wip_row.evaluation_errors = []

#             wip_row.applied_rule = matched_rule_obj
#             wip_row.tier_1_passed = wip_row.t1_category is not None
#             wip_row.tier_2_passed = wip_row.t2_category is not None
#             wip_row.tier_3_passed = matched_rule_obj is not None

#             modified_wip_rows.append(wip_row)

#         # ─── BLOCK 3: ATOMIC BULK TRANSACTION SAVE ───
#         if modified_wip_rows:
#             with transaction.atomic():
#                 WIPEvaluationMatrix.objects.bulk_update(
#                     modified_wip_rows,
#                     fields=[
#                         "t1_category",
#                         "t1_subcategory",
#                         "t2_category",
#                         "t2_subcategory",
#                         "t3_category",
#                         "t3_subcategory",
#                         "resolved_category",
#                         "resolved_subcategory",
#                         "confidence_score",
#                         "confidence_level",
#                         "evaluation_errors",
#                         "matched_category",
#                         "applied_rule",
#                         "tier_1_passed",
#                         "tier_2_passed",
#                         "tier_3_passed",
#                     ],
#                     batch_size=500,
#                 )

#         return {
#             "processed_rows": modified_wip_rows,
#             "staged_for_bulk_high": total_promoted_to_high,
#             "staged_for_bulk_medium": total_promoted_to_medium,
#             "uncategorized_vault_zero": total_failed_to_zero,
#         }
