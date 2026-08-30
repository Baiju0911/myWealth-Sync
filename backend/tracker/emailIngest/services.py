import base64
from datetime import datetime
from email.utils import parsedate_to_datetime
import hashlib
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from django.conf import settings

# 1. 32-Byte (256-bit) Fallback Key
DEFAULT_32BYTE_KEY = b"12345678901234567890123456789012"


def get_active_aes_key() -> bytes:
    """
    Retrieves the configured AES key from Django settings.
    Checks EMAIL_INGEST_AES_KEY first, then AES_SECRET_KEY, and falls back to DEFAULT_32BYTE_KEY.
    Ensures key is returned as raw bytes.
    """
    key_val = getattr(
        settings,
        "EMAIL_INGEST_AES_KEY",
        getattr(settings, "AES_SECRET_KEY", DEFAULT_32BYTE_KEY),
    )

    if isinstance(key_val, str):
        key_bytes = key_val.encode("utf-8")
    elif isinstance(key_val, bytes):
        key_bytes = key_val
    else:
        key_bytes = DEFAULT_32BYTE_KEY

    # Truncate or pad to 32 bytes (AES-256)
    if len(key_bytes) >= 32:
        return key_bytes[:32]
    return key_bytes.ljust(32, b"0")


def safe_parse_datetime(date_str: str):
    """
    Safely parses email date header strings into a timezone-aware datetime object.
    Falls back to current time if parsing fails or input is empty.
    """
    if not date_str:
        return datetime.now()

    try:
        # Standard RFC 2822 email date format parser
        return parsedate_to_datetime(date_str)
    except Exception:
        try:
            # ISO 8601 fallback
            return datetime.fromisoformat(date_str)
        except Exception:
            return datetime.now()


def generate_payload_hash(payload) -> str:
    """Generates a SHA-256 hash for transport deduplication."""
    if isinstance(payload, dict):
        payload_str = json.dumps(payload, sort_keys=True)
    else:
        payload_str = str(payload)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def generate_transaction_fingerprint(parsed_data: dict) -> str:
    """
    Generates a deterministic SHA-256 fingerprint based on core transaction attributes:
    email_date + bank_name + account_last4 + txn_type + amount
    """
    date_str = str(
        parsed_data.get("date") or parsed_data.get("email_date") or ""
    ).strip()
    bank = str(parsed_data.get("bank_name") or "").strip().upper()
    acc_last4 = str(parsed_data.get("account_last4") or "").strip()
    txn_type = str(parsed_data.get("txn_type") or "DEBIT").strip().upper()

    amount_raw = parsed_data.get("amount")
    try:
        amount_str = f"{float(amount_raw):.2f}" if amount_raw is not None else "0.00"
    except (ValueError, TypeError):
        amount_str = str(amount_raw or "0.00").strip()

    composite_key = f"{date_str}|{bank}|{acc_last4}|{txn_type}|{amount_str}"
    return hashlib.sha256(composite_key.encode("utf-8")).hexdigest()


def encrypt_aes_payload(data_dict: dict) -> str:
    """Encrypts a dictionary payload into an AES-256-CBC Base64 string with prepended IV."""
    key = get_active_aes_key()
    json_str = json.dumps(data_dict)
    cipher = AES.new(key, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(json_str.encode("utf-8"), AES.block_size))
    encrypted_data = cipher.iv + ct_bytes
    return base64.b64encode(encrypted_data).decode("utf-8")


def decrypt_aes_payload(encrypted_b64_str: str) -> dict:
    """Decrypts a Base64 AES-256-CBC encrypted string back to a dict."""
    key = get_active_aes_key()
    encrypted_data = base64.b64decode(encrypted_b64_str)
    iv = encrypted_data[:16]
    ct = encrypted_data[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return json.loads(pt.decode("utf-8"))
