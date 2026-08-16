from rest_framework import serializers

from ..models.models import TaxonomyTree
from ..models.subledger import (
    AssetCategory,
    AssetComplianceSchedule,
    AssetOperationalAccount,
    AssetSubLedger,
    AssetTransactionMapping,
    Vendor,
)

# ============================================================================
# 1. VENDOR & ASSET CATEGORY SERIALIZERS
# ============================================================================


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = "__all__"


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


class AssetSubledgerBreakdownItemSerializer(serializers.ModelSerializer):
    asset_id = serializers.UUIDField(source="id", read_only=True)
    mapped_transaction_total = serializers.DecimalField(
        max_digits=15, decimal_places=2, read_only=True, default=0
    )
    mapped_count = serializers.IntegerField(read_only=True, default=0)
    vendor_name = serializers.CharField(
        source="vendor.name", read_only=True, default="Independent / Uncategorized"
    )
    vendor_detail = VendorSerializer(source="vendor", read_only=True)

    class Meta:
        model = AssetSubLedger
        fields = [
            "asset_id",
            "asset_code",
            "name",
            "current_valuation",
            "mapped_transaction_total",
            "mapped_count",
            "vendor",
            "vendor_name",
            "vendor_detail",
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
    # Foreign Key writes accept primary key UUIDs
    vendor = serializers.PrimaryKeyRelatedField(
        queryset=Vendor.objects.all(), required=False, allow_null=True
    )
    vendor_detail = VendorSerializer(source="vendor", read_only=True)

    asset_category = serializers.PrimaryKeyRelatedField(
        queryset=AssetCategory.objects.all(), required=False, allow_null=True
    )
    asset_category_detail = AssetCategorySerializer(
        source="asset_category", read_only=True
    )

    linked_gl_account = serializers.SlugRelatedField(
        slug_field="subcategory",
        queryset=TaxonomyTree.objects.all(),
        required=False,
        allow_null=True,
    )

    # Display Helpers
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    ownership_type_display = serializers.CharField(
        source="get_ownership_type_display", read_only=True
    )

    # Nested Read-Only Statements
    operational_accounts = AssetOperationalAccountSerializer(many=True, read_only=True)
    compliance_schedules = AssetComplianceScheduleSerializer(many=True, read_only=True)

    # Single Writeable Audit Note
    user_note = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = AssetSubLedger
        fields = "__all__"

    def to_representation(self, instance):
        """Include user_note inside response body from metadata_payload JSON."""
        data = super().to_representation(instance)
        payload = instance.metadata_payload or {}
        data["user_note"] = (
            payload.get("user_note", "") if isinstance(payload, dict) else ""
        )
        return data

    def update(self, instance, validated_data):
        # 1. Pop user_note from validated_data
        user_note = validated_data.pop("user_note", None)
        if user_note is None and self.context.get("request"):
            user_note = self.context["request"].data.get("user_note")

        # 2. Merge metadata_payload safely
        if user_note is not None:
            instance.refresh_from_db(fields=["metadata_payload"])
            existing_payload = dict(instance.metadata_payload or {})
            existing_payload["user_note"] = str(user_note)

            instance.metadata_payload = existing_payload
            validated_data["metadata_payload"] = existing_payload

        # 3. Standard DRF Update (handles vendor, linked_gl_account, acquisition_cost, etc.)
        updated_instance = super().update(instance, validated_data)

        # 4. Explicit DB Save for JSON metadata
        if user_note is not None:
            updated_instance.save(update_fields=["metadata_payload"])

        return updated_instance


# class AssetSubLedgerSerializer(serializers.ModelSerializer):
#     vendor = serializers.PrimaryKeyRelatedField(
#         queryset=Vendor.objects.all(), required=False, allow_null=True
#     )
#     vendor_detail = VendorSerializer(source="vendor", read_only=True)
#     user_note = serializers.SerializerMethodField()
#     category_display = serializers.CharField(
#         source="get_category_display", read_only=True
#     )
#     status_display = serializers.CharField(source="get_status_display", read_only=True)
#     ownership_type_display = serializers.CharField(
#         source="get_ownership_type_display", read_only=True
#     )

#     # Primary Key Foreign Key for writing (POST/PUT accepts asset_category ID)
#     asset_category = serializers.PrimaryKeyRelatedField(
#         queryset=AssetCategory.objects.all(),
#         required=False,
#         allow_null=True,
#     )

#     # Nested read-only detail object for rich frontend representation
#     asset_category_detail = AssetCategorySerializer(
#         source="asset_category", read_only=True
#     )

#     # SlugRelatedField cleanly handles TaxonomyTree UUID resolution by subcategory name
#     linked_gl_account = serializers.SlugRelatedField(
#         slug_field="subcategory",
#         queryset=TaxonomyTree.objects.all(),
#         required=False,
#         allow_null=True,
#     )

#     operational_accounts = AssetOperationalAccountSerializer(many=True, read_only=True)
#     compliance_schedules = AssetComplianceScheduleSerializer(many=True, read_only=True)
#     user_note = serializers.CharField(
#         source="metadata_payload.user_note", required=False, allow_blank=True
#     )

#     def get_user_note(self, obj):
#         if obj.metadata_payload and isinstance(obj.metadata_payload, dict):
#             return obj.metadata_payload.get("user_note", "")
#         return ""

#     def update(self, instance, validated_data):
#         request = self.context.get("request")
#         user_note = None

#         if request and hasattr(request, "data"):
#             user_note = request.data.get("user_note")

#         print("\n--------------------------------------------------")
#         print("🔍 [SERIALIZER UPDATE] PROCESSING ASSET UPDATE")
#         print(f"Asset ID: {instance.id}")
#         print(f"Extracted user_note: {user_note}")

#         if user_note is not None:
#             # Fetch existing dict payload or initialize fresh dict
#             payload = dict(instance.metadata_payload or {})
#             payload["user_note"] = str(user_note)

#             # Assign directly into validated_data so DRF persists the JSON modification
#             validated_data["metadata_payload"] = payload
#             print(f"Updated metadata_payload dict: {payload}")

#         print("--------------------------------------------------\n")

#         return super().update(instance, validated_data)

#     class Meta:
#         model = AssetSubLedger
#         fields = "__all__"


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
    sync_acquisition_cost = serializers.BooleanField(default=True)
