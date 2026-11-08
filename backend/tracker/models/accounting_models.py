from __future__ import annotations
import uuid
from functools import cached_property
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from .base import BulkAuditManager
from .banking_models import Account


class TransactionHeader(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    narration = models.TextField()
    source = models.CharField(max_length=50, default="MANUAL")
    upi_rrn = models.CharField(max_length=50, blank=True, null=True)
    merchant_vpa = models.CharField(max_length=100, blank=True, null=True)
    scanned_by = models.CharField(max_length=100, blank=True, default="Unknown Device")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.date} - {self.narration[:30]}"


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
    rule_code = models.CharField(max_length=20, unique=True)
    rule_title = models.CharField(max_length=255)
    entry_type = models.CharField(
        max_length=10,
        choices=[("Debit", "Debit"), ("Credit", "Credit")],
    )
    rule_priority = models.IntegerField(default=1)

    taxonomy = models.ForeignKey(
        TaxonomyTree,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="accounting_rules",
        db_column="taxonomy_id",
    )
    description_tags = models.JSONField()
    examples = models.JSONField()
    rule_metadata = models.JSONField(default=dict)

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

    @property
    def resolved_category(self):
        return (
            self.taxonomy.category
            if self.taxonomy
            else self.rule_metadata.get("category")
        )

    @property
    def resolved_subcategory(self):
        return (
            self.taxonomy.subcategory
            if self.taxonomy
            else self.rule_metadata.get("subcategory")
        )

    def save(self, *args, **kwargs):
        if self.taxonomy:
            if not isinstance(self.rule_metadata, dict):
                self.rule_metadata = {}
            self.rule_metadata["category"] = self.taxonomy.category
            self.rule_metadata["subcategory"] = self.taxonomy.subcategory
        super().save(*args, **kwargs)


class MasterFinancialCategory(models.Model):
    objects = BulkAuditManager()

    CATEGORY_TYPES = [
        ("REGULAR", "Standard Balance Sheet / Expense Item"),
        ("KNOWN_DEFAULT", "Auto-Matched Known Rule Node"),
        ("SELF_TRANSFER", "Inter-Account Internal Transfer Rule"),
    ]

    id = models.AutoField(primary_key=True)
    sno = models.IntegerField(default=1)
    category_type = models.CharField(
        max_length=20, choices=CATEGORY_TYPES, default="REGULAR", db_index=True
    )
    act_category = models.CharField(max_length=100)
    act_subcategory = models.CharField(max_length=100)
    categories_items = models.CharField(max_length=100)
    dashboard_cat = models.CharField(max_length=100)

    keys = models.JSONField(default=dict)
    bank_types = models.JSONField(default=dict)

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


