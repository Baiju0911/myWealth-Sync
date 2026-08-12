# tracker/serviceWIP.py
import hashlib
import json
import re
import copy
from decimal import Decimal
from django.db import transaction
from collections import Counter
from .models.models import (
    StatementStagingLine,
    WIPEvaluationMatrix,
    MasterFinancialCategory,
    AccountingRule,
    DirectionalVectorOverride,
)
from django.apps import apps
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from .utils import run_in_parallel


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
            # 1. Fetch the pending staging lines using a row-level lock gate
            staging_queue = StatementStagingLine.objects.filter(
                account_id=account_context_id, routing_status="PENDING"
            ).select_for_update()

            # Perform a direct evaluate query scan count
            metrics["scanned"] = staging_queue.count()
            if metrics["scanned"] == 0:
                return metrics

            # 2. Track all active WIP states using the true row fingerprint identifiers
            existing_wip_hashes = set(
                WIPEvaluationMatrix.objects.filter(
                    account_id=account_context_id
                ).values_list("row_footprint_hash", flat=True)
            )

            wip_insertions = []
            staging_lines_to_update = []

            for row in staging_queue:
                # 🎯 Inherit the master identifier directly from the staging record
                row_hash = row.row_identifier

                # 🎯 THE SKIP GATEWAY FIX: Mark duplicates as COMPLETED so they drop out of the staging queue!
                if row_hash in existing_wip_hashes:
                    metrics["skipped"] += 1
                    row.routing_status = "COMPLETED"  # 👈 Clear it from staging
                    staging_lines_to_update.append(row)
                    continue

                dr_clean = row.debit if row.debit is not None else Decimal("0.00")
                cr_clean = row.credit if row.credit is not None else Decimal("0.00")

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
                wip_row.account_id = (
                    account_context_id  # Explicit foreign key binding safety
                )

                wip_insertions.append(wip_row)
                existing_wip_hashes.add(row_hash)

                # Move successful imports out of pending state
                row.routing_status = "COMPLETED"
                staging_lines_to_update.append(row)

            # =========================================================================
            # ⚡ EXECUTE SPEED BATCH WRITES TO DATABASE
            # =========================================================================
            if wip_insertions:
                WIPEvaluationMatrix.objects.bulk_create(wip_insertions, batch_size=1000)
                metrics["initialized"] = len(wip_insertions)

            if staging_lines_to_update:
                StatementStagingLine.objects.bulk_update(
                    staging_lines_to_update, fields=["routing_status"], batch_size=1000
                )

        return metrics


