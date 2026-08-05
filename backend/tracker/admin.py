from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import (
    User,
    Role,
    Permission,
    Account,
    JournalEntry,
    MasterFinancialCategory,
    AccountingRule,
    DirectionalVectorOverride,
    TaxonomyTree,  # 🎯 ADDED: Single Source of Truth Model
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


# 🌳 SINGLE SOURCE OF TRUTH (SSOT) MASTER TAXONOMY ADMIN
@admin.register(TaxonomyTree)
class TaxonomyTreeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "category",
        "subcategory",
        "display_order",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "is_active")
    search_fields = ("category", "subcategory")
    ordering = ("category", "display_order", "subcategory")
    list_editable = ("display_order", "is_active")


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
        "get_primary_match_key",  # 🎯 Points to custom json getter method below
    )
    list_filter = ("category_type", "act_category", "dashboard_cat")

    search_fields = (
        "categories_items",
        "act_subcategory",
        "act_category",
        "dashboard_cat",
    )
    ordering = ("category_type", "act_category", "categories_items")

    def get_primary_match_key(self, obj):
        if obj.keys and isinstance(obj.keys, dict):
            return obj.keys.get("key1", "")
        return ""

    get_primary_match_key.short_description = "Primary Match Key"


@admin.register(AccountingRule)
class AccountingRuleAdmin(admin.ModelAdmin):
    list_display = (
        "rule_code",
        "rule_title",
        "get_taxonomy_node",  # 🎯 UPDATED: Displays canonical Taxonomy node
        "get_golden_rule_type",
        "entry_type",
        "rule_priority",
        "is_active",
    )

    # 🔍 Allows easy searching/filtering by master category nodes directly in Django Admin
    list_filter = (
        "entry_type",
        "is_active",
        "taxonomy__category",  # 🎯 Filter by master SSOT category
    )
    search_fields = (
        "rule_code",
        "rule_title",
        "description_tags",
        "taxonomy__category",  # 🎯 Search by SSOT Category
        "taxonomy__subcategory",  # 🎯 Search by SSOT Subcategory
    )
    ordering = ("rule_priority",)
    autocomplete_fields = [
        "taxonomy"
    ]  # 🎯 Enables fast dropdown lookup for Taxonomy nodes

    def get_taxonomy_node(self, obj):
        if obj.taxonomy:
            return f"🌳 {obj.taxonomy.category} ➔ {obj.taxonomy.subcategory}"
        # Fallback if taxonomy_id is not yet set
        cat = obj.rule_metadata.get("category", "Unmapped")
        sub = obj.rule_metadata.get("subcategory", "Unmapped")
        return f"⚠️ {cat} ➔ {sub} (Unlinked)"

    get_taxonomy_node.short_description = "SSOT Taxonomy Mapping"

    def get_golden_rule_type(self, obj):
        if obj.rule_metadata and isinstance(obj.rule_metadata, dict):
            return obj.rule_metadata.get("golden_rule_type", "None")
        return "None"

    get_golden_rule_type.short_description = "Golden Rule Type"


# ==============================================================================
# 💸 3. HIGH-PRECISION DOUBLE-ENTRY ACCOUNTING MATRIX
# ==============================================================================


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "bank", "account_type", "ifsc_code", "branch_name"]
    list_filter = ["account_type", "bank"]
    search_fields = ["name", "ifsc_code", "branch_name"]


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    # 🎯 UPDATED: Reflects flat, decoupled table grid architecture
    list_display = (
        "transaction_date",
        "account",
        "row_identifier",
        "debit",
        "credit",
        "get_resolved_category",
        "created_at",
    )

    list_filter = (
        "account",
        "transaction_date",
    )

    search_fields = (
        "row_identifier",
        "account__name",
    )

    # 🤖 Pulls engine snapshot evaluation metadata cleanly for display in grid columns
    def get_resolved_category(self, obj):
        if obj.evaluation_matrix_snapshot and isinstance(
            obj.evaluation_matrix_snapshot, dict
        ):
            resolved_cat = obj.evaluation_matrix_snapshot.get("resolved_category")
            resolved_sub = obj.evaluation_matrix_snapshot.get("resolved_subcategory")
            if resolved_cat:
                return f"🏷️ {resolved_cat} -> {resolved_sub}"

            # Context indicator for balancing bank statement anchor row side
            if obj.evaluation_matrix_snapshot.get("leg_context") == "LIQUIDITY_CORE":
                return "🏦 Bank Account Pool Leg"

        return "⚠️ Unmapped / Neutral Anchor"

    get_resolved_category.short_description = "Resolved Rule Category"


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


# from django.contrib import admin
# from django.contrib.auth import get_user_model
# from .models import (
#     User,
#     Role,
#     Permission,
#     Account,
#     JournalEntry,
#     MasterFinancialCategory,
#     AccountingRule,
#     DirectionalVectorOverride,
# )

