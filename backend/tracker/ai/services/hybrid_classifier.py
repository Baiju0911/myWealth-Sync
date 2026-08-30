import time
import psycopg2
import os
from psycopg2 import pool
import json
import logging
from .ollama_service import classify_asset_narration
from tracker.classification.utils.taxonomy_gate import resolve_official_taxonomy

logger = logging.getLogger(__name__)

DB_PARAMS = {
    "dbname": "mywealth_vector_db",
    "user": "root",
    "password": "rootpassword",
    "host": os.environ.get("VECTOR_DB_HOST", "vector_db"),
    "port": int(os.environ.get("VECTOR_DB_PORT", "5432")),
    "connect_timeout": 3,
}

# Expand pool capacity (2 to 20 connections) to avoid connection blocking across worker threads
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(2, 20, **DB_PARAMS)
except Exception as e:
    logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
    db_pool = None


def get_db_connection():
    if db_pool:
        return db_pool.getconn()
    return psycopg2.connect(**DB_PARAMS)


def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)
    elif conn:
        conn.close()


def save_vendor_to_cache(vendor_name: str, category: str, schema: dict) -> bool:
    """
    Saves or updates a vendor's default category and metadata schema in PostgreSQL.
    Enforces TaxonomyTree single-source validation before writing.
    """
    if not vendor_name or vendor_name.lower() in {
        "unknown",
        "none",
        "",
        "suspense account",
        "null",
        "unclassified",
    }:
        return False

    # 🟢 Single Source Taxonomy Gate Enforcement
    official_cat, official_sub = resolve_official_taxonomy(category, vendor_name)

    if official_sub.lower() in {"suspense account", "none", "null"}:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql = """
        INSERT INTO vendor_memory (vendor_name, default_category, dynamic_schema)
        VALUES (%s, %s, %s)
        ON CONFLICT (vendor_name) 
        DO UPDATE SET 
            default_category = EXCLUDED.default_category,
            dynamic_schema = EXCLUDED.dynamic_schema;
        """
        schema_payload = schema if isinstance(schema, dict) else {}
        schema_payload["official_subcategory"] = official_sub

        cur.execute(sql, (official_sub, official_cat, json.dumps(schema_payload)))
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        logger.error(f"Failed to save vendor to cache: {e}")
        return False
    finally:
        release_db_connection(conn)


def classify_transaction(raw_text: str) -> dict:
    start_time = time.time()

    # 1. Fast Path: Check Vector / Vendor Memory DB
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT vendor_name, default_category, dynamic_schema FROM vendor_memory WHERE %s ILIKE '%%' || vendor_name || '%%';",
            (raw_text,),
        )
        match = cur.fetchone()
        cur.close()

        if match:
            raw_vendor, raw_cat, schema_raw = match[0], match[1], match[2]
            official_cat, official_sub = resolve_official_taxonomy(raw_cat, raw_vendor)

            schema = schema_raw if isinstance(schema_raw, dict) else {}
            if isinstance(schema_raw, str):
                try:
                    schema = json.loads(schema_raw)
                except Exception:
                    schema = {}

            return {
                "category": official_cat,
                "vendor_name": official_sub,
                "subcategory": official_sub,
                "confidence_score": 1.0,
                "extracted_metadata": schema,
                "source": "vector_db_cache",
                "_execution_time_seconds": round(time.time() - start_time, 4),
            }
    except Exception as e:
        logger.warning(f"Cache lookup failed: {e}")
    finally:
        release_db_connection(conn)

    # 2. Slow Path: Fallback to local Ollama SLM
    res = classify_asset_narration(raw_text)
    res["source"] = "ollama_slm"
    res["_execution_time_seconds"] = round(time.time() - start_time, 4)
    return res


def classify_and_learn(raw_text: str) -> dict:
    """
    Classifies narration via hybrid workflow and auto-caches high-confidence SLM outputs.
    """
    result = classify_transaction(raw_text)

    if (
        result.get("source") == "ollama_slm"
        and result.get("confidence_score", 0) >= 0.85
    ):
        vendor = result.get("vendor_name") or result.get("subcategory")
        category = result.get("category")
        schema = result.get("extracted_metadata")

        if save_vendor_to_cache(vendor, category, schema):
            result["_learned_status"] = "Cached into vector memory"

    return result


# =========================================================================
# 🟢 EXPORTED AI VECTOR CACHE INTERFACES
# =========================================================================


def query_local_vector_cache(narration: str) -> dict:
    """
    High-speed Cosine/Pattern Neighbor Lookup against local PostgreSQL vector memory.
    Fast-fails instantly on cache miss to preserve O(1) ingestion batch throughput.
    """
    if not narration or not str(narration).strip():
        return {"is_trained": False, "confidence_score": 0.0}

    start_time = time.time()
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT vendor_name, default_category, dynamic_schema FROM vendor_memory WHERE %s ILIKE '%%' || vendor_name || '%%';",
            (narration,),
        )
        match = cur.fetchone()
        cur.close()

        if match:
            raw_vendor, raw_cat, schema_raw = match[0], match[1], match[2]
            official_cat, official_sub = resolve_official_taxonomy(raw_cat, raw_vendor)

            return {
                "is_trained": True,
                "confidence_score": 1.0,
                "category": official_cat,
                "subcategory": official_sub,
                "vendor_name": official_sub,
                "source": "vector_db_cache",
                "_execution_time_seconds": round(time.time() - start_time, 4),
            }
    except Exception as e:
        logger.warning(f"Vector cache lookup error: {e}")
    finally:
        release_db_connection(conn)

    # 🟢 FAST-FAIL GATEWAY: Return unlearned state immediately without synchronous SLM calls.
    return {
        "is_trained": False,
        "confidence_score": 0.0,
        "category": "Expense",
        "subcategory": "Suspense Account",
        "source": "vector_cache_miss",
    }


def check_vector_exists(narration: str) -> bool:
    """
    Checks if a normalized narration pattern already exists in vector memory with high confidence.
    """
    if not narration or not str(narration).strip():
        return False
    try:
        res = query_local_vector_cache(narration)
        return bool(res.get("is_trained") and res.get("confidence_score", 0.0) >= 0.85)
    except Exception:
        return False


def push_to_vector_cache(
    narration: str,
    category: str,
    subcategory: str,
    rule_code: str = "AUTO",
    confidence: int = 100,
) -> None:
    """
    Seeds verified ground-truth pairs into PostgreSQL / Vector Cache.
    """
    if not narration or not str(narration).strip():
        return

    clean_sub = str(subcategory).strip()
    clean_sub_lower = clean_sub.lower()

    if (
        not clean_sub
        or clean_sub_lower in {"suspense account", "none", "null", "unclassified"}
        or clean_sub_lower.startswith("fed-")
        or clean_sub_lower.startswith("sbonr")
    ):
        return

    schema_payload = {
        "rule_code": str(rule_code),
        "confidence": confidence,
        "sample_narration": str(narration).strip()[:100],
    }

    try:
        save_vendor_to_cache(
            vendor_name=clean_sub, category=category, schema=schema_payload
        )
    except Exception as err:
        logger.warning(f"Vector push skipped due to pool contention: {err}")
