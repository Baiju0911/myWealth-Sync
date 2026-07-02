# S:\_BaijSoft\myWealth-Sync\backend\tracker\models.py

import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils import timezone
import json

# ==========================================
# 1. AUTHENTICATION & SECURITY TABLES (RBAC)
# ==========================================


class Permission(models.Model):
    """
    Table-driven fine-grained actions (e.g., 'CAN_UPLOAD_STATEMENT', 'CAN_READ_LEDGER')
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.codename


class Role(models.Model):
    """
    Table-driven security profiles. No hardcoded app strings.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)  # e.g., "PLATFORM_OWNER"
    permissions = models.ManyToManyField(
        Permission, related_name="roles", db_table="auth_role_permissions"
    )

    def __str__(self):
        return self.name


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError("Users must provide a valid email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        owner_role, _ = Role.objects.get_or_create(name="PLATFORM_OWNER")
        extra_fields.setdefault("is_staff", True)
        return self.create_user(email, password, role=owner_role, **extra_fields)


class User(AbstractBaseUser):
    """
    Unified high-end customer accounting core engine user identity.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=255, unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="users", null=True
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


# ==========================================
# 2. BANK & ROUTING PLATFORM ENTITIES
# ==========================================


class Bank(models.Model):
    code = models.CharField(max_length=10, unique=True)
    display_name = models.CharField(max_length=100)


class Account(models.Model):
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=100)  # e.g., "Primary Savings"
    account_type = models.CharField(max_length=20)  # ASSET, LIABILITY
    account_number = models.CharField(max_length=30, blank=True)  # 🌟 Full AC Number
    ifsc_code = models.CharField(max_length=20)
    branch_name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)


class BankCredential(models.Model):
    # 🎯 Points directly to the specific Account entity!
    account = models.OneToOneField(
        "Account", on_delete=models.CASCADE, related_name="credential"
    )

    # 🎯 THE UPGRADE: Replaced single CharField with a flexible JSON Array list vault
    password_vault = models.JSONField(default=list, blank=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bank_credentials",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bank Credential"
        verbose_name_plural = "Bank Credentials"
        unique_together = [("user", "account")]

    def __str__(self):
        return f"Keychain Vault for {self.account.name} ({self.user.username})"


class BankLayoutSchema(models.Model):
    """
    Stores layout structural instructions to dynamically parse messy
    CSV or PDF statement variations out of database maps.
    """

    FILE_TYPE_CHOICES = [
        ("CSV", "Comma Separated Values"),
        ("PDF", "Portable Document Format"),
    ]
    DIRECTION_CHOICES = [
        ("SIGNED", "Single Column Signed Amount"),
        ("SPLIT", "Separate Debit/Credit Columns"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100, unique=True, help_text="e.g., 'SBI_SAVINGS', 'FED_Savings'"
    )
    file_type = models.CharField(
        max_length=10, choices=FILE_TYPE_CHOICES, default="CSV"
    )

    # 🔍 Parsing Anchor Triggers
    header_trigger_text = models.CharField(
        max_length=255,
        help_text="Text snippet that signifies the main transaction grid header row starts",
    )

    # 🔢 Structural Column Layout Indices (0-indexed mapping maps)
    date_col_idx = models.IntegerField(default=0)
    narration_col_idx = models.IntegerField(default=1)

    # 💰 Balance Calculations Map Rules
    amount_style = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, default="SIGNED"
    )
    single_amount_col_idx = models.IntegerField(default=2, blank=True, null=True)
    debit_col_idx = models.IntegerField(blank=True, null=True)
    credit_col_idx = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} Schema ({self.file_type})"


# ==========================================
# 3. DOUBLE-ENTRY LEDGER OPERATION CORE
# ==========================================


class TransactionHeader(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    narration = models.TextField()
    source = models.CharField(
        max_length=50, default="MANUAL"
    )  # UPLOADED_STATEMENT, QR_SCAN
    upi_rrn = models.CharField(max_length=50, blank=True, null=True)
    merchant_vpa = models.CharField(max_length=100, blank=True, null=True)
    scanned_by = models.CharField(max_length=100, blank=True, default="Unknown Device")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.date} - {self.narration[:30]}"


class JournalEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        TransactionHeader, on_delete=models.CASCADE, related_name="entries"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="journal_lines"
    )
    # Positive = Debit (Asset Up, Expense Up)
    # Negative = Credit (Asset Down, Income Up, Liability Up)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Journal Entries"

    def __str__(self):
        type_prefix = "Dr" if self.amount >= 0 else "Cr"
        return f"{type_prefix}: {self.account.name} | Row Value: ₹{abs(self.amount)}"


########


class StatementStagingLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 🎯 TARGET CONNECTIONS
    account = models.ForeignKey(
        "Account", on_delete=models.CASCADE, related_name="staging_lines"
    )
    bank = models.ForeignKey(
        "Bank", on_delete=models.CASCADE, related_name="staging_lines"
    )

    # 🔗 THE AUDIT MATRIX LINK: Connects this individual row back to its master batch ingest profile run
    ingest_registry = models.ForeignKey(
        "StatementIngestRegistry",
        on_delete=models.CASCADE,
        related_name="staging_lines",
        null=True,  # Safe fallback for historical records
        blank=True,  # Allows flexible testing manipulation without validation crashes
        help_text="The parent file upload profile history record linked to this transaction.",
    )

    # 📅 METADATA TIMESTAMPS
    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )  # When you dropped the file in
    raw_statement_date = (
        models.DateField()
    )  # The actual TXN date from the statement file

    # 📝 EXTRACTED LINE VALUES
    narration = models.TextField()
    cheque_ref_number = models.TextField(blank=True, null=True)

    # 💰 BALANCE TRACKING QUANTITIES
    # Positive values flag Money Out (Debits), Negative values flag Money In (Credits)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    running_balance = models.DecimalField(
        max_digits=15, decimal_places=2, blank=True, null=True
    )
    debit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    bank_transaction_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Core banking transaction system identifier string (e.g., S29270471, FB209745)",
    )
    transaction_type = models.CharField(
        max_length=50, null=True, blank=True, help_text="e.g., NFT, UPI, CHQ, TFR"
    )
    # 🤖 ENGINE CLASSIFICATION STATS
    # PENDING = Waiting for user approval, SUGGESTED = Auto-routed by tokens, MATCHED = Ready to commit
    row_identifier = models.CharField(
        max_length=64, db_index=True, null=True, blank=True
    )
    routing_status = models.CharField(max_length=20, default="PENDING")
    suggested_contra_account = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staging_suggestions",
    )

    class Meta:
        db_table = "ledger_statementstagingline"
        verbose_name = "Statement Staging Line"
        verbose_name_plural = "Statement Staging Lines"
        ordering = ["raw_statement_date", "uploaded_at"]

    def __str__(self):
        return f"{self.raw_statement_date} | {self.bank.code} | {self.narration[:30]} | ₹{self.amount}"


class StatementIngestRegistry(models.Model):
    """
    📜 STATEMENT INGEST AUDIT REGISTRY:
    Tracks structural audit meta-profiles, balancing parameters, and source properties
    for every individual statement processing run.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        "Account", on_delete=models.CASCADE, related_name="ingest_logs"
    )

    # File Context Markers
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, help_text="PDF, CSV, etc.")
    vault_decrypted = models.BooleanField(default=False)

    # 📅 Statement Temporal Boundaries (NEW FIELDS)
    report_from_date = models.DateField(
        null=True,
        blank=True,
        help_text="The explicit start date covered by the bank statement.",
    )
    report_to_date = models.DateField(
        null=True,
        blank=True,
        help_text="The explicit end date covered by the bank statement.",
    )

    # Financial Balance Footprints
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    total_debit_amount = models.DecimalField(max_digits=15, decimal_places=2)
    total_credit_amount = models.DecimalField(max_digits=15, decimal_places=2)

    # Row Counter Footprints
    total_row_count = models.IntegerField(default=0)
    debit_line_count = models.IntegerField(default=0)
    credit_line_count = models.IntegerField(default=0)
    skipped_duplicate_count = models.IntegerField(default=0)

    admin_notes_count = models.IntegerField(
        default=0,
        help_text="Tracks system noise rows, statement footers, or non-financial note entries.",
    )

    # Environment Provenance Markers
    ingested_at = models.DateTimeField(default=timezone.now)
    source_channel = models.CharField(max_length=50, default="WEB_DASHBOARD")

    class Meta:
        db_table = "tracker_statement_ingest_registry"

    def __str__(self):
        # Enriched string representation to show coverage dates if available
        date_span = ""
        if self.report_from_date and self.report_to_date:
            date_span = f" [{self.report_from_date} to {self.report_to_date}]"
        return f"Ingest {self.file_name}{date_span} -> Account: {self.account.name} ({self.ingested_at.date()})"


