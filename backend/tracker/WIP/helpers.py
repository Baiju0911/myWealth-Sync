import json
from ..models.models import AccountingRule


class WIPHelpers:
    @staticmethod
    def resolve_directional_placement(
        credit_val: float, rule_subcategory: str
    ) -> tuple:
        category = "Income" if credit_val > 0 else "Expense"
        if not rule_subcategory:
            return category, "Suspense Account"

        clean = str(rule_subcategory).strip().lower()
        subcategory = (
            "Suspense Account"
            if clean in {"none", "expense", "expenses", "income", "incomes"}
            else str(rule_subcategory).strip()
        )
        return category, subcategory

    @staticmethod
    def safe_subcategory(subcat: str) -> str:
        if not subcat:
            return "Suspense Account"
        clean = str(subcat).strip().lower()
        return (
            "Suspense Account"
            if clean in {"none", "expense", "expenses", "income", "incomes"}
            else str(subcat).strip()
        )

    @classmethod
    def get_sub_norm_map(cls) -> dict:
        """Loads active subcategory normalization maps from GR900 series rules in DB."""
        sub_map = {}
        norm_rules = AccountingRule.objects.filter(
            is_active__in=[1, "1"], rule_code__startswith="GR90"
        )

        for rule in norm_rules:
            metadata = rule.rule_metadata
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            elif not isinstance(metadata, dict):
                metadata = {}

            target_sub = metadata.get("subcategory")

            tags = rule.description_tags
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = []
            elif not isinstance(tags, list):
                tags = []

            if target_sub and tags:
                for tag in tags:
                    if tag and isinstance(tag, str):
                        sub_map[tag.strip().lower()] = target_sub.strip()

        return sub_map
