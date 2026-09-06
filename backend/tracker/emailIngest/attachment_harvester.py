# tracker/services/attachment_harvester.py
import base64
import os
import re
from datetime import date, datetime
from typing import Optional, Tuple
from django.conf import settings
from django.utils import timezone
from tracker.models.emailModels import DocumentInboxItem
from tracker.emailIngest.gmail_api import get_gmail_service
from tracker import constants
from tracker.models.models import (
    Account,
)


class AttachmentHarvesterService:
    INBOX_DIR = os.path.join(settings.MEDIA_ROOT, "documents", "inbox")
    COMPLETED_DIR = os.path.join(settings.MEDIA_ROOT, "documents", "completed")

    def __init__(self):
        os.makedirs(self.INBOX_DIR, exist_ok=True)
        os.makedirs(self.COMPLETED_DIR, exist_ok=True)
        self.service = get_gmail_service()

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

        # Narrow by bank name if model contains institution/bank field
        if bank_name:
            if hasattr(Account, "bank_name"):
                query = query.filter(bank_name__iexact=bank_name)
            elif hasattr(Account, "institution"):
                query = query.filter(institution__iexact=bank_name)

        # Search for account ending in candidate_hint (and stripped leading zeroes for short numbers)
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
        """
        Extracts statement date range (from_date, to_date).
        Scans subject first, then body text, then falls back to filename date.
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
        """Helper to extract clean text from Gmail payload parts, checking both

        plain text and HTML bodies.
        """
        snippet = payload.get("snippet", "")
        collected_text = [snippet]

        def _walk_parts(parts):
            for part in parts:
                mime = part.get("mimeType", "")
                data = part.get("body", {}).get("data")

                if data and mime in ("text/plain", "text/html"):
                    try:
                        raw_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
                        text = raw_bytes.decode("utf-8", errors="ignore")
                        # Strip HTML tags if HTML
                        if mime == "text/html":
                            text = re.sub(r"<[^>]+>", " ", text)
                        collected_text.append(text)
                    except Exception:
                        pass

                # Recursively inspect subparts (multipart/alternative, etc.)
                if "parts" in part:
                    _walk_parts(part["parts"])

        _walk_parts(payload.get("parts", []))
        return " ".join(collected_text)

    def harvest_bank_attachments(
        self, max_results: int = 25
    ) -> list[DocumentInboxItem]:
        """Scans Gmail for bank emails containing PDF attachments using configured constants."""
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
        harvested_records = []

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

            # Traverse payload parts to find PDF attachments
            parts = payload.get("parts", [])
            for part in parts:
                filename = part.get("filename", "")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")

                if attachment_id and filename.lower().endswith(".pdf"):
                    att_hash = DocumentInboxItem.generate_hash(attachment_id)

                    # Deduplication check
                    if DocumentInboxItem.objects.filter(
                        attachment_hash=att_hash
                    ).exists():
                        continue

                    bank_hint = self.detect_bank_name(sender, subject, filename)

                    # Account verification pipeline:
                    raw_candidate = self.extract_raw_account_candidate(
                        subject, filename, body_text
                    )
                    _, verified_hint = self.resolve_account_from_db(
                        raw_candidate, bank_name=bank_hint
                    )

                    start_date, end_date = self.extract_period_dates(
                        subject, filename, body_text
                    )

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

                    record = DocumentInboxItem.objects.create(
                        message_id=msg_id,
                        attachment_id=attachment_id,
                        attachment_hash=att_hash,
                        filename=filename,
                        file_path=disk_path,
                        file_size=len(file_data),
                        doc_type=doc_type,
                        status=DocumentInboxItem.ProcessingStatus.INBOX,
                        sender=sender,
                        subject=subject,
                        received_date=received_dt,
                        account_hint=verified_hint,
                        bank_name=bank_hint,
                        period_start=start_date,
                        period_end=end_date,
                    )
                    harvested_records.append(record)

        return harvested_records
