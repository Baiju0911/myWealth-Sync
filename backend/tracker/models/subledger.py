import uuid
from decimal import Decimal
from datetime import timedelta
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

# ============================================================================
# 1. ENUMS & CHOICES
# ============================================================================


class AssetCategory(models.TextChoices):
    REAL_ESTATE = "REAL_ESTATE", "Real Estate & Land"
    FIXED_DEPOSIT = "FIXED_DEPOSIT", "Fixed Deposit (FD)"
    RECURRING_DEPOSIT = "RECURRING_DEPOSIT", "Recurring Deposit (RD)"
    MARKET_INVESTMENT = "MARKET_INVESTMENT", "Stocks, Mutual Funds & ETFs"
    PENSION_RETIREMENT = "PENSION_RETIREMENT", "Pension & Retirement (NPS, PPF, EPF)"
    INSURANCE_PLAN = "INSURANCE_PLAN", "Life & Endowment Insurance"
    VEHICLE = "VEHICLE", "Vehicles & Transport"
    PRECIOUS_METALS = "PRECIOUS_METALS", "Gold, Silver & SGBs"
    PERSONAL_RECEIVABLE = "PERSONAL_RECEIVABLE", "Personal Loan Given / Receivable"


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
    PROPERTY_TAX = "PROPERTY_TAX", "Local Body Property Tax (Panchayat/Corporation)"
    LAND_REVENUE_TAX = "LAND_REVENUE_TAX", "Land Revenue Tax (Thandaper)"
    ELECTRICITY = "ELECTRICITY", "Electricity Board (e.g., KSEB)"
    WATER = "WATER", "Water Authority (e.g., KWA)"
    BUILDING_MAINTENANCE = "BUILDING_MAINTENANCE", "Resident Association / Maintenance"
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


class AssetSubLedger(models.Model):
    """
    Master Asset Register & Sub-Ledger Hub.
    Holds core financial valuations, ownership split, and category-specific
    operational details in a structured JSON payload.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Human-readable code, e.g., AST-RE-001 or AST-NPS-002",
    )
    name = models.CharField(
        max_length=255, help_text="Display title, e.g., 'Ulloor Plot & House'"
    )
    category = models.CharField(
        max_length=32, choices=AssetCategory.choices, db_index=True
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
        max_length=20, choices=OwnershipType.choices, default=OwnershipType.INDIVIDUAL
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

    # 🔗 Link to General Ledger Balance Sheet Account
    linked_gl_account = models.ForeignKey(
        "Account", on_delete=models.PROTECT, related_name="subledger_assets"
    )

    # 🎨 Deep Dynamic Category Metadata Repository
    # Stores:
    # - Real Estate: {sale_deed_no, sro_name, survey_no, thandaper_no, area_sqft}
    # - Pension/NPS: {pran_number, tier_type, pfm_name, equity_pct, corporate_pct, govt_pct}
    # - Fixed Deposit: {fd_receipt_no, bank_branch, ifsc, interest_rate, maturity_date}
    # - Vehicle: {registration_no, chassis_no, engine_no, rc_doc_id}
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
            models.Index(fields=["asset_code"]),
        ]

    def __str__(self):
        return f"[{self.asset_code}] {self.name} ({self.get_category_display()})"


# ============================================================================
# 3. UTILITY & GOVERNMENT OPERATIONAL ACCOUNTS
# ============================================================================


class AssetOperationalAccount(models.Model):
    """
    Stores utility consumer numbers, local tax assessment IDs, meter numbers,
    and matching keywords used for auto-identifying bank statement lines.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        AssetSubLedger, on_delete=models.CASCADE, related_name="operational_accounts"
    )
    service_type = models.CharField(
        max_length=32, choices=ServiceProviderType.choices, db_index=True
    )
    provider_name = models.CharField(
        max_length=128,
        help_text="e.g., KSEB, KWA, Trivandrum Corporation, Revenue Dept",
    )
    consumer_identifier = models.CharField(
        max_length=64, help_text="Consumer No / Building Assessment No / Thandaper No"
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
    """
    Drives monthly/yearly reminders for property taxes, utility bills,
    SIPs, and pension contributions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        AssetSubLedger, on_delete=models.CASCADE, related_name="compliance_schedules"
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

    # 🔗 Links directly to journal entry row once settled
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
    """
    Binds a raw bank statement transaction (row_identifier) or manual cash entry
    directly to an Asset Sub-Ledger item and operational account.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        AssetSubLedger, on_delete=models.PROTECT, related_name="transaction_mappings"
    )
    operational_account = models.ForeignKey(
        AssetOperationalAccount, on_delete=models.SET_NULL, null=True, blank=True
    )
    schedule = models.ForeignKey(
        AssetComplianceSchedule, on_delete=models.SET_NULL, null=True, blank=True
    )

    # 🛡️ Link to General Ledger Journal Entry
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
    """
    Implements your ±5 to ±10 day sliding window algorithm to rank candidate
    bank statement rows for document binding.
    """

    @staticmethod
    def find_candidate_rows(
        document_date,
        target_amount,
        account_id=None,
        keywords=None,
        day_window=10,
        amount_tolerance_pct=Decimal("0.0"),
    ):
        """
        Queries unmapped ledger_journal_entry rows within ±day_window of document_date
        and returns scored results sorted by probability.
        """
        from tracker.models import (
            JournalEntry,
        )  # Import inside method to avoid circular import

        start_date = document_date - timedelta(days=day_window)
        end_date = document_date + timedelta(days=day_window)

        query = JournalEntry.objects.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date,
        )

        if account_id:
            query = query.filter(account_id=account_id)

        target_amount = Decimal(str(target_amount))
        min_amount = target_amount * (Decimal("1") - amount_tolerance_pct)
        max_amount = target_amount * (Decimal("1") + amount_tolerance_pct)

        query = query.filter(
            models.Q(debit__range=(min_amount, max_amount))
            | models.Q(credit__range=(min_amount, max_amount))
        )

        candidates = []

        for entry in query:
            score = 0
            entry_val = entry.debit if entry.debit > 0 else entry.credit

            # 1. Amount Score (50 Pts)
            if entry_val == target_amount:
                score += 50
            else:
                score += 35

            # 2. Date Proximity Score (30 Pts)
            date_diff = abs((entry.transaction_date - document_date).days)
            if date_diff == 0:
                score += 30
            elif date_diff <= 3:
                score += 20
            elif date_diff <= 7:
                score += 15
            else:
                score += 10

            # 3. Keyword Match Score (20 Pts)
            raw_remarks = str(entry.remarks).upper()
            if keywords:
                matched = [kw for kw in keywords if kw.upper() in raw_remarks]
                if matched:
                    score += 20

            candidates.append(
                {
                    "journal_id": str(entry.id),
                    "row_identifier": entry.row_identifier,
                    "account_id": entry.account_id,
                    "transaction_date": entry.transaction_date.strftime("%Y-%m-%d"),
                    "date_offset_days": (entry.transaction_date - document_date).days,
                    "debit": float(entry.debit),
                    "credit": float(entry.credit),
                    "remarks": entry.remarks,
                    "probability_score": min(score, 100),
                }
            )

        return sorted(candidates, key=lambda x: x["probability_score"], reverse=True)
