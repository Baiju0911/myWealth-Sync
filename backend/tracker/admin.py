from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import (
    User,
    Role,
    Permission,
    Account,
    TransactionHeader,
    JournalEntry,
    MasterFinancialCategory,
    AccountingRule,
    JournalEntryMapping,
    DirectionalVectorOverride,
)

# ==============================================================================
# 🔒 1. TABLE-DRIVEN SECURITY RULES (RBAC)
# ==============================================================================


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "role", "is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "id")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("codename", "description", "id")


# ==============================================================================
# 🎯 2. METADATA RULES & TAXONOMY CONFIGURATIONS
# ==============================================================================


@admin.register(MasterFinancialCategory)
class MasterFinancialCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sno",
        "category_type",
        "act_category",
        "act_subcategory",
        "categories_items",
        "dashboard_cat",
        "get_primary_match_key",  # 🎯 FIXED: Points to our custom json getter method below
    )
    list_filter = ("category_type", "act_category", "dashboard_cat")

    # 🎯 FIXED: Removed match_key1 and match_key2 since Django cannot search inside raw JSON strings out-of-the-box
    search_fields = (
        "categories_items",
        "act_subcategory",
        "act_category",
        "dashboard_cat",
    )
    ordering = ("category_type", "act_category", "categories_items")

    # Custom getter method to display the nested string token in your admin dashboard grid cleanly
    def get_primary_match_key(self, obj):
        if obj.keys and isinstance(obj.keys, dict):
            return obj.keys.get("key1", "")
        return ""

    # Set the column title header label name inside Django Admin interface grid
    get_primary_match_key.short_description = "Primary Match Key"


# ==============================================================================
# 🎯 2. METADATA RULES & TAXONOMY CONFIGURATIONS
# ==============================================================================


@admin.register(AccountingRule)
class AccountingRuleAdmin(admin.ModelAdmin):
    # 🎯 FIXED: Display the type by calling a custom method that extracts it from JSON
    list_display = (
        "rule_code",
        "rule_title",
        "get_golden_rule_type",
        "entry_type",
        "rule_priority",
        "is_active",
    )

    # 🎯 FIXED: Removed 'golden_rule_type' from list_filter since it can't index inside JSON directly
    list_filter = ("entry_type", "is_active")

    search_fields = ("rule_code", "rule_title", "description_tags")
    ordering = ("rule_priority",)

    # Custom getter method to show the value in your admin dashboard list grid view cleanly
    def get_golden_rule_type(self, obj):
        if obj.rule_metadata and isinstance(obj.rule_metadata, dict):
            return obj.rule_metadata.get("golden_rule_type", "None")
        return "None"

    # Set the column title header name inside Django Admin interface view
    get_golden_rule_type.short_description = "Golden Rule Type"


# ==============================================================================
# 💸 3. HIGH-PRECISION DOUBLE-ENTRY ACCOUNTING MATRIX
# ==============================================================================


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "bank", "account_type", "ifsc_code", "branch_name"]
    list_filter = ["account_type", "bank"]
    search_fields = ["name", "ifsc_code", "branch_name"]


class JournalEntryMappingInline(admin.StackedInline):
    """
    🎯 THE EXTENSION LAYER BRIDGE
    Allows you to instantly view or edit the multi-tier personal finance categories
    and applied rules right inside the individual splitting row view!
    """

    model = JournalEntryMapping
    extra = 0
    autocomplete_fields = ["assigned_category", "applied_rule"]


class JournalEntryInline(admin.TabularInline):
    """
    Shows Debit and Credit splits nested cleanly right inside the Parent Transaction layout view
    """

    model = JournalEntry
    extra = 2


@admin.register(TransactionHeader)
class TransactionHeaderAdmin(admin.ModelAdmin):
    list_display = ("date", "narration", "source", "user", "upi_rrn", "created_at")
    list_filter = ("source", "date")
    search_fields = ("narration", "upi_rrn", "user__email")
    inlines = [JournalEntryInline]


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = (
        "transaction",
        "account",
        "amount",
        "get_mapping_item",
        "created_at",
    )
    list_filter = (
        "account__account_type",
        "category_mapping__assigned_category__act_category",
    )
    search_fields = (
        "transaction__narration",
        "account__name",
        "category_mapping__assigned_category__categories_items",
    )
    inlines = [JournalEntryMappingInline]

    def get_mapping_item(self, obj):
        if hasattr(obj, "category_mapping"):
            return f"🏷️ {obj.category_mapping.assigned_category.categories_items}"
        return "⚠️ Unmapped"

    get_mapping_item.short_description = "Personal Finance Category"


@admin.register(DirectionalVectorOverride)
class DirectionalVectorOverrideAdmin(admin.ModelAdmin):
    list_display = (
        "source_category",
        "expected_vector",
        "target_category",
        "target_subcategory",
        "is_active",
    )
    list_filter = ("expected_vector", "is_active")
    search_fields = ("source_category", "target_category")
