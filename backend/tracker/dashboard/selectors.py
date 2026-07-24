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
    def get_category_breakdowns1(
        bank_account_id=3, taxonomy_account_id=99, from_date=None, to_date=None
    ):
        """
        Aggregates category breakdowns with optional date range filtering for a target account.
        """
        # 🎯 Filter Journal entries for the active bank account context
        qs = JournalEntry.objects.filter(account_id=bank_account_id)

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
    def get_category_breakdowns2(
        bank_account_id=3, taxonomy_account_id=99, from_date=None, to_date=None
    ):
        """
        Queries Account 99 taxonomy records joined by row_identifier to the selected bank account.
        """
        # 1. Gather all audit hex footprints belonging to the selected bank account
        bank_row_ids = JournalEntry.objects.filter(
            account_id=bank_account_id
        ).values_list("row_identifier", flat=True)

        # 2. Query Account 99 records matching those audit signatures
        qs = JournalEntry.objects.filter(
            account_id=taxonomy_account_id, row_identifier__in=bank_row_ids
        )

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
    def get_category_breakdowns(
        bank_account_id=3, taxonomy_account_id=99, from_date=None, to_date=None
    ):
        """
        Queries Account 99 taxonomy records:
        - If a specific bank account is selected, filters by its row_identifier signatures.
        - If Account 99 is selected, aggregates globally across all accounts.
        """
        qs = JournalEntry.objects.filter(account_id=taxonomy_account_id)

        # Only restrict to specific bank account if NOT selecting the global master node itself
        if int(bank_account_id) != int(taxonomy_account_id):
            bank_row_ids = JournalEntry.objects.filter(
                account_id=bank_account_id
            ).values_list("row_identifier", flat=True)

            qs = qs.filter(row_identifier__in=bank_row_ids)

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
