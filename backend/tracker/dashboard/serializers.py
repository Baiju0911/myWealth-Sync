from rest_framework import serializers


class DateBoundsSerializer(serializers.Serializer):
    min_date = serializers.CharField(allow_null=True)
    max_date = serializers.CharField(allow_null=True)
    applied_from_date = serializers.CharField(allow_null=True)
    applied_to_date = serializers.CharField(allow_null=True)


class CategoryBreakdownSerializer(serializers.Serializer):
    category = serializers.CharField(allow_null=True, required=False)
    subcategory = serializers.CharField(allow_null=True, required=False)
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
    date_bounds = DateBoundsSerializer()
    kpis = KPISummarySerializer()
    symmetry_proof = LedgerSymmetrySerializer()
    category_breakdown = CategoryBreakdownSerializer(many=True)
