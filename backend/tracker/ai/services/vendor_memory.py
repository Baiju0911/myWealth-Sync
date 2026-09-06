import logging
from .db_pool import get_db_connection, release_db_connection

logger = logging.getLogger(__name__)


def get_cached_vendor_schema(vendor_name: str):
    """Checks PostgreSQL for previously stored vendor schemas."""
    if not vendor_name:
        return None

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT dynamic_schema FROM vendor_memory WHERE LOWER(vendor_name) = LOWER(%s);",
            (str(vendor_name).strip(),),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Vector DB Lookup Error: {e}")
        return None
    finally:
        release_db_connection(conn)
