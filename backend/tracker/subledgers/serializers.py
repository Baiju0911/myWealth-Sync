from rest_framework import serializers
from ..models.subledger import (
    AssetSubLedger,
    AssetOperationalAccount,
    AssetComplianceSchedule,
    AssetTransactionMapping,
)
from ..models.models import TaxonomyTree


class AssetOperationalAccountSerializer(serializers.ModelSerializer):
    service_type_display = serializers.CharField(
        source="get_service_type_display", read_only=True
    )

    class Meta:
        model = AssetOperationalAccount
        fields = "__all__"


class AssetComplianceScheduleSerializer(serializers.ModelSerializer):
    schedule_type_display = serializers.CharField(
        source="get_schedule_type_display", read_only=True
    )
    recurrence_pattern_display = serializers.CharField(
        source="get_recurrence_pattern_display", read_only=True
    )

    class Meta:
        model = AssetComplianceSchedule
        fields = "__all__"


class AssetSubLedgerSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    ownership_type_display = serializers.CharField(
        source="get_ownership_type_display", read_only=True
    )

    # 🎯 PrimaryKeyRelatedField now cleanly handles the TaxonomyTree UUID!
    linked_gl_account = serializers.SlugRelatedField(
        slug_field="subcategory",
        queryset=TaxonomyTree.objects.all(),
        required=False,
        allow_null=True,
    )

    operational_accounts = AssetOperationalAccountSerializer(many=True, read_only=True)
    compliance_schedules = AssetComplianceScheduleSerializer(many=True, read_only=True)

    class Meta:
        model = AssetSubLedger
        fields = "__all__"


# class CandidateMatchRequestSerializer(serializers.Serializer):
#     document_date = serializers.DateField(required=True)  # Parses YYYY-MM-DD
#     target_amount = serializers.DecimalField(
#         max_digits=15,
#         decimal_places=2,
#         required=False,
#         allow_null=True,
#     )
#     account_id = serializers.IntegerField(required=False, allow_null=True)
#     keywords = serializers.ListField(
#         child=serializers.CharField(), required=False, default=list
#     )
#     day_window = serializers.IntegerField(default=10, min_value=1, max_value=60)


class CandidateMatchRequestSerializer(serializers.Serializer):
    document_date = serializers.DateField(required=True)  # Parses YYYY-MM-DD
    target_amount = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    account_id = serializers.IntegerField(required=False, allow_null=True)
    asset_id = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )  # 👈 Added asset_id (supports UUID or Integer primary keys)
    keywords = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    day_window = serializers.IntegerField(default=10, min_value=1, max_value=60)


class BindRowRequestSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField(required=True)
    schedule_id = serializers.UUIDField(required=False, allow_null=True)
    operational_account_id = serializers.UUIDField(required=False, allow_null=True)
    row_identifier = serializers.CharField(
        max_length=64, required=False, allow_blank=True, allow_null=True
    )
    is_cash_entry = serializers.BooleanField(default=False)
    transaction_date = serializers.DateField(required=True)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, required=True)
    transaction_purpose = serializers.CharField(max_length=64, required=True)
    user_note = serializers.CharField(required=False, allow_blank=True, default="")
