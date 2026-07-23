from django.db.models import Count, Sum, DecimalField, ExpressionWrapper
from django.db.models.fields.json import KeyTransform
from tracker.models import JournalEntry  # Adjust to your model name if different


class DashboardSelectors:
    @staticmethod
    def get_category_breakdowns(taxonomy_account_id=99):
        """
        Uses pure Django ORM with KeyTransform to aggregate category & subcategory
        summaries directly from the evaluation_matrix_snapshot JSON field.
        """
        return (
            JournalEntry.objects.filter(account_id=taxonomy_account_id)
            .annotate(
                resolved_cat=KeyTransform(
                    "resolved_category", "evaluation_matrix_snapshot"
                ),
                resolved_subcat=KeyTransform(
                    "resolved_subcategory", "evaluation_matrix_snapshot"
                ),
            )
            .values("resolved_cat", "resolved_subcat")
            .annotate(
                transaction_count=Count("id"),
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
                net_balance=ExpressionWrapper(
                    Sum("debit") - Sum("credit"),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                ),
            )
            .order_by("resolved_cat", "resolved_subcat")
        )

    @staticmethod
    def get_ledger_symmetry(bank_account_id=3, taxonomy_account_id=99):
        """
        Calculates double-entry symmetry and balance proof across Bank and Taxonomy nodes.
        """
        symmetry_qs = (
            JournalEntry.objects.filter(
                account_id__in=[bank_account_id, taxonomy_account_id]
            )
            .values("account_id")
            .annotate(
                total_debit=Sum("debit"),
                total_credit=Sum("credit"),
                net_balance=ExpressionWrapper(
                    Sum("debit") - Sum("credit"),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                ),
            )
        )

        acc_bank_net = DecimalField().to_python(0)
        acc_tax_net = DecimalField().to_python(0)

        for row in symmetry_qs:
            if row["account_id"] == bank_account_id:
                acc_bank_net = row["net_balance"] or 0
            elif row["account_id"] == taxonomy_account_id:
                acc_tax_net = row["net_balance"] or 0

        variance = round(float(acc_bank_net + acc_tax_net), 2)

        return {
            "bank_account_id": bank_account_id,
            "taxonomy_account_id": taxonomy_account_id,
            "bank_net": float(acc_bank_net),
            "taxonomy_net": float(acc_tax_net),
            "variance": variance,
            "is_balanced": abs(variance) < 0.01,
        }
