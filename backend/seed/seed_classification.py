import os
import sys
from pathlib import Path
import django

# Add backend directory to Python path so modules resolve properly
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "core.settings"
)  # Adjust if your settings module name differs
django.setup()

from backend.tracker.models.models import ClassificationRule

SEED_RULES = [
    {
        "name": "Food & Dining Aggregators",
        "patterns": ["SWIGGY", "ZOMATO", "COSTA LULU MALL TRIVAND"],
        "target_category": "Expense",
        "target_subcategory": "Food & Dining",
        "priority": 10,
    },
    {
        "name": "Groceries Vendors",
        "patterns": ["MOHANAN P"],
        "target_category": "Expense",
        "target_subcategory": "Groceries",
        "priority": 10,
    },
    {
        "name": "Retail & Shopping",
        "patterns": ["WESTSIDE UNIT OF TRENT LIMIT"],
        "target_category": "Expense",
        "target_subcategory": "Shopping",
        "priority": 10,
    },
    {
        "name": "Entertainment Subscriptions",
        "patterns": ["NETFLIX COM"],
        "target_category": "Expense",
        "target_subcategory": "Entertainment",
        "priority": 10,
    },
    {
        "name": "Vehicle & Property Maintenance",
        "patterns": ["ROYAL TYRE CLUB"],
        "target_category": "Expense",
        "target_subcategory": "Repair & Maintenance",
        "priority": 10,
    },
    {
        "name": "Temple & Offerings",
        "patterns": ["MANOJ K J"],
        "target_category": "Expense",
        "target_subcategory": "Temple",
        "priority": 10,
    },
    {
        "name": "Family Transfers - Wife",
        "patterns": ["SUMEE S"],
        "target_category": "Transfer",
        "target_subcategory": "Wife",
        "priority": 10,
    },
    {
        "name": "Loans & Borrowings",
        "patterns": ["BARAT K GOPINATH"],
        "target_category": "Transfer",
        "target_subcategory": "Permanent Loans",
        "priority": 10,
    },
    {
        "name": "Self Inter-Account Transfers",
        "patterns": ["BAIJU SUSEELAN NAIR"],
        "target_category": "Transfer",
        "target_subcategory": "Inter-Account Transfer",
        "priority": 10,
    },
]


def seed_classification_rules():
    # 1. Truncate existing entries
    deleted_count, _ = ClassificationRule.objects.all().delete()
    print(f"🧹 Cleaned up {deleted_count} old classification rule entries.")

    # 2. Seed fresh JSON pattern rules
    created_count = 0
    for item in SEED_RULES:
        ClassificationRule.objects.create(
            name=item["name"],
            patterns=item["patterns"],
            rule_type="CONTAINS",
            target_category=item["target_category"],
            target_subcategory=item["target_subcategory"],
            priority=item["priority"],
            is_active=True,
            created_from_manual_override=True,
        )
        created_count += 1

    print(
        f"✅ Seeding Complete! Created {created_count} consolidated JSON classification rules."
    )


if __name__ == "__main__":
    seed_classification_rules()
