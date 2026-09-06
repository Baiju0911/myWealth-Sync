import base64
import os
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tracker.emailIngest.parser import clean_html_to_text, parse_bank_email_body
from tracker.emailIngest.services import (
    generate_payload_hash,
    generate_transaction_fingerprint,
    safe_parse_datetime,
)
from .heplerIngesttunnel import append_batch_to_staging_buffer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def extract_email_body(payload: dict) -> str:
    """
    Recursively inspects Gmail payload MIME parts and returns valid base64 data.
    Prioritizes text/html first, falling back to text/plain.
    """
    if not payload or not isinstance(payload, dict):
        return ""

    body = payload.get("body", {})
    if body.get("data"):
        return body["data"]

    parts = payload.get("parts", [])

    # Pass 1: text/html
    for part in parts:
        mime_type = part.get("mimeType", "").lower()
        part_body = part.get("body", {})
        if mime_type == "text/html" and part_body.get("data"):
            return part_body["data"]

    # Pass 2: text/plain
    for part in parts:
        mime_type = part.get("mimeType", "").lower()
        part_body = part.get("body", {})
        if mime_type == "text/plain" and part_body.get("data"):
            return part_body["data"]

    # Pass 3: Nested parts
    for part in parts:
        if "parts" in part:
            nested_data = extract_email_body(part)
            if nested_data:
                return nested_data

    return ""


def get_gmail_service():
    """Handles OAuth authentication using a loopback redirect."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            print(f"⚠️ Failed to parse token.json: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ Token refresh failed: {e}")
                creds = None

        if not creds:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(
                host="localhost",
                port=8090,
                authorization_prompt_message="Open this link in your browser to authorize: {url}",
                success_message="Authentication successful! You can return to myWealth Ingest.",
                open_browser=False,
            )

            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# def _convert_msg_to_preview(msg, RawEmailPayload_model):
#     """
#     Parses a single Gmail message into a lightweight preview object.
#     Strips raw HTML and avoids duplicate encrypted blobs in the staging buffer.
#     """
#     msg_id = msg.get("id")
#     payload = msg.get("payload", {})
#     headers_dict = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

#     raw_b64 = extract_email_body(payload)
#     raw_body_html = ""
#     if raw_b64:
#         try:
#             padded_b64 = raw_b64 + "=" * (-len(raw_b64) % 4)
#             raw_body_html = base64.urlsafe_b64decode(padded_b64).decode(
#                 "utf-8", errors="ignore"
#             )
#         except Exception as e:
#             print(f"⚠️ Base64 decode error for msg {msg_id}: {e}")

#     # Extract plain text
#     clean_body_text = (
#         clean_html_to_text(raw_body_html) if "<" in raw_body_html else raw_body_html
#     )

#     email_from = headers_dict.get("from") or "SIB Alerts <alerts@sib.co.in>"
#     sender = headers_dict.get("sender") or email_from
#     subject = headers_dict.get("subject") or "Debit/Credit Alert From SIB"
#     raw_email_date = headers_dict.get("date") or ""
#     parsed_email_date = safe_parse_datetime(raw_email_date)

#     parsed_data = parse_bank_email_body(
#         clean_body_text or raw_body_html, sender=email_from
#     )

#     txn_fingerprint = parsed_data.get(
#         "txn_fingerprint"
#     ) or generate_transaction_fingerprint(parsed_data)
#     parsed_data["txn_fingerprint"] = txn_fingerprint
#     parsed_data["source"] = "GMAIL_API"

#     raw_bank = parsed_data.get("bank_name") or "UNKNOWN BANK"
#     account_last4 = parsed_data.get("account_last4") or "0060"
#     amount = str(parsed_data.get("amount") or "0.00")
#     upi_ref = str(parsed_data.get("upi_ref") or txn_fingerprint)
#     date_str = (
#         parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
#         if parsed_email_date
#         else "NO_DATE"
#     )

#     hash_components = [
#         str(raw_bank),
#         str(account_last4),
#         str(amount),
#         str(date_str),
#         str(upi_ref),
#         str(clean_body_text).strip(),
#     ]
#     payload_hash = generate_payload_hash("_".join(hash_components))

#     # Deduplicate against MySQL Database
#     is_duplicate = False
#     if (
#         txn_fingerprint
#         and RawEmailPayload_model.objects.filter(
#             txn_fingerprint=txn_fingerprint
#         ).exists()
#     ):
#         is_duplicate = True
#     elif (
#         payload_hash
#         and RawEmailPayload_model.objects.filter(payload_hash=payload_hash).exists()
#     ):
#         is_duplicate = True

