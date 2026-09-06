import uuid
import json
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import os
import hashlib


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

    # 🎯 Consolidated JSON input payload for Bank Statement Reconciliation Engine
    staging_payload = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text=_("Structured metadata snapshot evaluated during statement matching"),
    )

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

    def build_staging_payload(self) -> dict:
        """Constructs a normalized, comprehensive JSON input dictionary for statement matching."""
        headers = self.headers_json or {}
        if isinstance(headers, str):
            try:
                headers = json.loads(headers)
            except Exception:
                headers = {}

        parsed_summary = headers.get("parsed_summary", {})
        taxonomy = self.taxonomy_payload or {}
        if isinstance(taxonomy, str):
            try:
                taxonomy = json.loads(taxonomy)
            except Exception:
                taxonomy = {}

        return {
            "payload_id": str(self.id),
            "source": self.source,
            "bank_name": self.bank_name
            or parsed_summary.get("bank")
            or "SOUTH INDIAN BANK",
            "account_last4": self.account_last4
            or parsed_summary.get("account")
            or "0060",
            "amount": str(self.amount or parsed_summary.get("amount") or "0.00"),
            "txn_type": (self.txn_type or "DEBIT").upper(),
            "upi_ref": self.upi_ref or parsed_summary.get("upi_ref"),
            "merchant": self.merchant or self.subject or "UPI Transfer",
            "email_date": self.email_date.isoformat() if self.email_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sender": self.sender or self.email_from,
            "subject": self.subject,
            "decrypted_body": self.decrypted_body,
            "txn_fingerprint": self.txn_fingerprint,
            "payload_hash": self.payload_hash,
            "taxonomy": taxonomy.get("taxonomy", {}),
            "account_match": taxonomy.get("account_match", {}),
            "match_status": "UNMATCHED",
        }

    def mark_as_staged(self):
        """Helper method to stage payload and generate staging_payload for statement matching."""
        self.is_staged_for_matching = True
        self.staged_at = timezone.now()
        self.status = self.ProcessingStatus.STAGED
        self.staging_payload = self.build_staging_payload()
        self.save(
            update_fields=[
                "is_staged_for_matching",
                "staged_at",
                "status",
                "staging_payload",
            ]
        )

    def mark_as_completed(self):
        """Helper method to mark payload as reconciled with statement staging."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.status = self.ProcessingStatus.COMPLETED
        self.save(update_fields=["is_completed", "completed_at", "status"])

    def mark_as_unstaged(self):
        """Resets payload back to Unstaged/Vault state."""
        self.is_staged_for_matching = False
        self.staged_at = None
        self.status = self.ProcessingStatus.PARSED
        self.staging_payload = None
        self.save(
            update_fields=[
                "is_staged_for_matching",
                "staged_at",
                "status",
                "staging_payload",
            ]
        )


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


class DocumentInboxItem(models.Model):
    class DocType(models.TextChoices):
        STATEMENT = "STATEMENT", "Bank Statement"
        TERM_DEPOSIT = "TERM_DEPOSIT", "Term Deposit (FD/RD)"
        UNKNOWN = "UNKNOWN", "Unclassified Document"

    class ProcessingStatus(models.TextChoices):
        INBOX = "INBOX", "Pending in Inbox"
        PROCESSING = "PROCESSING", "Active in Staging"
        COMPLETED = "COMPLETED", "Extracted & Processed"
        ARCHIVED = "ARCHIVED", "Archived / Discarded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Gmail API message & attachment references
    message_id = models.CharField(max_length=128, db_index=True)
    attachment_id = models.TextField()  # Raw Gmail ID without length constraint
    attachment_hash = models.CharField(
        max_length=64, unique=True, db_index=True, default=""
    )

    # Document Metadata
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=512)
    file_size = models.PositiveIntegerField(default=0)  # in bytes

    doc_type = models.CharField(
        max_length=32,
        choices=DocType.choices,
        default=DocType.UNKNOWN,
        db_index=True,
    )
    status = models.CharField(
        max_length=32,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.INBOX,
        db_index=True,
    )

    # Origin Details
    sender = models.CharField(max_length=255)
    subject = models.CharField(max_length=500)
    received_date = models.DateTimeField(null=True, blank=True)

    # Heuristic Account Hint (e.g., '0060', '1050')
    account_hint = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    bank_name = models.CharField(max_length=128, blank=True, null=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_date", "-created_at"]

    @staticmethod
    def generate_hash(attachment_id: str) -> str:
        return hashlib.sha256(attachment_id.encode("utf-8")).hexdigest()

    def mark_completed(self):
        """Moves physical file to the completed directory and updates status."""
        current_path = self.file_path
        if os.path.exists(current_path):
            dir_name, base_name = os.path.split(current_path)
            completed_dir = os.path.join(os.path.dirname(dir_name), "completed")
            os.makedirs(completed_dir, exist_ok=True)

            new_path = os.path.join(completed_dir, base_name)
            os.rename(current_path, new_path)
            self.file_path = new_path

        self.status = self.ProcessingStatus.COMPLETED
        self.save(update_fields=["status", "file_path", "updated_at"])

    def mark_archived(self):
        self.status = self.ProcessingStatus.ARCHIVED
        self.save(update_fields=["status", "updated_at"])
