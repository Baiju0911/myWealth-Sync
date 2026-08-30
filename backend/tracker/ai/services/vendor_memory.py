import psycopg2
import json
import os

DB_PARAMS = {
    "dbname": "mywealth_vector_db",
    "user": "root",
    "password": "rootpassword",
    "host": os.environ.get("VECTOR_DB_HOST", "vector_db"),
    "port": int(os.environ.get("VECTOR_DB_PORT", "5432")),
    "connect_timeout": 3,
}


def get_cached_vendor_schema(vendor_name: str):
    """
    Checks PostgreSQL for previously stored vendor schemas.
    Returns schema dict if found, otherwise None.
    """
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()
        cur.execute(
            "SELECT dynamic_schema FROM vendor_memory WHERE LOWER(vendor_name) = LOWER(%s);",
            (vendor_name,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"Vector DB Lookup Error: {e}")
        return None
