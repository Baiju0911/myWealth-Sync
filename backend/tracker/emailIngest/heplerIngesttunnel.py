import json
from pathlib import Path

# Path to persistent local JSON buffer in your project directory
STAGING_JSON_FILE = Path(__file__).resolve().parent.parent / "staged_previews.json"


def load_staging_json() -> list:
    """Reads uncommitted live webhook payloads from the local JSON buffer."""
    if not STAGING_JSON_FILE.exists():
        return []
    try:
        with open(STAGING_JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Failed to load staging JSON: {e}")
        return []


def save_staging_json(data: list):
    """Saves the staging list back to the JSON file on disk."""
    try:
        with open(STAGING_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Failed to write staging JSON: {e}")


def add_to_staging_buffer(preview_obj: dict):
    """Inserts a new webhook item at the top of the JSON buffer file (with deduplication)."""
    buffer_items = load_staging_json()

    new_fp = preview_obj.get("parsed_transaction", {}).get("txn_fingerprint")
    new_hash = preview_obj.get("payload_hash")

    # Filter out existing duplicates with same fingerprint or payload_hash
    filtered = []
    for item in buffer_items:
        item_fp = item.get("parsed_transaction", {}).get("txn_fingerprint")
        item_hash = item.get("payload_hash")
        if (new_fp and item_fp == new_fp) or (new_hash and item_hash == new_hash):
            continue
        filtered.append(item)

    filtered.insert(0, preview_obj)
    save_staging_json(filtered)


def remove_from_staging_buffer(committed_fingerprints: list):
    """Purges committed items from the JSON file once saved to MySQL."""
    buffer_items = load_staging_json()
    remaining = [
        item
        for item in buffer_items
        if item.get("parsed_transaction", {}).get("txn_fingerprint")
        not in committed_fingerprints
    ]
    save_staging_json(remaining)