class UserStatementTemplate(models.Model):
    # Available parsing engines within the pipeline table
    STRATEGY_CHOICES = [
        ("STRICT_MATRIX", "Strict Coordinate Matrix"),
        ("RELATIVE_SEQUENCE", "Relative Text Sequences"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account = models.ForeignKey(
        "Account",  # Lazy reference handles import circularity cleanly
        on_delete=models.CASCADE,
        related_name="statement_templates",
        null=True,
        blank=True,
        help_text="Direct link to a specific bank account configuration.",
    )

    template_name = models.CharField(
        max_length=100, help_text="e.g., SBI_NRI_Stacked_2026"
    )
    matching_keyword = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Lookup search anchor signature matching bank layout profiles.",
    )

    # ─── 🎯 THE PIPELINE STRATEGY ROUTER ───
    parser_strategy_code = models.CharField(
        max_length=50,
        choices=STRATEGY_CHOICES,
        default="STRICT_MATRIX",
        help_text="Explicitly binds this layout template profile to a code-execution engine strategy.",
    )

    # ─── 📐 HORIZONTAL CANVAS POSITION CHANNELS ───
    date_x = models.FloatField(
        default=10.0, help_text="Horizontal percentage start point for Date"
    )
    narration_x = models.FloatField(
        default=18.0, help_text="Horizontal percentage start point for Description"
    )
    debit_x = models.FloatField(
        default=52.0, help_text="Horizontal percentage start point for Debits"
    )
    credit_x = models.FloatField(
        default=60.0, help_text="Horizontal percentage start point for Credits"
    )
    balance_x = models.FloatField(
        default=98.0, help_text="Horizontal percentage start point for Running Balances"
    )

    # ─── ⚖️ FALLBACK INDEX TRACKERS (FOR MULTI-COLUMN GRID FAMILIES) ───
    date_index = models.IntegerField(default=0)
    narration_index = models.IntegerField(default=1)
    balance_index = models.IntegerField(default=3)
    debit_index = models.IntegerField(null=True, blank=True)
    credit_index = models.IntegerField(null=True, blank=True)

    # ─── ⚙️ TUNING VARIABLES & CONFIG FLAGS ───
    date_format = models.CharField(max_length=50, default="%d-%m-%Y")
    y_tolerance = models.FloatField(
        default=3.0, help_text="Vertical line baseline grouping tolerance windows"
    )
    multiline_enabled = models.BooleanField(
        default=True,
        help_text="Toggles the multi-line narration accumulator logic loop",
    )
    header_lines_to_skip = models.IntegerField(
        default=0, help_text="Rows to discard at top of pages"
    )
    footer_lines_to_skip = models.IntegerField(
        default=0, help_text="Rows to discard at bottom of pages"
    )

    # ─── 🛡️ THE CENTRALIZED SSOT REGEX & NOISE GUARDIAN ───
    signature_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores regex_patterns, noise_patterns, and opening_balance_markers.",
    )

    # Dedicated Schema Mapper for Bank-Specific Column Aliases
    header_mapping_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores column label aliases, e.g., {'date': ['Date', 'Txn Date'], 'debit': ['Debit', 'Withdrawal']}",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_userstatementtemplate"
        verbose_name = "User Statement Template"
        verbose_name_plural = "User Statement Templates"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Handle emergency safety fallbacks for both JSON fields
        for field in ["signature_json", "header_mapping_json"]:
            try:
                val = getattr(self, field)
                if isinstance(val, str):
                    setattr(self, field, json.loads(val))
            except Exception:
                setattr(self, field, {})

    def __str__(self):
        return f"[{self.parser_strategy_code}] {self.template_name} -> {self.account.name if self.account else 'Unlinked'}"


