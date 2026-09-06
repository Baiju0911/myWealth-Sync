import os
import logging
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

DB_PARAMS = {
    "dbname": os.environ.get("VECTOR_DB_NAME", "mywealth_vector_db"),
    "user": os.environ.get("VECTOR_DB_USER", "root"),
    "password": os.environ.get("VECTOR_DB_PASSWORD", "rootpassword"),
    "host": os.environ.get("VECTOR_DB_HOST", "vector_db"),
    "port": int(os.environ.get("VECTOR_DB_PORT", "5432")),
    "connect_timeout": int(os.environ.get("VECTOR_DB_TIMEOUT", "3")),
}

try:
    _db_pool = ThreadedConnectionPool(2, 20, **DB_PARAMS)
except Exception as e:
    logger.error(f"Failed to initialize PostgreSQL ThreadedConnectionPool: {e}")
    _db_pool = None


def get_db_connection():
    """Retrieves a thread-safe connection from the pool."""
    if _db_pool:
        return _db_pool.getconn()
    import psycopg2

    return psycopg2.connect(**DB_PARAMS)


def release_db_connection(conn):
    """Safely returns connection back to the pool."""
    if _db_pool and conn:
        _db_pool.putconn(conn)
    elif conn:
        conn.close()
