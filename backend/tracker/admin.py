from django.contrib import admin
from .models import User, Role, Permission, Account, TransactionHeader, JournalEntry

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
# 💸 2. HIGH-PRECISION DOUBLE-ENTRY ACCOUNTING MATRIX
# ==============================================================================


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """
    💳 Ledger Branch Account Layout Admin Console
    """

    # 🎯 FIXED: Only display fields that explicitly live on your real Account model!
    list_display = ["id", "name", "bank", "account_type", "ifsc_code", "branch_name"]
    list_filter = ["account_type", "bank"]
    search_fields = ["name", "ifsc_code", "branch_name"]


class JournalEntryInline(admin.TabularInline):
    """
    Shows Debit and Credit splits nested cleanly right inside the Parent Transaction layout view
    """

    model = JournalEntry
    extra = 2  # Provides 2 blank lines for clean entry creation by default


@admin.register(TransactionHeader)
class TransactionHeaderAdmin(admin.ModelAdmin):
    list_display = ("date", "narration", "source", "user", "upi_rrn", "created_at")
    list_filter = ("source", "date")
    search_fields = ("narration", "upi_rrn", "user__email")
    inlines = [JournalEntryInline]


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("transaction", "account", "amount", "created_at")
    list_filter = ("account__account_type",)
