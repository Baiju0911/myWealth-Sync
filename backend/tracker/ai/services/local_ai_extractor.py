import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

OLLAMA_ENDPOINT = os.environ.get(
    "OLLAMA_API_URL", "http://localhost:11434/api/generate"
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")


def extract_merchant_local(narration: str) -> dict:
    prompt = f"""
    You are a financial narration parser. Return strictly valid JSON with keys "merchant", "payment_mode", and "clean_token".
    Narration: "{narration}"
    JSON Response:
    """

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    try:
        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=10)
        response.raise_for_status()
        res_data = response.json()
        return json.loads(res_data.get("response", "{}"))
    except Exception as e:
        logger.error(f"Local AI execution failed: {e}")
        return {"error": f"Local AI execution failed: {str(e)}"}
