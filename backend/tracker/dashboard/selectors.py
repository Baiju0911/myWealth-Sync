from django.db.models import Count, Sum, DecimalField, ExpressionWrapper, Min, Max
from django.db.models.expressions import RawSQL
from tracker.models import JournalEntry  # Ensure this matches your model name


class DashboardSelectors:
    @staticmethod
    def get_date_bounds(bank_account_id=3):
        """
        Retrieves the overall minimum and maximum transaction dates for the specified account.
        """
        bounds = JournalEntry.objects.filter(account_id=bank_account_id).aggregate(
            min_date=Min("transaction_date"), max_date=Max("transaction_date")
        )
        return {
            "min_date": (
                bounds["min_date"].strftime("%Y-%m-%d") if bounds["min_date"] else None
            ),
            "max_date": (
                bounds["max_date"].strftime("%Y-%m-%d") if bounds["max_date"] else None
            ),
        }

    @staticmethod
    def get_category_breakdowns(taxonomy_account_id=99, from_date=None, to_date=None):
        """
        Aggregates category breakdowns with optional date range filtering.
        """
        qs = JournalEntry.objects.filter(account_id=taxonomy_account_id)

        if from_date:
            qs = qs.filter(transaction_date__gte=from_date)
        if to_date:
            qs = qs.filter(transaction_date__lte=to_date)

        return (
            qs.annotate(
                category=RawSQL(
                    "JSON_UNQUOTE(JSON_EXTRACT(evaluation_matrix_snapshot, '$.resolved_category'))",
                    [],
                ),
                subcategory=RawSQL(
                    "JSON_UNQUOTE(JSON_EXTRACT(evaluation_matrix_snapshot, '$.resolved_subcategory'))",
                    [],
                ),
            )
            .values("category", "subcategory")
            .annotate(
                transaction_count=Count("id"),
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
                net_balance=ExpressionWrapper(
                    Sum("debit") - Sum("credit"),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                ),
            )
            .order_by("category", "subcategory")
        )

    @staticmethod
    def get_ledger_symmetry(
        bank_account_id=3, taxonomy_account_id=99, from_date=None, to_date=None
    ):
        """
        Calculates double-entry symmetry proof with optional date range filtering.
        """
        qs = JournalEntry.objects.filter(
            account_id__in=[bank_account_id, taxonomy_account_id]
        )

        if from_date:
            qs = qs.filter(transaction_date__gte=from_date)
        if to_date:
            qs = qs.filter(transaction_date__lte=to_date)

        symmetry_qs = qs.values("account_id").annotate(
            total_debit=Sum("debit"),
            total_credit=Sum("credit"),
            net_balance=ExpressionWrapper(
                Sum("debit") - Sum("credit"),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            ),
        )

        acc_bank_net = 0.0
        acc_tax_net = 0.0

        for row in symmetry_qs:
            if row["account_id"] == bank_account_id:
                acc_bank_net = float(row["net_balance"] or 0)
            elif row["account_id"] == taxonomy_account_id:
                acc_tax_net = float(row["net_balance"] or 0)

        variance = round(acc_bank_net + acc_tax_net, 2)

        return {
            "bank_account_id": bank_account_id,
            "taxonomy_account_id": taxonomy_account_id,
            "bank_net": acc_bank_net,
            "taxonomy_net": acc_tax_net,
            "variance": variance,
            "is_balanced": abs(variance) < 0.01,
        }