#     parsed_data["is_duplicate"] = is_duplicate

#     # Compact staging dictionary
#     return {
#         "id": msg_id,
#         "source": "GMAIL_API",
#         "status": "DUPLICATE" if is_duplicate else "PREVIEW_ONLY",
#         "committed": is_duplicate,
#         "is_duplicate": is_duplicate,
#         "parsed_transaction": parsed_data,
#         "payload_hash": payload_hash,
#         "raw_payload": {
#             "source": "GMAIL_API",
#             "sender": sender,
#             "email_from": email_from,
#             "email_date": date_str,
#             "subject": subject,
#             "decrypted_body": clean_body_text[:1000] if clean_body_text else "",
#             "headers_json": {
#                 "message_id": msg_id,
#                 "parsed_summary": {
#                     "bank": parsed_data.get("bank_name"),
#                     "account": parsed_data.get("account_last4"),
#                     "amount": str(parsed_data.get("amount") or "0.00"),
#                     "balance": (
#                         str(parsed_data.get("balance"))
#                         if parsed_data.get("balance")
#                         else None
#                     ),
#                     "upi_ref": parsed_data.get("upi_ref"),
#                     "full_narration": parsed_data.get("full_narration"),
#                 },
#             },
#         },
#     }


# def _convert_msg_to_preview(msg, RawEmailPayload_model):
#     """
#     Parses a single Gmail message into a lightweight preview object.
#     Drops non-financial/empty alerts where Amount and Balance are both missing or zero.
#     """
#     msg_id = msg.get("id")
#     payload = msg.get("payload", {})
#     headers_dict = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

#     raw_b64 = extract_email_body(payload)
#     raw_body_html = ""
#     if raw_b64:
#         try:
#             padded_b64 = raw_b64 + "=" * (-len(raw_b64) % 4)
#             raw_body_html = base64.urlsafe_b64decode(padded_b64).decode(
#                 "utf-8", errors="ignore"
#             )
#         except Exception as e:
#             print(f"⚠️ Base64 decode error for msg {msg_id}: {e}")

#     # Extract plain text
#     clean_body_text = (
#         clean_html_to_text(raw_body_html) if "<" in raw_body_html else raw_body_html
#     )

#     email_from = headers_dict.get("from") or "SIB Alerts <alerts@sib.co.in>"
#     sender = headers_dict.get("sender") or email_from
#     subject = headers_dict.get("subject") or "Debit/Credit Alert From SIB"
#     raw_email_date = headers_dict.get("date") or ""
#     parsed_email_date = safe_parse_datetime(raw_email_date)

#     parsed_data = parse_bank_email_body(
#         clean_body_text or raw_body_html, sender=email_from
#     )

#     # ------------------------------------------------------------------
#     # 🎯 DROP INVALID / ZERO-VALUE NON-FINANCIAL EMAILS
#     # ------------------------------------------------------------------
#     raw_amount = parsed_data.get("amount")
#     raw_balance = parsed_data.get("balance")

#     try:
#         parsed_amount_val = float(raw_amount) if raw_amount is not None else 0.0
#     except (ValueError, TypeError):
#         parsed_amount_val = 0.0

#     try:
#         parsed_balance_val = float(raw_balance) if raw_balance is not None else 0.0
#     except (ValueError, TypeError):
#         parsed_balance_val = 0.0

#     # If Dr/Cr amount is 0/empty AND running balance is 0/empty, ignore this email
#     if parsed_amount_val <= 0.0 and parsed_balance_val <= 0.0:
#         return None

#     # ------------------------------------------------------------------

#     txn_fingerprint = parsed_data.get(
#         "txn_fingerprint"
#     ) or generate_transaction_fingerprint(parsed_data)
#     parsed_data["txn_fingerprint"] = txn_fingerprint
#     parsed_data["source"] = "GMAIL_API"

#     raw_bank = parsed_data.get("bank_name") or "UNKNOWN BANK"
#     account_last4 = parsed_data.get("account_last4") or "0060"
#     amount = f"{parsed_amount_val:.2f}"
#     upi_ref = str(parsed_data.get("upi_ref") or txn_fingerprint)
#     date_str = (
#         parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
#         if parsed_email_date
#         else "NO_DATE"
#     )

#     hash_components = [
#         str(raw_bank),
#         str(account_last4),
#         str(amount),
#         str(date_str),
#         str(upi_ref),
#         str(clean_body_text).strip(),
#     ]
#     payload_hash = generate_payload_hash("_".join(hash_components))