class WIPReconciliationEngine:
    _cached_sub_norm_map = None

    @staticmethod
    def resolve_directional_placement(
        credit_val: float, rule_subcategory: str
    ) -> tuple:
        category = "Income" if credit_val > 0 else "Expense"
        if not rule_subcategory:
            return category, "Suspense Account"

        clean = str(rule_subcategory).strip().lower()
        subcategory = (
            "Suspense Account"
            if clean in {"none", "expense", "expenses", "income", "incomes"}
            else str(rule_subcategory).strip()
        )
        return category, subcategory

    @staticmethod
    def _safe_subcategory(subcat: str) -> str:
        if not subcat:
            return "Suspense Account"
        clean = str(subcat).strip().lower()
        return (
            "Suspense Account"
            if clean in {"none", "expense", "expenses", "income", "incomes"}
            else str(subcat).strip()
        )

    # @classmethod
    # def get_sub_norm_map(cls) -> dict:
    #     """Lazy-loads subcategory normalization map from GR900 rules in DB."""
    #     if cls._cached_sub_norm_map is None:
    #         sub_map = {}
    #         norm_rules = AccountingRule.objects.filter(
    #             is_active=1, rule_code__startswith="GR90"
    #         )
    #         for rule in norm_rules:
    #             target_sub = rule.rule_metadata.get("subcategory")
    #             tags = rule.description_tags or []
    #             if target_sub and tags:
    #                 for tag in tags:
    #                     sub_map[tag.strip().lower()] = target_sub
    #         cls._cached_sub_norm_map = sub_map
    #     return cls._cached_sub_norm_map

    @classmethod
    def get_sub_norm_map(cls) -> dict:
        """Dynamically loads active subcategory normalization maps from GR900 series rules in DB."""
        sub_map = {}

        # Fetch active GR900 series normalizer rules
        norm_rules = AccountingRule.objects.filter(
            is_active__in=[1, "1"], rule_code__startswith="GR90"
        )

        for rule in norm_rules:
            # Safely handle JSON strings or dict payloads
            metadata = rule.rule_metadata
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            elif not isinstance(metadata, dict):
                metadata = {}

            target_sub = metadata.get("subcategory")

            # Safely handle description tags
            tags = rule.description_tags
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = []
            elif not isinstance(tags, list):
                tags = []

            if target_sub and tags:
                for tag in tags:
                    if tag and isinstance(tag, str):
                        sub_map[tag.strip().lower()] = target_sub.strip()

        return sub_map

    @classmethod
    def _build_sub_norm_lookup(cls) -> dict:
        """Builds a dynamic subcategory normalization map from GR900 series rules in DB."""
        sub_map = {}
        norm_rules = AccountingRule.objects.filter(
            is_active=1, rule_code__startswith="GR900"
        )
        for rule in norm_rules:
            target_sub = rule.rule_metadata.get("subcategory")
            if target_sub and rule.description_tags:
                for tag in rule.description_tags:
                    sub_map[tag.strip().lower()] = target_sub
        return sub_map

    # @classmethod
    # def _process_row_batch_older(
    #     cls,
    #     batch_data,
    #     t1_t2_dict,
    #     master_t1_t2_regex,
    #     t3_lookup,
    #     t4_translation_map,
    #     t4_text_lookup,
    #     master_t4_regex,
    # ):
    #     """
    #     ⚡ O(1) COMPLEXITY VECTOR EVALUATION WORKER
    #     Bypasses nested iterative search structures using master regex mapping arrays.
    #     """
    #     batch_queue = []
    #     computed_updates = []
    #     matrix_counts = {
    #         "t1_system": {"real": 0, "suspense": 0},
    #         "t2_internal": {"real": 0, "none": 0},
    #         "t3_layout": {"real": 0, "suspense": 0},
    #         "t4_rulebook": {"real": 0, "suspense_fallback": 0},
    #     }

    #     for row in batch_data:
    #         raw_narration = row["narration"] or ""
    #         narration_clean = raw_narration.strip().lower()
    #         debit_val = row["debit"]
    #         credit_val = row["credit"]

    #         # -----------------------------------------------------------------
    #         # TRACK 1 & 2: Fast Single-Pass Master Pattern Extraction
    #         # -----------------------------------------------------------------
    #         t1_cat, t1_sub = "None", "None"
    #         t1_hit = 0
    #         t1_raw_db_category = "None"
    #         t2_cat, t2_sub = "None", "None"
    #         t2_hit = 0

    #         if master_t1_t2_regex:
    #             match = master_t1_t2_regex.search(narration_clean)
    #             if match:
    #                 matched_keyword = match.group(1)
    #                 rules = t1_t2_dict.get(matched_keyword, [])

    #                 for rule in rules:
    #                     # Validate exact inner boundary condition checks
    #                     if rule["type"] == "KNOWN_DEFAULT" and t1_hit == 0:
    #                         if not rule["p2"] or rule["p2"].search(narration_clean):
    #                             db_cat = rule["act_category"]
    #                             t1_raw_db_category = db_cat
    #                             if db_cat and db_cat.lower() not in {
    #                                 "none",
    #                                 "",
    #                                 "income",
    #                                 "expenses",
    #                             }:
    #                                 t1_cat, t1_sub = db_cat, cls._safe_subcategory(
    #                                     rule["act_subcategory"]
    #                                 )
    #                             else:
    #                                 t1_cat, t1_sub = cls.resolve_directional_placement(
    #                                     credit_val, rule["act_subcategory"]
    #                                 )
    #                             t1_hit = 1

    #                     elif rule["type"] == "SELF_TRANSFER" and t2_hit == 0:
    #                         if not rule["p2"] or rule["p2"].search(narration_clean):
    #                             db_cat = rule["act_category"]
    #                             if db_cat and db_cat.strip() not in {"None", ""}:
    #                                 (
    #                                     t2_cat,
    #                                     t2_sub,
    #                                 ) = db_cat.strip(), cls._safe_subcategory(
    #                                     rule["act_subcategory"]
    #                                 )
    #                             else:
    #                                 t2_cat, t2_sub = cls.resolve_directional_placement(
    #                                     credit_val, rule["act_subcategory"]
    #                                 )
    #                             t2_hit = 1

    #         # Accumulate Track 1 metrics
    #         if t1_hit == 1 and "suspense" not in t1_sub.lower():
    #             matrix_counts["t1_system"]["real"] += 1
    #             t1_weight = 100
    #         else:
    #             if t1_hit == 0:
    #                 t1_cat, t1_sub = cls.resolve_directional_placement(
    #                     credit_val, "Suspense Account"
    #                 )
    #             matrix_counts["t1_system"]["suspense"] += 1
    #             t1_weight = 0

    #         # Accumulate Track 2 metrics
    #         if t2_hit == 1:
    #             matrix_counts["t2_internal"]["real"] += 1
    #             t2_weight = 100
    #         else:
    #             matrix_counts["t2_internal"]["none"] += 1
    #             t2_weight = 0

    #         # -----------------------------------------------------------------
    #         # TRACK 3: T3 - Ledger Layout Maps
    #         # -----------------------------------------------------------------
    #         t3_cat, t3_sub = "None", "None"
    #         t3_hit = 0
    #         search_target = (
    #             t1_raw_db_category if t1_raw_db_category != "None" else t1_cat
    #         )

    #         if search_target and search_target.lower() not in {
    #             "none",
    #             "income",
    #             "expenses",
    #             "suspense account",
    #         }:
    #             for layout_rule in t3_lookup.get(search_target.lower(), []):
    #                 db_row_cat = layout_rule["act_category"].strip().lower()
    #                 if (credit_val > 0 and "expense" in db_row_cat) or (
    #                     credit_val <= 0
    #                     and ("income" in db_row_cat or db_row_cat == "oci")
    #                 ):
    #                     continue
    #                 t3_cat = layout_rule["act_category"].strip()
    #                 t3_sub = layout_rule["act_subcategory"].strip()
    #                 t3_hit = 1
    #                 break

    #         if t3_hit == 1 and "suspense" not in t3_sub.lower():
    #             matrix_counts["t3_layout"]["real"] += 1
    #             t3_weight = 100
    #         else:
    #             if t3_hit == 0:
    #                 t3_cat, t3_sub = cls.resolve_directional_placement(
    #                     credit_val, "Suspense Account"
    #                 )
    #             matrix_counts["t3_layout"]["suspense"] += 1
    #             t3_weight = 0

    #         system_certainty_score = round((t1_weight + t2_weight + t3_weight) / 3.0, 2)

    #         # -----------------------------------------------------------------
    #         # TRACK 4: T4 - Master Rulebook (Supervisor Enforcer)
    #         # -----------------------------------------------------------------
    #         t4_cat, t4_sub = "None", "None"
    #         t4_hit = False
    #         meta_cat = meta_sub = ""
    #         matched_rule_id = None

    #         resolved_upstream = t1_cat.lower()
    #         if resolved_upstream in t4_translation_map:
    #             for rule_id, dir_type, metadata in t4_translation_map[
    #                 resolved_upstream
    #             ]:
    #                 if (dir_type == "credit" and credit_val <= 0) or (
    #                     dir_type == "debit" and debit_val <= 0
    #                 ):
    #                     continue
    #                 meta_cat = metadata.get("category", "").strip()
    #                 meta_sub = metadata.get("subcategory", "").strip()
    #                 t4_hit = True
    #                 matched_rule_id = rule_id
    #                 break

    #         if not t4_hit and master_t4_regex:
    #             t4_match = master_t4_regex.search(narration_clean)
    #             if t4_match:
    #                 matched_tag = t4_match.group(1)
    #                 for rule_id, dir_type, metadata in t4_text_lookup.get(
    #                     matched_tag, []
    #                 ):
    #                     if (dir_type == "credit" and credit_val <= 0) or (
    #                         dir_type == "debit" and debit_val <= 0
    #                     ):
    #                         continue
    #                     meta_cat = metadata.get("category", "").strip()
    #                     meta_sub = metadata.get("subcategory", "").strip()
    #                     t4_hit = True
    #                     matched_rule_id = rule_id
    #                     break

    #         if t4_hit:
    #             t4_cat = (
    #                 meta_cat
    #                 if (meta_cat and meta_cat.strip() not in {"", "None"})
    #                 else t1_cat
    #             )
    #             t4_sub = (
    #                 meta_sub
    #                 if (meta_sub and meta_sub.strip() not in {"", "None"})
    #                 else "Suspense Account"
    #             )
    #             matrix_counts["t4_rulebook"]["real"] += 1
    #         else:
    #             t4_cat, t4_sub = cls.resolve_directional_placement(
    #                 credit_val, "Suspense Account"
    #             )
    #             matrix_counts["t4_rulebook"]["suspense_fallback"] += 1

    #         final_resolved_cat = t4_cat if t4_hit else t1_cat
    #         final_resolved_sub = t4_sub if t4_hit else t1_sub

    #         # Format Date strings cleanly
    #         formatted_date = "-"
    #         raw_date = row["raw_statement_date"]
    #         if raw_date:
    #             if hasattr(raw_date, "strftime"):
    #                 formatted_date = raw_date.strftime("%d/%b-%Y")
    #             else:
    #                 try:
    #                     parsed_dt = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d")
    #                     formatted_date = parsed_dt.strftime("%d/%b-%Y")
    #                 except Exception:
    #                     formatted_date = str(raw_date)

    #         batch_queue.append(
    #             {
    #                 "wip_id": str(row["id"]),
    #                 "narration": raw_narration,
    #                 "txn_date": formatted_date,
    #                 "date": formatted_date,
    #                 "raw_statement_date": formatted_date,
    #                 "debit": debit_val,
    #                 "credit": credit_val,
    #                 "matrix_evaluation": {
    #                     "system_certainty_score": system_certainty_score,
    #                     "t1": {
    #                         "category": t1_cat,
    #                         "subcategory": t1_sub,
    #                         "weight": t1_weight,
    #                     },
    #                     "t2": {
    #                         "category": t2_cat,
    #                         "subcategory": t2_sub,
    #                         "weight": t2_weight,
    #                     },
    #                     "t3": {
    #                         "category": t3_cat,
    #                         "subcategory": t3_sub,
    #                         "weight": t3_weight,
    #                     },
    #                     "t4": {
    #                         "category": t4_cat,
    #                         "subcategory": t4_sub,
    #                         "hit": t4_hit,
    #                     },
    #                 },
    #             }
    #         )

    #         computed_updates.append(
    #             {
    #                 "id": row["id"],
    #                 "t1_category": t1_cat,
    #                 "t1_subcategory": t1_sub,
    #                 "t2_category": t2_cat,
    #                 "t2_subcategory": t2_sub,
    #                 "t3_category": t3_cat,
    #                 "t3_subcategory": t3_sub,
    #                 "resolved_category": final_resolved_cat,
    #                 "resolved_subcategory": final_resolved_sub,
    #                 "confidence_score": system_certainty_score,
    #                 "applied_rule_id": matched_rule_id,
    #                 "tier_1_passed": True,
    #                 "tier_2_passed": True,
    #                 "tier_3_passed": True,
    #                 "evaluation_errors": [],
    #             }
    #         )

    #     return batch_queue, computed_updates, matrix_counts

    @classmethod
    def _process_row_batch(
        cls,
        batch_data,
        t1_t2_dict,
        master_t1_t2_regex,
        t3_lookup,
        t4_translation_map,
        t4_text_lookup,
        master_t4_regex,
    ):
        """
        ⚡ O(1) COMPLEXITY VECTOR EVALUATION WORKER
        Bypasses nested iterative search structures using master regex mapping arrays.
        """
        batch_queue = []
        computed_updates = []
        matrix_counts = {
            "t1_system": {"real": 0, "suspense": 0},
            "t2_internal": {"real": 0, "none": 0},
            "t3_layout": {"real": 0, "suspense": 0},
            "t4_rulebook": {"real": 0, "suspense_fallback": 0},
        }

        # Defined dynamic financial baseline classes
        VALID_PRIMARY_CLASSES = {
            "asset",
            "liability",
            "expense",
            "expenses",
            "income",
            "transfer",
        }

        for row in batch_data:
            raw_narration = row["narration"] or ""
            narration_clean = raw_narration.strip().lower()
            debit_val = row["debit"]
            credit_val = row["credit"]

            # -----------------------------------------------------------------
            # TRACK 1 & 2: Fast Single-Pass Master Pattern Extraction
            # -----------------------------------------------------------------
            t1_cat, t1_sub = "None", "None"
            t1_hit = 0
            t1_raw_db_category = "None"
            t2_cat, t2_sub = "None", "None"
            t2_hit = 0

            if master_t1_t2_regex:
                match = master_t1_t2_regex.search(narration_clean)
                if match:
                    matched_keyword = match.group(1)
                    rules = t1_t2_dict.get(matched_keyword, [])

                    for rule in rules:
                        if rule["type"] == "KNOWN_DEFAULT" and t1_hit == 0:
                            if not rule["p2"] or rule["p2"].search(narration_clean):
                                db_cat = rule["act_category"]
                                t1_raw_db_category = db_cat
                                if db_cat and db_cat.lower() not in {
                                    "none",
                                    "",
                                    "income",
                                    "expenses",
                                }:
                                    t1_cat, t1_sub = db_cat, cls._safe_subcategory(
                                        rule["act_subcategory"]
                                    )
                                else:
                                    t1_cat, t1_sub = cls.resolve_directional_placement(
                                        credit_val, rule["act_subcategory"]
                                    )
                                t1_hit = 1

                        elif rule["type"] == "SELF_TRANSFER" and t2_hit == 0:
                            if not rule["p2"] or rule["p2"].search(narration_clean):
                                db_cat = rule["act_category"]
                                if db_cat and db_cat.strip() not in {"None", ""}:
                                    (
                                        t2_cat,
                                        t2_sub,
                                    ) = db_cat.strip(), cls._safe_subcategory(
                                        rule["act_subcategory"]
                                    )
                                else:
                                    t2_cat, t2_sub = cls.resolve_directional_placement(
                                        credit_val, rule["act_subcategory"]
                                    )
                                t2_hit = 1

            # Accumulate Track 1 metrics
            if t1_hit == 1 and "suspense" not in t1_sub.lower():
                matrix_counts["t1_system"]["real"] += 1
                t1_weight = 100
            else:
                if t1_hit == 0:
                    t1_cat, t1_sub = cls.resolve_directional_placement(
                        credit_val, "Suspense Account"
                    )
                matrix_counts["t1_system"]["suspense"] += 1
                t1_weight = 0

            # Accumulate Track 2 metrics
            if t2_hit == 1:
                matrix_counts["t2_internal"]["real"] += 1
                t2_weight = 100
            else:
                matrix_counts["t2_internal"]["none"] += 1
                t2_weight = 0

            # -----------------------------------------------------------------
            # TRACK 3: T3 - Ledger Layout Maps
            # -----------------------------------------------------------------
            t3_cat, t3_sub = "None", "None"
            t3_hit = 0
            search_target = (
                t1_raw_db_category if t1_raw_db_category != "None" else t1_cat
            )

            if search_target and search_target.lower() not in {
                "none",
                "income",
                "expenses",
                "suspense account",
            }:
                for layout_rule in t3_lookup.get(search_target.lower(), []):
                    db_row_cat = layout_rule["act_category"].strip().lower()
                    if (credit_val > 0 and "expense" in db_row_cat) or (
                        credit_val <= 0
                        and ("income" in db_row_cat or db_row_cat == "oci")
                    ):
                        continue
                    t3_cat = layout_rule["act_category"].strip()
                    t3_sub = layout_rule["act_subcategory"].strip()
                    t3_hit = 1
                    break

            if t3_hit == 1 and "suspense" not in t3_sub.lower():
                matrix_counts["t3_layout"]["real"] += 1
                t3_weight = 100
            else:
                if t3_hit == 0:
                    t3_cat, t3_sub = cls.resolve_directional_placement(
                        credit_val, "Suspense Account"
                    )
                matrix_counts["t3_layout"]["suspense"] += 1
                t3_weight = 0

            system_certainty_score = round((t1_weight + t2_weight + t3_weight) / 3.0, 2)

            # -----------------------------------------------------------------
            # TRACK 4: T4 - Master Rulebook (Direct Narration Pattern Search)
            # -----------------------------------------------------------------
            t4_cat, t4_sub = "None", "None"
            t4_hit = False
            meta_cat = meta_sub = ""
            matched_rule_id = None

            # Direct Narration Regex Search against 52 Golden Rules
            if master_t4_regex:
                t4_match = master_t4_regex.search(narration_clean)
                if t4_match:
                    matched_tag = t4_match.group(1)
                    for rule_id, dir_type, metadata in t4_text_lookup.get(
                        matched_tag, []
                    ):
                        if (dir_type == "credit" and credit_val <= 0) or (
                            dir_type == "debit" and debit_val <= 0
                        ):
                            continue
                        meta_cat = metadata.get("category", "").strip()
                        meta_sub = metadata.get("subcategory", "").strip()
                        t4_hit = True
                        matched_rule_id = rule_id
                        break

            # Secondary Lookup: Fallback on Upstream Category if Narration missed
            if not t4_hit:
                resolved_upstream = t1_cat.lower()
                if resolved_upstream in t4_translation_map:
                    for rule_id, dir_type, metadata in t4_translation_map[
                        resolved_upstream
                    ]:
                        if (dir_type == "credit" and credit_val <= 0) or (
                            dir_type == "debit" and debit_val <= 0
                        ):
                            continue
                        meta_cat = metadata.get("category", "").strip()
                        meta_sub = metadata.get("subcategory", "").strip()
                        t4_hit = True
                        matched_rule_id = rule_id
                        break

            if t4_hit:
                t4_cat = (
                    meta_cat
                    if meta_cat and meta_cat.strip() not in {"", "None"}
                    else t1_cat
                )
                t4_sub = (
                    meta_sub
                    if meta_sub and meta_sub.strip() not in {"", "None"}
                    else "Suspense Account"
                )
                matrix_counts["t4_rulebook"]["real"] += 1
            else:
                t4_cat, t4_sub = cls.resolve_directional_placement(
                    credit_val, "Suspense Account"
                )
                matrix_counts["t4_rulebook"]["suspense_fallback"] += 1

            # -----------------------------------------------------------------
            # 🎯 DYNAMIC HIERARCHICAL RESOLUTION (NO HARDCODING)
            # -----------------------------------------------------------------
            # Rule 1: Direct Golden Rule hit always wins
            if t4_hit:
                final_resolved_cat = t4_cat
                final_resolved_sub = t4_sub
            # Rule 2: Inter-account / Self-transfers (Tier 2) win over default rules
            elif t2_hit and t2_cat.lower() in VALID_PRIMARY_CLASSES:
                final_resolved_cat = t2_cat
                final_resolved_sub = t2_sub
            # Rule 3: Tier 1 match is valid ONLY IF it mapped to a true primary financial class
            elif t1_hit and t1_cat.lower() in VALID_PRIMARY_CLASSES:
                final_resolved_cat = t1_cat
                final_resolved_sub = t1_sub
            # Rule 4: Tier 3 layout map is valid IF it mapped to a true primary financial class
            elif t3_hit and t3_cat.lower() in VALID_PRIMARY_CLASSES:
                final_resolved_cat = t3_cat
                final_resolved_sub = t3_sub
            # Rule 5: Pure Fallback -> Directional Placement (Expense / Income)
            else:
                final_resolved_cat, final_resolved_sub = (
                    cls.resolve_directional_placement(credit_val, "Suspense Account")
                )

            norm_map = WIPReconciliationEngine.get_sub_norm_map()

            # Force singular 'Expense' across all resolution paths
            if final_resolved_cat and final_resolved_cat.strip().lower() in {
                "expenses",
                "expense",
            }:
                final_resolved_cat = "Expense"

            # 2. Normalize Legacy Subcategories via GR900 DB Map
            if final_resolved_sub:
                clean_sub_lower = final_resolved_sub.strip().lower()
                if clean_sub_lower in norm_map:
                    final_resolved_sub = norm_map[clean_sub_lower]

            # Format Date strings cleanly
            formatted_date = "-"
            raw_date = row["raw_statement_date"]
            if raw_date:
                if hasattr(raw_date, "strftime"):
                    formatted_date = raw_date.strftime("%d/%b-%Y")
                else:
                    try:
                        parsed_dt = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d")
                        formatted_date = parsed_dt.strftime("%d/%b-%Y")
                    except Exception:
                        formatted_date = str(raw_date)

            batch_queue.append(
                {
                    "wip_id": str(row["id"]),
                    "narration": raw_narration,
                    "txn_date": formatted_date,
                    "date": formatted_date,
                    "raw_statement_date": formatted_date,
                    "debit": debit_val,
                    "credit": credit_val,
                    "matrix_evaluation": {
                        "system_certainty_score": system_certainty_score,
                        "t1": {
                            "category": t1_cat,
                            "subcategory": t1_sub,
                            "weight": t1_weight,
                        },
                        "t2": {
                            "category": t2_cat,
                            "subcategory": t2_sub,
                            "weight": t2_weight,
                        },
                        "t3": {
                            "category": t3_cat,
                            "subcategory": t3_sub,
                            "weight": t3_weight,
                        },
                        "t4": {
                            "category": t4_cat,
                            "subcategory": t4_sub,
                            "hit": t4_hit,
                        },
                    },
                }
            )

            computed_updates.append(
                {
                    "id": row["id"],
                    "t1_category": t1_cat,
                    "t1_subcategory": t1_sub,
                    "t2_category": t2_cat,
                    "t2_subcategory": t2_sub,
                    "t3_category": t3_cat,
                    "t3_subcategory": t3_sub,
                    "resolved_category": final_resolved_cat,
                    "resolved_subcategory": final_resolved_sub,
                    "confidence_score": system_certainty_score,
                    "applied_rule_id": matched_rule_id,
                    "tier_1_passed": True,
                    "tier_2_passed": True,
                    "tier_3_passed": True,
                    "evaluation_errors": [],
                }
            )

        return batch_queue, computed_updates, matrix_counts

    @classmethod
    def evaluate_account_queue(cls, account_id: int) -> dict:

        # =========================================================================
        # 🏗️ OPTIMIZED MASTER SINGLE-PASS REGEX COMPILATION
        # =========================================================================
        t1_t2_dict = {}
        t1_t2_keywords = set()

        for m_cat in MasterFinancialCategory.objects.filter(
            category_type__in=["KNOWN_DEFAULT", "SELF_TRANSFER"]
        ).values("act_category", "act_subcategory", "keys", "category_type"):
            keys_dict = m_cat["keys"]
            if isinstance(keys_dict, dict) and keys_dict.get("key1"):
                k1 = keys_dict["key1"].strip().lower()
                k2 = (keys_dict.get("key2") or "").strip().lower()

                t1_t2_dict.setdefault(k1, []).append(
                    {
                        "type": m_cat["category_type"],
                        "p2": re.compile(r"\b" + re.escape(k2) + r"\b") if k2 else None,
                        "act_category": (m_cat["act_category"] or "").strip(),
                        "act_subcategory": (m_cat["act_subcategory"] or "").strip(),
                    }
                )
                t1_t2_keywords.add(re.escape(k1))

        master_t1_t2_regex = (
            re.compile(r"\b(" + "|".join(t1_t2_keywords) + r")\b")
            if t1_t2_keywords
            else None
        )

        t3_lookup = {}
        for m_cat in MasterFinancialCategory.objects.filter(
            category_type="REGULAR"
        ).values("categories_items", "act_category", "act_subcategory"):
            target = (m_cat["categories_items"] or "").strip().lower()
            if target:
                t3_lookup.setdefault(target, []).append(
                    {
                        "act_category": (m_cat["act_category"] or "None"),
                        "act_subcategory": (m_cat["act_subcategory"] or "None"),
                    }
                )

        t4_translation_map = {}
        t4_text_lookup = {}
        t4_keywords = set()

        for rule_inst in AccountingRule.objects.filter(is_active="1").values(
            "id", "description_tags", "rule_metadata", "entry_type"
        ):
            tags = rule_inst["description_tags"]
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = []
            metadata = rule_inst["rule_metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}

            dir_type = (rule_inst["entry_type"] or "").strip().lower()
            rule_id = rule_inst["id"]

            for tag in tags or []:
                if tag:
                    t_clean = str(tag).strip().lower()
                    t4_translation_map.setdefault(t_clean, []).append(
                        (rule_id, dir_type, metadata)
                    )
                    t4_text_lookup.setdefault(t_clean, []).append(
                        (rule_id, dir_type, metadata)
                    )
                    t4_keywords.add(re.escape(t_clean))

        master_t4_regex = (
            re.compile(r"\b(" + "|".join(t4_keywords) + r")\b") if t4_keywords else None
        )

        # =========================================================================
        # 📥 DATA POOL EXTRACTION (🎯 ACCELERATED DIFFERENTIAL SELECTION)
        # =========================================================================
        raw_rows = list(
            WIPEvaluationMatrix.objects.filter(
                account_id=account_id,
                is_split_component=False,
                processing_status="PENDING",
                tier_1_passed=False,
            )
            .select_related("staging_line")
            .values(
                "id", "debit", "credit", "raw_statement_date", "staging_line__narration"
            )
        )

        total_rows = len(raw_rows)

        # 🎯 THE VIEW RETENTION SAFE GUARD: If everything is already processed,
        # load the active cache directly to unblock layout rendering.
        if total_rows == 0:
            existing_active_rows = list(
                WIPEvaluationMatrix.objects.filter(
                    account_id=account_id,
                    is_split_component=False,
                    processing_status="PENDING",
                )
                .select_related("staging_line")
                .values(
                    "id",
                    "debit",
                    "credit",
                    "raw_statement_date",
                    "staging_line__narration",
                    "t1_category",
                    "t1_subcategory",
                    "t2_category",
                    "t2_subcategory",
                    "t3_category",
                    "t3_subcategory",
                    "resolved_category",
                    "resolved_subcategory",
                    "confidence_score",
                    "applied_rule_id",
                )
            )

            final_queue = []
            for r in existing_active_rows:
                formatted_date = "-"
                raw_date = r["raw_statement_date"]
                if raw_date:
                    if hasattr(raw_date, "strftime"):
                        formatted_date = raw_date.strftime("%d/%b-%Y")
                    else:
                        try:
                            parsed_dt = datetime.strptime(
                                str(raw_date).strip(), "%Y-%m-%d"
                            )
                            formatted_date = parsed_dt.strftime("%d/%b-%Y")
                        except Exception:
                            formatted_date = str(raw_date)

                final_queue.append(
                    {
                        "wip_id": str(r["id"]),
                        "narration": r["staging_line__narration"] or "",
                        "txn_date": formatted_date,
                        "date": formatted_date,
                        "raw_statement_date": formatted_date,
                        "debit": float(r["debit"] or 0),
                        "credit": float(r["credit"] or 0),
                        "matrix_evaluation": {
                            "system_certainty_score": float(r["confidence_score"] or 0),
                            "t1": {
                                "category": r["t1_category"] or "None",
                                "subcategory": r["t1_subcategory"] or "None",
                                "weight": 100 if r["t1_category"] else 0,
                            },
                            "t2": {
                                "category": r["t2_category"] or "None",
                                "subcategory": r["t2_subcategory"] or "None",
                                "weight": 100 if r["t2_category"] else 0,
                            },
                            "t3": {
                                "category": r["t3_category"] or "None",
                                "subcategory": r["t3_subcategory"] or "None",
                                "weight": 100 if r["t3_category"] else 0,
                            },
                            "t4": {
                                "category": r["resolved_category"] or "None",
                                "subcategory": r["resolved_subcategory"] or "None",
                                "hit": bool(r["applied_rule_id"]),
                            },
                        },
                    }
                )

            total_active = len(final_queue)
            return {
                "workspace_queue": final_queue,
                "matrix_summary_stats": {
                    "t1_system": {"real": total_active, "suspense": 0},
                    "t2_internal": {"real": total_active, "suspense": 0},
                    "t3_layout": {"real": total_active, "suspense": 0},
                    "t4_rulebook": {"real": total_active, "suspense": 0},
                    "total_processed": total_active,
                },
            }

        thread_payload = []
        for r in raw_rows:
            try:
                d_val = float(r["debit"] or 0)
                c_val = float(r["credit"] or 0)
            except (ValueError, TypeError):
                d_val = c_val = 0.0

            thread_payload.append(
                {
                    "id": r["id"],
                    "debit": d_val,
                    "credit": c_val,
                    "raw_statement_date": r["raw_statement_date"],
                    "narration": r["staging_line__narration"] or "",
                }
            )

        # =========================================================================
        # 🚀 THREAD POOL HANDOFF (Safe pickling parameters)
        # =========================================================================
        caching_indexes = (
            t1_t2_dict,
            master_t1_t2_regex,
            t3_lookup,
            t4_translation_map,
            t4_text_lookup,
            master_t4_regex,
        )

        thread_responses = run_in_parallel(
            payload_list=thread_payload,
            worker_func=cls._process_row_batch,
            extra_args=caching_indexes,
            max_workers=4,
        )

        # =========================================================================
        # 📥 UNPACK ARTIFACTS
        # =========================================================================
        final_queue = []
        all_db_updates = []
        matrix_summary_stats = {
            "t1_system": {"real": 0, "suspense": 0},
            "t2_internal": {"real": 0, "suspense": 0},
            "t3_layout": {"real": 0, "suspense": 0},
            "t4_rulebook": {"real": 0, "suspense": 0},
            "total_processed": total_rows,
        }

        for batch_queue, batch_updates, batch_counts in thread_responses:
            final_queue.extend(batch_queue)
            all_db_updates.extend(batch_updates)

            for tier in ["t1_system", "t2_internal", "t3_layout"]:
                matrix_summary_stats[tier]["real"] += batch_counts[tier]["real"]
                matrix_summary_stats[tier]["suspense"] += batch_counts[tier].get(
                    "suspense", 0
                )

            matrix_summary_stats["t2_internal"]["suspense"] += batch_counts[
                "t2_internal"
            ].get("none", 0)
            matrix_summary_stats["t4_rulebook"]["real"] += batch_counts["t4_rulebook"][
                "real"
            ]
            matrix_summary_stats["t4_rulebook"]["suspense"] += batch_counts[
                "t4_rulebook"
            ].get("suspense_fallback", 0)

        # =========================================================================
        # ⚡ HIGH-SPEED IN-MEMORY DATABASE SHELL WRITEBACK COMMIT
        # =========================================================================
        with transaction.atomic():
            objs_to_update = []
            for update in all_db_updates:
                obj = WIPEvaluationMatrix(id=update["id"])
                obj.t1_category = update["t1_category"]
                obj.t1_subcategory = update["t1_subcategory"]
                obj.t2_category = update["t2_category"]
                obj.t2_subcategory = update["t2_subcategory"]
                obj.t3_category = update["t3_category"]
                obj.t3_subcategory = update["t3_subcategory"]
                obj.resolved_category = update["resolved_category"]
                obj.resolved_subcategory = update["resolved_subcategory"]
                obj.confidence_score = update["confidence_score"]
                obj.applied_rule_id = update["applied_rule_id"]
                obj.tier_1_passed = update["tier_1_passed"]
                obj.tier_2_passed = update["tier_2_passed"]
                obj.tier_3_passed = update["tier_3_passed"]
                obj.evaluation_errors = update["evaluation_errors"]
                objs_to_update.append(obj)

            WIPEvaluationMatrix.objects.bulk_update(
                objs_to_update,
                fields=[
                    "t1_category",
                    "t1_subcategory",
                    "t2_category",
                    "t2_subcategory",
                    "t3_category",
                    "t3_subcategory",
                    "resolved_category",
                    "resolved_subcategory",
                    "confidence_score",
                    "applied_rule_id",
                    "tier_1_passed",
                    "tier_2_passed",
                    "tier_3_passed",
                    "evaluation_errors",
                ],
                batch_size=2000,
            )

        return {
            "workspace_queue": final_queue,
            "matrix_summary_stats": matrix_summary_stats,
        }
