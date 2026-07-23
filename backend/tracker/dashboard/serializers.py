from rest_framework import serializers


class CategoryBreakdownSerializer(serializers.Serializer):
    category = serializers.CharField(source="resolved_cat", default="Uncategorized")
    subcategory = serializers.CharField(
        source="resolved_subcat", default="Suspense Account"
    )
    transaction_count = serializers.IntegerField()
    total_debit = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_credit = serializers.DecimalField(max_digits=15, decimal_places=2)
    net_balance = serializers.DecimalField(max_digits=15, decimal_places=2)


class LedgerSymmetrySerializer(serializers.Serializer):
    bank_account_id = serializers.IntegerField()
    taxonomy_account_id = serializers.IntegerField()
    bank_net = serializers.FloatField()
    taxonomy_net = serializers.FloatField()
    variance = serializers.FloatField()
    is_balanced = serializers.BooleanField()


class KPISummarySerializer(serializers.Serializer):
    net_liquidity = serializers.FloatField()
    total_income = serializers.FloatField()
    total_expense = serializers.FloatField()
    suspense_count = serializers.IntegerField()
    suspense_amount = serializers.FloatField()


class DashboardSummaryResponseSerializer(serializers.Serializer):
    kpis = KPISummarySerializer()
    symmetry_proof = LedgerSymmetrySerializer()
    category_breakdown = CategoryBreakdownSerializer(many=True)