#     # Deduplicate against MySQL Database
#     is_duplicate = False
#     if (
#         txn_fingerprint
#         and RawEmailPayload_model.objects.filter(
#             txn_fingerprint=txn_fingerprint
#         ).exists()
#     ):
#         is_duplicate = True
#     elif (
#         payload_hash
#         and RawEmailPayload_model.objects.filter(payload_hash=payload_hash).exists()
#     ):
#         is_duplicate = True

#     parsed_data["is_duplicate"] = is_duplicate

#     return {
#         "id": msg_id,
#         "source": "GMAIL_API",
#         "status": "DUPLICATE" if is_duplicate else "PREVIEW_ONLY",
#         "committed": is_duplicate,
#         "is_duplicate": is_duplicate,
#         "parsed_transaction": parsed_data,
#         "payload_hash": payload_hash,
#         "raw_payload": {
#             "source": "GMAIL_API",
#             "sender": sender,
#             "email_from": email_from,
#             "email_date": date_str,
#             "subject": subject,
#             "decrypted_body": clean_body_text[:1000] if clean_body_text else "",
#             "headers_json": {
#                 "message_id": msg_id,
#                 "parsed_summary": {
#                     "bank": parsed_data.get("bank_name"),
#                     "account": parsed_data.get("account_last4"),
#                     "amount": amount,
#                     "balance": (
#                         f"{parsed_balance_val:.2f}"
#                         if parsed_balance_val > 0.0
#                         else None
#                     ),
#                     "upi_ref": parsed_data.get("upi_ref"),
#                     "full_narration": parsed_data.get("full_narration"),
#                 },
#             },
#         },
#     }


def _convert_msg_to_preview(msg, RawEmailPayload_model):
    """
    Parses a single Gmail message into a lightweight preview object.
    Preserves raw body text for high-accuracy regex matching without truncating tokens.
    """
    msg_id = msg.get("id")
    payload = msg.get("payload", {})
    headers_dict = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    raw_b64 = extract_email_body(payload)
    raw_body_html = ""
    if raw_b64:
        try:
            padded_b64 = raw_b64 + "=" * (-len(raw_b64) % 4)
            raw_body_html = base64.urlsafe_b64decode(padded_b64).decode(
                "utf-8", errors="ignore"
            )
        except Exception as e:
            print(f"⚠️ Base64 decode error for msg {msg_id}: {e}")

    email_from = headers_dict.get("from") or "SIB Alerts <alerts@sib.co.in>"
    sender = headers_dict.get("sender") or email_from
    subject = headers_dict.get("subject") or "Debit/Credit Alert From SIB"
    raw_email_date = headers_dict.get("date") or ""
    parsed_email_date = safe_parse_datetime(raw_email_date)

    # Pass the decoded content directly to the parser
    parsed_data = parse_bank_email_body(raw_body_html, sender=email_from)

    raw_amount = parsed_data.get("amount")
    raw_balance = parsed_data.get("balance")

    try:
        parsed_amount_val = float(raw_amount) if raw_amount is not None else 0.0
    except (ValueError, TypeError):
        parsed_amount_val = 0.0

    try:
        parsed_balance_val = float(raw_balance) if raw_balance is not None else 0.0
    except (ValueError, TypeError):
        parsed_balance_val = 0.0

    # Only drop if the email is genuine noise (e.g. AMB notice, OTPs) or completely empty
    if parsed_data.get("is_noise"):
        return None

    txn_fingerprint = parsed_data.get(
        "txn_fingerprint"
    ) or generate_transaction_fingerprint(parsed_data)
    parsed_data["txn_fingerprint"] = txn_fingerprint
    parsed_data["source"] = "GMAIL_API"

    raw_bank = parsed_data.get("bank_name") or "SOUTH INDIAN BANK"
    account_last4 = parsed_data.get("account_last4")
    amount = f"{parsed_amount_val:.2f}" if parsed_amount_val > 0 else None
    upi_ref = parsed_data.get("upi_ref")
    date_str = (
        parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
        if parsed_email_date
        else "NO_DATE"
    )

    clean_snippet = clean_html_to_text(raw_body_html)

    hash_components = [
        str(raw_bank),
        str(account_last4 or "UNKNOWN_ACC"),
        str(amount or "0.00"),
        str(date_str),
        str(upi_ref or txn_fingerprint),
        str(clean_snippet)[:300],
    ]
    payload_hash = generate_payload_hash("_".join(hash_components))

    # Fast duplicate check against DB
    is_duplicate = False
    if RawEmailPayload_model.objects.filter(headers_json__message_id=msg_id).exists():
        is_duplicate = True
    elif (
        upi_ref
        and amount
        and RawEmailPayload_model.objects.filter(
            upi_ref=upi_ref, amount=amount
        ).exists()
    ):
        is_duplicate = True

    parsed_data["is_duplicate"] = is_duplicate

    return {
        "id": msg_id,
        "source": "GMAIL_API",
        "status": "DUPLICATE" if is_duplicate else "PREVIEW_ONLY",
        "committed": is_duplicate,
        "is_duplicate": is_duplicate,
        "parsed_transaction": parsed_data,
        "payload_hash": payload_hash,
        "raw_payload": {
            "source": "GMAIL_API",
            "sender": sender,
            "email_from": email_from,
            "email_date": date_str,
            "subject": subject,
            "decrypted_body": clean_snippet[:1000],
            "headers_json": {
                "message_id": msg_id,
                "parsed_summary": {
                    "bank": parsed_data.get("bank_name"),
                    "account": parsed_data.get("account_last4"),
                    "amount": amount,
                    "balance": (
                        f"{parsed_balance_val:.2f}"
                        if parsed_balance_val > 0.0
                        else None
                    ),
                    "upi_ref": upi_ref,
                    "full_narration": parsed_data.get("full_narration"),
                },
            },
        },
    }


