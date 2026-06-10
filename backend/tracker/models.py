# S:\_BaijSoft\myWealth-Sync\backend\tracker\models.py

import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils import timezone

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
    cheque_ref_number = models.CharField(max_length=50, blank=True, null=True)

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
