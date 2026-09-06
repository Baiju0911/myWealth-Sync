import json
import os
from pathlib import Path
import time
from django.db.models import Q
from tracker.constants import StreamSource, IngestStatus, MatchTier

STAGING_JSON_FILE = Path(__file__).resolve().parent / "staged_previews.json"


def ensure_parent_dir():
    """Guarantees the directory exists before file I/O operations."""
    STAGING_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_staging_json() -> list:
    """Reads uncommitted live payloads from the local JSON buffer, sorted newest first."""
    ensure_parent_dir()

    if not STAGING_JSON_FILE.exists():
        return []

    try:
        if STAGING_JSON_FILE.stat().st_size == 0:
            return []

        with open(STAGING_JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []

        # Sort descending: newest datetime on top
        def extract_sort_key(item: dict) -> str:
            raw = item.get("raw_payload", {})
            parsed = item.get("parsed_transaction", {})

            dt = (
                raw.get("email_date")
                or item.get("created_at")
                or parsed.get("full_datetime")
            )
            if dt:
                return str(dt)

            d = parsed.get("date")
            if d:
                return f"{d} 00:00:00"

            return ""

        return sorted(data, key=extract_sort_key, reverse=True)

    except (json.JSONDecodeError, OSError, PermissionError):
        return []


def save_staging_json(data):
    """Atomically writes data to staged_previews.json with retry backoff."""
    ensure_parent_dir()
    temp_file = STAGING_JSON_FILE.parent / f"{STAGING_JSON_FILE.name}.tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                os.replace(temp_file, STAGING_JSON_FILE)
                break
            except PermissionError:
                if attempt == max_retries - 1:
                    with open(STAGING_JSON_FILE, "w", encoding="utf-8") as fallback_f:
                        json.dump(data, fallback_f, indent=2)
                    if temp_file.exists():
                        try:
                            os.remove(temp_file)
                        except OSError:
                            pass
                else:
                    time.sleep(0.05)
    except Exception as e:
        print(f"⚠️ Direct JSON save fallback failed: {e}")


def _is_db_duplicate(item: dict) -> bool:
    """
    Universally checks if an alert already exists in the MySQL Vault using
    immutable message IDs, transaction reference IDs, or cryptographic hashes.
    """
    from tracker.models.emailModels import RawEmailPayload

    raw = item.get("raw_payload", {})
    parsed = item.get("parsed_transaction", {})
    headers = (
        raw.get("headers_json", {}) if isinstance(raw.get("headers_json"), dict) else {}
    )

    # 1. Immutable Gmail API Message ID
    msg_id = headers.get("message_id") or item.get("id")
    if (
        msg_id
        and not str(msg_id).startswith("live-")
        and not str(msg_id).startswith("gap_")
        and len(str(msg_id)) < 30
    ):
        if RawEmailPayload.objects.filter(
            Q(headers_json__message_id=msg_id) | Q(txn_fingerprint=msg_id)
        ).exists():
            return True

    # 2. Immutable UPI / RRN / IMPS Reference + Amount
    ref = parsed.get("upi_ref")
    amt = parsed.get("amount")
    acct = parsed.get("account_last4")
    bank = parsed.get("bank_name")
    txn_type = parsed.get("txn_type")

    if ref and amt and str(ref) not in ["None", "—", "REF", "NARRATION", ""]:
        query = Q(upi_ref=ref, amount=amt)
        if acct:
            query &= Q(account_last4=acct)
        if txn_type:
            query &= Q(txn_type=txn_type)

        if RawEmailPayload.objects.filter(query).exists():
            return True

    # 3. Payload Hash or Fingerprint
    fp = parsed.get("txn_fingerprint") or item.get("id")
    p_hash = item.get("payload_hash") or raw.get("payload_hash")
    if fp and RawEmailPayload.objects.filter(txn_fingerprint=fp).exists():
        return True
    if p_hash and RawEmailPayload.objects.filter(payload_hash=p_hash).exists():
        return True

    return False


def _try_merge_staging_item(incoming_item: dict, buffer_items: list) -> bool:
    """
    Symmetrically merges incoming SMS and Gmail alerts within the staging buffer
    only if they originate from DIFFERENT channels, match the same bank, account, amount, and reference.
    Resets status to MATCHED_2_WAY and constructs combined narration and audit metadata.
    """
    new_raw = incoming_item.get("raw_payload", {})
    new_parsed = incoming_item.get("parsed_transaction", {})

    new_source = (new_raw.get("source") or incoming_item.get("source") or "").upper()
    new_ref = new_parsed.get("upi_ref")
    new_amt = new_parsed.get("amount")
    new_acct = new_parsed.get("account_last4")
    new_bank = (new_parsed.get("bank_name") or "").upper()

    if not new_ref or not new_amt:
        return False

    for existing in buffer_items:
        ex_raw = existing.get("raw_payload", {})
        ex_parsed = existing.get("parsed_transaction", {})

        ex_source = (ex_raw.get("source") or existing.get("source") or "").upper()
        ex_ref = ex_parsed.get("upi_ref")
        ex_amt = ex_parsed.get("amount")
        ex_acct = ex_parsed.get("account_last4")
        ex_bank = (ex_parsed.get("bank_name") or "").upper()

        sources_differ = (
            new_source != ex_source and new_source != "" and ex_source != ""
        )
        banks_match = not new_bank or not ex_bank or new_bank == ex_bank
        accounts_match = bool(new_acct and ex_acct and new_acct == ex_acct)
        ref_and_amt_match = ex_ref == new_ref and ex_amt == new_amt

        if sources_differ and banks_match and accounts_match and ref_and_amt_match:
            headers = ex_raw.setdefault("headers_json", {})
            signals = headers.setdefault("signals", {})

            # 1. Identify which stream is Gmail and which is SMS
            gmail_body = ""
            sms_body = ""

            if "GMAIL" in new_source:
                gmail_body = new_raw.get("decrypted_body") or new_raw.get("body") or ""
                sms_body = ex_raw.get("decrypted_body") or ex_raw.get("body") or ""
            else:
                sms_body = new_raw.get("decrypted_body") or new_raw.get("body") or ""
                gmail_body = ex_raw.get("decrypted_body") or ex_raw.get("body") or ""

            # Store multi-channel signals
            signals[new_source.lower() or "ios_sms"] = {
                "received_at": new_raw.get("email_date"),
                "raw_text": new_raw.get("decrypted_body") or new_raw.get("body"),
                "reference": new_ref,
                "rail": new_parsed.get("payment_rail"),
            }

            # 2. Pick the cleanest beneficiary (prefer Email over noisy SMS text)
            m_incoming = (new_parsed.get("merchant") or "").strip()
            m_existing = (ex_parsed.get("merchant") or "").strip()

            def is_noisy(m):
                m_up = m.upper()
                return (
                    "UPI DEBIT" in m_up
                    or "WAS SPENT" in m_up
                    or m_up in ["DIRECT PAYMENT", "UNKNOWN VENDOR", ""]
                )

            if is_noisy(m_existing) and not is_noisy(m_incoming):
                ex_parsed["merchant"] = m_incoming
            elif not is_noisy(m_incoming) and len(m_incoming) > len(m_existing):
                ex_parsed["merchant"] = m_incoming

            # 3. Synchronize balance
            if new_parsed.get("balance") and not ex_parsed.get("balance"):
                ex_parsed["balance"] = new_parsed["balance"]

            # 4. Rebuild Clean Unified Narration
            rail = (
                ex_parsed.get("payment_rail") or new_parsed.get("payment_rail") or "UPI"
            )
            ref = ex_ref or new_ref or "REF"
            merchant = ex_parsed.get("merchant") or "Direct Payment"
            full_narration = f"{rail}/{ref}/{merchant}"

            ex_parsed["full_narration"] = full_narration

            # 5. Populate Merge Details so the modal can inspect both sources
            merge_details = {
                "gmail_body": gmail_body,
                "sms_body": sms_body,
                "resolved_narration": full_narration,
                "matched_rrn": ref,
                "matched_amount": ex_amt,
            }
            ex_raw["merge_details"] = merge_details
            headers["merge_details"] = merge_details

            # 6. Override Status at BOTH top-level item and parsed_transaction
            existing["source"] = StreamSource.MERGED_STREAM.value
            existing["status"] = IngestStatus.MATCHED_2_WAY.value
            existing["is_duplicate"] = False

            ex_raw["source"] = StreamSource.MERGED_STREAM.value
            headers["is_merged"] = True
            headers["match_tier"] = MatchTier.TIER_1_REFERENCE.value

            ex_parsed["is_merged"] = True
            ex_parsed["status"] = IngestStatus.MATCHED_2_WAY.value
            ex_parsed["is_duplicate"] = False

            return True

    return False


def add_to_staging_buffer(preview_obj: dict):
    """
    Inserts or merges a single preview item into the staging buffer.
    Checks for cross-stream merge (SMS + Email) before committing duplicate flags.
    """
    buffer_items = load_staging_json()

    # 1. Attempt Cross-Stream Merge First (SMS <-> Email)
    merged = _try_merge_staging_item(preview_obj, buffer_items)
    if merged:
        save_staging_json(buffer_items)
        return

    # 2. If not merged, run DB duplicate check
    if _is_db_duplicate(preview_obj):
        preview_obj["is_duplicate"] = True
        preview_obj["status"] = IngestStatus.DUPLICATE.value
        if isinstance(preview_obj.get("parsed_transaction"), dict):
            preview_obj["parsed_transaction"]["is_duplicate"] = True

    # 3. Retain newest unique items in buffer
    parsed = preview_obj.get("parsed_transaction", {})
    new_fp = parsed.get("txn_fingerprint") or preview_obj.get("id")
    new_hash = preview_obj.get("payload_hash")

    filtered = [
        item
        for item in buffer_items
        if not (
            (
                new_fp
                and (
                    item.get("parsed_transaction", {}).get("txn_fingerprint") == new_fp
                    or item.get("id") == new_fp
                )
            )
            or (new_hash and item.get("payload_hash") == new_hash)
        )
    ]

    filtered.insert(0, preview_obj)
    save_staging_json(filtered)


def append_batch_to_staging_buffer(new_items: list):
    """Appends a batch of items, prioritizing cross-stream merges over duplicate flags."""
    if not new_items:
        return

    buffer_items = load_staging_json()
    existing_ids = set()

    for item in buffer_items:
        parsed = item.get("parsed_transaction", {})
        fp = parsed.get("txn_fingerprint") or item.get("id")
        h = item.get("payload_hash")
        if fp:
            existing_ids.add(fp)
        if h:
            existing_ids.add(h)

    processed_new = []
    for item in new_items:
        # 1. Cross-stream merge (SMS + Email) takes absolute priority
        if _try_merge_staging_item(item, buffer_items):
            continue

        # 2. Check against MySQL database only if it didn't merge
        if _is_db_duplicate(item):
            item["is_duplicate"] = True
            item["status"] = IngestStatus.DUPLICATE.value
            if isinstance(item.get("parsed_transaction"), dict):
                item["parsed_transaction"]["is_duplicate"] = True

        parsed = item.get("parsed_transaction", {})
        new_fp = parsed.get("txn_fingerprint") or item.get("id")
        new_hash = item.get("payload_hash")

        # 3. Deduplicate against current staging batch
        if (new_fp and new_fp in existing_ids) or (
            new_hash and new_hash in existing_ids
        ):
            continue

        if new_fp:
            existing_ids.add(new_fp)
        if new_hash:
            existing_ids.add(new_hash)

        processed_new.append(item)

    combined = processed_new + buffer_items
    save_staging_json(combined)


def remove_from_staging_buffer(committed_fingerprints: list):
    """Purges committed items from the JSON buffer once saved to MySQL."""
    buffer_items = load_staging_json()
    remaining = [
        item
        for item in buffer_items
        if item.get("parsed_transaction", {}).get("txn_fingerprint")
        not in committed_fingerprints
        and item.get("id") not in committed_fingerprints
    ]
    save_staging_json(remaining)


def discard_from_staging_buffer(identifiers_to_remove: list) -> int:
    """
    Purges items from staged_previews.json matching any provided id,
    txn_fingerprint, or payload_hash. Returns the count of removed items.
    """
    if not identifiers_to_remove:
        return 0

    id_set = set(str(i) for i in identifiers_to_remove)
    buffer_items = load_staging_json()
    initial_count = len(buffer_items)

    surviving = []
    for item in buffer_items:
        parsed = item.get("parsed_transaction", {})
        item_id = str(item.get("id", ""))
        item_fp = str(parsed.get("txn_fingerprint", ""))
        item_hash = str(item.get("payload_hash", ""))

        if item_id not in id_set and item_fp not in id_set and item_hash not in id_set:
            surviving.append(item)

    save_staging_json(surviving)
    return initial_count - len(surviving)
