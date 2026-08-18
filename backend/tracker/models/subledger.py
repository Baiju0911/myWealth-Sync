import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from ..subledgers.services import (
    AssetCandidateMatcher as ServiceCandidateMatcher,
)

# ============================================================================
# 1. DYNAMIC ASSET CATEGORY TABLE (LOOKUP & TAXONOMY BRIDGE)
# ============================================================================


# class AssetCategory(models.Model):
#     """Dynamic Asset Category Lookup Table.

#     Uses an explicit primary key ID (1, 2, 3...) to allow full runtime CRUD
#     operations without breaking foreign key relationships or requiring DB
#     migrations when adding new categories.
#     """

#     id = models.AutoField(primary_key=True)
#     code = models.CharField(
#         max_length=50,
#         unique=True,
#         db_index=True,
#         help_text="System key code, e.g., REAL_ESTATE, FIXED_DEPOSIT",
#     )
#     name = models.CharField(
#         max_length=100,
#         help_text="Display label, e.g., Real Estate & Land, Fixed Deposit (FD)",
#     )

#     # 🎯 Single Source of Truth Alignment with Taxonomy Breakdown Matrix
#     default_taxonomy_category = models.CharField(
#         max_length=100,
#         default="Asset",
#         help_text="Primary taxonomy class, e.g., Asset, Liability",
#     )
#     default_taxonomy_subcategory = models.CharField(
#         max_length=100,
#         help_text="Exact subcategory matching Dashboard matrix, e.g., Real Estate, Fixed Deposits",
#     )

#     # Optional direct link to TaxonomyTree chart of accounts
#     linked_gl_account = models.ForeignKey(
#         "TaxonomyTree",
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name="asset_categories",
#         help_text="Default Chart of Accounts node for this category",
#     )

#     is_active = models.BooleanField(default=True, db_index=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = "ledger_asset_category"
#         verbose_name = "Asset Category"
#         verbose_name_plural = "Asset Categories"
#         ordering = ["id"]

#     def __str__(self):
#         return f"[{self.id}] {self.name} ({self.default_taxonomy_subcategory})"


# Legacy TextChoices retained for backwards compatibility / fallback references
# class AssetCategoryChoices(models.TextChoices):
#     REAL_ESTATE = "REAL_ESTATE", "Real Estate & Land"
#     FIXED_DEPOSIT = "FIXED_DEPOSIT", "Fixed Deposit (FD)"
#     RECURRING_DEPOSIT = "RECURRING_DEPOSIT", "Recurring Deposit (RD)"
#     MARKET_INVESTMENT = "MARKET_INVESTMENT", "Stocks, Mutual Funds & ETFs"
#     PENSION_RETIREMENT = (
#         "PENSION_RETIREMENT",
#         "Pension & Retirement (NPS, PPF, EPF)",
#     )
#     INSURANCE_PLAN = "INSURANCE_PLAN", "Life & Endowment Insurance"
#     VEHICLE = "VEHICLE", "Vehicles & Transport"
#     PRECIOUS_METALS = "PRECIOUS_METALS", "Gold, Silver & SGBs"
#     PERSONAL_RECEIVABLE = (
#         "PERSONAL_RECEIVABLE",
#         "Personal Loan Given / Receivable",
#     )


# 1. Define choices FIRST at the top of the module
class SubledgerCategoryType(models.TextChoices):
    ASSET = "ASSET", "Asset (Balance Sheet)"
    INCOME = "INCOME", "Income Stream (P&L Inflow)"
    EXPENSE = "EXPENSE", "Expense Cost Center (P&L Outflow)"


