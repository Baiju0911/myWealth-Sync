from rest_framework import serializers

from ..models.models import TaxonomyTree
from ..models.subledger import (
    AssetCategory,
    AssetComplianceSchedule,
    AssetOperationalAccount,
    AssetSubLedger,
    AssetTransactionMapping,
)

# ============================================================================
# 1. DYNAMIC ASSET CATEGORY SERIALIZER
# ============================================================================


class AssetCategorySerializer(serializers.ModelSerializer):
    """Serializes dynamic AssetCategory lookup instances."""

    class Meta:
        model = AssetCategory
        fields = [
            "id",
            "code",
            "name",
            "default_taxonomy_category",
            "default_taxonomy_subcategory",
            "linked_gl_account",
            "is_active",
        ]


# ============================================================================
# 2. OPERATIONAL ACCOUNTS & SCHEDULES
# ============================================================================


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


# ============================================================================
# 3. MASTER ASSET SUB-LEDGER SERIALIZER
# ============================================================================


class AssetSubLedgerSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    ownership_type_display = serializers.CharField(
        source="get_ownership_type_display", read_only=True
    )

    # 🎯 Primary Key Foreign Key for writing (POST/PUT accepts asset_category ID)
    asset_category = serializers.PrimaryKeyRelatedField(
        queryset=AssetCategory.objects.all(),
        required=False,
        allow_null=True,
    )

    # 🎯 Nested read-only detail object for rich frontend representation
    asset_category_detail = AssetCategorySerializer(
        source="asset_category", read_only=True
    )

    # SlugRelatedField cleanly handles TaxonomyTree UUID resolution by subcategory name
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


# ============================================================================
# 4. ACTION & MATCHING REQUEST SERIALIZERS
# ============================================================================


class CandidateMatchRequestSerializer(serializers.Serializer):
    document_date = serializers.DateField(required=True)
    target_amount = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    account_id = serializers.IntegerField(required=False, allow_null=True)
    asset_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    keywords = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    day_window = serializers.IntegerField(
        default=10, min_value=1, max_value=3650, required=False
    )


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
