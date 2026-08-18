import hashlib
from decimal import Decimal
from django.db import transaction
from ..models.models import StatementStagingLine, WIPEvaluationMatrix


class WIPIngestionSweeper:
    """
    🎛️ AIR-GAPPED TRANSACTION INITIALIZATION ENGINE
    Sweeps unallocated StatementStagingLines into the WIP Evaluation Sandbox.
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
    def execute_sweep(cls, account_context_id: int) -> dict:
        metrics = {"scanned": 0, "initialized": 0, "skipped": 0}

        with transaction.atomic():
            staging_queue = StatementStagingLine.objects.filter(
                account_id=account_context_id, routing_status="PENDING"
            ).select_for_update()

            metrics["scanned"] = staging_queue.count()
            if metrics["scanned"] == 0:
                return metrics

            existing_wip_hashes = set(
                WIPEvaluationMatrix.objects.filter(
                    account_id=account_context_id
                ).values_list("row_footprint_hash", flat=True)
            )

            wip_insertions = []
            staging_lines_to_update = []

            for row in staging_queue:
                row_hash = row.row_identifier

                if row_hash in existing_wip_hashes:
                    metrics["skipped"] += 1
                    row.routing_status = "COMPLETED"
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
                    matrix_evaluation={},
                    evaluation_errors=["UNPROCESSED_RUN"],
                )
                wip_row.account_id = account_context_id

                wip_insertions.append(wip_row)
                existing_wip_hashes.add(row_hash)

                row.routing_status = "COMPLETED"
                staging_lines_to_update.append(row)

            if wip_insertions:
                WIPEvaluationMatrix.objects.bulk_create(wip_insertions, batch_size=1000)
                metrics["initialized"] = len(wip_insertions)

            if staging_lines_to_update:
                StatementStagingLine.objects.bulk_update(
                    staging_lines_to_update, fields=["routing_status"], batch_size=1000
                )

        return metrics