class AssetCategoryChoices(models.TextChoices):
    REAL_ESTATE = "REAL_ESTATE", "Real Estate & Land"
    FIXED_DEPOSIT = "FIXED_DEPOSIT", "Fixed Deposit (FD)"
    RECURRING_DEPOSIT = "RECURRING_DEPOSIT", "Recurring Deposit (RD)"
    MARKET_INVESTMENT = "MARKET_INVESTMENT", "Stocks, Mutual Funds & ETFs"
    PENSION_RETIREMENT = "PENSION_RETIREMENT", "Pension & Retirement"
    INSURANCE_PLAN = "INSURANCE_PLAN", "Life & Endowment Insurance"
    VEHICLE = "VEHICLE", "Vehicles & Transport"
    PRECIOUS_METALS = "PRECIOUS_METALS", "Gold, Silver & SGBs"
    PERSONAL_RECEIVABLE = "PERSONAL_RECEIVABLE", "Personal Loan Given"
    RENTAL_STREAM = "RENTAL_STREAM", "Property Rental Stream"
    DIVIDEND_FOLIO = "DIVIDEND_FOLIO", "Dividend & Yield Stream"
    VENDOR_MERCHANT = "VENDOR_MERCHANT", "Merchant / Service Provider"
    CHARITY_RECIPIENT = "CHARITY_RECIPIENT", "Charity / 80G Recipient"


