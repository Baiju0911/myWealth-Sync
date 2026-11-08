from __future__ import annotations
import uuid
import json
from django.db import models
from django.conf import settings


class Bank(models.Model):
    code = models.CharField(max_length=10, unique=True)
    display_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code} - {self.display_name}"


class Account(models.Model):
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20)
    account_number = models.CharField(max_length=30, blank=True)
    ifsc_code = models.CharField(max_length=20)
    branch_name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.name} ({self.account_number[-4:] if len(self.account_number)>=4 else self.id})"


class BankCredential(models.Model):
    account = models.OneToOneField(
        Account, on_delete=models.CASCADE, related_name="credential"
    )
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
        return f"Keychain Vault for {self.account.name}"


class BankLayoutSchema(models.Model):
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
    header_trigger_text = models.CharField(max_length=255)
    date_col_idx = models.IntegerField(default=0)
    narration_col_idx = models.IntegerField(default=1)
    amount_style = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, default="SIGNED"
    )
    single_amount_col_idx = models.IntegerField(default=2, blank=True, null=True)
    debit_col_idx = models.IntegerField(blank=True, null=True)
    credit_col_idx = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} Schema ({self.file_type})"


class UserStatementTemplate(models.Model):
    STRATEGY_CHOICES = [
        ("STRICT_MATRIX", "Strict Coordinate Matrix"),
        ("RELATIVE_SEQUENCE", "Relative Text Sequences"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="statement_templates",
        null=True,
        blank=True,
    )
    template_name = models.CharField(max_length=100)
    matching_keyword = models.CharField(max_length=100, blank=True, default="")
    parser_strategy_code = models.CharField(
        max_length=50,
        choices=STRATEGY_CHOICES,
        default="STRICT_MATRIX",
    )
    date_x = models.FloatField(default=10.0)
    narration_x = models.FloatField(default=18.0)
    debit_x = models.FloatField(default=52.0)
    credit_x = models.FloatField(default=60.0)
    balance_x = models.FloatField(default=98.0)

    date_index = models.IntegerField(default=0)
    narration_index = models.IntegerField(default=1)
    balance_index = models.IntegerField(default=3)
    debit_index = models.IntegerField(null=True, blank=True)
    credit_index = models.IntegerField(null=True, blank=True)

    date_format = models.CharField(max_length=50, default="%d-%m-%Y")
    y_tolerance = models.FloatField(default=3.0)
    multiline_enabled = models.BooleanField(default=True)
    header_lines_to_skip = models.IntegerField(default=0)
    footer_lines_to_skip = models.IntegerField(default=0)

    signature_json = models.JSONField(default=dict, blank=True)
    header_mapping_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_userstatementtemplate"
        verbose_name = "User Statement Template"
        verbose_name_plural = "User Statement Templates"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ["signature_json", "header_mapping_json"]:
            try:
                val = getattr(self, field)
                if isinstance(val, str):
                    setattr(self, field, json.loads(val))
            except Exception:
                setattr(self, field, {})

    def __str__(self):
        return f"[{self.parser_strategy_code}] {self.template_name} -> {self.account.name if self.account else 'Unlinked'}"
