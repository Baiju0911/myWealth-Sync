import os
import json
import time
import re
import logging
import requests
from tracker.constants import NOISE_KEYWORD_BLACKLIST

logger = logging.getLogger(__name__)

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "45"))

TAXONOMY_PRIMARY_CLASSES = [
    "Expense",
    "Transfer",
    "Income",
    "Asset",
    "Liability",
    "Current Assets",
    "Transfers",
]

_session = requests.Session()


def sanitize_narration(raw_text: str) -> str:
    """Strips banking boilerplate and noise tokens using constants.py blacklist."""
    if not raw_text:
        return ""

    tokens = raw_text.upper().split()
    cleaned = [
        re.sub(r"[^A-Z]", "", t)
        for t in tokens
        if re.sub(r"[^A-Z]", "", t) not in NOISE_KEYWORD_BLACKLIST
        and len(re.sub(r"[^A-Z]", "", t)) > 2
    ]
    return " ".join(cleaned) if cleaned else raw_text


def classify_asset_narration(raw_text: str) -> dict:
    """Sends cleaned narration to Ollama SLM for structured classification."""
    start_time = time.time()
    clean_text = sanitize_narration(raw_text)

    prompt = f"""
    Analyze the following bank transaction narration and extract financial metadata.
    Respond ONLY in valid JSON with no conversational preamble.

    Cleaned Narration: "{clean_text}"
    Raw Narration: "{raw_text}"

    Required JSON keys:
    - category: string (MUST BE ONE OF: {", ".join(TAXONOMY_PRIMARY_CLASSES)})
    - vendor_name: string (Merchant, Payee, or Entity name extracted, e.g., "SWIGGY", "HDFC BANK", "KSEB")
    - confidence_score: float (0.0 to 1.0)
    - extracted_metadata: object (Key-value metadata like transaction references or branch names)

    Classification Rules:
    1. If the narration refers to inter-account transfers, self transfers, IMPS, NEFT, or FTO, classify as "Transfer".
    2. Do NOT assign "Asset" or "Real Estate" unless explicitly containing land, property, plot, or survey numbers.
    """

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }

    try:
        response = _session.post(
            OLLAMA_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        res_data = response.json()
        elapsed = round(time.time() - start_time, 2)

        raw_response_text = res_data.get("response", "{}")
        parsed_result = json.loads(raw_response_text)
        parsed_result["_execution_time_seconds"] = elapsed
        return parsed_result

    except Exception as e:
        logger.error(f"Ollama API Connection Error: {e}")
        return {
            "category": "Expense",
            "vendor_name": "Unclassified",
            "confidence_score": 0.0,
            "_execution_time_seconds": round(time.time() - start_time, 2),
            "extracted_metadata": {},
        }


def classify_with_vendor_memory(raw_text: str, vendor_schema: dict = None) -> dict:
    """Classifies narration while enforcing custom dynamic JSON schemas based on learned vendor memory."""
    base_schema_instruction = f"""
    Required JSON keys:
    - category: string (MUST BE ONE OF: {", ".join(TAXONOMY_PRIMARY_CLASSES)})
    - vendor_name: string
    - confidence_score: float (0.0 to 1.0)
    - extracted_metadata: object
    """

    vendor_instruction = (
        f"\nEnforce the following custom metadata fields for this vendor:\n{json.dumps(vendor_schema, indent=2)}\n"
        if vendor_schema
        else ""
    )

    prompt = f"""
    Analyze the following transaction narration and extract structured metadata.
    Respond ONLY in valid JSON.

    Narration: "{raw_text}"
    {base_schema_instruction}
    {vendor_instruction}
    """

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }

    try:
        response = _session.post(
            OLLAMA_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        res_data = response.json()
        return json.loads(res_data.get("response", "{}"))
    except Exception as e:
        logger.error(f"Ollama dynamic schema classification failed: {e}")
        return {"error": str(e)}
