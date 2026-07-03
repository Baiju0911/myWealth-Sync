# tracker/serviceWIP.py
import hashlib
from decimal import Decimal
from django.db import transaction
from .models import StatementStagingLine, WIPEvaluationMatrix


class WIPIngestionSweeper:
    """
    🎛️ AIR-GAPPED TRANSACTION INITIALIZATION ENGINE
    Sweeps unallocated StatementStagingLines into the WIP Evaluation Sandbox
    using strict deterministic SHA-256 state tracking keys.
    """

    @staticmethod
    def generate_row_hash(date_obj, debit_val, credit_val, balance_val) -> str:
        """
        Calculates a deterministic tracking key based on core transaction parameters.
        Normalizes strings and numbers to eliminate decimal formatting collisions.
        """

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
        """
        Scans staging records for an account context and populates missing records in the WIP sandbox.
        Uses select_for_update to prevent tab-concurrency insertion collisions.
        """
        metrics = {"scanned": 0, "initialized": 0, "skipped": 0}

        # 🛡️ Guardrail 4: Enforce an isolated database transaction block
        with transaction.atomic():
            # Lock the staging lines for this account during processing
            staging_queue = StatementStagingLine.objects.filter(
                account_id=account_context_id, routing_status="PENDING"
            ).select_for_update()

            metrics["scanned"] = staging_queue.count()

            # Bulk fetch existing WIP hashes to minimize database query loops
            existing_wip_hashes = set(
                WIPEvaluationMatrix.objects.filter(
                    account_id=account_context_id
                ).values_list("row_footprint_hash", flat=True)
            )

            wip_insertions = []

            for row in staging_queue:
                # 🛠️ Schema Normalization Layer: Ensure decimal fields are numeric 0.00, not NULL
                dr_clean = row.debit if row.debit is not None else Decimal("0.00")
                cr_clean = row.credit if row.credit is not None else Decimal("0.00")
                bal_clean = (
                    row.running_balance
                    if row.running_balance is not None
                    else Decimal("0.00")
                )

                # Generate tracking hash identifier
                row_hash = cls.generate_row_hash(
                    row.raw_statement_date, dr_clean, cr_clean, bal_clean
                )

                # 🛡️ Guardrail 9: Check if the hash matches an active WIP record
                if row_hash in existing_wip_hashes:
                    metrics["skipped"] += 1
                    continue

                # Instantiate new WIP matrix sandbox row object
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
                    confidence_level="ZERO",  # Starts at Zero until evaluation gates run
                    tier_1_passed=False,
                    tier_2_passed=False,
                    tier_3_passed=False,
                    evaluation_errors=["UNPROCESSED_RUN"],
                )

                wip_insertions.append(wip_row)
                existing_wip_hashes.add(
                    row_hash
                )  # Track locally to prevent batch duplicates

            # Commit new rows to the sandbox using a fast batch insert
            if wip_insertions:
                WIPEvaluationMatrix.objects.bulk_create(wip_insertions)
                metrics["initialized"] = len(wip_insertions)

        return metrics