def run_gmail_api_ingest(search_query=None):
    from tracker.models.emailModels import RawEmailPayload  # Lazy import

    service = get_gmail_service()
    query = search_query or "label:bankalerts"
    print(f"\n⚡ Executing Gmail API fetch query: '{query}'")

    # Step 1: Paginate to collect message references
    all_message_refs = []
    page_token = None

    while True:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=500,
                pageToken=page_token,
            )
            .execute()
        )

        messages = results.get("messages", [])
        if messages:
            all_message_refs.extend(messages)

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    print(f"📦 Found {len(all_message_refs)} total message references matching query.")

    if not all_message_refs:
        return []

    all_previews = []

    # Step 2: Rate-limit-aware chunk downloading with streaming disk flush
    def execute_and_stream_chunks(msg_refs_list, chunk_size=25, delay_sec=0.4):
        retry_queue = []

        for i in range(0, len(msg_refs_list), chunk_size):
            chunk = msg_refs_list[i : i + chunk_size]
            chunk_messages = []

            def make_callback(retries_list, container):
                def batch_callback(request_id, response, exception):
                    if exception is not None:
                        if isinstance(
                            exception, HttpError
                        ) and exception.resp.status in [429, 403]:
                            retries_list.append(request_id)
                        else:
                            print(f"⚠️ Error fetching msg ID {request_id}: {exception}")
                    else:
                        container.append(response)

                return batch_callback

            batch = service.new_batch_http_request(
                callback=make_callback(retry_queue, chunk_messages)
            )

            for msg_ref in chunk:
                msg_id = msg_ref["id"] if isinstance(msg_ref, dict) else msg_ref
                batch.add(
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full"),
                    request_id=msg_id,
                )

            batch.execute()

            # Append parsed chunk to staging JSON
            if chunk_messages:
                # Filter out dropped / non-financial items
                chunk_previews = [
                    preview
                    for m in chunk_messages
                    if (preview := _convert_msg_to_preview(m, RawEmailPayload))
                    is not None
                ]

                if chunk_previews:
                    append_batch_to_staging_buffer(chunk_previews)
                    all_previews.extend(chunk_previews)
                    print(f"📥 Staged {len(all_previews)} valid financial alerts...")

            time.sleep(delay_sec)

        return retry_queue

    print("⏳ Starting batch downloading with real-time staging buffer flush...")
    retries = execute_and_stream_chunks(all_message_refs, chunk_size=25, delay_sec=0.4)

    # Step 3: Retry pass for throttled requests
    max_attempts = 3
    attempt = 1
    while retries and attempt <= max_attempts:
        backoff_time = attempt * 2
        print(
            f"🔄 Rate-limited on {len(retries)} items. Backing off for {backoff_time}s (Attempt {attempt}/{max_attempts})..."
        )
        time.sleep(backoff_time)
        retries = execute_and_stream_chunks(retries, chunk_size=10, delay_sec=0.8)
        attempt += 1

    print(
        f"✅ Successfully staged {len(all_previews)} / {len(all_message_refs)} messages."
    )
    return all_previews
