# tracker/services/attachment_harvester.py
import base64
import json
import os
import re
import uuid
from datetime import date, datetime
from typing import Optional, Tuple

from django.conf import settings
from django.utils import timezone

from tracker import constants
from tracker.emailIngest.gmail_api import get_gmail_service
from tracker.models.emailModels import DocumentInboxItem
from tracker.models.models import Account


class AttachmentHarvesterService:
    BASE_DOCS_DIR = (
        os.path.join(settings.MEDIA_ROOT, "documents")
        if settings.MEDIA_ROOT
        else os.path.join(settings.BASE_DIR, "documents")
    )
    INBOX_DIR = os.path.join(BASE_DOCS_DIR, "inbox")
    COMPLETED_DIR = os.path.join(BASE_DOCS_DIR, "completed")
    STAGING_FILE_PATH = os.path.join(BASE_DOCS_DIR, "staged_inbox.json")

    def __init__(self):
        os.makedirs(self.INBOX_DIR, exist_ok=True)
        os.makedirs(self.COMPLETED_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(self.STAGING_FILE_PATH), exist_ok=True)
        self.service = get_gmail_service()

    # ==========================================
    # JSON Staging Helpers
    # ==========================================
    def load_staged_manifest(self) -> list[dict]:
        """Loads items currently staged in the JSON manifest."""
        if not os.path.exists(self.STAGING_FILE_PATH):
            return []
        try:
            with open(self.STAGING_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def save_staged_manifest(self, data: list[dict]) -> None:
        """Saves updated records back to the JSON manifest."""
        with open(self.STAGING_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    # ==========================================
    # Document Inspection & Parsing Helpers
    # ==========================================
    def detect_doc_type(self, subject: str, body: str = "") -> str:
        text = f"{subject} {body}".lower()
        if any(term in text for term in constants.TERM_DEPOSIT_KEYWORDS):
            return DocumentInboxItem.DocType.TERM_DEPOSIT
        if any(term in text for term in constants.STATEMENT_KEYWORDS):
            return DocumentInboxItem.DocType.STATEMENT
        return DocumentInboxItem.DocType.UNKNOWN

    def detect_bank_name(
        self, sender: str, subject: str, filename: str
    ) -> Optional[str]:
        context = f"{sender} {subject} {filename}".lower()
        for bank_name, signature in constants.BANK_INBOX_SIGNATURES.items():
            if any(s in context for s in signature["senders"]) or any(
                k in context for k in signature["keywords"]
            ):
                return bank_name
        return None

    def extract_raw_account_candidate(
        self, subject: str, filename: str, body: str = ""
    ) -> Optional[str]:
        """Scans subject, filename, and body (in order of reliability) for account candidate digits."""
        # Priority 1: Check subject
        for pattern in constants.ACCOUNT_HINT_PATTERNS:
            match = pattern.search(subject)
            if match:
                raw = match.group(1)
                return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

        # Priority 2: Check body snippet
        if body:
            for pattern in constants.ACCOUNT_HINT_PATTERNS:
                match = pattern.search(body)
                if match:
                    raw = match.group(1)
                    return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

        # Priority 3: Check filename
        for pattern in constants.ACCOUNT_HINT_PATTERNS:
            match = pattern.search(filename)
            if match:
                raw = match.group(1)
                return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

        return None

    def resolve_account_from_db(
        self, candidate_hint: Optional[str], bank_name: Optional[str] = None
    ) -> Tuple[Optional[Account], str]:
        """Validates candidate digits against active Account records in the database.

        Returns (Account instance or None, "XXXX" or "UNRECOGNIZED").
        """
        if not candidate_hint:
            return None, "UNRECOGNIZED"

        query = Account.objects.all()

        if bank_name:
            if hasattr(Account, "bank_name"):
                query = query.filter(bank_name__iexact=bank_name)
            elif hasattr(Account, "institution"):
                query = query.filter(institution__iexact=bank_name)

        clean_hint = candidate_hint.lstrip("0") or candidate_hint
        account = (
            query.filter(account_number__endswith=candidate_hint).first()
            or query.filter(account_number__endswith=clean_hint).first()
        )

        if account:
            verified_last4 = str(account.account_number)[-4:].zfill(4)
            return account, verified_last4

        return None, "UNRECOGNIZED"

    def extract_period_dates(
        self, subject: str, filename: str, body: str = ""
    ) -> Tuple[Optional[date], Optional[date]]:
        """Extracts statement date range (from_date, to_date).

        Scans subject and body text first, then falls back to filename date.
        """
        context = f"{subject} {body}"
        subj_match = constants.PERIOD_DATE_PATTERN.search(context)
        if subj_match:
            d1_raw, d2_raw = subj_match.group(1), subj_match.group(2)
            d1_clean = d1_raw.replace("/", "-")
            d2_clean = d2_raw.replace("/", "-")
            try:
                dt_start = datetime.strptime(d1_clean, "%d-%m-%Y").date()
                dt_end = datetime.strptime(d2_clean, "%d-%m-%Y").date()
                return dt_start, dt_end
            except ValueError:
                pass

        # Fallback: SIB filename format (RET_OG..._DDMMYYYY.pdf)
        fn_match = constants.SIB_FILENAME_DATE_PATTERN.search(filename)
        if fn_match:
            day, month, year = fn_match.groups()
            try:
                dt_end = datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y").date()
                return None, dt_end
            except ValueError:
                pass

        return None, None

    def _extract_body_snippet(self, payload: dict) -> str:
        """Recursively extracts clean text from Gmail payload parts (plain text & HTML)."""
        snippet = payload.get("snippet", "")
        collected_text = [snippet]

        def _walk_parts(parts):
            for part in parts:
                mime = part.get("mimeType", "").lower()
                data = part.get("body", {}).get("data")

                if data and mime in ("text/plain", "text/html"):
                    try:
                        raw_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
                        text = raw_bytes.decode("utf-8", errors="ignore")
                        if mime == "text/html":
                            text = re.sub(r"<[^>]+>", " ", text)
                        clean_text = text.replace("&nbsp;", " ").replace("\xa0", " ")
                        clean_text = re.sub(r"\s+", " ", clean_text)
                        collected_text.append(clean_text)
                    except Exception:
                        pass

                if "parts" in part:
                    _walk_parts(part["parts"])

        _walk_parts(payload.get("parts", []))
        return " ".join(collected_text)

    # ==========================================
    # Staging Harvester Core
    # ==========================================
    def harvest_bank_attachments(self, max_results: int = 25) -> list[dict]:
        """Scans Gmail for bank emails containing PDF attachments and stages

        them into documents/staged_inbox.json without saving to the DB.
        """
        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                q=constants.GMAIL_INBOX_HARVEST_QUERY,
                maxResults=max_results,
            )
            .execute()
        )
        messages = results.get("messages", [])

        manifest = self.load_staged_manifest()
        staged_hashes = {item.get("attachment_hash") for item in manifest}
        db_hashes = set(
            DocumentInboxItem.objects.values_list("attachment_hash", flat=True)
        )

        newly_staged_items = []

        for msg_summary in messages:
            msg_id = msg_summary["id"]
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            payload = msg.get("payload", {})
            headers = {
                h["name"].lower(): h["value"] for h in payload.get("headers", [])
            }

            subject = headers.get("subject", "No Subject")
            sender = headers.get("from", "Unknown")
            body_text = self._extract_body_snippet(payload)

            internal_date_ms = int(msg.get("internalDate", 0))
            received_dt = (
                timezone.make_aware(datetime.fromtimestamp(internal_date_ms / 1000.0))
                if internal_date_ms
                else timezone.now()
            )

            doc_type = self.detect_doc_type(subject, body_text)

            parts = payload.get("parts", [])
            for part in parts:
                filename = part.get("filename", "")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")

                if attachment_id and filename.lower().endswith(".pdf"):
                    att_hash = DocumentInboxItem.generate_hash(attachment_id)

                    # Deduplication check (skip if committed to DB or already in staged JSON)
                    if att_hash in db_hashes or att_hash in staged_hashes:
                        continue

                    bank_hint = self.detect_bank_name(sender, subject, filename)

                    raw_candidate = self.extract_raw_account_candidate(
                        subject, filename, body_text
                    )
                    _, verified_hint = self.resolve_account_from_db(
                        raw_candidate, bank_name=bank_hint
                    )

                    start_date, end_date = self.extract_period_dates(
                        subject, filename, body_text
                    )

                    # Download PDF and save physically to disk
                    attachment = (
                        self.service.users()
                        .messages()
                        .attachments()
                        .get(userId="me", messageId=msg_id, id=attachment_id)
                        .execute()
                    )

                    file_data = base64.urlsafe_b64decode(
                        attachment["data"].encode("UTF-8")
                    )
                    sanitized_name = f"{msg_id}_{filename}"
                    disk_path = os.path.join(self.INBOX_DIR, sanitized_name)

                    with open(disk_path, "wb") as f:
                        f.write(file_data)

                    stage_entry = {
                        "stage_id": str(uuid.uuid4()),
                        "message_id": msg_id,
                        "attachment_id": attachment_id,
                        "attachment_hash": att_hash,
                        "filename": filename,
                        "file_path": disk_path,
                        "file_size": len(file_data),
                        "doc_type": doc_type,
                        "status": DocumentInboxItem.ProcessingStatus.INBOX,
                        "sender": sender,
                        "subject": subject,
                        "received_date": received_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "account_hint": verified_hint,
                        "bank_name": bank_hint,
                        "period_start": (
                            start_date.strftime("%Y-%m-%d") if start_date else None
                        ),
                        "period_end": (
                            end_date.strftime("%Y-%m-%d") if end_date else None
                        ),
                        "selected": True,
                        "created_at": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    manifest.append(stage_entry)
                    staged_hashes.add(att_hash)
                    newly_staged_items.append(stage_entry)

        self.save_staged_manifest(manifest)
        return newly_staged_items

    # ==========================================
    # Commit Staged Items to Database Table
    # ==========================================
    def commit_staged_items(
        self, selected_stage_ids: list[str], overrides: Optional[dict] = None
    ) -> list[DocumentInboxItem]:
        """Commits selected staged items from JSON into the database table."""
        overrides = overrides or {}
        manifest = self.load_staged_manifest()
        selected_set = set(selected_stage_ids)

        committed_records = []
        remaining_manifest = []

        for item in manifest:
            stage_id = item.get("stage_id")
            if stage_id in selected_set:
                user_override = overrides.get(stage_id, {})
                acc_hint = user_override.get("account_hint", item.get("account_hint"))
                bank_name = user_override.get("bank_name", item.get("bank_name"))
                doc_type = user_override.get("doc_type", item.get("doc_type"))

                rec_dt = (
                    datetime.strptime(item["received_date"], "%Y-%m-%d %H:%M:%S")
                    if item.get("received_date")
                    else timezone.now()
                )
                rec_dt = (
                    timezone.make_aware(rec_dt) if timezone.is_naive(rec_dt) else rec_dt
                )

                p_start = (
                    datetime.strptime(item["period_start"], "%Y-%m-%d").date()
                    if item.get("period_start")
                    else None
                )
                p_end = (
                    datetime.strptime(item["period_end"], "%Y-%m-%d").date()
                    if item.get("period_end")
                    else None
                )

                record = DocumentInboxItem.objects.create(
                    message_id=item.get("message_id"),
                    attachment_id=item.get("attachment_id"),
                    attachment_hash=item.get("attachment_hash"),
                    filename=item["filename"],
                    file_path=item["file_path"],
                    file_size=item["file_size"],
                    doc_type=doc_type,
                    status=DocumentInboxItem.ProcessingStatus.INBOX,
                    sender=item.get("sender", ""),
                    subject=item.get("subject", ""),
                    received_date=rec_dt,
                    account_hint=acc_hint,
                    bank_name=bank_name,
                    period_start=p_start,
                    period_end=p_end,
                )
                committed_records.append(record)
            else:
                remaining_manifest.append(item)

        self.save_staged_manifest(remaining_manifest)
        return committed_records