############ Accounting Categories & Ledger Mapping Tables ############

# ========================================================
# 1. TAXONOMY RULES & CENTRAL CONFIGURATION PATTERNS
# ========================================================


class MasterFinancialCategory(models.Model):
    """
    🎯 CONSOLIDATED MASTER CATEGORY & PATTERN MATRIX
    Clubs balancesheetheader, knowndefaultheader, and selftransferheader into one framework.
    """

    CATEGORY_TYPES = [
        ("REGULAR", "Standard Balance Sheet / Expense Item"),
        ("KNOWN_DEFAULT", "Auto-Matched Known Rule Node"),
        ("SELF_TRANSFER", "Inter-Account Internal Transfer Rule"),
    ]

    id = models.AutoField(primary_key=True)
    sno = models.IntegerField(
        default=1, help_text="Stores legacy ID reference number tracks"
    )
    category_type = models.CharField(
        max_length=20, choices=CATEGORY_TYPES, default="REGULAR", db_index=True
    )

    # 📊 Taxonomy Layout Chains
    act_category = models.CharField(max_length=100)
    act_subcategory = models.CharField(max_length=100)
    categories_items = models.CharField(max_length=100)
    dashboard_cat = models.CharField(max_length=100)

    # ⚡ NEW COMPACT VAULTS
    keys = models.JSONField(
        default=dict, help_text="Stores matching tokens: {'key1': '...', 'key2': '...'}"
    )
    bank_types = models.JSONField(
        default=dict,
        help_text="Stores inter-bank routing details: {'from': '...', 'to': '...'}",
    )

    self_account = models.CharField(max_length=100, blank=True, null=True)
    transfer_value = models.CharField(max_length=200, blank=True, null=True)
    remarks = models.CharField(max_length=100, blank=True, null=True)
    concatenate = models.CharField(max_length=100, blank=True, null=True)
    monthly_expense = models.BooleanField(default=False)

    class Meta:
        db_table = "ledger_mastercategory"
        verbose_name = "Master Financial Category"
        verbose_name_plural = "Master Financial Categories"
        ordering = ["category_type", "act_category", "categories_items"]

    def __str__(self):
        return f"[{self.category_type}] {self.act_category} -> {self.categories_items}"