# 2. Define Model SECOND after choices exist
class AssetCategory(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)

    category_type = models.CharField(
        max_length=20,
        choices=SubledgerCategoryType.choices,
        default=SubledgerCategoryType.ASSET,
        db_index=True,
    )

    default_taxonomy_category = models.CharField(max_length=100, default="Asset")
    default_taxonomy_subcategory = models.CharField(max_length=100)

    linked_gl_account = models.ForeignKey(
        "TaxonomyTree",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asset_categories",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_asset_category"
        verbose_name = "Asset & Subledger Category"
        verbose_name_plural = "Asset & Subledger Categories"
        ordering = ["id"]

    def __str__(self):
        return (
            f"[{self.category_type}] {self.name} ({self.default_taxonomy_subcategory})"
        )


class OwnershipType(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL", "Individual / Sole Owner"
    JOINT = "JOINT", "Joint Ownership"
    FAMILY = "FAMILY", "Family Trust / Group"
    BUSINESS = "BUSINESS", "Business Entity"


class AssetStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active / Holding"
    MATURED = "MATURED", "Matured"
    LIQUIDATED = "LIQUIDATED", "Liquidated / Closed"
    SOLD = "SOLD", "Sold / Transferred"
    WRITTEN_OFF = "WRITTEN_OFF", "Written Off"


class ServiceProviderType(models.TextChoices):
    PROPERTY_TAX = (
        "PROPERTY_TAX",
        "Local Body Property Tax (Panchayat/Corporation)",
    )
    LAND_REVENUE_TAX = "LAND_REVENUE_TAX", "Land Revenue Tax (Thandaper)"
    ELECTRICITY = "ELECTRICITY", "Electricity Board (e.g., KSEB)"
    WATER = "WATER", "Water Authority (e.g., KWA)"
    BUILDING_MAINTENANCE = (
        "BUILDING_MAINTENANCE",
        "Resident Association / Maintenance",
    )
    INSURANCE = "INSURANCE", "Asset / Liability Insurance"
    GAS = "GAS", "Piped Gas / LPG Connection"


class ScheduleType(models.TextChoices):
    PROPERTY_TAX_DUE = "PROPERTY_TAX_DUE", "Property Tax Due"
    LAND_TAX_DUE = "LAND_TAX_DUE", "Land Revenue Tax Due"
    UTILITY_BILL = "UTILITY_BILL", "Utility Bill Payment"
    SIP_DUE = "SIP_DUE", "Investment / Pension SIP Installment"
    PREMIUM_DUE = "PREMIUM_DUE", "Insurance Premium"
    FD_MATURITY = "FD_MATURITY", "Deposit Maturity Payout"


class RecurrencePattern(models.TextChoices):
    ONE_OFF = "ONE_OFF", "One-Time / Ad-Hoc"
    MONTHLY = "MONTHLY", "Monthly"
    BIMONTHLY = "BIMONTHLY", "Bi-Monthly"
    QUARTERLY = "QUARTERLY", "Quarterly"
    HALF_YEARLY = "HALF_YEARLY", "Half-Yearly"
    ANNUALLY = "ANNUALLY", "Annually"


# ============================================================================
# 2. MASTER ASSET SUB-LEDGER
# ============================================================================
class Vendor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True)  # e.g., "Bhima Jewels"
    code = models.CharField(
        max_length=50, blank=True, null=True, unique=True
    )  # e.g., "VND-BHIMA"
    default_keywords = models.JSONField(
        default=list, blank=True
    )  # e.g., ["Bhima", "BHIMA JEWELLERY"]
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AssetSubLedger(models.Model):
    """Master Asset Register & Sub-Ledger Hub.

    Holds core financial valuations, ownership split, dynamic asset category
    pointers, and category-specific operational details in JSON payload.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Human-readable code, e.g., AST-RE-001 or AST-FD-002",
    )
    name = models.CharField(
        max_length=255, help_text="Display title, e.g., 'Ulloor Plot & House'"
    )

    # 🎯 Linked to dynamic AssetCategory model with explicit integer PK
    asset_category = models.ForeignKey(
        AssetCategory,
        on_delete=models.PROTECT,
        related_name="subledger_assets",
        null=True,
        blank=True,
        help_text="Foreign key to dynamic AssetCategory table",
    )

    # Fallback legacy string category column
    category = models.CharField(
        max_length=32, choices=AssetCategoryChoices.choices, db_index=True
    )

    # 🏛️ Financial Valuation & Cost Basis
    acquisition_date = models.DateField(default=timezone.now)
    acquisition_cost = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    current_valuation = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("0.00")
    )
    valuation_updated_at = models.DateTimeField(auto_now=True)

    # 👥 Ownership Matrix
    ownership_type = models.CharField(
        max_length=20,
        choices=OwnershipType.choices,
        default=OwnershipType.INDIVIDUAL,
    )
    ownership_share_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(Decimal("100.00")),
        ],
    )
    status = models.CharField(
        max_length=20,
        choices=AssetStatus.choices,
        default=AssetStatus.ACTIVE,
        db_index=True,
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets"
    )

    # 🔗 Link to General Ledger Balance Sheet Account
    linked_gl_account = models.ForeignKey(
        "TaxonomyTree",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subledger_assets",
        help_text="Chart of Accounts Taxonomy category for General Ledger alignment",
    )
    parent_asset = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_streams",
        help_text="Parent asset generating this income or incurring this expense (e.g. SBI-NRE1 FD generating Interest)",
    )

    # 🎨 Deep Dynamic Category Metadata Repository
    metadata_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores category-specific attributes (deed numbers, PRAN, survey numbers, etc.)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_asset_subledger"
        verbose_name = "Asset Sub-Ledger Record"
        verbose_name_plural = "Asset Sub-Ledger Registry"
        indexes = [
            models.Index(fields=["category", "status"]),
            models.Index(fields=["asset_category", "status"]),
            models.Index(fields=["asset_code"]),
        ]

    def __str__(self):
        cat_name = (
            self.asset_category.name
            if self.asset_category
            else self.get_category_display()
        )
        return f"[{self.asset_code}] {self.name} ({cat_name})"


# ============================================================================
# 3. UTILITY & GOVERNMENT OPERATIONAL ACCOUNTS
# ============================================================================


class AssetOperationalAccount(models.Model):
    """Stores utility consumer numbers, local tax assessment IDs, meter numbers,

    and matching keywords used for auto-identifying bank statement lines.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        AssetSubLedger,
        on_delete=models.CASCADE,
        related_name="operational_accounts",
    )
    service_type = models.CharField(
        max_length=32, choices=ServiceProviderType.choices, db_index=True
    )
    provider_name = models.CharField(
        max_length=128,
        help_text="e.g., KSEB, KWA, Trivandrum Corporation, Revenue Dept",
    )
    consumer_identifier = models.CharField(
        max_length=64,
        help_text="Consumer No / Building Assessment No / Thandaper No",
    )
    meter_number = models.CharField(max_length=64, blank=True, null=True)
    matching_keyword = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Narration pattern to assist matching algorithm, e.g., 'KSEB 1156890012'",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "ledger_asset_operational_account"
        verbose_name = "Operational Utility / Tax Account"
        verbose_name_plural = "Operational Utility / Tax Accounts"

    def __str__(self):
        return f"{self.asset.name} - {self.get_service_type_display()} ({self.consumer_identifier})"


