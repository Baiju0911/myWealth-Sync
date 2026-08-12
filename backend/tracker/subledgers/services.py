from datetime import timedelta
from decimal import Decimal
from django.db import models


class AssetCandidateMatcher:
    """
    Implements your ±5 to ±10 day sliding window algorithm.
    """

    @staticmethod
    def find_candidate_rows(
        document_date,
        target_amount,
        account_id=None,
        keywords=None,
        day_window=10,
        amount_tolerance_pct=Decimal("0.0"),
    ):
        from tracker.models import JournalEntry  # Lazy import

        start_date = document_date - timedelta(days=day_window)
        end_date = document_date + timedelta(days=day_window)

        query = JournalEntry.objects.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date,
        )

        if account_id:
            query = query.filter(account_id=account_id)

        target_amount = Decimal(str(target_amount))
        min_amount = target_amount * (Decimal("1") - amount_tolerance_pct)
        max_amount = target_amount * (Decimal("1") + amount_tolerance_pct)

        query = query.filter(
            models.Q(debit__range=(min_amount, max_amount))
            | models.Q(credit__range=(min_amount, max_amount))
        )

        candidates = []

        for entry in query:
            score = 0
            entry_val = entry.debit if entry.debit > 0 else entry.credit

            if entry_val == target_amount:
                score += 50
            else:
                score += 35

            date_diff = abs((entry.transaction_date - document_date).days)
            if date_diff == 0:
                score += 30
            elif date_diff <= 3:
                score += 20
            elif date_diff <= 7:
                score += 15
            else:
                score += 10

            raw_remarks = str(entry.remarks).upper()
            if keywords:
                matched = [kw for kw in keywords if kw and kw.upper() in raw_remarks]
                if matched:
                    score += 20

            candidates.append(
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
                }
            )

        return sorted(candidates, key=lambda x: x["probability_score"], reverse=True)