class AccountingRule(models.Model):
    """
    📜 TIERED ACCOUNTING POLICIES & GOLDEN RULES MATRIX
    Maintains traditional financial evaluation tracking vectors (GR01 - GR75).
    """

    id = models.BigAutoField(primary_key=True)
    rule_code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Unique custom rule code indicator string token: GR01, GR07",
    )
    rule_title = models.CharField(max_length=255)
    entry_type = models.CharField(
        max_length=10,
        choices=[("Debit", "Debit"), ("Credit", "Credit")],
        help_text="Target verification accounting vector direction",
    )
    rule_priority = models.IntegerField(
        default=1,
        help_text="Sorting weight priority indicator to settle keyword competition logs",
    )

    # 🔍 Rule Search Verification Constraints
    description_tags = models.JSONField(
        help_text="Array listing search trigger tracking tags keywords"
    )
    examples = models.JSONField(
        help_text="Array containing mock raw ledger transactions data"
    )

    # 🧳 THE METADATA VAULT (Combines summary, categorization type, layout targets)
    rule_metadata = models.JSONField(
        default=dict,
        help_text="Stores: golden_rule_type, account_type, golden_rule_summary, category, subcategory",
    )

    # 🛡️ Pipeline Controls
    is_active = models.BooleanField(default=True)
    apply_to_ai = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_accountingrule"
        verbose_name = "Accounting Rule"
        verbose_name_plural = "Accounting Rules"
        ordering = ["rule_priority"]

    def __str__(self):
        return f"{self.rule_code}: {self.rule_title} ({self.entry_type})"


# ========================================================
# 2. EXTENDED DOUBLE-ENTRY LEDGER LINE ALLOCATIONS
# ========================================================


class JournalEntryMapping(models.Model):
    """
    🔗 THE RELATIONAL INTEGRATION LINK
    Instead of building a separate transaction ledger table, this extends your
    existing core JournalEntry row. It decorates your double-entry rows with
    your multi-tier category structures and tracking rule codes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 🎯 Points directly back to your existing core transaction lines
    journal_entry = models.OneToOneField(
        "JournalEntry",  # Use 'your_app.JournalEntry' if this model sits in a different folder
        on_delete=models.CASCADE,
        related_name="category_mapping",
        help_text="Links to your signed-amount double-entry row line",
    )

    # 📊 Assigns your custom category tracks
    assigned_category = models.ForeignKey(
        MasterFinancialCategory, on_delete=models.PROTECT, related_name="mapped_entries"
    )

    # 📜 Tracks exactly which rule processed this row for clear audit logging
    applied_rule = models.ForeignKey(
        AccountingRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mapped_entries",
    )

    class Meta:
        db_table = "ledger_entry_mapping"
        verbose_name = "Journal Entry Mapping"
        verbose_name_plural = "Journal Entry Mappings"

    def __str__(self):
        return f"Mapping -> {self.assigned_category.categories_items} (Rule: {self.applied_rule.rule_code if self.applied_rule else 'MANUAL'})"
