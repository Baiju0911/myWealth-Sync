from __future__ import annotations
from django.db import models


class WorkbenchGroupHierarchy(models.Model):
    header_scope = models.CharField(
        max_length=50,
        help_text="Header scope: SUSPENSE, ASSETS, EXPENSES, etc.",
        db_index=True,
    )
    group_tag = models.CharField(
        max_length=100,
        help_text="Canonical primary group tag, e.g., #CONTRA, #UTILITIES",
        db_index=True,
    )
    subgroup_tag = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Optional subgroup label under this parent group",
    )
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workbench_group_hierarchies"
        ordering = ["header_scope", "display_order", "group_tag"]
        constraints = [
            models.UniqueConstraint(
                fields=["header_scope", "group_tag", "subgroup_tag"],
                name="unique_group_subgroup_per_header",
            )
        ]

    def __str__(self) -> str:
        if self.subgroup_tag:
            return f"[{self.header_scope}] {self.group_tag} -> {self.subgroup_tag}"
        return f"[{self.header_scope}] {self.group_tag}"


class MasterNarrationTagRule(models.Model):
    class MatchType(models.TextChoices):
        CONTAINS = "CONTAINS", "Contains Substring"
        EXACT = "EXACT", "Exact Match"
        REGEX = "REGEX", "Regular Expression"
        LAST4 = "LAST4", "Account Last 4 Digits"

    class VectorConstraint(models.TextChoices):
        ANY = "ANY", "Inflow & Outflow (Both)"
        INFLOW = "INFLOW", "Inflow Only (Credits)"
        OUTFLOW = "OUTFLOW", "Outflow Only (Debits)"

    keyword_pattern = models.CharField(
        max_length=255,
        help_text="Narration substring, payee keyword, or account identifier",
        db_index=True,
    )
    match_type = models.CharField(
        max_length=20,
        choices=MatchType.choices,
        default=MatchType.CONTAINS,
    )
    allowed_vector = models.CharField(
        max_length=10,
        choices=VectorConstraint.choices,
        default=VectorConstraint.ANY,
    )
    header_scope = models.CharField(
        max_length=50,
        default="GLOBAL",
        help_text="GLOBAL, or specific headers: SUSPENSE, ASSETS, EXPENSES",
        db_index=True,
    )
    parent_group_tag = models.CharField(
        max_length=100,
        help_text="Assigned primary group tag, e.g., #CONTRA, #UTILITIES",
    )
    subgroup_tag = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Assigned subgroup label (e.g., NRE_TO_NRO, PRAVEEN_P)",
    )
    require_internal_contra = models.BooleanField(
        default=False,
        help_text="Enforces that both host and counterparty resolve in the Dynamic Account Registry",
    )
    source_account_id = models.IntegerField(
        blank=True,
        null=True,
        help_text="Optional: rule only triggers for statement lines of this specific account",
    )
    priority = models.IntegerField(
        default=10,
        help_text="Higher values evaluate first",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "master_narration_tag_rules"
        ordering = ["-priority", "keyword_pattern"]
        constraints = [
            models.UniqueConstraint(
                fields=["header_scope", "keyword_pattern", "allowed_vector"],
                name="unique_rule_per_header_vector",
            )
        ]

    def __str__(self) -> str:
        return (
            f"[{self.header_scope}] '{self.keyword_pattern}' -> {self.parent_group_tag}"
        )
