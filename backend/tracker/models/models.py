# S:\_BaijSoft\myWealth-Sync\backend\tracker\models.py

import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils import timezone
import json
import re
from django.core.exceptions import ValidationError
from django.db import models, transaction
from functools import cached_property
from tracker.constants import NOISE_KEYWORD_BLACKLIST


class BulkAuditQuerySet(models.QuerySet):
    """
    Custom QuerySet that intercepts bulk operations (bulk_create, bulk_update)
    and automatically emits AuditLog records for high-performance ingestion engines.
    """

    def bulk_create(self, objs, *args, **kwargs):
        created_objs = super().bulk_create(objs, *args, **kwargs)

        # Lazy import inside method to prevent circular import issues
        from .models import AuditLog

        audit_logs = []
        for obj in created_objs:
            account_id = getattr(obj, "account_id", None)
            row_identifier = getattr(obj, "row_identifier", None)
            applied_rule = None

            if hasattr(obj, "evaluation_matrix_snapshot") and isinstance(
                obj.evaluation_matrix_snapshot, dict
            ):
                applied_rule = obj.evaluation_matrix_snapshot.get(
                    "applied_rule_code"
                ) or obj.evaluation_matrix_snapshot.get("applied_rule")

            audit_logs.append(
                AuditLog(
                    action_type=f"{obj.__class__.__name__.upper()}_BULK_CREATE",
                    target_table=obj._meta.db_table,
                    account_id=account_id,
                    row_identifier=row_identifier,
                    previous_state={},
                    new_state={
                        f.name: str(getattr(obj, f.name))
                        for f in obj._meta.concrete_fields
                        if getattr(obj, f.name) is not None
                    },
                    applied_rule_code=applied_rule,
                    notes=f"Bulk created via engine pipeline (PK: {obj.pk})",
                )
            )

        if audit_logs:
            AuditLog.objects.bulk_create(audit_logs, batch_size=1000)

        return created_objs

    def bulk_update(self, objs, fields, *args, **kwargs):
        result = super().bulk_update(objs, fields, *args, **kwargs)

        from .models import AuditLog

        audit_logs = []
        for obj in objs:
            account_id = getattr(obj, "account_id", None)
            row_identifier = getattr(obj, "row_identifier", None)

            audit_logs.append(
                AuditLog(
                    action_type=f"{obj.__class__.__name__.upper()}_BULK_UPDATE",
                    target_table=obj._meta.db_table,
                    account_id=account_id,
                    row_identifier=row_identifier,
                    previous_state={},
                    new_state={
                        f: str(getattr(obj, f)) for f in fields if hasattr(obj, f)
                    },
                    notes=f"Bulk updated fields {fields} (PK: {obj.pk})",
                )
            )

        if audit_logs:
            AuditLog.objects.bulk_create(audit_logs, batch_size=1000)

        return result


class BulkAuditManager(models.Manager):
    def get_queryset(self):
        return BulkAuditQuerySet(self.model, using=self._db)


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


# class JournalEntry(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     # 🏛️ Core Context Mappings
#     account = models.ForeignKey(
#         Account, on_delete=models.PROTECT, related_name="journal_lines"
#     )

#     # 📅 Date & Tracking Vectors
#     transaction_date = models.DateField(default=timezone.now)

#     # 🛡️ THE AUDIT LINK: Matches the Hex fingerprint signature inside StatementStagingLine
#     row_identifier = models.CharField(max_length=64, db_index=True)

#     # 💰 Explicit Double-Entry Matrix Fields
#     debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
#     credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

#     # 🤖 Multi-Tier Evaluation Metadata JSON Repository
#     evaluation_matrix_snapshot = models.JSONField(
#         default=dict,
#         help_text="Stores: {t1_cat, t2_cat, t3_cat, resolved_cat, resolved_sub, applied_rule}",
#     )

#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         db_table = "ledger_journal_entry"
#         verbose_name_plural = "Journal Entries"


class TaxonomyTree(models.Model):
    objects = BulkAuditManager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=100)
    subcategory = models.CharField(max_length=100)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_taxonomy_tree"
        unique_together = ("category", "subcategory")
        ordering = ["category", "display_order", "subcategory"]

    def __str__(self):
        return f"{self.category} ➔ {self.subcategory}"


