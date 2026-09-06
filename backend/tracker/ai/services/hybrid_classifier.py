import logging
from typing import Dict, Any

from .ai_rule_trainer_engine import AIRuleTrainerEngine
from ..db_pool import get_db_connection, release_db_connection

logger = logging.getLogger(__name__)


def save_vendor_to_cache(vendor_name: str, category: str, schema: dict) -> bool:
    return AIRuleTrainerEngine.save_vendor_to_cache(vendor_name, category, schema)


def classify_transaction(raw_text: str) -> Dict[str, Any]:
    return AIRuleTrainerEngine.classify(raw_text)


def classify_and_learn(raw_text: str) -> Dict[str, Any]:
    return AIRuleTrainerEngine.classify(raw_text)


def query_local_vector_cache(narration: str) -> Dict[str, Any]:
    res = AIRuleTrainerEngine._query_vector_memory(narration)
    if res:
        return res
    return {
        "is_trained": False,
        "confidence_score": 0.0,
        "category": "Expense",
        "subcategory": "Suspense Account",
        "source": "vector_cache_miss",
    }


def check_vector_exists(narration: str) -> bool:
    return AIRuleTrainerEngine.check_vector_exists(narration)


def push_to_vector_cache(
    narration: str,
    category: str,
    subcategory: str,
    rule_code: str = "AUTO",
    confidence: int = 100,
) -> None:
    AIRuleTrainerEngine.push_to_vector_cache(
        narration=narration,
        category=category,
        subcategory=subcategory,
        rule_code=rule_code,
        confidence=confidence,
    )
