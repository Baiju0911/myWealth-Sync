# tracker/emailingest/attachment_harvester.py
import base64
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta
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
        # Lazy initialize service so manifest reads & commits do not trigger OAuth
        self._service = None

    @property
    def service(self):
        """Lazy-load Gmail service only when network calls are required."""
        if self._service is None:
            self._service = get_gmail_service()
        return self._service

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
        """Scans subject, filename, and body for account candidate digits."""
        for pattern in constants.ACCOUNT_HINT_PATTERNS:
            match = pattern.search(subject)
            if match:
                raw = match.group(1)
                return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

        if body:
            for pattern in constants.ACCOUNT_HINT_PATTERNS:
                match = pattern.search(body)
                if match:
                    raw = match.group(1)
                    return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

        for pattern in constants.ACCOUNT_HINT_PATTERNS:
            match = pattern.search(filename)
            if match:
                raw = match.group(1)
                return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

        return None

    def resolve_account_from_db(
        self, candidate_hint: Optional[str], bank_name: Optional[str] = None
    ) -> Tuple[Optional[Account], str]:
        """Validates candidate digits against active Account records in the database."""
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
        """Extracts statement date range (from_date, to_date)."""
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

        fn_match = constants.SIB_FILENAME_DATE_PATTERN.search(filename)
        if fn_match:
            day, month, year = fn_match.groups()
            try:
                dt_end = datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y").date()
                return None, dt_end
            except ValueError:
                pass

        return None, None

    # def _extract_body_snippet(self, payload: dict) -> str:
    #     """Recursively extracts clean text from Gmail payload parts (plain text & HTML)."""
    #     snippet = payload.get("snippet", "")
    #     collected_text = [snippet]

    #     def _walk_parts(parts):
    #         for part in parts:
    #             mime = part.get("mimeType", "").lower()
    #             data = part.get("body", {}).get("data")

    #             if data and mime in ("text/plain", "text/html"):
    #                 try:
    #                     raw_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
    #                     text = raw_bytes.decode("utf-8", errors="ignore")
    #                     if mime == "text/html":
    #                         text = re.sub(r"<[^>]+>", " ", text)
    #                     clean_text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    #                     clean_text = re.sub(r"\s+", " ", clean_text)
    #                     collected_text.append(clean_text)
    #                 except Exception:
    #                     pass

    #             if "parts" in part:
    #                 _walk_parts(part["parts"])

    #     _walk_parts(payload.get("parts", []))
    #     return " ".join(collected_text)

    def _extract_body_snippet(self, payload: dict, snippet: str = "") -> str:
        """Recursively extracts clean text from Gmail payload parts (plain text & HTML)."""
        if not isinstance(payload, dict):
            return snippet or ""

        collected_text = [snippet] if snippet else []

        def _walk_parts(parts):
            if not isinstance(parts, list):
                return
            for part in parts:
                if not isinstance(part, dict):
                    continue

                mime = part.get("mimeType", "").lower()
                body = part.get("body")
                data = body.get("data") if isinstance(body, dict) else None

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

                sub_parts = part.get("parts")
                if isinstance(sub_parts, list):
                    _walk_parts(sub_parts)

        parts = payload.get("parts", [])
        if isinstance(parts, list):
            _walk_parts(parts)

        return " ".join(collected_text)

    def _build_gmail_date_query(
        self,
        base_query: str,
        date_preset: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """Appends after: and before: filters to the Gmail query."""
        today = timezone.localdate()
        after_date = None
        before_date = None

        if date_preset == "THIS_WEEK":
            after_date = today - timedelta(days=today.weekday())
        elif date_preset == "THIS_MONTH":
            after_date = today.replace(day=1)
        elif date_preset == "LAST_MONTH":
            first_of_this_month = today.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            after_date = last_month_end.replace(day=1)
            before_date = first_of_this_month
        elif date_preset == "LAST_6_MONTHS":
            after_date = today - timedelta(days=180)
        elif date_preset == "CUSTOM" and start_date and end_date:
            try:
                after_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                before_date = datetime.strptime(
                    end_date, "%Y-%m-%d"
                ).date() + timedelta(days=1)
            except ValueError:
                pass

        query_parts = [base_query]
        if after_date:
            query_parts.append(f"after:{after_date.strftime('%Y/%m/%d')}")
        if before_date:
            query_parts.append(f"before:{before_date.strftime('%Y/%m/%d')}")

        return " ".join(query_parts)

    # ==========================================
    # Staging Harvester Core
    # ==========================================
    def harvest_bank_attachments(
        self,
        max_results: int = 50,
        date_preset: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Scans Gmail with date ranges, detects existing files in DB/manifest,
        and labels duplicates instead of dropping them.
        """
        search_query = self._build_gmail_date_query(
            constants.GMAIL_INBOX_HARVEST_QUERY,
            date_preset=date_preset,
            start_date=start_date,
            end_date=end_date,
        )

        # Uses self.service here on demand
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=search_query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])

        raw_manifest = self.load_staged_manifest()
        manifest = (
            [item for item in raw_manifest if isinstance(item, dict)]
            if isinstance(raw_manifest, list)
            else []
        )
        manifest_map = {
            item.get("stage_id"): item for item in manifest if item.get("stage_id")
        }

        # Cache existing committed DB identifiers
        committed_hashes = set(
            DocumentInboxItem.objects.exclude(attachment_hash__isnull=True)
            .exclude(attachment_hash="")
            .values_list("attachment_hash", flat=True)
        )
        committed_msg_files = set(
            DocumentInboxItem.objects.values_list("message_id", "filename")
        )

        staged_hashes = {
            item.get("attachment_hash")
            for item in manifest
            if item.get("attachment_hash")
        }
        staged_msg_files = {
            (item.get("message_id"), item.get("filename"))
            for item in manifest
            if item.get("message_id") and item.get("filename")
        }

        # for msg_summary in messages:
        #     msg_id = msg_summary["id"]
        #     msg = (
        #         self.service.users()
        #         .messages()
        #         .get(userId="me", id=msg_id, format="full")
        #         .execute()
        #     )

        #     payload = msg.get("payload", {})
        #     headers = {
        #         h["name"].lower(): h["value"] for h in payload.get("headers", [])
        #     }

        #     subject = headers.get("subject", "No Subject")
        #     sender = headers.get("from", "Unknown")
        #     body_text = self._extract_body_snippet(payload)

        #     internal_date_ms = int(msg.get("internalDate", 0))
        #     received_dt = (
        #         timezone.make_aware(datetime.fromtimestamp(internal_date_ms / 1000.0))
        #         if internal_date_ms
        #         else timezone.now()
        #     )

        #     doc_type = self.detect_doc_type(subject, body_text)
        #     parts = payload.get("parts", [])

        #     for part in parts:
        #         filename = part.get("filename", "")
        #         body = part.get("body", {})
        #         attachment_id = body.get("attachmentId")

        #         if attachment_id and filename.lower().endswith(".pdf"):
        for msg_summary in messages:
            if not isinstance(msg_summary, dict) or "id" not in msg_summary:
                continue
            msg_id = msg_summary["id"]
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            if not isinstance(msg, dict):
                continue

            payload = msg.get("payload", {})
            if not isinstance(payload, dict):
                continue

            raw_headers = payload.get("headers", [])
            headers = {}
            if isinstance(raw_headers, list):
                headers = {
                    h.get("name", "").lower(): h.get("value", "")
                    for h in raw_headers
                    if isinstance(h, dict)
                }

            subject = headers.get("subject", "No Subject")
            sender = headers.get("from", "Unknown")
            raw_snippet = msg.get("snippet", "")
            body_text = self._extract_body_snippet(payload, snippet=raw_snippet)

            internal_date_ms = int(msg.get("internalDate", 0))
            received_dt = (
                timezone.make_aware(datetime.fromtimestamp(internal_date_ms / 1000.0))
                if internal_date_ms
                else timezone.now()
            )

            doc_type = self.detect_doc_type(subject, body_text)
            parts = payload.get("parts", [])
            if not isinstance(parts, list):
                parts = []

            # Flatten or recursively collect all attachment parts
            def _collect_attachment_parts(parts_list):
                found = []
                for p in parts_list:
                    if isinstance(p, dict):
                        found.append(p)
                        sub = p.get("parts")
                        if isinstance(sub, list):
                            found.extend(_collect_attachment_parts(sub))
                return found

            all_parts = _collect_attachment_parts(parts)

            for part in all_parts:
                filename = part.get("filename", "")
                body = part.get("body", {})
                if not isinstance(body, dict):
                    continue
                attachment_id = body.get("attachmentId")

                if attachment_id and filename.lower().endswith(".pdf"):
                    sanitized_name = f"{msg_id}_{filename}"
                    disk_path = os.path.join(self.INBOX_DIR, sanitized_name)

                    # Read from disk if present, otherwise download
                    if os.path.exists(disk_path):
                        with open(disk_path, "rb") as f:
                            file_data = f.read()
                    else:
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
                        with open(disk_path, "wb") as f:
                            f.write(file_data)

                    content_hash = hashlib.sha256(file_data).hexdigest()

                    # Deduplication check against DB and Manifest
                    is_in_db = (
                        content_hash in committed_hashes
                        or (msg_id, filename) in committed_msg_files
                    )
                    is_in_manifest = (
                        content_hash in staged_hashes
                        or (msg_id, filename) in staged_msg_files
                    )

                    is_duplicate = is_in_db or is_in_manifest
                    stage_status = "DUPLICATE" if is_duplicate else "STAGED"

                    bank_hint = self.detect_bank_name(sender, subject, filename)
                    raw_candidate = self.extract_raw_account_candidate(
                        subject, filename, body_text
                    )
                    _, verified_hint = self.resolve_account_from_db(
                        raw_candidate, bank_name=bank_hint
                    )
                    start_date_obj, end_date_obj = self.extract_period_dates(
                        subject, filename, body_text
                    )

                    # Find existing stage entry or create a new one
                    stage_id = str(uuid.uuid4())
                    for existing_item in manifest:
                        if existing_item.get("attachment_hash") == content_hash or (
                            existing_item.get("message_id") == msg_id
                            and existing_item.get("filename") == filename
                        ):
                            stage_id = existing_item.get("stage_id", stage_id)
                            break

                    entry = {
                        "stage_id": stage_id,
                        "message_id": msg_id,
                        "attachment_id": attachment_id,
                        "attachment_hash": content_hash,
                        "filename": filename,
                        "file_path": disk_path,
                        "file_size": len(file_data),
                        "doc_type": doc_type,
                        "status": stage_status,
                        "is_duplicate": is_duplicate,
                        "sender": sender,
                        "subject": subject,
                        "received_date": received_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "account_hint": verified_hint,
                        "bank_name": bank_hint,
                        "period_start": (
                            start_date_obj.strftime("%Y-%m-%d")
                            if start_date_obj
                            else None
                        ),
                        "period_end": (
                            end_date_obj.strftime("%Y-%m-%d") if end_date_obj else None
                        ),
                        "selected": not is_duplicate,
                        "created_at": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    manifest_map[stage_id] = entry
                    staged_hashes.add(content_hash)
                    staged_msg_files.add((msg_id, filename))

        updated_manifest = list(manifest_map.values())
        self.save_staged_manifest(updated_manifest)
        return updated_manifest

    # ==========================================
    # Commit Staged Items to Database Table
    # ==========================================
    def commit_staged_items(
        self, selected_stage_ids: list[str], overrides: Optional[dict] = None
    ) -> list[DocumentInboxItem]:
        """Commits selected staged items from JSON into DocumentInboxItem DB records
        and removes them from staged_inbox.json.
        """
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

                record, _ = DocumentInboxItem.objects.update_or_create(
                    message_id=item.get("message_id"),
                    filename=item["filename"],
                    defaults={
                        "attachment_id": item.get("attachment_id"),
                        "attachment_hash": item.get("attachment_hash"),
                        "file_path": item["file_path"],
                        "file_size": item["file_size"],
                        "doc_type": doc_type,
                        "status": DocumentInboxItem.ProcessingStatus.INBOX,
                        "sender": item.get("sender", ""),
                        "subject": item.get("subject", ""),
                        "received_date": rec_dt,
                        "account_hint": acc_hint,
                        "bank_name": bank_name,
                        "period_start": p_start,
                        "period_end": p_end,
                    },
                )
                committed_records.append(record)
            else:
                remaining_manifest.append(item)

        self.save_staged_manifest(remaining_manifest)
        return committed_records


# # tracker/services/attachment_harvester.py
# import base64
# import hashlib
# import json
# import os
# import re
# import uuid
# from datetime import date, datetime, timedelta
# from typing import Optional, Tuple

# from django.conf import settings
# from django.utils import timezone

# from tracker import constants
# from tracker.emailIngest.gmail_api import get_gmail_service
# from tracker.models.emailModels import DocumentInboxItem
# from tracker.models.models import Account


# class AttachmentHarvesterService:
#     BASE_DOCS_DIR = (
#         os.path.join(settings.MEDIA_ROOT, "documents")
#         if settings.MEDIA_ROOT
#         else os.path.join(settings.BASE_DIR, "documents")
#     )
#     INBOX_DIR = os.path.join(BASE_DOCS_DIR, "inbox")
#     COMPLETED_DIR = os.path.join(BASE_DOCS_DIR, "completed")
#     STAGING_FILE_PATH = os.path.join(BASE_DOCS_DIR, "staged_inbox.json")

#     def __init__(self):
#         os.makedirs(self.INBOX_DIR, exist_ok=True)
#         os.makedirs(self.COMPLETED_DIR, exist_ok=True)
#         os.makedirs(os.path.dirname(self.STAGING_FILE_PATH), exist_ok=True)
#         self.service = get_gmail_service()

#     # ==========================================
#     # JSON Staging Helpers
#     # ==========================================
#     def load_staged_manifest(self) -> list[dict]:
#         """Loads items currently staged in the JSON manifest."""
#         if not os.path.exists(self.STAGING_FILE_PATH):
#             return []
#         try:
#             with open(self.STAGING_FILE_PATH, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         except (json.JSONDecodeError, OSError):
#             return []

#     def save_staged_manifest(self, data: list[dict]) -> None:
#         """Saves updated records back to the JSON manifest."""
#         with open(self.STAGING_FILE_PATH, "w", encoding="utf-8") as f:
#             json.dump(data, f, indent=2, default=str)

#     # ==========================================
#     # Document Inspection & Parsing Helpers
#     # ==========================================
#     def detect_doc_type(self, subject: str, body: str = "") -> str:
#         text = f"{subject} {body}".lower()
#         if any(term in text for term in constants.TERM_DEPOSIT_KEYWORDS):
#             return DocumentInboxItem.DocType.TERM_DEPOSIT
#         if any(term in text for term in constants.STATEMENT_KEYWORDS):
#             return DocumentInboxItem.DocType.STATEMENT
#         return DocumentInboxItem.DocType.UNKNOWN

#     def detect_bank_name(
#         self, sender: str, subject: str, filename: str
#     ) -> Optional[str]:
#         context = f"{sender} {subject} {filename}".lower()
#         for bank_name, signature in constants.BANK_INBOX_SIGNATURES.items():
#             if any(s in context for s in signature["senders"]) or any(
#                 k in context for k in signature["keywords"]
#             ):
#                 return bank_name
#         return None

#     def extract_raw_account_candidate(
#         self, subject: str, filename: str, body: str = ""
#     ) -> Optional[str]:
#         """Scans subject, filename, and body for account candidate digits."""
#         for pattern in constants.ACCOUNT_HINT_PATTERNS:
#             match = pattern.search(subject)
#             if match:
#                 raw = match.group(1)
#                 return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

#         if body:
#             for pattern in constants.ACCOUNT_HINT_PATTERNS:
#                 match = pattern.search(body)
#                 if match:
#                     raw = match.group(1)
#                     return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

#         for pattern in constants.ACCOUNT_HINT_PATTERNS:
#             match = pattern.search(filename)
#             if match:
#                 raw = match.group(1)
#                 return raw[-4:] if len(raw) >= 4 else raw.zfill(4)

#         return None

#     def resolve_account_from_db(
#         self, candidate_hint: Optional[str], bank_name: Optional[str] = None
#     ) -> Tuple[Optional[Account], str]:
#         """Validates candidate digits against active Account records in the database."""
#         if not candidate_hint:
#             return None, "UNRECOGNIZED"

#         query = Account.objects.all()

#         if bank_name:
#             if hasattr(Account, "bank_name"):
#                 query = query.filter(bank_name__iexact=bank_name)
#             elif hasattr(Account, "institution"):
#                 query = query.filter(institution__iexact=bank_name)

#         clean_hint = candidate_hint.lstrip("0") or candidate_hint
#         account = (
#             query.filter(account_number__endswith=candidate_hint).first()
#             or query.filter(account_number__endswith=clean_hint).first()
#         )

#         if account:
#             verified_last4 = str(account.account_number)[-4:].zfill(4)
#             return account, verified_last4

#         return None, "UNRECOGNIZED"

#     def extract_period_dates(
#         self, subject: str, filename: str, body: str = ""
#     ) -> Tuple[Optional[date], Optional[date]]:
#         """Extracts statement date range (from_date, to_date)."""
#         context = f"{subject} {body}"
#         subj_match = constants.PERIOD_DATE_PATTERN.search(context)
#         if subj_match:
#             d1_raw, d2_raw = subj_match.group(1), subj_match.group(2)
#             d1_clean = d1_raw.replace("/", "-")
#             d2_clean = d2_raw.replace("/", "-")
#             try:
#                 dt_start = datetime.strptime(d1_clean, "%d-%m-%Y").date()
#                 dt_end = datetime.strptime(d2_clean, "%d-%m-%Y").date()
#                 return dt_start, dt_end
#             except ValueError:
#                 pass

#         fn_match = constants.SIB_FILENAME_DATE_PATTERN.search(filename)
#         if fn_match:
#             day, month, year = fn_match.groups()
#             try:
#                 dt_end = datetime.strptime(f"{day}-{month}-{year}", "%d-%m-%Y").date()
#                 return None, dt_end
#             except ValueError:
#                 pass

#         return None, None

#     def _extract_body_snippet(self, payload: dict) -> str:
#         """Recursively extracts clean text from Gmail payload parts (plain text & HTML)."""
#         snippet = payload.get("snippet", "")
#         collected_text = [snippet]

#         def _walk_parts(parts):
#             for part in parts:
#                 mime = part.get("mimeType", "").lower()
#                 data = part.get("body", {}).get("data")

#                 if data and mime in ("text/plain", "text/html"):
#                     try:
#                         raw_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
#                         text = raw_bytes.decode("utf-8", errors="ignore")
#                         if mime == "text/html":
#                             text = re.sub(r"<[^>]+>", " ", text)
#                         clean_text = text.replace("&nbsp;", " ").replace("\xa0", " ")
#                         clean_text = re.sub(r"\s+", " ", clean_text)
#                         collected_text.append(clean_text)
#                     except Exception:
#                         pass

#                 if "parts" in part:
#                     _walk_parts(part["parts"])

#         _walk_parts(payload.get("parts", []))
#         return " ".join(collected_text)

#     def _build_gmail_date_query(
#         self,
#         base_query: str,
#         date_preset: Optional[str] = None,
#         start_date: Optional[str] = None,
#         end_date: Optional[str] = None,
#     ) -> str:
#         """Appends after: and before: filters to the Gmail query."""
#         today = timezone.localdate()
#         after_date = None
#         before_date = None

#         if date_preset == "THIS_WEEK":
#             after_date = today - timedelta(days=today.weekday())
#         elif date_preset == "THIS_MONTH":
#             after_date = today.replace(day=1)
#         elif date_preset == "LAST_MONTH":
#             first_of_this_month = today.replace(day=1)
#             last_month_end = first_of_this_month - timedelta(days=1)
#             after_date = last_month_end.replace(day=1)
#             before_date = first_of_this_month
#         elif date_preset == "LAST_6_MONTHS":
#             after_date = today - timedelta(days=180)
#         elif date_preset == "CUSTOM" and start_date and end_date:
#             try:
#                 after_date = datetime.strptime(start_date, "%Y-%m-%d").date()
#                 before_date = datetime.strptime(
#                     end_date, "%Y-%m-%d"
#                 ).date() + timedelta(days=1)
#             except ValueError:
#                 pass

#         query_parts = [base_query]
#         if after_date:
#             query_parts.append(f"after:{after_date.strftime('%Y/%m/%d')}")
#         if before_date:
#             query_parts.append(f"before:{before_date.strftime('%Y/%m/%d')}")

#         return " ".join(query_parts)

#     # ==========================================
#     # Staging Harvester Core
#     # ==========================================
#     def harvest_bank_attachments(
#         self,
#         max_results: int = 50,
#         date_preset: Optional[str] = None,
#         start_date: Optional[str] = None,
#         end_date: Optional[str] = None,
#     ) -> list[dict]:
#         """Scans Gmail with date ranges, detects existing files in DB/manifest,
#         and labels duplicates instead of dropping them.
#         """
#         search_query = self._build_gmail_date_query(
#             constants.GMAIL_INBOX_HARVEST_QUERY,
#             date_preset=date_preset,
#             start_date=start_date,
#             end_date=end_date,
#         )

#         results = (
#             self.service.users()
#             .messages()
#             .list(userId="me", q=search_query, maxResults=max_results)
#             .execute()
#         )
#         messages = results.get("messages", [])

#         manifest = self.load_staged_manifest()
#         manifest_map = {item.get("stage_id"): item for item in manifest}

#         # Cache existing committed DB identifiers
#         committed_hashes = set(
#             DocumentInboxItem.objects.exclude(attachment_hash__isnull=True)
#             .exclude(attachment_hash="")
#             .values_list("attachment_hash", flat=True)
#         )
#         committed_msg_files = set(
#             DocumentInboxItem.objects.values_list("message_id", "filename")
#         )

#         staged_hashes = {
#             item.get("attachment_hash")
#             for item in manifest
#             if item.get("attachment_hash")
#         }
#         staged_msg_files = {
#             (item.get("message_id"), item.get("filename")) for item in manifest
#         }

#         for msg_summary in messages:
#             msg_id = msg_summary["id"]
#             msg = (
#                 self.service.users()
#                 .messages()
#                 .get(userId="me", id=msg_id, format="full")
#                 .execute()
#             )

#             payload = msg.get("payload", {})
#             headers = {
#                 h["name"].lower(): h["value"] for h in payload.get("headers", [])
#             }

#             subject = headers.get("subject", "No Subject")
#             sender = headers.get("from", "Unknown")
#             body_text = self._extract_body_snippet(payload)

#             internal_date_ms = int(msg.get("internalDate", 0))
#             received_dt = (
#                 timezone.make_aware(datetime.fromtimestamp(internal_date_ms / 1000.0))
#                 if internal_date_ms
#                 else timezone.now()
#             )

#             doc_type = self.detect_doc_type(subject, body_text)
#             parts = payload.get("parts", [])

#             for part in parts:
#                 filename = part.get("filename", "")
#                 body = part.get("body", {})
#                 attachment_id = body.get("attachmentId")

#                 if attachment_id and filename.lower().endswith(".pdf"):
#                     sanitized_name = f"{msg_id}_{filename}"
#                     disk_path = os.path.join(self.INBOX_DIR, sanitized_name)

#                     # Read from disk if present, otherwise download
#                     if os.path.exists(disk_path):
#                         with open(disk_path, "rb") as f:
#                             file_data = f.read()
#                     else:
#                         attachment = (
#                             self.service.users()
#                             .messages()
#                             .attachments()
#                             .get(userId="me", messageId=msg_id, id=attachment_id)
#                             .execute()
#                         )
#                         file_data = base64.urlsafe_b64decode(
#                             attachment["data"].encode("UTF-8")
#                         )
#                         with open(disk_path, "wb") as f:
#                             f.write(file_data)

#                     content_hash = hashlib.sha256(file_data).hexdigest()

#                     # Deduplication check against DB and Manifest
#                     is_in_db = (
#                         content_hash in committed_hashes
#                         or (msg_id, filename) in committed_msg_files
#                     )
#                     is_in_manifest = (
#                         content_hash in staged_hashes
#                         or (msg_id, filename) in staged_msg_files
#                     )

#                     is_duplicate = is_in_db or is_in_manifest
#                     stage_status = "DUPLICATE" if is_duplicate else "STAGED"

#                     bank_hint = self.detect_bank_name(sender, subject, filename)
#                     raw_candidate = self.extract_raw_account_candidate(
#                         subject, filename, body_text
#                     )
#                     _, verified_hint = self.resolve_account_from_db(
#                         raw_candidate, bank_name=bank_hint
#                     )
#                     start_date_obj, end_date_obj = self.extract_period_dates(
#                         subject, filename, body_text
#                     )

#                     # Find existing stage entry or create a new one
#                     stage_id = str(uuid.uuid4())
#                     for existing_item in manifest:
#                         if existing_item.get("attachment_hash") == content_hash or (
#                             existing_item.get("message_id") == msg_id
#                             and existing_item.get("filename") == filename
#                         ):
#                             stage_id = existing_item.get("stage_id", stage_id)
#                             break

#                     entry = {
#                         "stage_id": stage_id,
#                         "message_id": msg_id,
#                         "attachment_id": attachment_id,
#                         "attachment_hash": content_hash,
#                         "filename": filename,
#                         "file_path": disk_path,
#                         "file_size": len(file_data),
#                         "doc_type": doc_type,
#                         "status": stage_status,
#                         "is_duplicate": is_duplicate,
#                         "sender": sender,
#                         "subject": subject,
#                         "received_date": received_dt.strftime("%Y-%m-%d %H:%M:%S"),
#                         "account_hint": verified_hint,
#                         "bank_name": bank_hint,
#                         "period_start": (
#                             start_date_obj.strftime("%Y-%m-%d")
#                             if start_date_obj
#                             else None
#                         ),
#                         "period_end": (
#                             end_date_obj.strftime("%Y-%m-%d") if end_date_obj else None
#                         ),
#                         "selected": not is_duplicate,
#                         "created_at": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
#                     }

#                     manifest_map[stage_id] = entry
#                     staged_hashes.add(content_hash)
#                     staged_msg_files.add((msg_id, filename))

#         updated_manifest = list(manifest_map.values())
#         self.save_staged_manifest(updated_manifest)
#         return updated_manifest

#     # ==========================================
#     # Commit Staged Items to Database Table
#     # ==========================================
#     def commit_staged_items(
#         self, selected_stage_ids: list[str], overrides: Optional[dict] = None
#     ) -> list[DocumentInboxItem]:
#         """Commits selected staged items from JSON into DocumentInboxItem DB records
#         and removes them from staged_inbox.json.
#         """
#         overrides = overrides or {}
#         manifest = self.load_staged_manifest()
#         selected_set = set(selected_stage_ids)

#         committed_records = []
#         remaining_manifest = []

#         for item in manifest:
#             stage_id = item.get("stage_id")
#             if stage_id in selected_set:
#                 user_override = overrides.get(stage_id, {})
#                 acc_hint = user_override.get("account_hint", item.get("account_hint"))
#                 bank_name = user_override.get("bank_name", item.get("bank_name"))
#                 doc_type = user_override.get("doc_type", item.get("doc_type"))

#                 rec_dt = (
#                     datetime.strptime(item["received_date"], "%Y-%m-%d %H:%M:%S")
#                     if item.get("received_date")
#                     else timezone.now()
#                 )
#                 rec_dt = (
#                     timezone.make_aware(rec_dt) if timezone.is_naive(rec_dt) else rec_dt
#                 )

#                 p_start = (
#                     datetime.strptime(item["period_start"], "%Y-%m-%d").date()
#                     if item.get("period_start")
#                     else None
#                 )
#                 p_end = (
#                     datetime.strptime(item["period_end"], "%Y-%m-%d").date()
#                     if item.get("period_end")
#                     else None
#                 )

#                 record, _ = DocumentInboxItem.objects.update_or_create(
#                     message_id=item.get("message_id"),
#                     filename=item["filename"],
#                     defaults={
#                         "attachment_id": item.get("attachment_id"),
#                         "attachment_hash": item.get("attachment_hash"),
#                         "file_path": item["file_path"],
#                         "file_size": item["file_size"],
#                         "doc_type": doc_type,
#                         "status": DocumentInboxItem.ProcessingStatus.INBOX,
#                         "sender": item.get("sender", ""),
#                         "subject": item.get("subject", ""),
#                         "received_date": rec_dt,
#                         "account_hint": acc_hint,
#                         "bank_name": bank_name,
#                         "period_start": p_start,
#                         "period_end": p_end,
#                     },
#                 )
#                 committed_records.append(record)
#             else:
#                 remaining_manifest.append(item)

#         self.save_staged_manifest(remaining_manifest)
#         return committed_records