# # ==============================================================================
# # 🔒 1. TABLE-DRIVEN SECURITY RULES (RBAC)
# # ==============================================================================


# @admin.register(User)
# class UserAdmin(admin.ModelAdmin):
#     list_display = ("email", "first_name", "last_name", "role", "is_active", "is_staff")
#     search_fields = ("email", "first_name", "last_name")


# @admin.register(Role)
# class RoleAdmin(admin.ModelAdmin):
#     list_display = ("name", "id")


# @admin.register(Permission)
# class PermissionAdmin(admin.ModelAdmin):
#     list_display = ("codename", "description", "id")


# # ==============================================================================
# # 🎯 2. METADATA RULES & TAXONOMY CONFIGURATIONS
# # ==============================================================================


# @admin.register(MasterFinancialCategory)
# class MasterFinancialCategoryAdmin(admin.ModelAdmin):
#     list_display = (
#         "id",
#         "sno",
#         "category_type",
#         "act_category",
#         "act_subcategory",
#         "categories_items",
#         "dashboard_cat",
#         "get_primary_match_key",  # 🎯 Points to our custom json getter method below
#     )
#     list_filter = ("category_type", "act_category", "dashboard_cat")

#     search_fields = (
#         "categories_items",
#         "act_subcategory",
#         "act_category",
#         "dashboard_cat",
#     )
#     ordering = ("category_type", "act_category", "categories_items")

#     def get_primary_match_key(self, obj):
#         if obj.keys and isinstance(obj.keys, dict):
#             return obj.keys.get("key1", "")
#         return ""

#     get_primary_match_key.short_description = "Primary Match Key"


# @admin.register(AccountingRule)
# class AccountingRuleAdmin(admin.ModelAdmin):
#     list_display = (
#         "rule_code",
#         "rule_title",
#         "get_golden_rule_type",
#         "entry_type",
#         "rule_priority",
#         "is_active",
#     )

#     list_filter = ("entry_type", "is_active")
#     search_fields = ("rule_code", "rule_title", "description_tags")
#     ordering = ("rule_priority",)

#     def get_golden_rule_type(self, obj):
#         if obj.rule_metadata and isinstance(obj.rule_metadata, dict):
#             return obj.rule_metadata.get("golden_rule_type", "None")
#         return "None"

#     get_golden_rule_type.short_description = "Golden Rule Type"


# # ==============================================================================
# # 💸 3. HIGH-PRECISION DOUBLE-ENTRY ACCOUNTING MATRIX
# # ==============================================================================


# @admin.register(Account)
# class AccountAdmin(admin.ModelAdmin):
#     list_display = ["id", "name", "bank", "account_type", "ifsc_code", "branch_name"]
#     list_filter = ["account_type", "bank"]
#     search_fields = ["name", "ifsc_code", "branch_name"]


# @admin.register(JournalEntry)
# class JournalEntryAdmin(admin.ModelAdmin):
#     # 🎯 UPDATED: Reflects the flat, decoupled table grid architecture
#     list_display = (
#         "transaction_date",
#         "account",
#         "row_identifier",
#         "debit",
#         "credit",
#         "get_resolved_category",
#         "created_at",
#     )

#     list_filter = (
#         "account",
#         "transaction_date",
#     )

#     search_fields = (
#         "row_identifier",
#         "account__name",
#     )

#     # 🤖 Pulls the engine snapshot evaluation metadata cleanly for display in the grid columns
#     def get_resolved_category(self, obj):
#         if obj.evaluation_matrix_snapshot and isinstance(
#             obj.evaluation_matrix_snapshot, dict
#         ):
#             resolved_cat = obj.evaluation_matrix_snapshot.get("resolved_category")
#             resolved_sub = obj.evaluation_matrix_snapshot.get("resolved_subcategory")
#             if resolved_cat:
#                 return f"🏷️ {resolved_cat} -> {resolved_sub}"

#             # Context indicator for the balancing bank statement anchor row side
#             if obj.evaluation_matrix_snapshot.get("leg_context") == "LIQUIDITY_CORE":
#                 return "🏦 Bank Account Pool Leg"

#         return "⚠️ Unmapped / Neutral Anchor"

#     get_resolved_category.short_description = "Resolved Rule Category"


# @admin.register(DirectionalVectorOverride)
# class DirectionalVectorOverrideAdmin(admin.ModelAdmin):
#     list_display = (
#         "source_category",
#         "expected_vector",
#         "target_category",
#         "target_subcategory",
#         "is_active",
#     )
#     list_filter = ("expected_vector", "is_active")
#     search_fields = ("source_category", "target_category")
