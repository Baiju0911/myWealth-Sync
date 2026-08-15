import os
import sys

# 1. Resolve path to 'backend' directory dynamically
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)  # Goes up one level from 'seed' to 'backend'

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 2. Set Django Settings Module
# (If your main settings folder is named 'backend' or 'myWealth' instead of 'core', adjust string here)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# 3. Initialize Django
import django

django.setup()

# 4. Model Imports & Seeding Logic
from django.db import connection, transaction
from tracker.models.subledger import AssetCategory

INITIAL_CATEGORIES = [
    {
        "id": 1,
        "code": "REAL_ESTATE",
        "name": "Real Estate & Land",
        "subcategory": "Real Estate",
    },
    {
        "id": 2,
        "code": "FIXED_DEPOSIT",
        "name": "Fixed Deposit (FD)",
        "subcategory": "Fixed Deposits",
    },
    {
        "id": 3,
        "code": "RECURRING_DEPOSIT",
        "name": "Recurring Deposit (RD)",
        "subcategory": "Recurring Deposits",
    },
    {
        "id": 4,
        "code": "MARKET_INVESTMENT",
        "name": "Stocks, Mutual Funds & ETFs",
        "subcategory": "Mutual Funds",
    },
    {
        "id": 5,
        "code": "PENSION_RETIREMENT",
        "name": "Pension & Retirement (NPS, PPF, EPF)",
        "subcategory": "Retirement Accounts",
    },
    {
        "id": 6,
        "code": "INSURANCE_PLAN",
        "name": "Life & Endowment Insurance",
        "subcategory": "Insurance Policies",
    },
    {
        "id": 7,
        "code": "VEHICLE",
        "name": "Vehicles & Transport",
        "subcategory": "Vehicles",
    },
    {
        "id": 8,
        "code": "PRECIOUS_METALS",
        "name": "Gold, Silver & SGBs",
        "subcategory": "Gold & Precious Metals",
    },
    {
        "id": 9,
        "code": "PERSONAL_RECEIVABLE",
        "name": "Personal Loan Given / Receivable",
        "subcategory": "Loans & Receivables",
    },
]


def run_seed():
    with transaction.atomic():
        for item in INITIAL_CATEGORIES:
            obj, created = AssetCategory.objects.get_or_create(
                id=item["id"],
                defaults={
                    "code": item["code"],
                    "name": item["name"],
                    "default_taxonomy_category": "Asset",
                    "default_taxonomy_subcategory": item["subcategory"],
                },
            )
            if created:
                print(f"➕ Created Category [{obj.id}]: {obj.name}")
            else:
                print(f"ℹ️ Category [{obj.id}] already exists.")

    # Reset MySQL AUTO_INCREMENT sequence so future inserts start at 10
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE ledger_asset_category AUTO_INCREMENT = 10;")

    print(
        "\n✅ Asset categories seeded successfully and AUTO_INCREMENT counter set to 10!"
    )


if __name__ == "__main__":
    run_seed()
