import json
import re
from datetime import datetime
from django.db import transaction

from .helpers import WIPHelpers
from .worker import process_row_batch_worker
from ..models.models import (
    WIPEvaluationMatrix,
    MasterFinancialCategory,
    AccountingRule,
)
from .utils import run_in_parallel


class WIPReconciliationEngine:
    @classmethod
    def get_sub_norm_map(cls) -> dict:
        return WIPHelpers.get_sub_norm_map()

    @classmethod
    def resolve_directional_placement(
        cls, credit_val: float, rule_subcategory: str
    ) -> tuple:
        return WIPHelpers.resolve_directional_placement(credit_val, rule_subcategory)

    @classmethod
    def evaluate_account_queue(cls, account_id: int) -> dict:
        # =========================================================================
        # 🏗️ MASTER SINGLE-PASS REGEX COMPILATION
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
        # 📥 COLD DATA EXTRACTION (UNPROCESSED QUEUE)
        # =========================================================================
        raw_rows = list(
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
                "matrix_evaluation",
            )
        )

        cold_rows = [r for r in raw_rows if not r["matrix_evaluation"]]
        total_rows = len(cold_rows)

        # Retain current workspace state if no cold rows need processing
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
                    "matrix_evaluation",
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
                        "resolved_category": r["resolved_category"],
                        "resolved_subcategory": r["resolved_subcategory"],
                        "confidence_score": r["confidence_score"],
                        "matrix_evaluation": r["matrix_evaluation"] or {},
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
                    "t5_ai": {"real": total_active, "suspense": 0},
                    "total_processed": total_active,
                },
            }

        # Build thread worker payload (FULL cold_rows array without slicing)
        thread_payload = []
        for r in cold_rows:
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

        caching_indexes = (
            t1_t2_dict,
            master_t1_t2_regex,
            t3_lookup,
            t4_translation_map,
            t4_text_lookup,
            master_t4_regex,
        )

        # 🚀 Execute worker pool across the FULL un-sliced batch payload
        thread_responses = run_in_parallel(
            payload_list=thread_payload,
            worker_func=process_row_batch_worker,
            extra_args=caching_indexes,
            max_workers=4,
        )

        # =========================================================================
        # 📥 UNPACK WORKER RESULTS & AGGREGATE STATS
        # =========================================================================
        final_queue = []
        all_db_updates = []
        matrix_summary_stats = {
            "t1_system": {"real": 0, "suspense": 0},
            "t2_internal": {"real": 0, "suspense": 0},
            "t3_layout": {"real": 0, "suspense": 0},
            "t4_rulebook": {"real": 0, "suspense": 0},
            "t5_ai": {"real": 0, "suspense": 0},
            "total_processed": total_rows,
        }

        for batch_queue, batch_updates, batch_counts in thread_responses:
            final_queue.extend(batch_queue)
            all_db_updates.extend(batch_updates)

            for tier in ["t1_system", "t2_internal", "t3_layout", "t5_ai"]:
                if tier in batch_counts:
                    matrix_summary_stats[tier]["real"] += batch_counts[tier].get(
                        "real", 0
                    )
                    matrix_summary_stats[tier]["suspense"] += batch_counts[tier].get(
                        "suspense", 0
                    )

            matrix_summary_stats["t2_internal"]["suspense"] += batch_counts[
                "t2_internal"
            ].get("none", 0)

            if "t4_rulebook" in batch_counts:
                matrix_summary_stats["t4_rulebook"]["real"] += batch_counts[
                    "t4_rulebook"
                ]["real"]
                matrix_summary_stats["t4_rulebook"]["suspense"] += batch_counts[
                    "t4_rulebook"
                ].get("suspense_fallback", 0)

        # =========================================================================
        # ⚡ ATOMIC BULK COMMIT TO DATABASE
        # =========================================================================
        with transaction.atomic():
            objs_to_update = []
            for update in all_db_updates:
                obj = WIPEvaluationMatrix(id=update["id"])
                obj.matrix_evaluation = update.get("matrix_evaluation", {})
                obj.resolved_category = update.get("resolved_category", "Expense")
                obj.resolved_subcategory = update.get(
                    "resolved_subcategory", "Suspense Account"
                )
                obj.confidence_score = update.get("confidence_score", 0)
                obj.applied_rule_id = update.get("applied_rule_id", None)
                obj.evaluation_errors = update.get("evaluation_errors", [])
                objs_to_update.append(obj)

            WIPEvaluationMatrix.objects.bulk_update(
                objs_to_update,
                fields=[
                    "matrix_evaluation",
                    "resolved_category",
                    "resolved_subcategory",
                    "confidence_score",
                    "applied_rule_id",
                    "evaluation_errors",
                ],
                batch_size=2000,
            )

        return {
            "workspace_queue": final_queue,
            "matrix_summary_stats": matrix_summary_stats,
        }
