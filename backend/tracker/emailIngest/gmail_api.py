import base64
import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

# Ensure this scope matches the authorization request exactly
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

    # First pass: text/html
    for part in parts:
        mime_type = part.get("mimeType", "").lower()
        part_body = part.get("body", {})
        if mime_type == "text/html" and part_body.get("data"):
            return part_body["data"]

    # Second pass: text/plain
    for part in parts:
        mime_type = part.get("mimeType", "").lower()
        part_body = part.get("body", {})
        if mime_type == "text/plain" and part_body.get("data"):
            return part_body["data"]

    # Third pass: recurse into nested parts
    for part in parts:
        if "parts" in part:
            nested_data = extract_email_body(part)
            if nested_data:
                return nested_data

    return ""


def get_gmail_service():
    """Handles OAuth authentication using a valid loopback redirect."""
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

            # Uses standard localhost loopback redirect compliant with Google OAuth policies
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


# def get_gmail_service():
#     """Handles OAuth authentication cleanly in Docker/Headless environments."""
#     creds = None

#     if os.path.exists(TOKEN_PATH):
#         try:
#             creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
#         except Exception as e:
#             print(f"⚠️ Failed to parse token.json: {e}. Re-authenticating...")
#             creds = None

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             try:
#                 creds.refresh(Request())
#             except Exception as e:
#                 print(f"⚠️ Token refresh failed: {e}. Generating new token...")
#                 creds = None

#         if not creds:
#             if not os.path.exists(CREDENTIALS_PATH):
#                 raise FileNotFoundError(
#                     f"credentials.json not found at {CREDENTIALS_PATH}. Download it from Google Cloud Console."
#                 )

#             flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

#             # In Docker containers, host bind must allow external browser access or console fallback
#             try:
#                 creds = flow.run_local_server(
#                     host="0.0.0.0",
#                     port=8090,
#                     authorization_prompt_message="Please visit this URL to authorize Gmail Access: {url}",
#                     success_message="Authentication successful! You may close this window.",
#                     open_browser=False,
#                 )
#             except Exception:
#                 # Fallback to local server with automatic port assignment if 8090 is blocked
#                 creds = flow.run_local_server(port=0, open_browser=False)

#             with open(TOKEN_PATH, "w") as token_file:
#                 token_file.write(creds.to_json())

#     return build("gmail", "v1", credentials=creds)


def run_gmail_api_ingest(search_query=None):
    service = get_gmail_service()
    query = search_query or "label:bankalerts"
    print(f"\n⚡ Executing Gmail API fetch query: '{query}'")

    results = (
        service.users().messages().list(userId="me", q=query, maxResults=50).execute()
    )
    messages = results.get("messages", [])
    preview_items = []

    from tracker.emailIngest.parser import parse_bank_email_body
    from tracker.emailIngest.services import (
        encrypt_aes_payload,
        generate_payload_hash,
        safe_parse_datetime,
    )

    for msg_ref in messages:
        msg_id = msg_ref["id"]
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

        raw_b64 = extract_email_body(payload)
        decoded_body = ""
        if raw_b64:
            try:
                padded_b64 = raw_b64 + "=" * (-len(raw_b64) % 4)
                decoded_body = base64.urlsafe_b64decode(padded_b64).decode(
                    "utf-8", errors="ignore"
                )
            except Exception as e:
                print(f"⚠️ Base64 decode error for msg {msg_id}: {e}")

        email_from = headers.get("from", "")
        raw_email_date = headers.get("date", "")
        parsed_email_date = safe_parse_datetime(raw_email_date)
        subject = headers.get("subject", "")

        raw_payload = {
            "source": "GMAIL_API",
            "sender": email_from,
            "email_from": email_from,
            "email_date": (
                parsed_email_date.isoformat() if parsed_email_date else raw_email_date
            ),
            "subject": subject,
            "decrypted_body": decoded_body,
            "headers_json": {"message_id": msg_id},
        }

        encrypted_str = encrypt_aes_payload(raw_payload)
        payload_hash = generate_payload_hash(encrypted_str)
        parsed_data = parse_bank_email_body(decoded_body, sender=email_from)

        preview_items.append(
            {
                "status": "PREVIEW_ONLY",
                "committed": False,
                "parsed_transaction": parsed_data,
                "payload_hash": payload_hash,
                "raw_payload": raw_payload,
                "encrypted_payload": encrypted_str,
            }
        )

    return preview_items


# def run_gmail_api_ingest(search_query=None):
#     service = get_gmail_service()
#     query = search_query or "label:bankalerts"
#     print(f"\n⚡ Executing Gmail API fetch query: '{query}'")

#     results = (
#         service.users().messages().list(userId="me", q=query, maxResults=50).execute()
#     )
#     messages = results.get("messages", [])
#     preview_items = []

#     from tracker.models.emailModels import RawEmailPayload  # 👈 Added DB model import
#     from tracker.emailIngest.parser import parse_bank_email_body
#     from tracker.emailIngest.services import (
#         encrypt_aes_payload,
#         generate_payload_hash,
#         safe_parse_datetime,
#     )

#     for msg_ref in messages:
#         msg_id = msg_ref["id"]
#         msg = (
#             service.users()
#             .messages()
#             .get(userId="me", id=msg_id, format="full")
#             .execute()
#         )
#         payload = msg.get("payload", {})
#         headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

#         raw_b64 = extract_email_body(payload)
#         decoded_body = ""
#         if raw_b64:
#             try:
#                 padded_b64 = raw_b64 + "=" * (-len(raw_b64) % 4)
#                 decoded_body = base64.urlsafe_b64decode(padded_b64).decode(
#                     "utf-8", errors="ignore"
#                 )
#             except Exception as e:
#                 print(f"⚠️ Base64 decode error for msg {msg_id}: {e}")

#         email_from = headers.get("from", "")
#         raw_email_date = headers.get("date", "")
#         parsed_email_date = safe_parse_datetime(raw_email_date)
#         subject = headers.get("subject", "")

#         raw_payload = {
#             "source": "GMAIL_API",
#             "sender": email_from,
#             "email_from": email_from,
#             "email_date": (
#                 parsed_email_date.isoformat() if parsed_email_date else raw_email_date
#             ),
#             "subject": subject,
#             "decrypted_body": decoded_body,
#             "headers_json": {"message_id": msg_id},
#         }

#         encrypted_str = encrypt_aes_payload(raw_payload)
#         payload_hash = generate_payload_hash(encrypted_str)
#         parsed_data = parse_bank_email_body(decoded_body, sender=email_from)

#         # 🎯 Duplicate Detection against existing MySQL DB
#         txn_fingerprint = parsed_data.get("txn_fingerprint")
#         is_duplicate = False
#         if (
#             txn_fingerprint
#             and RawEmailPayload.objects.filter(txn_fingerprint=txn_fingerprint).exists()
#         ):
#             is_duplicate = True
#         elif (
#             payload_hash
#             and RawEmailPayload.objects.filter(payload_hash=payload_hash).exists()
#         ):
#             is_duplicate = True

#         parsed_data["is_duplicate"] = is_duplicate

#         preview_items.append(
#             {
#                 "id": payload_hash,  # Unique preview ID
#                 "status": "PREVIEW_ONLY",
#                 "committed": False,
#                 "is_duplicate": is_duplicate,
#                 "parsed_transaction": parsed_data,
#                 "payload_hash": payload_hash,
#                 "raw_payload": raw_payload,
#                 "encrypted_payload": encrypted_str,
#             }
#         )

#     return preview_items
