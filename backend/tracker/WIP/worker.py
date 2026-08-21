import logging
import time
from datetime import datetime

from tracker.ai.services.ai_rule_trainer_engine import AIRuleTrainerEngine
from .helpers import WIPHelpers
from ..classification.utils.taxonomy_gate import resolve_official_taxonomy

logger = logging.getLogger(__name__)

VALID_PRIMARY_CLASSES = {
    "asset",
    "liability",
    "expense",
    "expenses",
    "income",
    "transfer",
}


def process_row_batch_worker(
    batch_data,
    t1_t2_dict,
    master_t1_t2_regex,
    t3_lookup,
    t4_translation_map,
    t4_text_lookup,
    master_t4_regex,
):
    """⚡ O(1) COMPLEXITY VECTOR EVALUATION WORKER.

    Processes every row in the provided batch queue without artificial batch
    capping using the unified AIRuleTrainerEngine.
    """
    batch_queue = []
    computed_updates = []
    matrix_counts = {
        "t1_system": {"real": 0, "suspense": 0},
        "t2_internal": {"real": 0, "none": 0},
        "t3_layout": {"real": 0, "suspense": 0},
        "t4_rulebook": {"real": 0, "suspense_fallback": 0},
        "t5_ai": {"real": 0, "suspense": 0},
    }

    # Iterate through the complete batch queue passed to this worker
    for idx, row in enumerate(batch_data, 1):
        row_start_time = time.time()
        raw_narration = row["narration"] or ""
        narration_clean = raw_narration.strip().lower()
        debit_val = row["debit"]
        credit_val = row["credit"]

        # -----------------------------------------------------------------
        # TRACK 1 & 2: Regex Pattern Extraction
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
                                t1_cat, t1_sub = (
                                    db_cat,
                                    WIPHelpers.safe_subcategory(
                                        rule["act_subcategory"]
                                    ),
                                )
                            else:
                                t1_cat, t1_sub = (
                                    WIPHelpers.resolve_directional_placement(
                                        credit_val, rule["act_subcategory"]
                                    )
                                )
                            t1_hit = 1

                    elif rule["type"] == "SELF_TRANSFER" and t2_hit == 0:
                        if not rule["p2"] or rule["p2"].search(narration_clean):
                            db_cat = rule["act_category"]
                            if db_cat and db_cat.strip() not in {"None", ""}:
                                t2_cat, t2_sub = (
                                    db_cat.strip(),
                                    WIPHelpers.safe_subcategory(
                                        rule["act_subcategory"]
                                    ),
                                )
                            else:
                                t2_cat, t2_sub = (
                                    WIPHelpers.resolve_directional_placement(
                                        credit_val, rule["act_subcategory"]
                                    )
                                )
                            t2_hit = 1

        if t1_hit == 1 and "suspense" not in t1_sub.lower():
            matrix_counts["t1_system"]["real"] += 1
            t1_weight = 100
        else:
            if t1_hit == 0:
                t1_cat, t1_sub = WIPHelpers.resolve_directional_placement(
                    credit_val, "Suspense Account"
                )
            matrix_counts["t1_system"]["suspense"] += 1
            t1_weight = 0

        if t2_hit == 1:
            matrix_counts["t2_internal"]["real"] += 1
            t2_weight = 100
        else:
            matrix_counts["t2_internal"]["none"] += 1
            t2_weight = 0

        # -----------------------------------------------------------------
        # TRACK 3: Ledger Layout Maps
        # -----------------------------------------------------------------
        t3_cat, t3_sub = "None", "None"
        t3_hit = 0
        search_target = t1_raw_db_category if t1_raw_db_category != "None" else t1_cat

        if search_target and search_target.lower() not in {
            "none",
            "income",
            "expenses",
            "suspense account",
        }:
            for layout_rule in t3_lookup.get(search_target.lower(), []):
                db_row_cat = layout_rule["act_category"].strip().lower()
                if (credit_val > 0 and "expense" in db_row_cat) or (
                    credit_val <= 0 and ("income" in db_row_cat or db_row_cat == "oci")
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
                t3_cat, t3_sub = WIPHelpers.resolve_directional_placement(
                    credit_val, "Suspense Account"
                )
            matrix_counts["t3_layout"]["suspense"] += 1
            t3_weight = 0

        system_certainty_score = round((t1_weight + t2_weight + t3_weight) / 3.0, 2)

        # -----------------------------------------------------------------
        # TRACK 4: Master Rulebook
        # -----------------------------------------------------------------
        t4_cat, t4_sub = "None", "None"
        t4_hit = False
        meta_cat = meta_sub = ""
        matched_rule_id = None

        if master_t4_regex:
            t4_match = master_t4_regex.search(narration_clean)
            if t4_match:
                matched_tag = t4_match.group(1)
                for rule_id, dir_type, metadata in t4_text_lookup.get(matched_tag, []):
                    if (dir_type == "credit" and credit_val <= 0) or (
                        dir_type == "debit" and debit_val <= 0
                    ):
                        continue
                    meta_cat = metadata.get("category", "").strip()
                    meta_sub = metadata.get("subcategory", "").strip()
                    t4_hit = True
                    matched_rule_id = rule_id
                    break

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
            t4_cat, t4_sub = WIPHelpers.resolve_directional_placement(
                credit_val, "Suspense Account"
            )
            matrix_counts["t4_rulebook"]["suspense_fallback"] += 1

        # -----------------------------------------------------------------
        # TRACK 5 & DYNAMIC RESOLUTION (CENTRALIZED AI ENGINE)
        # -----------------------------------------------------------------
        t5_cat, t5_sub = "None", "None"
        t5_hit = False
        t5_source = "bypassed"
        has_deterministic_match = False

        if t4_hit:
            raw_resolved_cat, raw_resolved_sub = t4_cat, t4_sub
            has_deterministic_match = True
            rule_source = matched_rule_id or "T4_GOLDEN_RULE"
        elif t2_hit and t2_cat.lower() in VALID_PRIMARY_CLASSES:
            raw_resolved_cat, raw_resolved_sub = t2_cat, t2_sub
            has_deterministic_match = True
            rule_source = "T2_SELF_TRANSFER"
        elif t1_hit and t1_cat.lower() in VALID_PRIMARY_CLASSES:
            raw_resolved_cat, raw_resolved_sub = t1_cat, t1_sub
            has_deterministic_match = True
            rule_source = "T1_SYSTEM_DEFAULT"
        elif t3_hit and t3_cat.lower() in VALID_PRIMARY_CLASSES:
            raw_resolved_cat, raw_resolved_sub = t3_cat, t3_sub
            has_deterministic_match = True
            rule_source = "T3_LAYOUT_MAP"

        if has_deterministic_match:
            # 🟢 AUTO-SEED DETERMINISTIC HITS THROUGH UNIFIED ENGINE
            (
                final_resolved_cat,
                final_resolved_sub,
                t5_source,
                is_valid,
            ) = AIRuleTrainerEngine.auto_seed_deterministic_hit(
                raw_narration=raw_narration,
                raw_resolved_cat=raw_resolved_cat,
                raw_resolved_sub=raw_resolved_sub,
                rule_source=rule_source,
            )
            t5_cat, t5_sub = final_resolved_cat, final_resolved_sub
            t5_hit = True
        else:
            # 🔴 CLASSIFY VIA UNIFIED AI ENGINE (Fast Vector DB + Ollama Fallback)
            t5_start_time = time.time()
            ai_res = AIRuleTrainerEngine.classify(raw_narration)
            t5_elapsed = round(time.time() - t5_start_time, 4)
            score = ai_res.get("confidence_score", 0.0)

            if ai_res.get("is_trained") and score >= 0.85:
                final_resolved_cat = ai_res.get("category", "Expense")
                final_resolved_sub = ai_res.get("subcategory", "AI Unclassified")
                system_certainty_score = int(score * 100)
                t5_cat, t5_sub = final_resolved_cat, final_resolved_sub
                t5_hit = True
                t5_source = ai_res.get("source", "vector_cache_hit")
                matrix_counts["t5_ai"]["real"] += 1
                print(
                    f"🟢 [ROW {idx}] T5 Vector Hit in {t5_elapsed}s -> '{raw_narration[:30]}' -> {final_resolved_cat}/{final_resolved_sub}"
                )
            else:
                dir_cat, dir_sub = WIPHelpers.resolve_directional_placement(
                    credit_val, "Suspense Account"
                )
                final_resolved_cat, final_resolved_sub = resolve_official_taxonomy(
                    dir_cat, dir_sub
                )
                t5_cat, t5_sub = final_resolved_cat, final_resolved_sub
                t5_hit = False
                t5_source = "suspense_pending_workbench_training"
                matrix_counts["t5_ai"]["suspense"] += 1
                print(
                    f"🔴 [ROW {idx}] T5 Miss/Fallback in {t5_elapsed}s -> '{raw_narration[:30]}' -> Suspense"
                )

        norm_map = WIPHelpers.get_sub_norm_map()
        if final_resolved_sub and final_resolved_sub.strip().lower() in norm_map:
            final_resolved_sub = norm_map[final_resolved_sub.strip().lower()]

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

        eval_matrix_payload = {
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
            "t4": {"category": t4_cat, "subcategory": t4_sub, "hit": t4_hit},
            "t5": {
                "category": t5_cat,
                "subcategory": t5_sub,
                "hit": t5_hit,
                "source": t5_source,
            },
        }

        batch_queue.append(
            {
                "wip_id": str(row["id"]),
                "narration": raw_narration,
                "txn_date": formatted_date,
                "date": formatted_date,
                "raw_statement_date": formatted_date,
                "debit": debit_val,
                "credit": credit_val,
                "matrix_evaluation": eval_matrix_payload,
            }
        )

        computed_updates.append(
            {
                "id": row["id"],
                "matrix_evaluation": eval_matrix_payload,
                "resolved_category": final_resolved_cat,
                "resolved_subcategory": final_resolved_sub,
                "confidence_score": system_certainty_score,
                "applied_rule_id": matched_rule_id,
                "evaluation_errors": [],
            }
        )

        total_row_elapsed = round(time.time() - row_start_time, 4)
        if total_row_elapsed > 0.05:
            print(
                f"⚠️ [SLOW ROW {idx}] Took {total_row_elapsed}s for '{raw_narration[:40]}'"
            )

    return batch_queue, computed_updates, matrix_counts


# import time
# import logging
# from datetime import datetime
# from .helpers import WIPHelpers
# from ..ai.services.hybrid_classifier import (
#     check_vector_exists,
#     push_to_vector_cache,
#     query_local_vector_cache,
# )
# from ..classification.utils.taxonomy_gate import resolve_official_taxonomy
# from tracker.ai.services.ai_rule_trainer_engine import AIRuleTrainerEngine

# logger = logging.getLogger(__name__)

# VALID_PRIMARY_CLASSES = {
#     "asset",
#     "liability",
#     "expense",
#     "expenses",
#     "income",
#     "transfer",
# }

# INVALID_SUB_TOKENS = {
#     "suspense account",
#     "none",
#     "null",
#     "unclassified",
#     "unknown",
#     "expense",
#     "expenses",
#     "income",
# }


# def process_row_batch_worker(
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
#     Processes every row in the provided batch queue without artificial batch capping.
#     """
#     batch_queue = []
#     computed_updates = []
#     matrix_counts = {
#         "t1_system": {"real": 0, "suspense": 0},
#         "t2_internal": {"real": 0, "none": 0},
#         "t3_layout": {"real": 0, "suspense": 0},
#         "t4_rulebook": {"real": 0, "suspense_fallback": 0},
#         "t5_ai": {"real": 0, "suspense": 0},
#     }

#     # Iterate through the complete batch queue passed to this worker
#     for idx, row in enumerate(batch_data, 1):
#         row_start_time = time.time()
#         raw_narration = row["narration"] or ""
#         narration_clean = raw_narration.strip().lower()
#         debit_val = row["debit"]
#         credit_val = row["credit"]

#         # -----------------------------------------------------------------
#         # TRACK 1 & 2: Regex Pattern Extraction
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
#                                 t1_cat, t1_sub = db_cat, WIPHelpers.safe_subcategory(
#                                     rule["act_subcategory"]
#                                 )
#                             else:
#                                 t1_cat, t1_sub = (
#                                     WIPHelpers.resolve_directional_placement(
#                                         credit_val, rule["act_subcategory"]
#                                     )
#                                 )
#                             t1_hit = 1

#                     elif rule["type"] == "SELF_TRANSFER" and t2_hit == 0:
#                         if not rule["p2"] or rule["p2"].search(narration_clean):
#                             db_cat = rule["act_category"]
#                             if db_cat and db_cat.strip() not in {"None", ""}:
#                                 (
#                                     t2_cat,
#                                     t2_sub,
#                                 ) = db_cat.strip(), WIPHelpers.safe_subcategory(
#                                     rule["act_subcategory"]
#                                 )
#                             else:
#                                 t2_cat, t2_sub = (
#                                     WIPHelpers.resolve_directional_placement(
#                                         credit_val, rule["act_subcategory"]
#                                     )
#                                 )
#                             t2_hit = 1

#         if t1_hit == 1 and "suspense" not in t1_sub.lower():
#             matrix_counts["t1_system"]["real"] += 1
#             t1_weight = 100
#         else:
#             if t1_hit == 0:
#                 t1_cat, t1_sub = WIPHelpers.resolve_directional_placement(
#                     credit_val, "Suspense Account"
#                 )
#             matrix_counts["t1_system"]["suspense"] += 1
#             t1_weight = 0

#         if t2_hit == 1:
#             matrix_counts["t2_internal"]["real"] += 1
#             t2_weight = 100
#         else:
#             matrix_counts["t2_internal"]["none"] += 1
#             t2_weight = 0

#         # -----------------------------------------------------------------
#         # TRACK 3: Ledger Layout Maps
#         # -----------------------------------------------------------------
#         t3_cat, t3_sub = "None", "None"
#         t3_hit = 0
#         search_target = t1_raw_db_category if t1_raw_db_category != "None" else t1_cat

#         if search_target and search_target.lower() not in {
#             "none",
#             "income",
#             "expenses",
#             "suspense account",
#         }:
#             for layout_rule in t3_lookup.get(search_target.lower(), []):
#                 db_row_cat = layout_rule["act_category"].strip().lower()
#                 if (credit_val > 0 and "expense" in db_row_cat) or (
#                     credit_val <= 0 and ("income" in db_row_cat or db_row_cat == "oci")
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
#                 t3_cat, t3_sub = WIPHelpers.resolve_directional_placement(
#                     credit_val, "Suspense Account"
#                 )
#             matrix_counts["t3_layout"]["suspense"] += 1
#             t3_weight = 0

#         system_certainty_score = round((t1_weight + t2_weight + t3_weight) / 3.0, 2)

#         # -----------------------------------------------------------------
#         # TRACK 4: Master Rulebook
#         # -----------------------------------------------------------------
#         t4_cat, t4_sub = "None", "None"
#         t4_hit = False
#         meta_cat = meta_sub = ""
#         matched_rule_id = None

#         if master_t4_regex:
#             t4_match = master_t4_regex.search(narration_clean)
#             if t4_match:
#                 matched_tag = t4_match.group(1)
#                 for rule_id, dir_type, metadata in t4_text_lookup.get(matched_tag, []):
#                     if (dir_type == "credit" and credit_val <= 0) or (
#                         dir_type == "debit" and debit_val <= 0
#                     ):
#                         continue
#                     meta_cat = metadata.get("category", "").strip()
#                     meta_sub = metadata.get("subcategory", "").strip()
#                     t4_hit = True
#                     matched_rule_id = rule_id
#                     break

#         if not t4_hit:
#             resolved_upstream = t1_cat.lower()
#             if resolved_upstream in t4_translation_map:
#                 for rule_id, dir_type, metadata in t4_translation_map[
#                     resolved_upstream
#                 ]:
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
#                 if meta_cat and meta_cat.strip() not in {"", "None"}
#                 else t1_cat
#             )
#             t4_sub = (
#                 meta_sub
#                 if meta_sub and meta_sub.strip() not in {"", "None"}
#                 else "Suspense Account"
#             )
#             matrix_counts["t4_rulebook"]["real"] += 1
#         else:
#             t4_cat, t4_sub = WIPHelpers.resolve_directional_placement(
#                 credit_val, "Suspense Account"
#             )
#             matrix_counts["t4_rulebook"]["suspense_fallback"] += 1

#         # -----------------------------------------------------------------
#         # TRACK 5 & DYNAMIC RESOLUTION
#         # -----------------------------------------------------------------
#         t5_cat, t5_sub = "None", "None"
#         t5_hit = False
#         t5_source = "bypassed"
#         has_deterministic_match = False

#         if t4_hit:
#             raw_resolved_cat, raw_resolved_sub = t4_cat, t4_sub
#             has_deterministic_match = True
#             rule_source = matched_rule_id or "T4_GOLDEN_RULE"
#         elif t2_hit and t2_cat.lower() in VALID_PRIMARY_CLASSES:
#             raw_resolved_cat, raw_resolved_sub = t2_cat, t2_sub
#             has_deterministic_match = True
#             rule_source = "T2_SELF_TRANSFER"
#         elif t1_hit and t1_cat.lower() in VALID_PRIMARY_CLASSES:
#             raw_resolved_cat, raw_resolved_sub = t1_cat, t1_sub
#             has_deterministic_match = True
#             rule_source = "T1_SYSTEM_DEFAULT"
#         elif t3_hit and t3_cat.lower() in VALID_PRIMARY_CLASSES:
#             raw_resolved_cat, raw_resolved_sub = t3_cat, t3_sub
#             has_deterministic_match = True
#             rule_source = "T3_LAYOUT_MAP"

#         if has_deterministic_match:
#             final_resolved_cat, final_resolved_sub = resolve_official_taxonomy(
#                 raw_resolved_cat, raw_resolved_sub
#             )

#             # 🟢 STRICT AUTO-SEEDING GUARD:
#             # Block raw un-mapped tokens (FED-NRO-1050), suspense placeholders, or invalid subcategories
#             clean_sub_lower = (final_resolved_sub or "").strip().lower()
#             is_valid_subcategory = (
#                 bool(clean_sub_lower)
#                 and clean_sub_lower not in INVALID_SUB_TOKENS
#                 and not clean_sub_lower.startswith("fed-")
#                 and not clean_sub_lower.startswith("sbonr")
#             )

#             if is_valid_subcategory:
#                 is_ai_trained = check_vector_exists(raw_narration)
#                 if not is_ai_trained:
#                     push_to_vector_cache(
#                         narration=raw_narration,
#                         category=final_resolved_cat,
#                         subcategory=final_resolved_sub,
#                         rule_code=rule_source,
#                         confidence=100,
#                     )
#                     t5_source = "auto_trained_from_t1_t4"
#                 else:
#                     t5_source = "vector_cache_verified"
#             else:
#                 t5_source = "bypassed_invalid_taxonomy"

#             t5_cat, t5_sub = final_resolved_cat, final_resolved_sub
#             t5_hit = True
#         else:
#             t5_start_time = time.time()
#             ai_res = query_local_vector_cache(raw_narration)
#             t5_elapsed = round(time.time() - t5_start_time, 4)
#             score = ai_res.get("confidence_score", 0)

#             if ai_res.get("is_trained") and score >= 0.85:
#                 raw_cat = ai_res.get("category", "").title()
#                 raw_sub = ai_res.get("subcategory") or "AI Unclassified"
#                 final_resolved_cat, final_resolved_sub = resolve_official_taxonomy(
#                     raw_cat, raw_sub
#                 )
#                 system_certainty_score = int(score * 100)
#                 t5_cat, t5_sub = final_resolved_cat, final_resolved_sub
#                 t5_hit = True
#                 t5_source = ai_res.get("source", "vector_cache_hit")
#                 matrix_counts["t5_ai"]["real"] += 1
#                 print(
#                     f"🟢 [ROW {idx}] T5 Vector Hit in {t5_elapsed}s -> '{raw_narration[:30]}' -> {final_resolved_cat}/{final_resolved_sub}"
#                 )
#             else:
#                 dir_cat, dir_sub = WIPHelpers.resolve_directional_placement(
#                     credit_val, "Suspense Account"
#                 )
#                 final_resolved_cat, final_resolved_sub = resolve_official_taxonomy(
#                     dir_cat, dir_sub
#                 )
#                 t5_cat, t5_sub = final_resolved_cat, final_resolved_sub
#                 t5_hit = False
#                 t5_source = "suspense_pending_workbench_training"
#                 matrix_counts["t5_ai"]["suspense"] += 1
#                 print(
#                     f"🔴 [ROW {idx}] T5 Miss/Fallback in {t5_elapsed}s -> '{raw_narration[:30]}' -> Suspense"
#                 )

#         norm_map = WIPHelpers.get_sub_norm_map()
#         if final_resolved_sub and final_resolved_sub.strip().lower() in norm_map:
#             final_resolved_sub = norm_map[final_resolved_sub.strip().lower()]

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

#         eval_matrix_payload = {
#             "system_certainty_score": system_certainty_score,
#             "t1": {"category": t1_cat, "subcategory": t1_sub, "weight": t1_weight},
#             "t2": {"category": t2_cat, "subcategory": t2_sub, "weight": t2_weight},
#             "t3": {"category": t3_cat, "subcategory": t3_sub, "weight": t3_weight},
#             "t4": {"category": t4_cat, "subcategory": t4_sub, "hit": t4_hit},
#             "t5": {
#                 "category": t5_cat,
#                 "subcategory": t5_sub,
#                 "hit": t5_hit,
#                 "source": t5_source,
#             },
#         }

#         batch_queue.append(
#             {
#                 "wip_id": str(row["id"]),
#                 "narration": raw_narration,
#                 "txn_date": formatted_date,
#                 "date": formatted_date,
#                 "raw_statement_date": formatted_date,
#                 "debit": debit_val,
#                 "credit": credit_val,
#                 "matrix_evaluation": eval_matrix_payload,
#             }
#         )

#         computed_updates.append(
#             {
#                 "id": row["id"],
#                 "matrix_evaluation": eval_matrix_payload,
#                 "resolved_category": final_resolved_cat,
#                 "resolved_subcategory": final_resolved_sub,
#                 "confidence_score": system_certainty_score,
#                 "applied_rule_id": matched_rule_id,
#                 "evaluation_errors": [],
#             }
#         )

#         total_row_elapsed = round(time.time() - row_start_time, 4)
#         if total_row_elapsed > 0.05:
#             print(
#                 f"⚠️ [SLOW ROW {idx}] Took {total_row_elapsed}s for '{raw_narration[:40]}'"
#             )

#     return batch_queue, computed_updates, matrix_counts
