from __future__ import annotations
import uuid
import decimal
from django.db import models
from django.utils import timezone
from .base import BulkAuditManager
from .banking_models import Account, Bank


class StatementIngestRegistry(models.Model):
    objects = BulkAuditManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="ingest_logs"
    )
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10)
    vault_decrypted = models.BooleanField(default=False)

    report_from_date = models.DateField(null=True, blank=True)
    report_to_date = models.DateField(null=True, blank=True)

    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    total_debit_amount = models.DecimalField(max_digits=15, decimal_places=2)
    total_credit_amount = models.DecimalField(max_digits=15, decimal_places=2)

    total_row_count = models.IntegerField(default=0)
    debit_line_count = models.IntegerField(default=0)
    credit_line_count = models.IntegerField(default=0)
    skipped_duplicate_count = models.IntegerField(default=0)
    admin_notes_count = models.IntegerField(default=0)

    ingested_at = models.DateTimeField(default=timezone.now)
    source_channel = models.CharField(max_length=50, default="WEB_DASHBOARD")

    class Meta:
        db_table = "tracker_statement_ingest_registry"

    def __str__(self):
        date_span = ""
        if self.report_from_date and self.report_to_date:
            date_span = f" [{self.report_from_date} to {self.report_to_date}]"
        return f"Ingest {self.file_name}{date_span} -> {self.account.name} ({self.ingested_at.date()})"


class StatementStagingLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="staging_lines"
    )
    bank = models.ForeignKey(
        Bank, on_delete=models.CASCADE, related_name="staging_lines"
    )
    ingest_registry = models.ForeignKey(
        StatementIngestRegistry,
        on_delete=models.CASCADE,
        related_name="staging_lines",
        null=True,
        blank=True,
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)
    raw_statement_date = models.DateField()

    # Immutable ground-truth column in DB
    raw_narration = models.TextField(db_column="narration", editable=False)
    cheque_ref_number = models.TextField(blank=True, null=True)

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    running_balance = models.DecimalField(
        max_digits=15, decimal_places=2, blank=True, null=True
    )
    debit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    bank_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    transaction_type = models.CharField(max_length=50, null=True, blank=True)

    row_identifier = models.CharField(
        max_length=64, db_index=True, null=True, blank=True
    )
    routing_status = models.CharField(max_length=20, default="PENDING")
    suggested_contra_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staging_suggestions",
    )

    is_enriched_from_live = models.BooleanField(default=False, db_index=True)
    live_upi_rrn = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    live_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ledger_statementstagingline"
        verbose_name = "Statement Staging Line"
        verbose_name_plural = "Statement Staging Lines"
        ordering = ["raw_statement_date", "uploaded_at"]

    def __str__(self):
        return f"{self.raw_statement_date} | {self.bank.code if self.bank else 'BANK'} | {self.narration[:30]} | ₹{self.amount}"

    def save(self, *args, **kwargs):
        if self.amount is None or self.amount == decimal.Decimal("0.00"):
            if self.debit is not None and self.debit > 0:
                self.amount = self.debit
            elif self.credit is not None and self.credit > 0:
                self.amount = self.credit
        super().save(*args, **kwargs)

    @property
    def live_merchant(self) -> str | None:
        return (
            self.live_metadata.get("merchant")
            if isinstance(self.live_metadata, dict)
            else None
        )

    @property
    def live_source(self) -> str | None:
        return (
            self.live_metadata.get("source")
            if isinstance(self.live_metadata, dict)
            else None
        )

    @property
    def parsed_narration(self) -> dict:
        if not hasattr(self, "_cached_parsed_narration"):
            from tracker.parsers.universal_narration import UniversalNarrationExtractor

            self._cached_parsed_narration = (
                UniversalNarrationExtractor.resolve_from_staging_line(self)
            )
        return self._cached_parsed_narration

    @property
    def display_payee(self) -> str:
        resolved = self.parsed_narration.get("suggested_payee")
        if resolved:
            return resolved
        raw_payee = self.parsed_narration.get("statement_payee_raw")
        if raw_payee:
            return raw_payee
        return self.raw_narration

    @property
    def narration(self) -> str:
        return self.display_payee

    @narration.setter
    def narration(self, value: str):
        self.raw_narration = value

    @property
    def display_remark(self) -> str | None:
        return self.parsed_narration.get("suggested_remark")

    @property
    def detected_rail(self) -> str:
        return self.parsed_narration.get("detected_rail", "BANK_TRANSFER")

    @property
    def detected_reference(self) -> str | None:
        return self.parsed_narration.get("detected_reference")
