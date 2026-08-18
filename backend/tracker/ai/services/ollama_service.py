import json
import time
import re
import urllib.request
import urllib.error
from tracker.constants import NOISE_KEYWORD_BLACKLIST

OLLAMA_API_URL = "http://localhost:11434/api/generate"

TAXONOMY_PRIMARY_CLASSES = [
    "Expense",
    "Transfer",
    "Income",
    "Asset",
    "Liability",
    "Current Assets",
    "Transfers",
]


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
    """
    Sends cleaned narration to Llama 3.2 for structured classification.
    """
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
        "model": "llama3.2:3b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            elapsed = round(time.time() - start_time, 2)

            parsed_result = json.loads(res_data.get("response", "{}"))
            parsed_result["_execution_time_seconds"] = elapsed
            return parsed_result
    except urllib.error.URLError as e:
        print(f"Ollama API Connection Error: {e}")
        return {
            "category": "Expense",
            "vendor_name": "Unclassified",
            "confidence_score": 0.0,
        }


def classify_with_vendor_memory(raw_text: str, vendor_schema: dict = None) -> dict:
    """
    Classifies narration while enforcing custom dynamic JSON schemas based on learned vendor memory.
    """
    base_schema_instruction = f"""
    Required JSON keys:
    - category: string (MUST BE ONE OF: {", ".join(TAXONOMY_PRIMARY_CLASSES)})
    - vendor_name: string
    - confidence_score: float (0.0 to 1.0)
    - extracted_metadata: object
    """

    if vendor_schema:
        schema_str = json.dumps(vendor_schema, indent=2)
        vendor_instruction = f"\nEnforce the following custom metadata fields for this vendor:\n{schema_str}\n"
    else:
        vendor_instruction = ""

    prompt = f"""
    Analyze the following transaction narration and extract structured metadata.
    Respond ONLY in valid JSON.

    Narration: "{raw_text}"
    {base_schema_instruction}
    {vendor_instruction}
    """

    payload = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
    }

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return json.loads(res_data.get("response", "{}"))
    except Exception as e:
        return {"error": str(e)}