class ClassificationStatus(models.TextChoices):
    INITIAL = "INITIAL", "Initial Auto-Classification"
    RECLASSIFIED = "RECLASSIFIED", "Manually Reclassified"
    SUSPENSE = "SUSPENSE", "Pending Suspense"
    AUTO_SWEPT = "AUTO_SWEPT", "Auto-Swept by Rule Engine"
    CONFIRMED = "CONFIRMED", "Audited & Confirmed"
    SPLIT = "SPLIT", "Split Transaction"
    SYSTEM_INTERNAL = "SYSTEM_INTERNAL", "System Contra / Inter-Account Transfer"


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

    patterns = models.JSONField(default=list, blank=True)
    priority = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_from_manual_override = models.BooleanField(default=True)
    match_count = models.IntegerField(default=0)
    taxonomy = models.ForeignKey(
        TaxonomyTree, on_delete=models.SET_NULL, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_classification_rule"

    def __str__(self):
        return f"{self.rule_code} -> {self.target_subcategory} ({len(self.get_patterns())} patterns)"

    def save(self, *args, **kwargs):
        if isinstance(self.patterns, list):
            clean_pats = set()
            for pat in self.patterns:
                if not pat or not str(pat).strip():
                    continue
                clean_pats.add(str(pat).strip().upper())
            self.patterns = sorted(
                list(clean_pats), key=lambda x: (-len(x.split()), -len(x))
            )

        if "_cached_patterns" in self.__dict__:
            del self.__dict__["_cached_patterns"]
        super().save(*args, **kwargs)

    @cached_property
    def _cached_patterns(self) -> list[str]:
        if not self.patterns or not isinstance(self.patterns, list):
            return []
        return [
            p.strip().upper() for p in self.patterns if isinstance(p, str) and p.strip()
        ]

    def get_patterns(self) -> list[str]:
        return self._cached_patterns

    def add_pattern(self, new_pattern: str) -> bool:
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


class JournalEntry(models.Model):
    objects = BulkAuditManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="journal_lines"
    )
    transaction_date = models.DateField(default=timezone.now)
    row_identifier = models.CharField(max_length=64, db_index=True)

    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    is_reclassified = models.BooleanField(default=False, db_index=True)
    classification_status = models.CharField(
        max_length=20,
        choices=ClassificationStatus.choices,
        default=ClassificationStatus.INITIAL,
        db_index=True,
    )

    remarks = models.JSONField(default=dict, blank=True)
    evaluation_matrix_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_journal_entry"
        verbose_name_plural = "Journal Entries"
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
        prev_cat = current_snapshot.get("resolved_category") or current_snapshot.get(
            "resolved_cat", "Uncategorized"
        )
        prev_sub = current_snapshot.get("resolved_subcategory") or current_snapshot.get(
            "resolved_sub", "Suspense Account"
        )
        prev_rule = current_snapshot.get("applied_rule_code") or current_snapshot.get(
            "applied_rule", "UNKNOWN"
        )

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
        prefix_99 = "By" if entry_99.debit > 0 else "To"
        display_text_99 = (
            f"{prefix_99} {target_account_label} | Classified via {rule_code}"
        )
        if user_note and user_note.strip():
            display_text_99 += f" | Note: {user_note.strip()}"

        entry_99.evaluation_matrix_snapshot = updated_snapshot
        entry_99.is_reclassified = True
        entry_99.classification_status = ClassificationStatus.RECLASSIFIED
        entry_99.remarks = {
            **existing_remark_99,
            "directional_prefix": prefix_99,
            "target_account_name": target_account_label,
            "display_text": display_text_99,
            "rule_code": rule_code,
            "user_note": user_note.strip() if user_note else None,
            "updated_at": timezone.now().isoformat(),
        }
        entry_99.save(
            update_fields=[
                "evaluation_matrix_snapshot",
                "is_reclassified",
                "classification_status",
                "remarks",
            ]
        )

        if bank_leg:
            existing_remark_bank = (
                bank_leg.remarks if isinstance(bank_leg.remarks, dict) else {}
            )
            prefix_bank = "By" if bank_leg.debit > 0 else "To"
            display_text_bank = f"{prefix_bank} Bank A/c | Reclassified to {target_account_label} via {rule_code}"
            if user_note and user_note.strip():
                display_text_bank += f" | Note: {user_note.strip()}"

            bank_leg.classification_status = ClassificationStatus.RECLASSIFIED
            bank_leg.is_reclassified = True
            bank_leg.remarks = {
                **existing_remark_bank,
                "directional_prefix": prefix_bank,
                "target_account_name": "Bank A/c",
                "display_text": display_text_bank,
                "rule_code": rule_code,
                "user_note": user_note.strip() if user_note else None,
                "updated_at": timezone.now().isoformat(),
            }
            bank_leg.save(
                update_fields=["classification_status", "is_reclassified", "remarks"]
            )

        return entry_99


class JournalEntryMapping(models.Model):
    objects = BulkAuditManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journal_entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="category_mapping",
    )
    assigned_category = models.ForeignKey(
        MasterFinancialCategory, on_delete=models.PROTECT, related_name="mapped_entries"
    )
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
        return f"Mapping -> {self.assigned_category.categories_items}"


class WIPEvaluationMatrix(models.Model):
    objects = BulkAuditManager()

    CONFIDENCE_CHOICES = [
        ("HIGH", "100% Validated (Staged for Bulk Approval)"),
        ("ZERO", "Validation Failed (Sent to Uncategorized Container)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staging_line = models.ForeignKey(
        "StatementStagingLine", on_delete=models.CASCADE, related_name="wip_records"
    )
    row_footprint_hash = models.CharField(max_length=64, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    bank = models.ForeignKey("Bank", on_delete=models.CASCADE)
    raw_statement_date = models.DateField()
    narration_normalized = models.TextField()

    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    parent_wip = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="split_children",
    )
    is_split_component = models.BooleanField(default=False)

    matched_category = models.ForeignKey(
        MasterFinancialCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    applied_rule = models.ForeignKey(
        AccountingRule, on_delete=models.SET_NULL, null=True, blank=True
    )
    matrix_evaluation = models.JSONField(default=dict, blank=True)
    evaluation_errors = models.JSONField(default=list, blank=True)

    resolved_category = models.CharField(max_length=100, null=True, blank=True)
    resolved_subcategory = models.CharField(max_length=100, null=True, blank=True)

    confidence_score = models.IntegerField(default=0)
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
    source_category = models.CharField(max_length=100)
    expected_vector = models.CharField(
        max_length=10,
        choices=[("DEBIT", "Debit (Outflow)"), ("CREDIT", "Credit (Inflow)")],
        default="DEBIT",
    )
    target_category = models.CharField(max_length=100)
    target_subcategory = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tracker_directional_vector_override"
        verbose_name = "Directional Vector Override"
        verbose_name_plural = "Directional Vector Overrides"
        unique_together = ("source_category", "expected_vector")

    def __str__(self):
        return f"If {self.source_category} is {self.expected_vector} -> Pivot to {self.target_category}"
