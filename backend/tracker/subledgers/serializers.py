from rest_framework import serializers

from ..models.models import TaxonomyTree
from ..models.subledger import (
    AcquisitionFundingSource,
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
        fields = ["id", "name", "code", "default_keywords", "created_at"]
        extra_kwargs = {
            "code": {
                "required": False
            },  # Auto-generates in model or serializer if omitted
        }


class AssetCategorySerializer(serializers.ModelSerializer):
    """Serializes dynamic AssetCategory lookup instances."""

    class Meta:
        model = AssetCategory
        fields = [
            "id",
            "code",
            "name",
            "category_type",
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

    # 🟢 Raw incoming string fallback for legacy choice column
    category = serializers.CharField(required=False, allow_blank=True)

    # 🧾 Funding Source & Missing Bank Row Fields
    acquisition_funding_source = serializers.ChoiceField(
        choices=AcquisitionFundingSource.choices,
        default=AcquisitionFundingSource.BANK_STAGING,
        required=False,
    )

    acquisition_funding_source_display = serializers.CharField(
        source="get_acquisition_funding_source_display", read_only=True
    )
    is_bank_row_missing = serializers.BooleanField(required=False)

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

    def validate(self, attrs):
        """
        🟢 DYNAMIC AUTO-SYNC: Automatically resolves asset_category FK and legacy
        category string, and syncs `is_bank_row_missing` based on `acquisition_funding_source`.
        """
        # 1. Resolve funding source from incoming payload OR existing model instance
        funding_source = attrs.get("acquisition_funding_source")
        if funding_source is None and self.instance:
            funding_source = self.instance.acquisition_funding_source

        # 2. Sync is_bank_row_missing automatically
        if funding_source:
            attrs["is_bank_row_missing"] = (
                funding_source != AcquisitionFundingSource.BANK_STAGING
            )

        # 3. Dynamic Taxonomy & AssetCategory Auto-Match
        gl_node = attrs.get("linked_gl_account")  # Resolved TaxonomyTree instance

        print("\n" + "=" * 60)
        print("🔍 [DEBUG AUTO-SYNC] Serializer Validation Started")
        print(f"📥 Received Payload GL Account Node: {gl_node}")
        print(f"📥 Raw Payload Category Choice: {attrs.get('category')}")
        print(f"📥 Resolved Funding Source Choice: {funding_source}")
        print(f"📥 Computed is_bank_row_missing: {attrs.get('is_bank_row_missing')}")

        if gl_node:
            subcategory_str = getattr(gl_node, "subcategory", str(gl_node)).strip()
            print(f"⚡ Processing GL Subcategory String: '{subcategory_str}'")

            # 🎯 1. Exact Match by default_taxonomy_subcategory
            matching_cat = AssetCategory.objects.filter(
                default_taxonomy_subcategory__iexact=subcategory_str
            ).first()

            if matching_cat:
                print(
                    f"✅ STEP 1 EXACT MATCH SUCCESS: Found AssetCategory -> {matching_cat} (Code: {matching_cat.code})"
                )
            else:
                print(
                    f"⚠️ STEP 1 EXACT MATCH MISSED: No exact category for default_taxonomy_subcategory='{subcategory_str}'"
                )

                # 🎯 2. Fallback: Formatted Code Match (e.g., 'RENT_INCOME')
                fallback_code = subcategory_str.replace(" ", "_").upper()
                print(f"🔄 Attempting STEP 2 Formatted Code Match: '{fallback_code}'")

                matching_cat = AssetCategory.objects.filter(
                    code__iexact=fallback_code
                ).first()

                if matching_cat:
                    print(
                        f"✅ STEP 2 CODE MATCH SUCCESS: Found AssetCategory -> {matching_cat} (Code: {matching_cat.code})"
                    )
                else:
                    print(f"⚠️ STEP 2 CODE MATCH MISSED: No code='{fallback_code}'")

                    # 🎯 3. Fallback: Fuzzy Root Substring Match
                    normalized_root = (
                        subcategory_str.lower()
                        .replace("income", "")
                        .replace("expense", "")
                        .replace("stream", "")
                        .strip()
                    )
                    print(
                        f"🔄 Attempting STEP 3 Fuzzy Root Match with: '{normalized_root}'"
                    )

                    if normalized_root:
                        matching_cat = AssetCategory.objects.filter(
                            default_taxonomy_subcategory__icontains=normalized_root
                        ).first()

                    if matching_cat:
                        print(
                            f"✅ STEP 3 FUZZY MATCH SUCCESS: Matched root '{normalized_root}' -> {matching_cat} (Code: {matching_cat.code})"
                        )
                    else:
                        print(
                            f"❌ STEP 3 FUZZY MATCH MISSED: No match found for '{normalized_root}'"
                        )

            # 🎯 4. Sync Foreign Key and Choice Enum Columns
            if matching_cat:
                attrs["asset_category"] = matching_cat
                attrs["category"] = matching_cat.code
                print(
                    f"🚀 FINAL AUTO-SYNC APPLIED: Overwrote attrs['category'] with '{matching_cat.code}' and attrs['asset_category'] with ID {matching_cat.id}"
                )
            else:
                print(
                    f"⚠️ NO MATCH FOUND: Payload category left as-is ('{attrs.get('category')}')"
                )

        else:
            print("ℹ️ No linked_gl_account provided in attrs. Skipping auto-sync.")

        print("=" * 60 + "\n")

        return super().validate(attrs)

    def to_representation(self, instance):
        """Include user_note inside response body from metadata_payload JSON."""
        data = super().to_representation(instance)
        payload = instance.metadata_payload or {}
        data["user_note"] = (
            payload.get("user_note", "") if isinstance(payload, dict) else ""
        )
        return data

        # def to_representation(self, instance):
        """
        Dynamically computes financial metrics and injects user_note from metadata_payload.
        """
        data = super().to_representation(instance)

        # 1. Inject user_note safely from JSON payload
        payload = instance.metadata_payload or {}
        data["user_note"] = (
            payload.get("user_note", "") if isinstance(payload, dict) else ""
        )

        # 2. Check node type (Income/Expense streams vs Physical Assets)
        category_code = str(instance.category or "").upper()
        asset_code = str(instance.asset_code or "").upper()
        is_income_or_expense = (
            asset_code.startswith("INC")
            or asset_code.startswith("EXP")
            or "INCOME" in category_code
            or "EXPENSE" in category_code
        )

        # 3. Income & Expense nodes always have ₹0.00 Acquisition Cost Baseline
        if is_income_or_expense:
            data["acquisition_cost"] = 0.0

        # 4. Compute Pure Operating Cash Flows from Bound Mappings
        inflows = instance.mappings.filter(transaction_purpose="INFLOW").aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        outflows = instance.mappings.filter(transaction_purpose="OUTFLOW").aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        net_yield = inflows - outflows
        base_cost = (
            Decimal("0.00")
            if is_income_or_expense
            else (instance.acquisition_cost or Decimal("0.00"))
        )

        # 5. Overwrite dynamic calculated values
        data["cumulative_inflows"] = float(inflows)
        data["operating_outflows"] = float(outflows)
        data["net_yield"] = float(net_yield)
        data["current_valuation"] = float(base_cost + net_yield)

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

        # 3. Standard DRF Update
        updated_instance = super().update(instance, validated_data)

        # 4. Explicit DB Save for JSON metadata
        if user_note is not None:
            updated_instance.save(update_fields=["metadata_payload"])

        return updated_instance


# ============================================================================
# 4. CANDIDATE MATCHING & BINDING REQUEST SERIALIZERS
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
