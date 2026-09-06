import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from tracker.classification.utils.taxonomy_gate import resolve_official_taxonomy
from .ollama_service import classify_asset_narration
from ..db_pool import get_db_connection, release_db_connection

logger = logging.getLogger(__name__)

INVALID_SUB_TOKENS = {
    "suspense account",
    "none",
    "null",
    "unclassified",
    "unknown",
    "ai unclassified",
}


class AIRuleTrainerEngine:
    """Unified AI Engine for Transaction Classification, Vector Cache

    Management, and Online Learning.
    """

    @classmethod
    def _get_connection(cls):
        return get_db_connection()

    @classmethod
    def _release_connection(cls, conn):
        release_db_connection(conn)

    @classmethod
    def classify(cls, narration: str) -> Dict[str, Any]:
        """Classifies a raw transaction narration using Hybrid Strategy:

        1. Fast Path: PostgreSQL Vector Cache / Vendor Memory (O(1))
        2. Slow Path: Fallback to Local Ollama SLM if cache misses.
        """
        if not narration or not str(narration).strip():
            return cls._empty_classification_payload("Empty narration")

        start_time = time.time()
        raw_text = str(narration).strip()

        # Step A: Vector DB / Vendor Memory Lookup (Fast Path)
        cache_hit = cls._query_vector_memory(raw_text)
        if cache_hit:
            cache_hit["_execution_time_seconds"] = round(time.time() - start_time, 4)
            return cache_hit

        # Step B: Fallback to Ollama Local SLM (Slow Path)
        try:
            slm_res = classify_asset_narration(raw_text)
            raw_vendor = slm_res.get("vendor_name") or slm_res.get("subcategory")
            raw_cat = slm_res.get("category")

            official_cat, official_sub = resolve_official_taxonomy(raw_cat, raw_vendor)
            confidence = float(slm_res.get("confidence_score", 0.85))

            payload = {
                "category": official_cat,
                "subcategory": official_sub,
                "vendor_name": official_sub,
                "confidence_score": confidence,
                "is_trained": False,
                "source": "ollama_slm",
                "extracted_metadata": slm_res.get("extracted_metadata", {}),
                "_execution_time_seconds": round(time.time() - start_time, 4),
            }

            # Auto-learn high-confidence SLM hits
            if confidence >= 0.85 and cls.is_valid_subcategory(official_sub):
                cls.save_vendor_to_cache(
                    vendor_name=official_sub,
                    category=official_cat,
                    schema=slm_res.get("extracted_metadata", {}),
                )
                payload["is_trained"] = True
                payload["source"] = "ollama_slm_learned"

            return payload

        except Exception as err:
            logger.error(f"Ollama SLM classification failed: {err}")
            return cls._empty_classification_payload(f"SLM Error: {err}")

    @classmethod
    def auto_seed_deterministic_hit(
        cls,
        raw_narration: str,
        raw_resolved_cat: str,
        raw_resolved_sub: str,
        rule_source: str = "AUTO",
    ) -> Tuple[str, str, str, bool]:
        """Validates and seeds a deterministic rule hit into vector memory."""
        final_cat, final_sub = resolve_official_taxonomy(
            raw_resolved_cat, raw_resolved_sub
        )

        if not cls.is_valid_subcategory(final_sub):
            return final_cat, final_sub, "bypassed_invalid_taxonomy", False

        if cls.check_vector_exists(raw_narration):
            return final_cat, final_sub, "vector_cache_verified", True

        cls.push_to_vector_cache(
            narration=raw_narration,
            category=final_cat,
            subcategory=final_sub,
            rule_code=rule_source,
            confidence=100,
        )
        return final_cat, final_sub, "auto_trained_from_t1_t4", True

    @classmethod
    def learn_from_binding(
        cls,
        narration: str,
        category: str,
        subcategory: str,
        user_note: Optional[str] = None,
        rule_code: str = "MANUAL_BIND",
    ) -> bool:
        """Captures ground-truth confirmation from UI 'Bind' action and updates Vector Memory."""
        if not cls.is_valid_subcategory(subcategory):
            logger.warning(
                f"[AI ENGINE] Skipped learning for invalid subcategory: {subcategory}"
            )
            return False

        official_cat, official_sub = resolve_official_taxonomy(category, subcategory)

        # Trust explicit user bindings if taxonomy gate fell back to Suspense Account
        if official_sub == "Suspense Account" and cls.is_valid_subcategory(subcategory):
            official_cat, official_sub = category, subcategory

        schema_payload = {
            "rule_code": rule_code,
            "confidence": 100,
            "user_note": user_note or "",
            "learned_at_timestamp": time.time(),
            "sample_narration": str(narration).strip()[:100],
        }

        return cls.save_vendor_to_cache(
            vendor_name=official_sub,
            category=official_cat,
            schema=schema_payload,
            bypass_taxonomy_fallback=True,
        )

    @classmethod
    def is_valid_subcategory(cls, subcategory: Optional[str]) -> bool:
        if not subcategory or not str(subcategory).strip():
            return False

        clean = str(subcategory).strip().lower()
        if (
            clean in INVALID_SUB_TOKENS
            or clean.startswith("fed-")
            or clean.startswith("sbonr")
        ):
            return False

        return True

    @classmethod
    def check_vector_exists(cls, narration: str) -> bool:
        if not narration or not str(narration).strip():
            return False
        res = cls._query_vector_memory(narration)
        return bool(res and res.get("confidence_score", 0.0) >= 0.85)

    @classmethod
    def push_to_vector_cache(
        cls,
        narration: str,
        category: str,
        subcategory: str,
        rule_code: str = "AUTO",
        confidence: int = 100,
    ) -> None:
        if not cls.is_valid_subcategory(subcategory):
            return

        schema_payload = {
            "rule_code": str(rule_code),
            "confidence": confidence,
            "sample_narration": str(narration).strip()[:100],
        }

        cls.save_vendor_to_cache(
            vendor_name=subcategory, category=category, schema=schema_payload
        )

    @classmethod
    def save_vendor_to_cache(
        cls,
        vendor_name: str,
        category: str,
        schema: dict,
        bypass_taxonomy_fallback: bool = False,
    ) -> bool:
        if not cls.is_valid_subcategory(vendor_name):
            return False

        official_cat, official_sub = resolve_official_taxonomy(category, vendor_name)

        if (
            official_sub == "Suspense Account"
            and bypass_taxonomy_fallback
            and cls.is_valid_subcategory(vendor_name)
        ):
            official_cat, official_sub = category, vendor_name

        if not cls.is_valid_subcategory(official_sub):
            return False

        conn = None
        try:
            conn = cls._get_connection()
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
            logger.error(f"Failed to save vendor to vector cache: {e}")
            return False
        finally:
            cls._release_connection(conn)

    @classmethod
    def _query_vector_memory(cls, narration: str) -> Optional[Dict[str, Any]]:
        conn = None
        try:
            conn = cls._get_connection()
            cur = conn.cursor()

            # Word boundary regex matching with length sorting: longest match wins
            query = """
                SELECT vendor_name, default_category, dynamic_schema 
                FROM vendor_memory 
                WHERE length(vendor_name) >= 3 
                  AND %s ~* ('\\m' || regexp_replace(vendor_name, '([[\\]().*+?^$|{}])', '\\\\\\1', 'g') || '\\M')
                ORDER BY length(vendor_name) DESC 
                LIMIT 1;
            """
            cur.execute(query, (narration,))
            match = cur.fetchone()
            cur.close()

            if match:
                raw_vendor, raw_cat, schema_raw = match[0], match[1], match[2]
                official_cat, official_sub = resolve_official_taxonomy(
                    raw_cat, raw_vendor
                )

                schema = schema_raw if isinstance(schema_raw, dict) else {}
                if isinstance(schema_raw, str):
                    try:
                        schema = json.loads(schema_raw)
                    except Exception:
                        schema = {}

                return {
                    "category": official_cat,
                    "subcategory": official_sub,
                    "vendor_name": official_sub,
                    "confidence_score": 1.0,
                    "is_trained": True,
                    "source": "vector_db_cache",
                    "extracted_metadata": schema,
                }
        except Exception as e:
            logger.warning(f"Vector memory lookup error: {e}")
        finally:
            cls._release_connection(conn)

        return None

    @classmethod
    def _empty_classification_payload(cls, source_reason: str) -> Dict[str, Any]:
        return {
            "category": "Expense",
            "subcategory": "Suspense Account",
            "vendor_name": "Suspense Account",
            "confidence_score": 0.0,
            "is_trained": False,
            "source": source_reason,
            "extracted_metadata": {},
            "_execution_time_seconds": 0.0,
        }


# Legacy interface functions mapped directly for backward compatibility
classify_transaction = AIRuleTrainerEngine.classify
query_local_vector_cache = AIRuleTrainerEngine._query_vector_memory
check_vector_exists = AIRuleTrainerEngine.check_vector_exists
push_to_vector_cache = AIRuleTrainerEngine.push_to_vector_cache
save_vendor_to_cache = AIRuleTrainerEngine.save_vendor_to_cache