# ============================================================================
# 4. COMPLIANCE SCHEDULE & DUE REMINDERS
# ============================================================================


class AssetComplianceSchedule(models.Model):
    """Drives monthly/yearly reminders for property taxes, utility bills, SIPs,

    and pension contributions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        AssetSubLedger,
        on_delete=models.CASCADE,
        related_name="compliance_schedules",
    )
    operational_account = models.ForeignKey(
        AssetOperationalAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
    )
    title = models.CharField(
        max_length=255,
        help_text="e.g., 'Panchayat Land Tax 2026-27' or 'NPS Monthly SIP'",
    )
    schedule_type = models.CharField(
        max_length=32, choices=ScheduleType.choices, db_index=True
    )
    recurrence_pattern = models.CharField(
        max_length=20,
        choices=RecurrencePattern.choices,
        default=RecurrencePattern.MONTHLY,
    )

    due_date = models.DateField(db_index=True)
    expected_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    advance_notice_days = models.PositiveIntegerField(
        default=10, help_text="Days in advance to alert on dashboard"
    )

    is_paid = models.BooleanField(default=False, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    linked_row_identifier = models.CharField(
        max_length=64, blank=True, null=True, db_index=True
    )

    class Meta:
        db_table = "ledger_asset_compliance_schedule"
        verbose_name = "Compliance Schedule / Reminder"
        verbose_name_plural = "Compliance Schedules & Reminders"
        ordering = ["due_date"]

    def __str__(self):
        status = "PAID" if self.is_paid else "PENDING"
        return (
            f"{self.title} | Due: {self.due_date} | ₹{self.expected_amount} [{status}]"
        )


# ============================================================================
# 5. LINE-ITEM SUB-LEDGER TRANSACTION MAPPER
# ============================================================================


class AssetTransactionMapping(models.Model):
    """Binds a raw bank statement transaction (row_identifier) or manual cash

    entry directly to an Asset Sub-Ledger item and operational account.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        AssetSubLedger,
        on_delete=models.PROTECT,
        related_name="transaction_mappings",
    )
    operational_account = models.ForeignKey(
        AssetOperationalAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    schedule = models.ForeignKey(
        AssetComplianceSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    row_identifier = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        null=True,
        help_text="Hex fingerprint matching ledger_journal_entry. Null if cash entry.",
    )
    is_cash_entry = models.BooleanField(
        default=False,
        help_text="True if transaction occurred offline via cash without a bank row.",
    )

    transaction_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_purpose = models.CharField(
        max_length=64,
        help_text="e.g., PROPERTY_TAX, UTILITY_BILL, SIP_CONTRIBUTION, CAPITAL_IMPROVEMENT",
    )
    user_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_asset_transaction_mapping"
        verbose_name = "Asset Transaction Mapping"
        verbose_name_plural = "Asset Transaction Mappings"

    def __str__(self):
        source = "CASH" if self.is_cash_entry else f"ROW: {self.row_identifier[:8]}..."
        return f"[{self.asset.asset_code}] ₹{self.amount} ({self.transaction_purpose}) via {source}"


# ============================================================================
# 6. CANDIDATE MATCHING ALGORITHM SERVICE METHOD
# ============================================================================


class AssetCandidateMatcher:

    @staticmethod
    def find_candidate_rows(*args, **kwargs):
        return ServiceCandidateMatcher.find_candidate_rows(*args, **kwargs)
