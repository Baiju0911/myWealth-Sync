import json
import requests

OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"


def extract_merchant_local(narration: str) -> dict:
    prompt = f"""
    You are a financial narration parser. Return strictly valid JSON with keys "merchant", "payment_mode", and "clean_token".
    Narration: "{narration}"
    JSON Response:
    """

    payload = {
        "model": "llama3.2:3b",
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    try:
        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=5)
        res_data = response.json()
        return json.loads(res_data.get("response", "{}"))
    except Exception as e:
        return {"error": f"Local AI execution failed: {str(e)}"}
