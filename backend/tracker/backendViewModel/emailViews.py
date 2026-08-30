import json
import os
import re
import urllib.request
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from tracker.emailIngest.heplerIngesttunnel import (
    add_to_staging_buffer,
    load_staging_json,
    remove_from_staging_buffer,
)
from tracker.emailIngest.parser import parse_bank_email_body, parse_rfc_or_iso_date
from tracker.emailIngest.serializers import (
    IngestRequestSerializer,
    RawEmailPayloadSerializer,
)
from tracker.emailIngest.services import (
    decrypt_aes_payload,
    generate_payload_hash,
    generate_transaction_fingerprint,
)
from tracker.models.emailModels import RawEmailPayload
from ..emailIngest.gmail_api import run_gmail_api_ingest


def safe_parse_datetime(date_val):
    """
    Parses SMS/Email timestamp strings into naive datetimes to preserve
    exact local wall-clock hours in MySQL (e.g., '30-08-26 12:34:19').
    """
    if not date_val:
        return datetime.now()

    if isinstance(date_val, datetime):
        return date_val.replace(tzinfo=None)

    if isinstance(date_val, str):
        # 1. Parse Indian Bank SMS formats (e.g. '30-08-26 12:34:19')
        for fmt in ("%d-%m-%y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                return datetime.strptime(date_val.strip(), fmt)
            except ValueError:
                continue

        # 2. ISO/RFC Parsers
        parsed = parse_datetime(date_val)
        if parsed:
            return parsed.replace(tzinfo=None)

        parsed_custom = parse_rfc_or_iso_date(date_val)
        if isinstance(parsed_custom, datetime):
            return parsed_custom.replace(tzinfo=None)

    return datetime.now()


# class EmailIngestStagingViewSet(viewsets.ViewSet):
#     permission_classes = [AllowAny]

#     @action(detail=False, methods=["get"], url_path="pending")
#     def get_pending_staging(self, request):
#         try:
#             buffer_items = load_staging_json()
#             return Response(
#                 {
#                     "status": "SUCCESS",
#                     "count": len(buffer_items),
#                     "previews": buffer_items,
#                     "data": buffer_items,
#                 },
#                 status=status.HTTP_200_OK,
#             )
#         except Exception as e:
#             return Response(
#                 {
#                     "status": "ERROR",
#                     "message": "Failed to load staged previews from JSON buffer.",
#                     "error": str(e),
#                     "previews": [],
#                     "data": [],
#                 },
#                 status=status.HTTP_200_OK,
#             )

#     @action(detail=False, methods=["post"], url_path="ingest")
#     def receive_email(self, request):
#         """
#         Preview/Staging endpoint: Buffers data strictly into staged_previews.json.
#         No database rows are created here.
#         """
#         print("\n" + "=" * 60)
#         print("📥 INCOMING REQUEST DATA FROM SHORTCUT:")
#         print(repr(request.data))
#         print("=" * 60)

#         input_data = (
#             request.data
#             if isinstance(request.data, dict)
#             else {"body": str(request.data)}
#         )

#         serializer = IngestRequestSerializer(data=input_data)
#         if not serializer.is_valid():
#             return Response(
#                 {
#                     "status": "INVALID_PAYLOAD",
#                     "error": "Serializer validation failed.",
#                     "details": serializer.errors,
#                 },
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         encrypted_data = serializer.validated_data.get("encrypted_payload", "")
#         provided_hash = serializer.validated_data.get("payload_hash")
#         source = serializer.validated_data.get("source", "IOS_SMS")

#         bypass_crypto = (
#             request.query_params.get("bypass_crypto", "false").lower() == "true"
#         )
#         raw_body_text = str(input_data.get("body") or "").strip()

#         is_bypass_request = (
#             bypass_crypto
#             or str(encrypted_data).upper()
#             in ["BYPASS", "PLAIN_TEXT_BYPASS", "DUMMY_STRING", ""]
#             or (
#                 bool(raw_body_text)
#                 and not str(encrypted_data).startswith("==")
#                 and len(str(encrypted_data)) < 32
#             )
#         )

#         if is_bypass_request:
#             payload_json = input_data
#             raw_body = raw_body_text
#         else:
#             try:
#                 payload_json = decrypt_aes_payload(encrypted_data)
#                 raw_body = str(payload_json.get("body", "")).strip()
#             except Exception as e:
#                 if raw_body_text:
#                     payload_json = input_data
#                     raw_body = raw_body_text
#                 else:
#                     return Response(
#                         {"status": "DECRYPTION_FAILED", "error": str(e)},
#                         status=status.HTTP_422_UNPROCESSABLE_ENTITY,
#                     )

#         sender = str(
#             payload_json.get("sender") or input_data.get("sender") or "UNKNOWN_SENDER"
#         ).strip()[:255]
#         email_from = str(
#             payload_json.get("email_from")
#             or payload_json.get("from")
#             or input_data.get("email_from")
#             or sender
#         ).strip()[:255]
#         subject = str(
#             payload_json.get("subject") or input_data.get("subject") or "NO_SUBJECT"
#         ).strip()[:255]

#         parsed_data = parse_bank_email_body(raw_body, sender=email_from)

#         raw_email_date = (
#             payload_json.get("email_date")
#             or payload_json.get("date")
#             or parsed_data.get("full_datetime")
#             or parsed_data.get("date")
#         )
#         parsed_email_date = safe_parse_datetime(raw_email_date)

#         txn_fingerprint = parsed_data.get(
#             "txn_fingerprint"
#         ) or generate_transaction_fingerprint(parsed_data)
#         parsed_data["txn_fingerprint"] = txn_fingerprint

#         if not provided_hash:
#             hash_components = [
#                 str(parsed_data.get("bank_name") or "UNKNOWN_BANK"),
#                 str(parsed_data.get("account_last4") or "0000"),
#                 str(parsed_data.get("amount") or "0.00"),
#                 str(parsed_email_date.isoformat() if parsed_email_date else "NO_DATE"),
#                 str(parsed_data.get("upi_ref") or txn_fingerprint),
#                 raw_body,
#             ]
#             provided_hash = generate_payload_hash("_".join(hash_components))

#         headers_data = payload_json.get("headers") or input_data.get("headers") or {}
#         if not isinstance(headers_data, dict):
#             headers_data = {"raw_headers": str(headers_data)}

#         headers_data.update(
#             {
#                 "source": source,
#                 "sender": sender,
#                 "bypass_crypto": is_bypass_request,
#                 "extracted_date": (
#                     parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
#                     if parsed_email_date
#                     else None
#                 ),
#                 "parsed_summary": {
#                     "bank": parsed_data.get("bank_name"),
#                     "account": parsed_data.get("account_last4"),
#                     "amount": parsed_data.get("amount"),
#                     "balance": parsed_data.get("balance"),
#                     "upi_ref": parsed_data.get("upi_ref"),
#                     "full_narration": parsed_data.get("full_narration"),
#                 },
#             }
#         )

#         if parsed_data.get("metadata_json"):
#             headers_data.update(parsed_data["metadata_json"])

#         is_duplicate = False
#         if (
#             txn_fingerprint
#             and RawEmailPayload.objects.filter(txn_fingerprint=txn_fingerprint).exists()
#         ):
#             is_duplicate = True
#         elif (
#             provided_hash
#             and RawEmailPayload.objects.filter(payload_hash=provided_hash).exists()
#         ):
#             is_duplicate = True

#         parsed_data["is_duplicate"] = is_duplicate

#         preview_obj = {
#             "id": str(uuid.uuid4()),
#             "status": "PREVIEW_ONLY",
#             "committed": False,
#             "is_duplicate": is_duplicate,
#             "parsed_transaction": parsed_data,
#             "payload_hash": provided_hash,
#             "raw_payload": {
#                 "encrypted_payload": encrypted_data,
#                 "source": source,
#                 "sender": sender,
#                 "email_from": email_from,
#                 "email_date": (
#                     parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
#                     if parsed_email_date
#                     else None
#                 ),
#                 "subject": subject,
#                 "decrypted_body": raw_body,
#                 "headers_json": headers_data,
#             },
#         }

#         # Save to disk staging buffer only
#         add_to_staging_buffer(preview_obj)

#         return Response(preview_obj, status=status.HTTP_200_OK)

#     @action(detail=False, methods=["post"], url_path="commit-selected")
#     def commit_selected_payloads(self, request):
#         """
#         Commits staged items to MySQL with synchronized processed_at and email_date values.
#         """
#         items_to_commit = request.data.get("items", [])
#         saved_records = []
#         committed_fps = []

#         now_timestamp = timezone.now()

#         with transaction.atomic():
#             for item in items_to_commit:
#                 raw_info = item.get("raw_payload") or item
#                 parsed = item.get("parsed_transaction") or {}

#                 fp = parsed.get("txn_fingerprint") or item.get("id")
#                 payload_hash = item.get("payload_hash") or raw_info.get("payload_hash")

#                 already_exists = False
#                 if fp and RawEmailPayload.objects.filter(txn_fingerprint=fp).exists():
#                     already_exists = True
#                 elif (
#                     payload_hash
#                     and RawEmailPayload.objects.filter(
#                         payload_hash=payload_hash
#                     ).exists()
#                 ):
#                     already_exists = True

#                 if already_exists:
#                     if fp:
#                         committed_fps.append(fp)
#                     continue

#                 raw_email_date = (
#                     raw_info.get("email_date")
#                     or item.get("email_date")
#                     or parsed.get("full_datetime")
#                     or parsed.get("date")
#                 )
#                 parsed_email_date = safe_parse_datetime(raw_email_date)

#                 headers_json = raw_info.get("headers_json") or {}
#                 if not isinstance(headers_json, dict):
#                     headers_json = {"raw_headers": str(headers_json)}

#                 headers_json.update(
#                     {
#                         "committed_via": "UI_TAB_1",
#                         "committed_at": now_timestamp.isoformat(),
#                         "processed_at": now_timestamp.isoformat(),
#                         "parsed_summary": {
#                             "bank": parsed.get("bank_name"),
#                             "account": parsed.get("account_last4"),
#                             "amount": parsed.get("amount"),
#                             "balance": parsed.get("balance"),
#                             "upi_ref": parsed.get("upi_ref"),
#                             "full_narration": parsed.get("full_narration"),
#                         },
#                     }
#                 )

#                 if parsed.get("metadata_json"):
#                     headers_json.update(parsed["metadata_json"])

#                 decrypted_body = raw_info.get("decrypted_body") or ""
#                 email_from = (
#                     raw_info.get("email_from") or raw_info.get("sender") or "UNKNOWN"
#                 )
#                 raw_merchant = parsed.get("merchant") or "UNKNOWN VENDOR"
#                 raw_bank = parsed.get("bank_name") or "UNKNOWN BANK"

#                 if not payload_hash:
#                     hash_components = [
#                         str(raw_bank),
#                         str(parsed.get("account_last4") or "0000"),
#                         str(parsed.get("amount") or "0.00"),
#                         str(parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")),
#                         str(parsed.get("upi_ref") or fp),
#                         decrypted_body,
#                     ]
#                     payload_hash = generate_payload_hash("_".join(hash_components))

#                 try:
#                     record = RawEmailPayload.objects.create(
#                         txn_fingerprint=fp,
#                         encrypted_payload=raw_info.get("encrypted_payload") or "BYPASS",
#                         payload_hash=payload_hash,
#                         source=raw_info.get("source") or "IOS_SMS",
#                         sender=str(raw_info.get("sender") or "")[:255],
#                         email_from=str(email_from)[:255],
#                         email_date=parsed_email_date,  # Matches SMS local time: 2026-08-30 12:34:19
#                         subject=str(raw_info.get("subject") or "NO_SUBJECT")[:255],
#                         decrypted_body=decrypted_body,
#                         headers_json=headers_json,
#                         bank_name=str(raw_bank)[:100],
#                         account_last4=parsed.get("account_last4"),
#                         amount=parsed.get("amount"),
#                         txn_type=parsed.get("txn_type") or "DEBIT",
#                         merchant=str(raw_merchant)[:255],
#                         upi_ref=parsed.get("upi_ref"),
#                         status=RawEmailPayload.ProcessingStatus.PARSED,
#                         processed_at=now_timestamp,  # Exact execution timestamp
#                     )
#                     saved_records.append(str(record.id))
#                 except IntegrityError:
#                     pass

#                 if fp:
#                     committed_fps.append(fp)

#         if committed_fps:
#             remove_from_staging_buffer(committed_fps)

#         return Response(
#             {
#                 "status": "SUCCESS",
#                 "committed_count": len(saved_records),
#                 "ids": saved_records,
#             },
#             status=status.HTTP_201_CREATED,
#         )


class EmailIngestStagingViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=["get"], url_path="pending")
    def get_pending_staging(self, request):
        try:
            buffer_items = load_staging_json()
            return Response(
                {
                    "status": "SUCCESS",
                    "count": len(buffer_items),
                    "previews": buffer_items,
                    "data": buffer_items,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "status": "ERROR",
                    "message": "Failed to load staged previews from JSON buffer.",
                    "error": str(e),
                    "previews": [],
                    "data": [],
                },
                status=status.HTTP_200_OK,
            )

    # 🎯 MISSING ACTION ENDPOINT: Maps to POST /api/ingest/email/staging/sync/
    @action(detail=False, methods=["post"], url_path="sync")
    def sync_stream(self, request):
        """
        Fetches live emails from Gmail based strictly on DATE FILTERS
        (THIS_WEEK, THIS_MONTH, LAST_MONTH, etc.), without forcing account strings into the query.
        """
        try:
            date_preset = request.data.get("date_preset", "THIS_WEEK")
            start_date_str = request.data.get("start_date")
            end_date_str = request.data.get("end_date")

            # 🎯 Build dynamic Gmail date query based on date_preset
            today = datetime.now().date()
            query_parts = []

            if date_preset == "THIS_WEEK":
                start_dt = today - timedelta(days=today.weekday())
                query_parts.append(f"after:{start_dt.strftime('%Y/%m/%d')}")

            elif date_preset == "THIS_MONTH":
                start_dt = today.replace(day=1)
                query_parts.append(f"after:{start_dt.strftime('%Y/%m/%d')}")

            elif date_preset == "LAST_MONTH":
                first_this_month = today.replace(day=1)
                last_month_end = first_this_month - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)
                query_parts.append(f"after:{last_month_start.strftime('%Y/%m/%d')}")
                query_parts.append(f"before:{first_this_month.strftime('%Y/%m/%d')}")

            elif date_preset == "LAST_6_MONTHS":
                six_months_ago = today - timedelta(days=180)
                query_parts.append(f"after:{six_months_ago.strftime('%Y/%m/%d')}")

            elif date_preset == "CUSTOM" and start_date_str and end_date_str:
                query_parts.append(f"after:{start_date_str.replace('-', '/')}")
                query_parts.append(f"before:{end_date_str.replace('-', '/')}")

            # Combine with base bank label or domain filter
            # (Use 'label:bankalerts' or generic bank search terms)
            base_filter = "label:bankalerts"

            if query_parts:
                search_query = f"{base_filter} {' '.join(query_parts)}"
            else:
                search_query = base_filter

            print(
                f"\n⚡ [Gmail Sync] Executing live fetch query: '{search_query}' (Filter: {date_preset})"
            )

            # 🎯 Run Gmail API Ingest with date-driven query
            live_previews = run_gmail_api_ingest(search_query=search_query)

            # Buffer new items into local staging disk
            if live_previews:
                for item in live_previews:
                    add_to_staging_buffer(item)

            buffer_items = load_staging_json()

            return Response(
                {
                    "status": "SUCCESS",
                    "message": f"Fetched {len(live_previews or [])} live email(s) for period: {date_preset}.",
                    "count": len(buffer_items),
                    "previews": buffer_items,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            print(f"❌ [Gmail Sync Error]: {str(e)}")
            buffer_items = load_staging_json()
            return Response(
                {
                    "status": "ERROR",
                    "message": f"Gmail Sync Failed: {str(e)}",
                    "error": str(e),
                    "previews": buffer_items,
                },
                status=status.HTTP_200_OK,
            )

    @action(detail=False, methods=["post"], url_path="ingest")
    def receive_email(self, request):
        """
        Preview/Staging endpoint: Buffers data strictly into staged_previews.json.
        No database rows are created here.
        """
        print("\n" + "=" * 60)
        print("📥 INCOMING REQUEST DATA FROM SHORTCUT:")
        print(repr(request.data))
        print("=" * 60)

        input_data = (
            request.data
            if isinstance(request.data, dict)
            else {"body": str(request.data)}
        )

        serializer = IngestRequestSerializer(data=input_data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "INVALID_PAYLOAD",
                    "error": "Serializer validation failed.",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        encrypted_data = serializer.validated_data.get("encrypted_payload", "")
        provided_hash = serializer.validated_data.get("payload_hash")
        source = serializer.validated_data.get("source", "IOS_SMS")

        bypass_crypto = (
            request.query_params.get("bypass_crypto", "false").lower() == "true"
        )
        raw_body_text = str(input_data.get("body") or "").strip()

        is_bypass_request = (
            bypass_crypto
            or str(encrypted_data).upper()
            in ["BYPASS", "PLAIN_TEXT_BYPASS", "DUMMY_STRING", ""]
            or (
                bool(raw_body_text)
                and not str(encrypted_data).startswith("==")
                and len(str(encrypted_data)) < 32
            )
        )

        if is_bypass_request:
            payload_json = input_data
            raw_body = raw_body_text
        else:
            try:
                payload_json = decrypt_aes_payload(encrypted_data)
                raw_body = str(payload_json.get("body", "")).strip()
            except Exception as e:
                if raw_body_text:
                    payload_json = input_data
                    raw_body = raw_body_text
                else:
                    return Response(
                        {"status": "DECRYPTION_FAILED", "error": str(e)},
                        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )

        sender = str(
            payload_json.get("sender") or input_data.get("sender") or "UNKNOWN_SENDER"
        ).strip()[:255]
        email_from = str(
            payload_json.get("email_from")
            or payload_json.get("from")
            or input_data.get("email_from")
            or sender
        ).strip()[:255]
        subject = str(
            payload_json.get("subject") or input_data.get("subject") or "NO_SUBJECT"
        ).strip()[:255]

        parsed_data = parse_bank_email_body(raw_body, sender=email_from)

        raw_email_date = (
            payload_json.get("email_date")
            or payload_json.get("date")
            or parsed_data.get("full_datetime")
            or parsed_data.get("date")
        )
        parsed_email_date = safe_parse_datetime(raw_email_date)

        txn_fingerprint = parsed_data.get(
            "txn_fingerprint"
        ) or generate_transaction_fingerprint(parsed_data)
        parsed_data["txn_fingerprint"] = txn_fingerprint

        if not provided_hash:
            hash_components = [
                str(parsed_data.get("bank_name") or "UNKNOWN_BANK"),
                str(parsed_data.get("account_last4") or "0000"),
                str(parsed_data.get("amount") or "0.00"),
                str(parsed_email_date.isoformat() if parsed_email_date else "NO_DATE"),
                str(parsed_data.get("upi_ref") or txn_fingerprint),
                raw_body,
            ]
            provided_hash = generate_payload_hash("_".join(hash_components))

        headers_data = payload_json.get("headers") or input_data.get("headers") or {}
        if not isinstance(headers_data, dict):
            headers_data = {"raw_headers": str(headers_data)}

        headers_data.update(
            {
                "source": source,
                "sender": sender,
                "bypass_crypto": is_bypass_request,
                "extracted_date": (
                    parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
                    if parsed_email_date
                    else None
                ),
                "parsed_summary": {
                    "bank": parsed_data.get("bank_name"),
                    "account": parsed_data.get("account_last4"),
                    "amount": parsed_data.get("amount"),
                    "balance": parsed_data.get("balance"),
                    "upi_ref": parsed_data.get("upi_ref"),
                    "full_narration": parsed_data.get("full_narration"),
                },
            }
        )

        if parsed_data.get("metadata_json"):
            headers_data.update(parsed_data["metadata_json"])

        is_duplicate = False
        if (
            txn_fingerprint
            and RawEmailPayload.objects.filter(txn_fingerprint=txn_fingerprint).exists()
        ):
            is_duplicate = True
        elif (
            provided_hash
            and RawEmailPayload.objects.filter(payload_hash=provided_hash).exists()
        ):
            is_duplicate = True

        parsed_data["is_duplicate"] = is_duplicate

        preview_obj = {
            "id": str(uuid.uuid4()),
            "status": "PREVIEW_ONLY",
            "committed": False,
            "is_duplicate": is_duplicate,
            "parsed_transaction": parsed_data,
            "payload_hash": provided_hash,
            "raw_payload": {
                "encrypted_payload": encrypted_data,
                "source": source,
                "sender": sender,
                "email_from": email_from,
                "email_date": (
                    parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
                    if parsed_email_date
                    else None
                ),
                "subject": subject,
                "decrypted_body": raw_body,
                "headers_json": headers_data,
            },
        }

        # Save to disk staging buffer only
        add_to_staging_buffer(preview_obj)

        return Response(preview_obj, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="commit-selected")
    def commit_selected_payloads(self, request):
        """
        Commits staged items to MySQL with synchronized processed_at and email_date values.
        """
        items_to_commit = request.data.get("items", [])
        saved_records = []
        committed_fps = []

        now_timestamp = timezone.now()

        with transaction.atomic():
            for item in items_to_commit:
                raw_info = item.get("raw_payload") or item
                parsed = item.get("parsed_transaction") or {}

                fp = parsed.get("txn_fingerprint") or item.get("id")
                payload_hash = item.get("payload_hash") or raw_info.get("payload_hash")

                already_exists = False
                if fp and RawEmailPayload.objects.filter(txn_fingerprint=fp).exists():
                    already_exists = True
                elif (
                    payload_hash
                    and RawEmailPayload.objects.filter(
                        payload_hash=payload_hash
                    ).exists()
                ):
                    already_exists = True

                if already_exists:
                    if fp:
                        committed_fps.append(fp)
                    continue

                raw_email_date = (
                    raw_info.get("email_date")
                    or item.get("email_date")
                    or parsed.get("full_datetime")
                    or parsed.get("date")
                )
                parsed_email_date = safe_parse_datetime(raw_email_date)

                headers_json = raw_info.get("headers_json") or {}
                if not isinstance(headers_json, dict):
                    headers_json = {"raw_headers": str(headers_json)}

                headers_json.update(
                    {
                        "committed_via": "UI_TAB_1",
                        "committed_at": now_timestamp.isoformat(),
                        "processed_at": now_timestamp.isoformat(),
                        "parsed_summary": {
                            "bank": parsed.get("bank_name"),
                            "account": parsed.get("account_last4"),
                            "amount": parsed.get("amount"),
                            "balance": parsed.get("balance"),
                            "upi_ref": parsed.get("upi_ref"),
                            "full_narration": parsed.get("full_narration"),
                        },
                    }
                )

                if parsed.get("metadata_json"):
                    headers_json.update(parsed["metadata_json"])

                decrypted_body = raw_info.get("decrypted_body") or ""
                email_from = (
                    raw_info.get("email_from") or raw_info.get("sender") or "UNKNOWN"
                )
                raw_merchant = parsed.get("merchant") or "UNKNOWN VENDOR"
                raw_bank = parsed.get("bank_name") or "UNKNOWN BANK"

                if not payload_hash:
                    hash_components = [
                        str(raw_bank),
                        str(parsed.get("account_last4") or "0000"),
                        str(parsed.get("amount") or "0.00"),
                        str(parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")),
                        str(parsed.get("upi_ref") or fp),
                        decrypted_body,
                    ]
                    payload_hash = generate_payload_hash("_".join(hash_components))

                try:
                    record = RawEmailPayload.objects.create(
                        txn_fingerprint=fp,
                        encrypted_payload=raw_info.get("encrypted_payload") or "BYPASS",
                        payload_hash=payload_hash,
                        source=raw_info.get("source") or "IOS_SMS",
                        sender=str(raw_info.get("sender") or "")[:255],
                        email_from=str(email_from)[:255],
                        email_date=parsed_email_date,
                        subject=str(raw_info.get("subject") or "NO_SUBJECT")[:255],
                        decrypted_body=decrypted_body,
                        headers_json=headers_json,
                        bank_name=str(raw_bank)[:100],
                        account_last4=parsed.get("account_last4"),
                        amount=parsed.get("amount"),
                        txn_type=parsed.get("txn_type") or "DEBIT",
                        merchant=str(raw_merchant)[:255],
                        upi_ref=parsed.get("upi_ref"),
                        status=RawEmailPayload.ProcessingStatus.PARSED,
                        processed_at=now_timestamp,
                    )
                    saved_records.append(str(record.id))
                except IntegrityError:
                    pass

                if fp:
                    committed_fps.append(fp)

        if committed_fps:
            remove_from_staging_buffer(committed_fps)

        return Response(
            {
                "status": "SUCCESS",
                "committed_count": len(saved_records),
                "ids": saved_records,
            },
            status=status.HTTP_201_CREATED,
        )


class RawEmailPayloadVaultViewSet(viewsets.ReadOnlyModelViewSet):
    """Manages committed records in MySQL, serving queries for Tab 2 DataTables."""

    queryset = RawEmailPayload.objects.all().order_by("-email_date", "-created_at")
    serializer_class = RawEmailPayloadSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        staged_only = self.request.query_params.get("staged_only")
        if staged_only == "true":
            queryset = queryset.filter(is_staged_for_matching=True)
        elif staged_only == "false":
            queryset = queryset.filter(is_staged_for_matching=False)
        else:
            queryset = queryset.filter(is_staged_for_matching=False)

        search = self.request.query_params.get("search")
        status_param = self.request.query_params.get("status")
        date_preset = self.request.query_params.get("date_preset")
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if search:
            queryset = queryset.filter(
                Q(bank_name__icontains=search)
                | Q(merchant__icontains=search)
                | Q(subject__icontains=search)
            )

        if status_param and status_param != "ALL":
            queryset = queryset.filter(status=status_param)

        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()

        if date_preset == "THIS_WEEK":
            monday = today - timedelta(days=today.weekday())
            start_of_week = timezone.make_aware(
                datetime.combine(monday, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(created_at__gte=start_of_week) | Q(email_date__gte=start_of_week)
            )

        elif date_preset == "THIS_MONTH":
            first_day = today.replace(day=1)
            start_of_month = timezone.make_aware(
                datetime.combine(first_day, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(created_at__gte=start_of_month) | Q(email_date__gte=start_of_month)
            )

        elif date_preset == "LAST_MONTH":
            first_day_this_month = today.replace(day=1)
            last_month_end = first_day_this_month - timedelta(days=1)
            first_day_last_month = last_month_end.replace(day=1)

            start_dt = timezone.make_aware(
                datetime.combine(first_day_last_month, datetime.min.time())
            )
            end_dt = timezone.make_aware(
                datetime.combine(first_day_this_month, datetime.min.time())
            )

            queryset = queryset.filter(
                Q(email_date__gte=start_dt, email_date__lt=end_dt)
                | Q(created_at__gte=start_dt, created_at__lt=end_dt)
            )

        elif date_preset == "LAST_6_MONTHS":
            six_months_ago = today - timedelta(days=180)
            start_dt = timezone.make_aware(
                datetime.combine(six_months_ago, datetime.min.time())
            )
            queryset = queryset.filter(
                Q(created_at__gte=start_dt) | Q(email_date__gte=start_dt)
            )

        elif date_preset == "CUSTOM":
            if start_date and end_date:
                try:
                    s_d = datetime.strptime(start_date, "%Y-%m-%d").date()
                    e_d = datetime.strptime(end_date, "%Y-%m-%d").date()

                    s_dt = timezone.make_aware(
                        datetime.combine(s_d, datetime.min.time())
                    )
                    e_dt = timezone.make_aware(
                        datetime.combine(e_d, datetime.max.time())
                    )

                    queryset = queryset.filter(
                        Q(email_date__range=(s_dt, e_dt))
                        | Q(created_at__range=(s_dt, e_dt))
                    )
                except ValueError:
                    queryset = queryset.none()
            else:
                queryset = queryset.none()

        return queryset

    @action(detail=False, methods=["get"], url_path="stats")
    def get_stats(self, request):
        filtered_qs = self.get_queryset()

        total = filtered_qs.count()
        parsed = filtered_qs.filter(
            status=RawEmailPayload.ProcessingStatus.PARSED
        ).count()
        duplicate = filtered_qs.filter(
            status=RawEmailPayload.ProcessingStatus.DUPLICATE
        ).count()
        failed = filtered_qs.filter(
            status__in=[
                RawEmailPayload.ProcessingStatus.FAILED,
                RawEmailPayload.ProcessingStatus.DECRYPTED,
            ]
        ).count()

        return Response(
            {
                "total": total,
                "parsed": parsed,
                "duplicate": duplicate,
                "failed": failed,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["patch"], url_path="taxonomy")
    def update_taxonomy(self, request, pk=None):
        payload = self.get_object()

        category_id = request.data.get("category_id")
        category_name = request.data.get("category_name")
        subcategory_id = request.data.get("subcategory_id")
        subcategory_name = request.data.get("subcategory_name")

        # Ensure taxonomy_payload dictionary is initialized
        if not payload.taxonomy_payload:
            payload.taxonomy_payload = {}

        if "taxonomy" not in payload.taxonomy_payload:
            payload.taxonomy_payload["taxonomy"] = {}

        # Update taxonomy fields
        if category_id is not None:
            payload.taxonomy_payload["taxonomy"]["category_id"] = category_id
        if category_name is not None:
            payload.taxonomy_payload["taxonomy"]["category_name"] = category_name
        if subcategory_id is not None:
            payload.taxonomy_payload["taxonomy"]["subcategory_id"] = subcategory_id
        if subcategory_name is not None:
            payload.taxonomy_payload["taxonomy"]["subcategory_name"] = subcategory_name

        payload.save(update_fields=["taxonomy_payload"])

        return Response(
            {
                "status": "success",
                "message": "Taxonomy updated successfully",
                "taxonomy_payload": payload.taxonomy_payload,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="batch-taxonomy")
    def batch_update_taxonomy(self, request):
        updates = request.data.get("updates", [])
        updated_count = 0

        for item in updates:
            payload_id = item.get("payloadId")
            cat_name = item.get("categoryName")
            sub_name = item.get("subcategoryName")

            try:
                payload = RawEmailPayload.objects.get(pk=payload_id)
                if not payload.taxonomy_payload:
                    payload.taxonomy_payload = {}
                if "taxonomy" not in payload.taxonomy_payload:
                    payload.taxonomy_payload["taxonomy"] = {}

                payload.taxonomy_payload["taxonomy"]["category_name"] = cat_name
                payload.taxonomy_payload["taxonomy"]["subcategory_name"] = sub_name
                payload.save(update_fields=["taxonomy_payload"])
                updated_count += 1
            except RawEmailPayload.DoesNotExist:
                continue

        return Response(
            {
                "status": "success",
                "message": f"Successfully updated taxonomy for {updated_count} record(s).",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="stage-for-matching")
    def stage_for_matching(self, request):
        payload_ids = request.data.get("payload_ids", [])

        if not payload_ids:
            return Response(
                {"error": "No payload IDs provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_count = (
            self.get_queryset()
            .filter(pk__in=payload_ids)
            .update(
                is_staged_for_matching=True,
                staged_at=timezone.now(),
                status="STAGED",
            )
        )

        return Response(
            {
                "status": "success",
                "message": f"Successfully staged {updated_count} payload(s) for matching.",
                "staged_count": updated_count,
            },
            status=status.HTTP_200_OK,
        )


class CloudflareTunnelViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    PUBLIC_TUNNEL_URL = os.getenv(
        "CLOUDFLARE_TUNNEL_PUBLIC_URL", "https://ingest.bluedotservices.net"
    )
    INTERNAL_METRICS_URL = os.getenv(
        "CLOUDFLARE_TUNNEL_METRICS_URL", "http://quick_tunnel:20000/ready"
    )

    def _get_dynamic_tunnel_url(self):
        return self.PUBLIC_TUNNEL_URL.rstrip("/")

    @action(detail=False, methods=["get"], url_path="status")
    def get_status(self, request):
        active_tunnel_url = self._get_dynamic_tunnel_url()
        edge_location = os.getenv("CLOUDFLARE_EDGE_LOCATION", "maa05 (Chennai)")
        protocol = os.getenv("CLOUDFLARE_TUNNEL_PROTOCOL", "QUIC")

        is_healthy = False

        try:
            req = urllib.request.urlopen(self.INTERNAL_METRICS_URL, timeout=1.5)
            if req.status == 200:
                is_healthy = True
        except Exception:
            try:
                public_check_url = (
                    f"{active_tunnel_url}/api/ingest/email/tunnel/inspect-endpoint/"
                )
                req = urllib.request.urlopen(public_check_url, timeout=2.0)
                if req.status in [200, 404, 405]:
                    is_healthy = True
            except Exception as e:
                print(f"⚠️ Tunnel Health Check Error: {e}")

        if is_healthy:
            return Response(
                {
                    "status": "ONLINE",
                    "tunnel_url": active_tunnel_url,
                    "ingest_endpoint": f"{active_tunnel_url}/api/ingest/email/staging/ingest/?confirm=false",
                    "protocol": protocol,
                    "edge_location": edge_location,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "OFFLINE",
                "tunnel_url": None,
                "ingest_endpoint": None,
                "protocol": None,
                "edge_location": None,
                "error": "Cloudflare Tunnel service unreachable.",
            },
            status=status.HTTP_200_OK,
        )


class BalanceCheckViewSet(viewsets.ViewSet):
    """
    Isolated ViewSet for auditing running balance continuity
    and detecting missing SMS/Email transaction gaps.
    """

    @action(detail=False, methods=["get"], url_path="audit")
    def audit_discrepancies(self, request):
        account_number = request.query_params.get("account", "0060")
        bank_name = request.query_params.get("bank", "SOUTH INDIAN BANK")

        # 1. Fetch all parsed records for the specified account ordered chronologically (oldest first)
        records = RawEmailPayload.objects.filter(status="PARSED").order_by(
            "email_date", "created_at"
        )

        # Filter in Python for JSON match on account_last4 if not a direct DB column
        filtered_records = []
        for r in records:
            headers = r.headers_json or {}
            if isinstance(headers, str):
                import json

                try:
                    headers = json.loads(headers)
                except Exception:
                    headers = {}

            summary = headers.get("parsed_summary", {})
            acc = r.account_last4 or summary.get("account")

            # Extract balance safely
            bal = summary.get("balance")
            if acc == account_number and bal is not None:
                filtered_records.append(
                    {
                        "id": str(r.id),
                        "source": r.source,
                        "bank_name": r.bank_name or summary.get("bank") or bank_name,
                        "account_last4": acc,
                        "merchant": r.merchant or r.subject or "UPI Transfer",
                        "amount": str(r.amount or summary.get("amount") or "0.00"),
                        "txn_type": (r.txn_type or "DEBIT").upper(),
                        "balance": str(bal),
                        "upi_ref": r.upi_ref or summary.get("upi_ref") or "—",
                        "status": r.status,
                        "email_date": (
                            r.email_date.isoformat() if r.email_date else None
                        ),
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                )

        # 2. Evaluate Running Balance Delta Invariants
        audited_results = []
        gap_count = 0

        for i in range(len(filtered_records)):
            current = filtered_records[i]
            audited_results.append(current)

            if i == 0:
                continue

            previous = filtered_records[i - 1]

            prev_bal = Decimal(str(previous["balance"]))
            curr_bal = Decimal(str(current["balance"]))
            curr_amt = Decimal(str(current["amount"]))
            txn_type = current["txn_type"].upper()

            # Calculate expected balance using the true transaction direction
            if txn_type == "DEBIT":
                expected_bal = prev_bal - curr_amt
            else:
                expected_bal = prev_bal + curr_amt

            delta = curr_bal - expected_bal

            # If a gap exists, inject a synthetic suspense gap row
            if abs(delta) > Decimal("0.01"):
                gap_type = "CREDIT" if delta > 0 else "DEBIT"
                gap_dc = "Cr" if delta > 0 else "Dr"
                intermediate_balance = (
                    prev_bal + delta if gap_type == "CREDIT" else prev_bal - abs(delta)
                )

                synthetic_gap = {
                    "id": f"gap_{previous['id'][:8]}_{current['id'][:8]}",
                    "source": "AUDIT_GAP",
                    "bank_name": current["bank_name"],
                    "account_last4": current["account_last4"],
                    "merchant": "⚠️ [UNMATCHED GAP] Pre-Statement Suspense",
                    "amount": str(abs(delta)),
                    "txn_type": gap_type,
                    "dc_type": gap_dc,  # 👈 Explicit Cr / Dr
                    "balance": str(intermediate_balance),
                    "upi_ref": "PENDING_STATEMENT",
                    "status": "SUSPENSE",
                    "email_date": current["email_date"],
                    "created_at": current["created_at"],
                    "is_synthetic_gap": True,
                    "gap_start_date": previous["email_date"],
                    "gap_end_date": current["email_date"],
                    "delta_amount": str(delta),
                }
                audited_results.append(synthetic_gap)

        # 4. Reverse to return newest first for UI display
        audited_results.reverse()

        return Response(
            {
                "account": account_number,
                "total_records": len(filtered_records),
                "discrepancies_found": gap_count,
                "results": audited_results,
            },
            status=status.HTTP_200_OK,
        )
