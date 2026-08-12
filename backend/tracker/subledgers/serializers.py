from rest_framework import serializers
from ..models.subledger import (
    AssetSubLedger,
    AssetOperationalAccount,
    AssetComplianceSchedule,
    AssetTransactionMapping,
)


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

    operational_accounts = AssetOperationalAccountSerializer(many=True, read_only=True)
    compliance_schedules = AssetComplianceScheduleSerializer(many=True, read_only=True)

    class Meta:
        model = AssetSubLedger
        fields = "__all__"


class CandidateMatchRequestSerializer(serializers.Serializer):
    document_date = serializers.DateField(required=True)
    target_amount = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=True
    )
    account_id = serializers.IntegerField(required=False, allow_null=True)
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
