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


# Absolute import from your app
from tracker.models.subledger import AssetCategory, SubledgerCategoryType

categories = [
    # 💰 Income Categories
    {
        "code": "RENTAL_STREAM",
        "name": "Property Rental Stream",
        "category_type": SubledgerCategoryType.INCOME,
        "default_taxonomy_category": "Income",
        "default_taxonomy_subcategory": "Rental Income",
    },
    {
        "code": "DIVIDEND_FOLIO",
        "name": "Dividend & Yield Stream",
        "category_type": SubledgerCategoryType.INCOME,
        "default_taxonomy_category": "Income",
        "default_taxonomy_subcategory": "Dividend Income",
    },
    # 📊 Expense Categories
    {
        "code": "VENDOR_MERCHANT",
        "name": "Merchant / Service Provider",
        "category_type": SubledgerCategoryType.EXPENSE,
        "default_taxonomy_category": "Expense",
        "default_taxonomy_subcategory": "General Operating Expenses",
    },
    {
        "code": "CHARITY_RECIPIENT",
        "name": "Charity / 80G Recipient",
        "category_type": SubledgerCategoryType.EXPENSE,
        "default_taxonomy_category": "Expense",
        "default_taxonomy_subcategory": "Charity",
    },
]

if __name__ == "__main__":
    print("🌱 Seeding Subledger Categories...")
    for cat in categories:
        obj, created = AssetCategory.objects.get_or_create(
            code=cat["code"], defaults=cat
        )
        if created:
            print(f"  ✅ Created: {obj.name} [{obj.category_type}]")
        else:
            print(f"  ℹ️ Already exists: {obj.name}")
    print("✨ Seeding completed successfully!")
