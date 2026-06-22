# trackers/parsers/services/parser_orchestrator.py

from typing import List, Dict, Any, Optional
from .strategies.paddle_universal_fallback import execute_paddle_fallback_pipeline
from .confidence.evaluator import ConfidenceEvaluator
from .geometry.lane_detector import StructuredRow


class FallbackOrchestratorService:
    """
    Top-Level Fallback Controller.
    Manages layout extraction, canonical mapping, and quality assurance scoring.
    """

    @staticmethod
    def get_default_lane_config() -> Dict[str, Dict[str, float]]:
        """
        Standard default percentage grid template to use if a bank variant
        is completely new or un-mapped in the system database.
        """
        return {
            "date": {
                "x_start": 0.0,
                "x_end": 11.5,
            },  # Tightened from 20.0 to fix date bleeding
            "narration": {
                "x_start": 11.5,
                "x_end": 68.0,
            },  # Expanded to capture description blocks cleanly
            "debit": {"x_start": 68.0, "x_end": 79.0},
            "credit": {"x_start": 79.0, "x_end": 90.0},
            "balance": {"x_start": 90.0, "x_end": 100.0},
        }

    @classmethod
    def process_failed_document(
        cls,
        image_paths: List[str],
        bank_template_override: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """
        Triggers the intelligent fallback sequence for a document.

        Args:
            image_paths: List of file paths to the page images.
            bank_template_override: Optional database template boundaries (e.g., SBI or HDFC lane specifications).
        """
        # Use database coordinates if provided; otherwise, use our standard fallback template grid
        lane_config = (
            bank_template_override
            if bank_template_override
            else cls.get_default_lane_config()
        )

        print("\n=== 🎯 ORCHESTRATOR DEBUG: CURRENT ACTIVE LANE_CONFIG ===")
        import pprint

        pprint.pprint(lane_config)
        print("========================================================\n")

        # 1. Execute the full PaddleOCR + Geometry extraction loop
        # extracted_data_dicts = execute_paddle_fallback_pipeline(
        #     image_paths=image_paths, lane_config=lane_config
        # )
        extracted_data_dicts = execute_paddle_fallback_pipeline(
            image_paths=image_paths, lane_config=lane_config
        )

        # ─── CONSOLIDATED PROCESSING PASS ─────────────────────────────────────
        eval_rows = []
        serialized_transactions = []

        # Capture raw stream fallback data if it exists inside the dictionary bundle
        raw_stream_payload = ""
        if (
            isinstance(extracted_data_dicts, dict)
            and "raw_csv_stream" in extracted_data_dicts
        ):
            raw_stream_payload = extracted_data_dicts.get("raw_csv_stream", "")
            # Re-assign data iterable to inner list if engine returned dictionary wrapper
            extracted_data_dicts = extracted_data_dicts.get("transactions", [])

        for d in extracted_data_dicts:
            clean_date = d.get("Txn Date") or d.get("date") or d.get("post_date") or ""
            clean_val_date = (
                d.get("Val Date")
                or d.get("val_date")
                or d.get("value_date")
                or clean_date
            )

            if (
                clean_date == "IF8C"
                or "ACCOUNT OPEN DATE" in str(d.get("narration", "")).upper()
            ):
                continue

            row = StructuredRow()
            row.date = clean_date
            row.val_date = clean_val_date
            row.narration = d.get("narration") or d.get("narration_description") or ""
            row.debit = d.get("debit") or ""
            row.credit = d.get("credit") or ""
            row.balance = d.get("balance") or ""
            eval_rows.append(row)

            row_payload = {
                "date": row.date,
                "val_date": row.val_date,
                "narration": row.narration,
                "debit": row.debit,
                "credit": row.credit,
                "balance": row.balance,
                "post_date": row.date,
                "value_date": row.val_date,
                "narration_description": row.narration,
                "Txn Date": clean_date,
                "Val Date": clean_val_date,
                "Narration Description": row.narration,
                "Debit (-)": row.debit,
                "Credit (+)": row.credit,
                "Balance": row.balance,
                "Status": d.get("status") or d.get("Status") or "NEW",
                "Type": d.get("Type")
                or ("TRF" if "TRF" in row.narration.upper() else "-"),
                "Chq/Ref": d.get("Chq/Ref") or "",
            }
            serialized_transactions.append(row_payload)

        # ─── 🎯 ENGINE-LEVEL WYSIWYG RE-GENERATION PASS ─────────────────────
        # If the underlying fallback script completely omitted the raw string generation,
        # we assemble it dynamically using the final verified payload objects.
        if not raw_stream_payload and serialized_transactions:
            raw_csv_lines = [
                f"{r['post_date']} ~ {r['narration_description']} ~ {r['debit']} ~ {r['credit']} ~ {r['balance']}"
                for r in serialized_transactions
            ]
            raw_stream_payload = "\n".join(raw_csv_lines)

        final_score = ConfidenceEvaluator.evaluate_dataset(eval_rows)

        return {
            "status": "success" if final_score >= 80 else "manual_review_recommended",
            "fallback_engine_executed": "PaddleOCR_v1",
            "confidence_score": final_score,
            "total_transactions_found": len(eval_rows),
            "transactions": serialized_transactions,  # List of dict items for your view/math engines
            "raw_csv_stream": raw_stream_payload,  # Perfect, synchronized string stream
        }
