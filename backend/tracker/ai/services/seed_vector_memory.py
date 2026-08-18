import json
import psycopg2
from tracker.models.models import MasterFinancialCategory, AccountingRule

DB_PARAMS = {
    "dbname": "mywealth_vector_db",
    "user": "root",
    "password": "rootpassword",
    "host": "localhost",
    "port": "5433",
}


def seed_vector_memory_from_db():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    records_added = 0

    sql = """
    INSERT INTO vendor_memory (vendor_name, default_category, dynamic_schema)
    VALUES (%s, %s, %s)
    ON CONFLICT (vendor_name) DO UPDATE SET
        default_category = EXCLUDED.default_category,
        dynamic_schema = EXCLUDED.dynamic_schema;
    """

    # 1. Harvest from MasterFinancialCategory
    default_cats = MasterFinancialCategory.objects.exclude(act_category__isnull=True)
    for row in default_cats:
        vendor_keyword = (row.act_category or "").strip()
        subcat = (row.act_subcategory or "").strip()

        # Extract key1/key2 tokens from keys JSON
        keys_dict = row.keys if isinstance(row.keys, dict) else {}
        k1 = (keys_dict.get("key1") or "").strip()

        if k1 and len(k1) >= 3:
            cur.execute(
                sql,
                (
                    k1.upper(),
                    vendor_keyword.title(),
                    json.dumps({"subcategory": subcat, "source": "MasterCategory"}),
                ),
            )
            records_added += 1

    # 2. Harvest from AccountingRule (Parse rule_metadata & description_tags)
    rules = AccountingRule.objects.filter(is_active="1")
    for rule in rules:
        metadata = rule.rule_metadata
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        elif not isinstance(metadata, dict):
            metadata = {}

        target_cat = metadata.get("category", "Expense").strip().title()
        target_sub = metadata.get("subcategory", "General").strip()

        tags = rule.description_tags
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        elif not isinstance(tags, list):
            tags = []

        for tag in tags:
            clean_tag = str(tag).strip().upper()
            if len(clean_tag) >= 3:
                cur.execute(
                    sql,
                    (
                        clean_tag,
                        target_cat,
                        json.dumps(
                            {"subcategory": target_sub, "rule_code": rule.rule_code}
                        ),
                    ),
                )
                records_added += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Pre-seeded {records_added} rules into PostgreSQL vendor_memory!")


if __name__ == "__main__":
    seed_vector_memory_from_db()
