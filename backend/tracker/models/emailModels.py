import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class RawEmailPayload(models.Model):
    class ProcessingStatus(models.TextChoices):
        RECEIVED = "RECEIVED", _("Received")
        DECRYPTED = "DECRYPTED", _("Decrypted")
        PARSED = "PARSED", _("Parsed")
        STAGED = "STAGED", _("Staged for Matching")
        FAILED = "FAILED", _("Failed")
        DUPLICATE = "DUPLICATE", _("Duplicate")
        COMPLETED = "COMPLETED", _("Completed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=50, default="POWER_AUTOMATE")
    encrypted_payload = models.TextField()
    payload_hash = models.CharField(max_length=64, unique=True, db_index=True)

    # Core Email Header & Display Metadata
    sender = models.CharField(max_length=255, null=True, blank=True)
    email_from = models.CharField(max_length=255, null=True, blank=True)
    email_date = models.DateTimeField(null=True, blank=True, db_index=True)
    subject = models.CharField(max_length=500, null=True, blank=True)

    # Internal Body & Header Audit Logs
    decrypted_body = models.TextField(null=True, blank=True)
    headers_json = models.JSONField(null=True, blank=True, default=dict)

    # Parsed Financial Transaction Fields
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    account_last4 = models.CharField(max_length=10, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    txn_type = models.CharField(max_length=10, null=True, blank=True)  # DEBIT / CREDIT
    merchant = models.CharField(max_length=255, null=True, blank=True)
    upi_ref = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    txn_fingerprint = models.CharField(
        max_length=64, null=True, blank=True, db_index=True
    )

    # Attachment Readiness Flag
    has_attachments = models.BooleanField(default=False)

    # Taxonomy & Subledger Metadata
    taxonomy_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "JSON containing account_match, taxonomy IDs, normalized_txn, and audit_trail"
        ),
    )

    # Lifecycle Reconciliation Metadata
    is_staged_for_matching = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("True when ready for reconciling with ledger_statementstagingline"),
    )
    staged_at = models.DateTimeField(null=True, blank=True)

    is_completed = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("True when reconciled with ledger_statementstagingline"),
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    # Status & Timestamps
    status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED,
    )
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "raw_email_payloads"
        ordering = ["-created_at"]

    def mark_as_staged(self):
        """Helper method to stage payload for statement matching."""
        from django.utils import timezone

        self.is_staged_for_matching = True
        self.staged_at = timezone.now()
        self.status = self.ProcessingStatus.STAGED
        self.save(update_fields=["is_staged_for_matching", "staged_at", "status"])

    def mark_as_completed(self):
        """Helper method to mark payload as reconciled with statement staging."""
        from django.utils import timezone

        self.is_completed = True
        self.completed_at = timezone.now()
        self.status = self.ProcessingStatus.COMPLETED
        self.save(update_fields=["is_completed", "completed_at", "status"])


class EmailAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload = models.ForeignKey(
        RawEmailPayload, on_delete=models.CASCADE, related_name="attachments"
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    file_size = models.IntegerField(help_text="Size in bytes")
    file_path = models.FileField(upload_to="email_attachments/%Y/%m/")
    is_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_attachments"