class AccountingRule(models.Model):
    objects = BulkAuditManager()

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

    # 🎯 SINGLE SOURCE OF TRUTH (SSOT) BINDING
    taxonomy = models.ForeignKey(
        TaxonomyTree,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="accounting_rules",
        db_column="taxonomy_id",
        help_text="Master taxonomy node authority governing this rule",
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

    # 💡 HELPER PROPERTIES (Ensures zero-breakage for existing pipeline code)
    @property
    def resolved_category(self):
        """Returns canonical category from TaxonomyTree if linked, else falls back to metadata."""
        if self.taxonomy:
            return self.taxonomy.category
        return self.rule_metadata.get("category")

    @property
    def resolved_subcategory(self):
        """Returns canonical subcategory from TaxonomyTree if linked, else falls back to metadata."""
        if self.taxonomy:
            return self.taxonomy.subcategory
        return self.rule_metadata.get("subcategory")

    def save(self, *args, **kwargs):
        """
        Auto-syncs rule_metadata JSON keys ('category' & 'subcategory')
        with the linked TaxonomyTree node upon saving.
        """
        if self.taxonomy:
            if not isinstance(self.rule_metadata, dict):
                self.rule_metadata = {}
            self.rule_metadata["category"] = self.taxonomy.category
            self.rule_metadata["subcategory"] = self.taxonomy.subcategory

        super().save(*args, **kwargs)


########


class StatementStagingLine(models.Model):

    objects = BulkAuditManager()

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
    objects = BulkAuditManager()
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
    objects = BulkAuditManager()

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


# ========================================================
# 2. EXTENDED DOUBLE-ENTRY LEDGER LINE ALLOCATIONS
# ========================================================


class JournalEntryMapping(models.Model):
    objects = BulkAuditManager()

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


# class WIPEvaluationMatrix(models.Model):
#     objects = BulkAuditManager()

#     CONFIDENCE_CHOICES = [
#         ("HIGH", "100% Validated (Staged for Bulk Approval)"),
#         ("ZERO", "Validation Failed (Sent to Uncategorized Container)"),
#     ]

#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     # 🔗 Cloned Parent Identity Link from Staging row
#     staging_line = models.ForeignKey(
#         "StatementStagingLine", on_delete=models.CASCADE, related_name="wip_records"
#     )

#     # 🛡️ THE ARCHITECTURAL STATE Machine KEY
#     # Generated exactly as: SHA256(date + dr + cr + running_balance) or inherited sequence
#     row_footprint_hash = models.CharField(
#         max_length=64,
#         db_index=True,
#         help_text="Cloned hash state footprint linking back to Staging line",
#     )

#     # 💼 Copied Structural Context Bindings
#     account = models.ForeignKey("Account", on_delete=models.CASCADE)
#     bank = models.ForeignKey("Bank", on_delete=models.CASCADE)
#     raw_statement_date = models.DateField()
#     narration_normalized = models.TextField(
#         help_text="Cleaned, lowercase text token scanning target"
#     )

#     # 💰 Absolute Value Ledger Matrix Legs (No calculations inside table)
#     debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
#     credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

#     # 🔀 Manual Split Layout Infrastructure
#     parent_wip = models.ForeignKey(
#         "self",
#         on_delete=models.CASCADE,
#         null=True,
#         blank=True,
#         related_name="split_children",
#         help_text="Points to the parent container when split across multiple headers",
#     )
#     is_split_component = models.BooleanField(default=False)

#     # 🤖 Three-Tier Verification Engine Mappings
#     confidence_level = models.CharField(
#         max_length=10, choices=CONFIDENCE_CHOICES, default="ZERO", db_index=True
#     )
#     matched_category = models.ForeignKey(
#         "MasterFinancialCategory", on_delete=models.SET_NULL, null=True, blank=True
#     )
#     applied_rule = models.ForeignKey(
#         "AccountingRule", on_delete=models.SET_NULL, null=True, blank=True
#     )

#     # 🛡️ Pipeline Auditing Flags
#     tier_1_passed = models.BooleanField(default=False)
#     tier_2_passed = models.BooleanField(default=False)
#     tier_3_passed = models.BooleanField(default=False)
#     evaluation_errors = models.JSONField(
#         default=list,
#         blank=True,
#         help_text="Array listing gate block errors: ['UNMAPPED_PATTERN', 'MISALIGNED_HEADER']",
#     )

#     # 🎯 Tier 1: Pattern/Keyword Match Results
#     t1_category = models.CharField(max_length=100, null=True, blank=True)
#     t1_subcategory = models.CharField(max_length=100, null=True, blank=True)

#     # 🎯 Tier 2: Dashboard Context Match Results
#     t2_category = models.CharField(max_length=100, null=True, blank=True)
#     t2_subcategory = models.CharField(max_length=100, null=True, blank=True)

#     # 🎯 Tier 3: Accounting Golden Rule Match Results
#     t3_category = models.CharField(max_length=100, null=True, blank=True)
#     t3_subcategory = models.CharField(max_length=100, null=True, blank=True)

#     # 🎯 Tier 4: Master Rulebook (52 Golden Rules Regex Search)
#     t4_category = models.CharField(max_length=100, null=True, blank=True)
#     t4_subcategory = models.CharField(max_length=100, null=True, blank=True)
#     t4_passed = models.BooleanField(default=False)

#     # 🎯 Tier 5: Local AI Memory & Hybrid SLM Classifier
#     t5_category = models.CharField(max_length=100, null=True, blank=True)
#     t5_subcategory = models.CharField(max_length=100, null=True, blank=True)
#     t5_source = models.CharField(
#         max_length=50,
#         null=True,
#         blank=True,
#         help_text="Classification origin: 'vector_db_cache', 'ollama_slm', or 'bypassed'"
#     )
#     tier_5_passed = models.BooleanField(default=False)

#     # 🏆 Final Resolved Winner (Calculated via Weightage Engine)
#     resolved_category = models.CharField(max_length=100, null=True, blank=True)
#     resolved_subcategory = models.CharField(max_length=100, null=True, blank=True)

#     confidence_score = models.IntegerField(default=0)  # 0 to 100%
#     confidence_level = models.CharField(
#         max_length=10, default="ZERO"
#     )  # HIGH, MEDIUM, ZERO

#     processing_status = models.CharField(
#         max_length=20,
#         default="PENDING",
#         choices=[("PENDING", "Pending Ledger Sync"), ("COMPLETED", "Synced to Ledger")],
#     )

#     class Meta:
#         db_table = "ledger_wip_evaluation_matrix"
#         verbose_name = "WIP Evaluation Matrix"
#         verbose_name_plural = "WIP Evaluation Matrices"
#         ordering = ["raw_statement_date"]

#     def __str__(self):
#         return f"WIP [{self.confidence_level}] - Hash: {self.row_footprint_hash[:8]} - DR: {self.debit} | CR: {self.credit}"


class WIPEvaluationMatrix(models.Model):
    objects = BulkAuditManager()

    CONFIDENCE_CHOICES = [
        ("HIGH", "100% Validated (Staged for Bulk Approval)"),
        ("ZERO", "Validation Failed (Sent to Uncategorized Container)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 🔗 Cloned Parent Identity Link from Staging row
    staging_line = models.ForeignKey(
        "StatementStagingLine", on_delete=models.CASCADE, related_name="wip_records"
    )

    # 🛡️ Architectural State Machine Footprint Hash
    row_footprint_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Cloned hash state footprint linking back to Staging line",
    )

    # 💼 Copied Structural Context Bindings
    account = models.ForeignKey("Account", on_delete=models.CASCADE)
    bank = models.ForeignKey("Bank", on_delete=models.CASCADE)
    raw_statement_date = models.DateField()
    narration_normalized = models.TextField(
        help_text="Cleaned, lowercase text token scanning target"
    )

    # 💰 Ledger Matrix Legs
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    # 🔀 Manual Split Infrastructure
    parent_wip = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="split_children",
    )
    is_split_component = models.BooleanField(default=False)

    # 🤖 Verification Engine Mappings
    matched_category = models.ForeignKey(
        "MasterFinancialCategory", on_delete=models.SET_NULL, null=True, blank=True
    )
    applied_rule = models.ForeignKey(
        "AccountingRule", on_delete=models.SET_NULL, null=True, blank=True
    )

    # 🧩 CONSOLIDATED 5-TIER EVALUATION MATRIX SNAPSHOT (JSON)
    # Stores t1, t2, t3, t4, and t5 AI outputs in one structured payload
    matrix_evaluation = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON payload containing t1..t5 tier breakdowns and system certainty scores",
    )

    evaluation_errors = models.JSONField(
        default=list,
        blank=True,
        help_text="Array listing gate block errors",
    )

    # 🏆 Final Resolved Winner
    resolved_category = models.CharField(max_length=100, null=True, blank=True)
    resolved_subcategory = models.CharField(max_length=100, null=True, blank=True)

    confidence_score = models.IntegerField(default=0)  # 0 to 100%
    confidence_level = models.CharField(
        max_length=10, choices=CONFIDENCE_CHOICES, default="ZERO", db_index=True
    )

    processing_status = models.CharField(
        max_length=20,
        default="PENDING",
        choices=[("PENDING", "Pending Ledger Sync"), ("COMPLETED", "Synced to Ledger")],
    )

    class Meta:
        db_table = "ledger_wip_evaluation_matrix"
        verbose_name = "WIP Evaluation Matrix"
        verbose_name_plural = "WIP Evaluation Matrices"
        ordering = ["raw_statement_date"]

    def __str__(self):
        return f"WIP [{self.confidence_level}] - Hash: {self.row_footprint_hash[:8]} - DR: {self.debit} | CR: {self.credit}"


