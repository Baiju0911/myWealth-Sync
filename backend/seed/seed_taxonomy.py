import os
import sys
from pathlib import Path
import django

# Add backend directory to Python path so modules resolve properly
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.db import transaction
from tracker.models import TaxonomyTree, ClassificationRule

AUDITED_TAXONOMY = [
    {
        "category": "Asset",
        "subcategories": [
            "Real Estate",
            "ShareMarket & Mutual Funds",
        ],
    },
    {
        "category": "Expense",
        "subcategories": [
            "Bank Charges & Fees",
            "Donations",
            "Entertainment",
            "Festivals",
            "Food & Dining",
            "Fuels",
            "General Operating Expenses",
            "Groceries",
            "Hardware & Home Repairs",
            "Healthcare",
            "Housing & Rent",
            "Loans & EMI",
            "Personal & Family",
            "Repair & Maintenance",
            "Shopping",
            "Suspense Account",
            "Tax & Government Fees",
            "Temple",
            "Utilities & Bills",
        ],
    },
    {
        "category": "Income",
        "subcategories": [
            "Business Income",
            "Interest Income",
            "Investment Returns",
            "Other Comprehensive Income",
            "Refunds & Cashbacks",
            "Rental Income",
            "Revenue & Gains",
            "Salary",
        ],
    },
    {
        "category": "Liability",
        "subcategories": [
            "Loans & Repayments",
        ],
    },
    {
        "category": "Transfer",
        "subcategories": [
            "ATM & Cash Withdrawals",
            "Credit Card Payment",
            "Inter-Account Transfer",
            "Investment Deposit",
            "Permanent Loans",
            "Self Inter-Account",
            "Temporary Loans",
            "Family Transfers",
        ],
    },
]

# Baseline rule definitions mapped to (category, subcategory)
BASELINE_RULES = [
    {
        "rule_code": "RULE_FOOD_01",
        "name": "Food Delivery & Dining",
        "patterns": ["SWIGGY", "ZOMATO", "RESTAURANT", "EATS"],
        "target": ("Expense", "Food & Dining"),
        "priority": 50,
    },
    {
        "rule_code": "RULE_GROCERY_01",
        "name": "Groceries & Supermarket",
        "patterns": ["BIGBASKET", "BLINKIT", "ZEPTO", "MORE RETAIL", "SUPERMARKET"],
        "target": ("Expense", "Groceries"),
        "priority": 50,
    },
    {
        "rule_code": "RULE_FUEL_01",
        "name": "Fuel Outlets",
        "patterns": ["PETROLEUM", "INDIAN OIL", "HPCL", "BPCL", "SHELL"],
        "target": ("Expense", "Fuels"),
        "priority": 50,
    },
    {
        "rule_code": "RULE_TEMPLE_01",
        "name": "Temple & Religious Offerings",
        "patterns": ["TEMPLE", "DEVASTHANAM", "TRUST", "PANCHAMI"],
        "target": ("Expense", "Temple"),
        "priority": 60,
    },
    {
        "rule_code": "RULE_BANK_FEES_01",
        "name": "Bank Charges & Tax",
        "patterns": ["CHARGES", "CONVENIENCE FEE", "IMPS CHARGE", "SMS CHARGES"],
        "target": ("Expense", "Bank Charges & Fees"),
        "priority": 40,
    },
    {
        "rule_code": "RULE_INT_01",
        "name": "Bank Interest Received",
        "patterns": ["CREDIT INTEREST", "INT.PAID"],
        "target": ("Income", "Interest Income"),
        "priority": 60,
    },
    {
        "rule_code": "RULE_ATM_01",
        "name": "ATM Withdrawals",
        "patterns": ["ATM WDL", "CASH WDL", "NFS ATM"],
        "target": ("Transfer", "ATM & Cash Withdrawals"),
        "priority": 60,
    },
]


@transaction.atomic
def seed_taxonomy_and_rules():
    print("🌱 Starting Taxonomy and Classification Rules Seeding...")

    created_taxonomy_count = 0
    taxonomy_map = {}

    # 1. Seed Taxonomy Nodes
    for group in AUDITED_TAXONOMY:
        category_name = group["category"]
        for idx, sub_name in enumerate(group["subcategories"]):
            display_order = (idx + 1) * 10
            node, created = TaxonomyTree.objects.get_or_create(
                category=category_name,
                subcategory=sub_name,
                defaults={"display_order": display_order, "is_active": True},
            )
            taxonomy_map[(category_name, sub_name)] = node
            if created:
                created_taxonomy_count += 1

    print(
        f"✅ Taxonomy Seeding Complete! ({created_taxonomy_count} new nodes, {len(taxonomy_map)} total active nodes)"
    )

    # 2. Seed Baseline Classification Rules
    created_rule_count = 0
    for r_item in BASELINE_RULES:
        target_node = taxonomy_map.get(r_item["target"])
        if not target_node:
            print(f"⚠️ Target taxonomy not found for rule: {r_item['name']}")
            continue

        rule, created = ClassificationRule.objects.get_or_create(
            rule_code=r_item["rule_code"],
            defaults={
                "name": r_item["name"],
                "patterns": r_item["patterns"],
                "rule_type": "CONTAINS",
                "taxonomy": target_node,
                "priority": r_item["priority"],
                "is_active": True,
            },
        )
        if created:
            created_rule_count += 1

    print(f"✅ Rules Seeding Complete! ({created_rule_count} new rules inserted)")


if __name__ == "__main__":
    seed_taxonomy_and_rules()