class DirectionalVectorOverride(models.Model):
    """
    🔄 COGNITIVE VECTOR OVERRIDE TABLE
    Dynamically routes a transaction to its true counterpart group when
    the financial cashflow direction (Debit vs Credit) conflicts with the rule.
    """

    source_category = models.CharField(
        max_length=100, help_text="e.g., Expenses, Charity"
    )
    expected_vector = models.CharField(
        max_length=10,
        choices=[("DEBIT", "Debit (Outflow)"), ("CREDIT", "Credit (Inflow)")],
        default="DEBIT",
        help_text="The directional vector this category normally expects.",
    )

    # Target values to swap to when the mismatch occurs
    target_category = models.CharField(max_length=100, help_text="e.g., Income")
    target_subcategory = models.CharField(
        max_length=100, help_text="e.g., Refunds & Reversals"
    )

    is_active = models.BooleanField(default=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tracker_directional_vector_override"
        verbose_name = "Directional Vector Override"
        verbose_name_plural = "Directional Vector Overrides"
        unique_together = ("source_category", "expected_vector")

    def __str__(self):
        return f"If {self.source_category} is {self.expected_vector} -> Pivot to {self.target_category}"


###For Classification Future AI thing


# ============================================================================
# 1. TAXONOMY TREE
# ============================================================================
# class AccountingRule(models.Model):
#     objects = BulkAuditManager()

#     id = models.BigAutoField(primary_key=True)
#     rule_code = models.CharField(
#         max_length=20,
#         unique=True,
#         help_text="Unique custom rule code indicator string token: GR01, GR07",
#     )
#     rule_title = models.CharField(max_length=255)
#     entry_type = models.CharField(
#         max_length=10,
#         choices=[("Debit", "Debit"), ("Credit", "Credit")],
#         help_text="Target verification accounting vector direction",
#     )
#     rule_priority = models.IntegerField(
#         default=1,
#         help_text="Sorting weight priority indicator to settle keyword competition logs",
#     )

#     # 🔍 Rule Search Verification Constraints
#     description_tags = models.JSONField(
#         help_text="Array listing search trigger tracking tags keywords"
#     )
#     examples = models.JSONField(
#         help_text="Array containing mock raw ledger transactions data"
#     )

#     # 🧳 THE METADATA VAULT (Combines summary, categorization type, layout targets)
#     rule_metadata = models.JSONField(
#         default=dict,
#         help_text="Stores: golden_rule_type, account_type, golden_rule_summary, category, subcategory",
#     )

#     # 🛡️ Pipeline Controls
#     is_active = models.BooleanField(default=True)
#     apply_to_ai = models.BooleanField(default=False)
#     notes = models.TextField(blank=True, null=True)

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = "ledger_accountingrule"
#         verbose_name = "Accounting Rule"
#         verbose_name_plural = "Accounting Rules"
#         ordering = ["rule_priority"]

#     def __str__(self):
#         return f"{self.rule_code}: {self.rule_title} ({self.entry_type})"


# class TaxonomyTree(models.Model):
#     objects = BulkAuditManager()
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     category = models.CharField(max_length=100)
#     subcategory = models.CharField(max_length=100)
#     display_order = models.IntegerField(default=0)
#     is_active = models.BooleanField(default=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = "ledger_taxonomy_tree"
#         unique_together = ("category", "subcategory")
#         ordering = ["category", "display_order", "subcategory"]

#     def __str__(self):
#         return f"{self.category} ➔ {self.subcategory}"


# ============================================================================
# 2. CLASSIFICATION STATUS ENUM
# ============================================================================
class ClassificationStatus(models.TextChoices):
    INITIAL = "INITIAL", "Initial Auto-Classification"
    RECLASSIFIED = "RECLASSIFIED", "Manually Reclassified"
    SUSPENSE = "SUSPENSE", "Pending Suspense"
    AUTO_SWEPT = "AUTO_SWEPT", "Auto-Swept by Rule Engine"
    CONFIRMED = "CONFIRMED", "Audited & Confirmed"
    SPLIT = "SPLIT", "Split Transaction"
    SYSTEM_INTERNAL = "SYSTEM_INTERNAL", "System Contra / Inter-Account Transfer"


# ============================================================================
# 3. CLASSIFICATION RULE
# ============================================================================
# class ClassificationRule(models.Model):
#     name = models.CharField(max_length=255)
#     rule_code = models.CharField(max_length=50, unique=True)
#     rule_type = models.CharField(
#         max_length=10,
#         choices=[("Debit", "Debit"), ("Credit", "Credit")],
#         default="Debit",
#     )
#     target_category = models.CharField(max_length=100)
#     target_subcategory = models.CharField(max_length=100)

#     # 🎯 1. Use native JSONField for cleaner pattern array manipulation
#     patterns = models.JSONField(
#         default=list,
#         blank=True,
#         help_text="JSON list of clean multi-token pattern strings e.g. ['MOHANAN P', 'SWIGGY YESPAY']",
#     )

#     priority = models.IntegerField(default=1)
#     is_active = models.BooleanField(default=True)
#     created_from_manual_override = models.BooleanField(default=True)
#     match_count = models.IntegerField(default=0)
#     taxonomy = models.ForeignKey(
#         "TaxonomyTree", on_delete=models.SET_NULL, null=True, blank=True
#     )

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = "ledger_classification_rule"

#     def __str__(self):
#         return f"{self.rule_code} -> {self.target_subcategory} ({len(self.patterns)} patterns)"

#     def get_patterns(self) -> list[str]:
#         """Returns a clean list of pattern strings from the JSON field."""
#         if not self.patterns:
#             return []
#         if isinstance(self.patterns, list):
#             return [str(p).strip() for p in self.patterns if p and str(p).strip()]
#         if isinstance(self.patterns, str):
#             try:
#                 parsed = json.loads(self.patterns)
#                 if isinstance(parsed, list):
#                     return [str(p).strip() for p in parsed if p and str(p).strip()]
#             except json.JSONDecodeError:
#                 return [self.patterns.strip()]
#         return []

#     # 🎯 2. Add Helper Methods directly on the Model class
#     def add_pattern(self, new_pattern: str) -> bool:
#         """Appends a new pattern string to the JSON array if not already present."""
#         if not new_pattern or not str(new_pattern).strip():
#             return False

#         clean_p = str(new_pattern).strip().upper()

#         if not isinstance(self.patterns, list):
#             self.patterns = []

#         if clean_p not in self.patterns:
#             self.patterns.append(clean_p)
#             self.match_count = (self.match_count or 0) + 1
#             self.save(update_fields=["patterns", "match_count", "updated_at"])
#             return True

#         return False

#     def remove_pattern(self, pattern_to_remove: str) -> bool:
#         """Removes a pattern from the JSON array without destroying the rule."""
#         clean_p = str(pattern_to_remove).strip().upper()

#         if isinstance(self.patterns, list) and clean_p in self.patterns:
#             self.patterns.remove(clean_p)
#             self.save(update_fields=["patterns", "updated_at"])
#             return True

#         return False


# class ClassificationRule(models.Model):
#     name = models.CharField(max_length=255)
#     rule_code = models.CharField(max_length=50, unique=True)
#     rule_type = models.CharField(
#         max_length=10,
#         choices=[("Debit", "Debit"), ("Credit", "Credit")],
#         default="Debit",
#     )
#     target_category = models.CharField(max_length=100)
#     target_subcategory = models.CharField(max_length=100)

#     # 🎯 1. Native JSONField
#     patterns = models.JSONField(
#         default=list,
#         blank=True,
#         help_text="JSON list of clean multi-token pattern strings e.g. ['MOHANAN P', 'SWIGGY YESPAY']",
#     )

#     priority = models.IntegerField(default=1)
#     is_active = models.BooleanField(default=True)
#     created_from_manual_override = models.BooleanField(default=True)
#     match_count = models.IntegerField(default=0)
#     taxonomy = models.ForeignKey(
#         "TaxonomyTree", on_delete=models.SET_NULL, null=True, blank=True
#     )

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = "ledger_classification_rule"

#     def __str__(self):
#         return f"{self.rule_code} -> {self.target_subcategory} ({len(self.get_patterns())} patterns)"

#     def save(self, *args, **kwargs):
#         """Clears cached property when saving updated patterns."""
#         if hasattr(self, "_cached_patterns"):
#             del self.__dict__["_cached_patterns"]
#         super().save(*args, **kwargs)

#     def save(self, *args, **kwargs):
#         """
#         Dynamically extracts and appends high-value VPA/brand tokens
#         from whatever narration string is added to self.patterns.
#         Works generically for ANY category (Amazon, Blinkit, Swiggy, Uber, etc.).
#         """
#         if isinstance(self.patterns, list):
#             expanded_patterns = set()

#             for pat in self.patterns:
#                 if not pat or not str(pat).strip():
#                     continue

#                 raw_str = str(pat).strip().upper()
#                 expanded_patterns.add(raw_str)

#                 # Extract pure alphanumeric segments (split by /, @, spaces, dots)
#                 tokens = [t for t in re.split(r"[/@\s._\-]+", raw_str) if len(t) >= 4]

#                 for t in tokens:
#                     # Ignore pure numbers or transaction IDs
#                     if not t.isdigit():
#                         expanded_patterns.add(t)

#             self.patterns = list(expanded_patterns)

#         # Clear cached property if present
#         if "_cached_patterns" in self.__dict__:
#             del self.__dict__["_cached_patterns"]

#         super().save(*args, **kwargs)

#     @cached_property
#     def _cached_patterns(self) -> list[str]:
#         """Request-scoped cached list of patterns."""
#         if not self.patterns or not isinstance(self.patterns, list):
#             return []
#         return [
#             p.strip().upper() for p in self.patterns if isinstance(p, str) and p.strip()
#         ]

#     def get_patterns(self) -> list[str]:
#         return self._cached_patterns

#     def add_pattern(self, new_pattern: str) -> bool:
#         """Appends a new pattern and updates DB efficiently."""
#         if not new_pattern or not str(new_pattern).strip():
#             return False

#         clean_p = str(new_pattern).strip().upper()

#         current_pats = list(self.patterns) if isinstance(self.patterns, list) else []

#         if clean_p not in current_pats:
#             current_pats.append(clean_p)
#             self.patterns = current_pats
#             self.match_count = (self.match_count or 0) + 1
#             self.save(update_fields=["patterns", "match_count", "updated_at"])
#             return True

#         return False

#     def remove_pattern(self, pattern_to_remove: str) -> bool:
#         """Removes a pattern without destroying the rule."""
#         clean_p = str(pattern_to_remove).strip().upper()

#         if isinstance(self.patterns, list) and clean_p in self.patterns:
#             self.patterns.remove(clean_p)
#             self.save(update_fields=["patterns", "updated_at"])
#             return True

#         return False


# class ClassificationRule(models.Model):
#     name = models.CharField(max_length=255)
#     rule_code = models.CharField(max_length=50, unique=True)
#     rule_type = models.CharField(
#         max_length=10,
#         choices=[("Debit", "Debit"), ("Credit", "Credit")],
#         default="Debit",
#     )
#     target_category = models.CharField(max_length=100)
#     target_subcategory = models.CharField(max_length=100)

#     # 🎯 Native JSONField
#     patterns = models.JSONField(
#         default=list,
#         blank=True,
#         help_text="JSON list of clean multi-token pattern strings e.g. ['MOHANAN P', 'SWIGGY YESPAY']",
#     )

#     priority = models.IntegerField(default=1)
#     is_active = models.BooleanField(default=True)
#     created_from_manual_override = models.BooleanField(default=True)
#     match_count = models.IntegerField(default=0)
#     taxonomy = models.ForeignKey(
#         "TaxonomyTree", on_delete=models.SET_NULL, null=True, blank=True
#     )

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = "ledger_classification_rule"

#     def __str__(self):
#         return f"{self.rule_code} -> {self.target_subcategory} ({len(self.get_patterns())} patterns)"

#     def save(self, *args, **kwargs):
#         """
#         Dynamically extracts VPA/brand tokens while filtering out
#         noise words (ACCOUNT, INTENT, MERCHANT, etc.).
#         Clears request-scoped cache upon saving.
#         """
#         if isinstance(self.patterns, list):
#             expanded_patterns = set()

#             for pat in self.patterns:
#                 if not pat or not str(pat).strip():
#                     continue

#                 raw_str = str(pat).strip().upper()

#                 # Add multi-word string if it's not a generic noise word
#                 if raw_str not in NOISE_KEYWORD_BLACKLIST:
#                     expanded_patterns.add(raw_str)

#                 # Extract pure alphanumeric segments (split by /, @, spaces, dots)
#                 tokens = [t for t in re.split(r"[/@\s._\-]+", raw_str) if len(t) >= 4]

#                 for t in tokens:
#                     # Ignore pure numbers, transaction IDs, and noise keywords
#                     if not t.isdigit() and t not in NOISE_KEYWORD_BLACKLIST:
#                         expanded_patterns.add(t)

#             self.patterns = list(expanded_patterns)

#         # Clear cached property if present
#         if "_cached_patterns" in self.__dict__:
#             del self.__dict__["_cached_patterns"]

#         super().save(*args, **kwargs)

#     @cached_property
#     def _cached_patterns(self) -> list[str]:
#         """Request-scoped cached list of patterns."""
#         if not self.patterns or not isinstance(self.patterns, list):
#             return []
#         return [
#             p.strip().upper() for p in self.patterns if isinstance(p, str) and p.strip()
#         ]

#     def get_patterns(self) -> list[str]:
#         return self._cached_patterns

#     def add_pattern(self, new_pattern: str) -> bool:
#         """Appends a new pattern and updates DB efficiently."""
#         if not new_pattern or not str(new_pattern).strip():
#             return False

#         clean_p = str(new_pattern).strip().upper()
#         current_pats = list(self.patterns) if isinstance(self.patterns, list) else []

#         if clean_p not in current_pats:
#             current_pats.append(clean_p)
#             self.patterns = current_pats
#             self.match_count = (self.match_count or 0) + 1
#             self.save(update_fields=["patterns", "match_count", "updated_at"])
#             return True

#         return False

#     def remove_pattern(self, pattern_to_remove: str) -> bool:
#         """
#         Safely purges a token or full pattern string from this rule's patterns array.
#         Handles exact string matches AND sub-token stripping from compound phrases.
#         """
#         if not self.patterns or not isinstance(self.patterns, list):
#             return False

#         target = str(pattern_to_remove).strip().lstrip("#").upper()
#         updated_patterns = []
#         removed = False

#         for pat in self.patterns:
#             pat_str = str(pat).strip().upper()

#             # 1. Exact pattern match removal
#             if pat_str == target:
#                 removed = True
#                 continue

#             # 2. Sub-token removal inside compound phrases (e.g. 'ACCOUNT' in 'OWN ACCOUNT BAIJU')
#             tokens = [t for t in pat_str.split() if t != target]

#             if len(tokens) < len(pat_str.split()):
#                 removed = True
#                 if tokens:  # Rebuild pattern with remaining valid tokens
#                     updated_patterns.append(" ".join(tokens))
#             else:
#                 updated_patterns.append(pat_str)

#         if removed:
#             self.patterns = updated_patterns

#             if "_cached_patterns" in self.__dict__:
#                 del self.__dict__["_cached_patterns"]

#             self.save(update_fields=["patterns", "updated_at"])
#             return True

#         return False


class ClassificationRule(models.Model):
    name = models.CharField(max_length=255)
    rule_code = models.CharField(max_length=50, unique=True)
    rule_type = models.CharField(
        max_length=10,
        choices=[("Debit", "Debit"), ("Credit", "Credit")],
        default="Debit",
    )
    target_category = models.CharField(max_length=100)
    target_subcategory = models.CharField(max_length=100)

    # 🎯 Native JSONField
    patterns = models.JSONField(
        default=list,
        blank=True,
        help_text="JSON list of clean multi-token pattern strings e.g. ['MOHANAN P', 'SWIGGY YESPAY']",
    )

    priority = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_from_manual_override = models.BooleanField(default=True)
    match_count = models.IntegerField(default=0)
    taxonomy = models.ForeignKey(
        "TaxonomyTree", on_delete=models.SET_NULL, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_classification_rule"

    def __str__(self):
        return f"{self.rule_code} -> {self.target_subcategory} ({len(self.get_patterns())} patterns)"

    def save(self, *args, **kwargs):
        """
        Deduplicates, sanitizes, and sorts pattern strings compound-first.
        NO auto-splitting of compound phrases into single words!
        Clears request-scoped cache upon saving.
        """
        if isinstance(self.patterns, list):
            clean_pats = set()
            for pat in self.patterns:
                if not pat or not str(pat).strip():
                    continue
                clean_p = str(pat).strip().upper()
                clean_pats.add(clean_p)

            # Sort compound phrases first (multi-word -> single-word -> length)
            self.patterns = sorted(
                list(clean_pats), key=lambda x: (-len(x.split()), -len(x))
            )

        # Clear cached property if present
        if "_cached_patterns" in self.__dict__:
            del self.__dict__["_cached_patterns"]

        super().save(*args, **kwargs)

    @cached_property
    def _cached_patterns(self) -> list[str]:
        """Request-scoped cached list of patterns."""
        if not self.patterns or not isinstance(self.patterns, list):
            return []
        return [
            p.strip().upper() for p in self.patterns if isinstance(p, str) and p.strip()
        ]

    def get_patterns(self) -> list[str]:
        return self._cached_patterns

    def add_pattern(self, new_pattern: str) -> bool:
        """Appends a new pattern and updates DB efficiently."""
        if not new_pattern or not str(new_pattern).strip():
            return False

        clean_p = str(new_pattern).strip().upper()
        current_pats = list(self.patterns) if isinstance(self.patterns, list) else []

        if clean_p not in current_pats:
            current_pats.append(clean_p)
            self.patterns = current_pats
            self.match_count = (self.match_count or 0) + 1
            self.save()
            return True

        return False

    def remove_pattern(self, pattern_to_remove: str) -> bool:
        """
        Safely purges a token or full pattern string from this rule's patterns array.
        """
        if not self.patterns or not isinstance(self.patterns, list):
            return False

        target = str(pattern_to_remove).strip().lstrip("#").upper()
        updated_patterns = []
        removed = False

        for pat in self.patterns:
            pat_str = str(pat).strip().upper()

            if pat_str == target:
                removed = True
                continue

            # Remove matching sub-tokens if necessary
            tokens = [t for t in pat_str.split() if t != target]
            if len(tokens) < len(pat_str.split()):
                removed = True
                if tokens:
                    updated_patterns.append(" ".join(tokens))
            else:
                updated_patterns.append(pat_str)

        if removed:
            self.patterns = updated_patterns
            if "_cached_patterns" in self.__dict__:
                del self.__dict__["_cached_patterns"]
            self.save()
            return True

        return False


# class JournalEntry(models.Model):
#     objects = BulkAuditManager()
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     # 🏛️ Core Context Mappings
#     account = models.ForeignKey(
#         "Account", on_delete=models.PROTECT, related_name="journal_lines"
#     )

#     # 📅 Date & Tracking Vectors
#     transaction_date = models.DateField(default=timezone.now)

#     # 🛡️ THE AUDIT LINK: Matches the Hex fingerprint signature inside StatementStagingLine
#     row_identifier = models.CharField(max_length=64, db_index=True)

#     # 💰 Explicit Double-Entry Matrix Fields
#     debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
#     credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

#     # 🟢 Reclassification & Audit Tracking Flags
#     is_reclassified = models.BooleanField(default=False, db_index=True)
#     classification_status = models.CharField(
#         max_length=20,
#         choices=ClassificationStatus.choices,
#         default=ClassificationStatus.INITIAL,
#         db_index=True,
#     )

#     # 📝 Integrated JSON Remarks Repository (Stores structured text, payee, upi_ref, user_note)
#     remarks = models.JSONField(
#         default=dict,
#         blank=True,
#         help_text="Stores: {display_text, directional_prefix, target_account_name, payee, upi_ref, user_note, rule_code}",
#     )

#     # 🤖 Multi-Tier Evaluation Metadata JSON Repository (Stores t1/t2/t3, rules, audit history)
#     evaluation_matrix_snapshot = models.JSONField(
#         default=dict,
#         blank=True,
#         help_text="Stores: {t1_cat, t2_cat, t3_cat, resolved_cat, resolved_sub, applied_rule, audit_history}",
#     )

#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         db_table = "ledger_journal_entry"
#         verbose_name_plural = "Journal Entries"
#         indexes = [
#             models.Index(fields=["row_identifier", "account"]),
#             models.Index(fields=["account", "is_reclassified"]),
#             models.Index(fields=["classification_status"]),
#         ]

#     def __str__(self):
#         return f"Account #{self.account_id} | DR: {self.debit} | CR: {self.credit} | Status: {self.classification_status}"

#     @classmethod
#     @transaction.atomic
#     def reclassify_statement_line(
#         cls,
#         row_identifier: str,
#         new_category: str,
#         new_subcategory: str,
#         rule_code: str = "MANUAL",
#         taxonomy_node_account_id: int = 99,
#         user_note: str = None,
#     ):
#         """
#         Safely reclassifies Node 99 counter-entry for a specific row_identifier while preserving
#         the historical audit trail inside evaluation_matrix_snapshot JSON and storing structured
#         JSON remarks on BOTH legs.
#         """
#         # 1. Fetch BOTH double-entry legs for this row_identifier
#         all_legs = list(
#             cls.objects.select_for_update().filter(row_identifier=row_identifier)
#         )

#         entry_99 = next(
#             (leg for leg in all_legs if leg.account_id == taxonomy_node_account_id),
#             None,
#         )
#         bank_leg = next(
#             (leg for leg in all_legs if leg.account_id != taxonomy_node_account_id),
#             None,
#         )

#         if not entry_99:
#             raise ValueError(
#                 f"No Taxonomy Node ({taxonomy_node_account_id}) counter-entry found for row_identifier: {row_identifier}"
#             )

#         current_snapshot = entry_99.evaluation_matrix_snapshot or {}

#         # 2. Extract current state for audit trail
#         prev_cat = current_snapshot.get("resolved_category") or current_snapshot.get(
#             "resolved_cat", "Uncategorized"
#         )
#         prev_sub = current_snapshot.get("resolved_subcategory") or current_snapshot.get(
#             "resolved_sub", "Suspense Account"
#         )
#         prev_rule = current_snapshot.get("applied_rule_code") or current_snapshot.get(
#             "applied_rule", "UNKNOWN"
#         )

#         # 3. Construct updated metadata payload with full history
#         updated_snapshot = {
#             **current_snapshot,
#             "previous_category": prev_cat,
#             "previous_subcategory": prev_sub,
#             "previous_rule_code": prev_rule,
#             "resolved_category": new_category,
#             "resolved_subcategory": new_subcategory,
#             "applied_rule_code": rule_code,
#             "confidence_score": 100,
#             "is_reclassified": True,
#             "reclassified_at": timezone.now().isoformat(),
#         }

#         target_account_label = f"{new_category} > {new_subcategory}"
#         existing_remark_99 = (
#             entry_99.remarks if isinstance(entry_99.remarks, dict) else {}
#         )

#         # 4. Generate updated JSON remark for Counter/Taxonomy Leg
#         prefix_99 = "By" if entry_99.debit > 0 else "To"
#         display_text_99 = (
#             f"{prefix_99} {target_account_label} | Classified via {rule_code}"
#         )
#         if user_note and user_note.strip():
#             display_text_99 += f" | Note: {user_note.strip()}"

#         json_remark_99 = {
#             **existing_remark_99,
#             "directional_prefix": prefix_99,
#             "target_account_name": target_account_label,
#             "display_text": display_text_99,
#             "rule_code": rule_code,
#             "user_note": user_note.strip() if user_note else None,
#             "updated_at": timezone.now().isoformat(),
#         }

#         entry_99.evaluation_matrix_snapshot = updated_snapshot
#         entry_99.is_reclassified = True
#         entry_99.classification_status = ClassificationStatus.RECLASSIFIED
#         entry_99.remarks = json_remark_99
#         entry_99.save(
#             update_fields=[
#                 "evaluation_matrix_snapshot",
#                 "is_reclassified",
#                 "classification_status",
#                 "remarks",
#             ]
#         )

#         # 5. Generate updated JSON remark for Bank Leg if present
#         if bank_leg:
#             existing_remark_bank = (
#                 bank_leg.remarks if isinstance(bank_leg.remarks, dict) else {}
#             )
#             prefix_bank = "By" if bank_leg.debit > 0 else "To"
#             display_text_bank = f"{prefix_bank} Bank A/c | Reclassified to {target_account_label} via {rule_code}"
#             if user_note and user_note.strip():
#                 display_text_bank += f" | Note: {user_note.strip()}"

#             json_remark_bank = {
#                 **existing_remark_bank,
#                 "directional_prefix": prefix_bank,
#                 "target_account_name": "Bank A/c",
#                 "display_text": display_text_bank,
#                 "rule_code": rule_code,
#                 "user_note": user_note.strip() if user_note else None,
#                 "updated_at": timezone.now().isoformat(),
#             }

#             bank_leg.classification_status = ClassificationStatus.RECLASSIFIED
#             bank_leg.is_reclassified = True
#             bank_leg.remarks = json_remark_bank
#             bank_leg.save(
#                 update_fields=["classification_status", "is_reclassified", "remarks"]
#             )

#         return entry_99


class JournalEntry(models.Model):
    objects = BulkAuditManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 🏛️ Core Context Mappings
    account = models.ForeignKey(
        "Account", on_delete=models.PROTECT, related_name="journal_lines"
    )

    # 📅 Date & Tracking Vectors
    transaction_date = models.DateField(default=timezone.now)

    # 🛡️ THE AUDIT LINK: Matches the Hex fingerprint signature inside StatementStagingLine
    row_identifier = models.CharField(max_length=64, db_index=True)

    # 💰 Explicit Double-Entry Matrix Fields
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    # 🟢 Reclassification & Audit Tracking Flags
    is_reclassified = models.BooleanField(default=False, db_index=True)
    classification_status = models.CharField(
        max_length=20,
        choices=ClassificationStatus.choices,
        default=ClassificationStatus.INITIAL,
        db_index=True,
    )

    # 📝 Integrated JSON Remarks Repository
    remarks = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores: {display_text, directional_prefix, target_account_name, payee, upi_ref, user_note, rule_code}",
    )

    # 🤖 Multi-Tier Evaluation Metadata JSON Repository
    evaluation_matrix_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores: {t1_cat, t2_cat, t3_cat, resolved_cat, resolved_sub, applied_rule, audit_history}",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_journal_entry"
        verbose_name_plural = "Journal Entries"

        # 🔒 ROOT PROTECTION: Enforces exactly ONE leg per account per transaction
        constraints = [
            models.UniqueConstraint(
                fields=["row_identifier", "account"],
                name="uq_row_identifier_account",
            )
        ]

        indexes = [
            models.Index(fields=["row_identifier", "account"]),
            models.Index(fields=["account", "is_reclassified"]),
            models.Index(fields=["classification_status"]),
        ]

    def __str__(self):
        return f"Account #{self.account_id} | DR: {self.debit} | CR: {self.credit} | Status: {self.classification_status}"

    @classmethod
    @transaction.atomic
    def reclassify_statement_line(
        cls,
        row_identifier: str,
        new_category: str,
        new_subcategory: str,
        rule_code: str = "MANUAL",
        taxonomy_node_account_id: int = 99,
        user_note: str = None,
    ):
        """
        Safely reclassifies Node 99 counter-entry for a specific row_identifier while preserving
        the historical audit trail inside evaluation_matrix_snapshot JSON and storing structured
        JSON remarks on BOTH legs.
        """
        # 1. Fetch BOTH double-entry legs for this row_identifier
        all_legs = list(
            cls.objects.select_for_update().filter(row_identifier=row_identifier)
        )

        entry_99 = next(
            (leg for leg in all_legs if leg.account_id == taxonomy_node_account_id),
            None,
        )
        bank_leg = next(
            (leg for leg in all_legs if leg.account_id != taxonomy_node_account_id),
            None,
        )

        if not entry_99:
            raise ValueError(
                f"No Taxonomy Node ({taxonomy_node_account_id}) counter-entry found for row_identifier: {row_identifier}"
            )

        current_snapshot = entry_99.evaluation_matrix_snapshot or {}

        # 2. Extract current state for audit trail
        prev_cat = current_snapshot.get("resolved_category") or current_snapshot.get(
            "resolved_cat", "Uncategorized"
        )
        prev_sub = current_snapshot.get("resolved_subcategory") or current_snapshot.get(
            "resolved_sub", "Suspense Account"
        )
        prev_rule = current_snapshot.get("applied_rule_code") or current_snapshot.get(
            "applied_rule", "UNKNOWN"
        )

        # 3. Construct updated metadata payload with full history
        updated_snapshot = {
            **current_snapshot,
            "previous_category": prev_cat,
            "previous_subcategory": prev_sub,
            "previous_rule_code": prev_rule,
            "resolved_category": new_category,
            "resolved_subcategory": new_subcategory,
            "applied_rule_code": rule_code,
            "confidence_score": 100,
            "is_reclassified": True,
            "reclassified_at": timezone.now().isoformat(),
        }

        target_account_label = f"{new_category} > {new_subcategory}"
        existing_remark_99 = (
            entry_99.remarks if isinstance(entry_99.remarks, dict) else {}
        )

        # 4. Generate updated JSON remark for Counter/Taxonomy Leg
        prefix_99 = "By" if entry_99.debit > 0 else "To"
        display_text_99 = (
            f"{prefix_99} {target_account_label} | Classified via {rule_code}"
        )
        if user_note and user_note.strip():
            display_text_99 += f" | Note: {user_note.strip()}"

        json_remark_99 = {
            **existing_remark_99,
            "directional_prefix": prefix_99,
            "target_account_name": target_account_label,
            "display_text": display_text_99,
            "rule_code": rule_code,
            "user_note": user_note.strip() if user_note else None,
            "updated_at": timezone.now().isoformat(),
        }

        entry_99.evaluation_matrix_snapshot = updated_snapshot
        entry_99.is_reclassified = True
        entry_99.classification_status = ClassificationStatus.RECLASSIFIED
        entry_99.remarks = json_remark_99
        entry_99.save(
            update_fields=[
                "evaluation_matrix_snapshot",
                "is_reclassified",
                "classification_status",
                "remarks",
            ]
        )

        # 5. Generate updated JSON remark for Bank Leg if present
        if bank_leg:
            existing_remark_bank = (
                bank_leg.remarks if isinstance(bank_leg.remarks, dict) else {}
            )
            prefix_bank = "By" if bank_leg.debit > 0 else "To"
            display_text_bank = f"{prefix_bank} Bank A/c | Reclassified to {target_account_label} via {rule_code}"
            if user_note and user_note.strip():
                display_text_bank += f" | Note: {user_note.strip()}"

            json_remark_bank = {
                **existing_remark_bank,
                "directional_prefix": prefix_bank,
                "target_account_name": "Bank A/c",
                "display_text": display_text_bank,
                "rule_code": rule_code,
                "user_note": user_note.strip() if user_note else None,
                "updated_at": timezone.now().isoformat(),
            }

            bank_leg.classification_status = ClassificationStatus.RECLASSIFIED
            bank_leg.is_reclassified = True
            bank_leg.remarks = json_remark_bank
            bank_leg.save(
                update_fields=["classification_status", "is_reclassified", "remarks"]
            )

        return entry_99


class AuditLog(models.Model):
    """
    📜 IMMUTABLE FINANCIAL & SYSTEM AUDIT TRAIL
    Centralized event logger for CISA/SOC-2 compliance tracking across all ledger operations.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # User / Actor Reference
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )

    # Target Entity Mapping
    action_type = models.CharField(
        max_length=50, db_index=True
    )  # e.g. 'JOURNALENTRY_UPDATE', 'RULE_CREATE'
    target_table = models.CharField(
        max_length=100, db_index=True
    )  # e.g. 'ledger_journal_entry'
    account_id = models.IntegerField(null=True, blank=True, db_index=True)
    row_identifier = models.CharField(
        max_length=64, null=True, blank=True, db_index=True
    )

    # State Diffs (JSON)
    previous_state = models.JSONField(default=dict, blank=True)
    new_state = models.JSONField(default=dict, blank=True)

    # Execution Metadata
    applied_rule_code = models.CharField(max_length=50, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "ledger_audit_log"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["account_id", "action_type"]),
            models.Index(fields=["target_table", "row_identifier"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        user_str = self.user.email if self.user else "SYSTEM"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.action_type} by {user_str} on {self.target_table}"
