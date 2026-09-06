import json
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from tracker.models.emailModels import RawEmailPayload
from tracker.models.models import Account as LedgerAccount
from tracker.emailIngest.gmail_api import run_gmail_api_ingest
from tracker.emailIngest.heplerIngesttunnel import (
    add_to_staging_buffer,
    append_batch_to_staging_buffer,
    load_staging_json,
    remove_from_staging_buffer,
    discard_from_staging_buffer,
)
from tracker.emailIngest.parser import parse_bank_email_body
from tracker.emailIngest.serializers import IngestRequestSerializer
from tracker.emailIngest.services import (
    decrypt_aes_payload,
    generate_payload_hash,
    generate_transaction_fingerprint,
)
from tracker.emailIngest.watermark import get_latest_transaction_watermark
from .emailViewsutils.emailViewhelper import safe_parse_datetime


class EmailIngestStagingViewSet(viewsets.ViewSet):
    """Handles Tab 1 (Preview Buffer, Live Gmail Sync, Stream Ingest, Discard, and Commit)."""

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

    @action(detail=False, methods=["post"], url_path="discard")
    def discard_staging(self, request):
        """Removes selected uncommitted items from the JSON buffer."""
        ids_to_remove = request.data.get("ids", [])
        if not isinstance(ids_to_remove, list):
            return Response(
                {"status": "ERROR", "message": "'ids' must be a list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        removed_count = discard_from_staging_buffer(ids_to_remove)
        buffer_items = load_staging_json()
        return Response(
            {
                "status": "SUCCESS",
                "removed_count": removed_count,
                "remaining_count": len(buffer_items),
                "previews": buffer_items,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="sync")
    def sync_stream(self, request):
        start_time = time.perf_counter()
        try:
            date_preset = request.data.get("date_preset", "THIS_WEEK")
            start_date_str = request.data.get("start_date")
            end_date_str = request.data.get("end_date")
            account_last4 = request.data.get("account")
            today = datetime.now().date()

            requested_start = None
            if date_preset == "THIS_WEEK":
                requested_start = today - timedelta(days=today.weekday())
            elif date_preset == "THIS_MONTH":
                requested_start = today.replace(day=1)
            elif date_preset == "LAST_MONTH":
                first_this_month = today.replace(day=1)
                last_month_end = first_this_month - timedelta(days=1)
                requested_start = last_month_end.replace(day=1)
            elif date_preset == "LAST_6_MONTHS":
                requested_start = today - timedelta(days=180)
            elif date_preset == "CUSTOM" and start_date_str:
                try:
                    requested_start = datetime.strptime(
                        start_date_str, "%Y-%m-%d"
                    ).date()
                except ValueError:
                    requested_start = None

            watermark_dt = None
            if date_preset not in ["ALL", "ALL_TIME"]:
                watermark_dt = get_latest_transaction_watermark(
                    account_last4=account_last4
                )

            effective_start = requested_start
            if watermark_dt:
                buffered_watermark = watermark_dt.date() - timedelta(days=1)
                effective_start = (
                    min(requested_start, buffered_watermark)
                    if requested_start
                    else buffered_watermark
                )

            query_parts = []
            if effective_start and date_preset not in ["ALL", "ALL_TIME"]:
                query_parts.append(f"after:{effective_start.strftime('%Y/%m/%d')}")

            if date_preset == "LAST_MONTH":
                first_this_month = today.replace(day=1)
                query_parts.append(f"before:{first_this_month.strftime('%Y/%m/%d')}")
            elif date_preset == "CUSTOM" and end_date_str:
                query_parts.append(f"before:{end_date_str.replace('-', '/')}")

            base_filter = "label:bankalerts"
            search_query = (
                f"{base_filter} {' '.join(query_parts)}" if query_parts else base_filter
            )

            live_previews = run_gmail_api_ingest(search_query=search_query)
            if live_previews:
                append_batch_to_staging_buffer(live_previews)

            buffer_items = load_staging_json()
            elapsed_sec = round(time.perf_counter() - start_time, 2)

            return Response(
                {
                    "status": "SUCCESS",
                    "message": f"Fetched {len(live_previews or [])} live email(s) in {elapsed_sec}s for period: {date_preset}.",
                    "total_fetched": len(live_previews or []),
                    "total_buffered": len(buffer_items),
                    "duration_seconds": elapsed_sec,
                    "previews": buffer_items[:100],
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            elapsed_sec = round(time.perf_counter() - start_time, 2)
            return Response(
                {
                    "status": "ERROR",
                    "message": f"Gmail Sync Failed after {elapsed_sec}s: {str(e)}",
                    "error": str(e),
                    "duration_seconds": elapsed_sec,
                    "previews": load_staging_json(),
                },
                status=status.HTTP_200_OK,
            )

    @action(detail=False, methods=["post"], url_path="ingest")
    def receive_email(self, request):
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

        # 1. Parse content using normalized engine
        parsed_data = parse_bank_email_body(raw_body, sender=email_from)

        raw_email_date = (
            payload_json.get("email_date")
            or payload_json.get("date")
            or parsed_data.get("full_datetime")
            or parsed_data.get("date")
        )
        parsed_email_date = safe_parse_datetime(raw_email_date)

        # 2. Derive deterministic fingerprint
        txn_fingerprint = parsed_data.get(
            "txn_fingerprint"
        ) or generate_transaction_fingerprint(parsed_data)
        parsed_data["txn_fingerprint"] = txn_fingerprint

        # 3. Payload hash generation (independent of ephemeral body formatting variations)
        if not provided_hash:
            date_str = (
                parsed_email_date.strftime("%Y-%m-%d")
                if parsed_email_date
                else (parsed_data.get("date") or "NO_DATE")
            )
            hash_components = [
                str(parsed_data.get("bank_name") or "UNKNOWN_BANK"),
                str(parsed_data.get("account_last4") or "0000"),
                str(parsed_data.get("amount") or "0.00"),
                date_str,
                str(parsed_data.get("upi_ref") or txn_fingerprint),
            ]
            provided_hash = generate_payload_hash("_".join(hash_components))

        # 4. Check for duplicates against both DB and the Active Staging Buffer
        is_duplicate = False
        if txn_fingerprint:
            is_duplicate = RawEmailPayload.objects.filter(
                txn_fingerprint=txn_fingerprint
            ).exists()
        if not is_duplicate and provided_hash:
            is_duplicate = RawEmailPayload.objects.filter(
                payload_hash=provided_hash
            ).exists()

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

        parsed_data["is_duplicate"] = is_duplicate

        preview_obj = {
            "id": str(uuid.uuid4()),
            "status": "DUPLICATE" if is_duplicate else "PREVIEW_ONLY",
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

        add_to_staging_buffer(preview_obj)
        return Response(preview_obj, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="commit-selected")
    def commit_selected_payloads(self, request):
        items_to_commit = (
            request.data
            if isinstance(request.data, list)
            else request.data.get("items", [])
        )
        if not items_to_commit:
            return Response(
                {"status": "ERROR", "message": "No items provided to commit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        saved_records = []
        committed_fps = []
        duplicates_count = 0
        now_timestamp = timezone.now()

        with transaction.atomic():
            for item in items_to_commit:
                raw_info = item.get("raw_payload") or item
                parsed = item.get("parsed_transaction") or {}

                decrypted_body = (
                    raw_info.get("decrypted_body")
                    or raw_info.get("body")
                    or item.get("body")
                    or ""
                )
                email_from = (
                    raw_info.get("email_from")
                    or raw_info.get("sender")
                    or item.get("email_from")
                    or ""
                )

                headers_json = (
                    raw_info.get("headers_json") or item.get("headers_json") or {}
                )
                if isinstance(headers_json, str):
                    try:
                        headers_json = json.loads(headers_json)
                    except Exception:
                        headers_json = {}
                elif not isinstance(headers_json, dict):
                    headers_json = {"raw_headers": str(headers_json)}

                summary = headers_json.get("parsed_summary", {})
                inherited_bank = (
                    parsed.get("bank_name")
                    or summary.get("bank")
                    or item.get("bank_name")
                    or ""
                )

                # Re-parse body if parsed details were missing from preview stage
                if not parsed.get("is_parsed"):
                    freshly_parsed = parse_bank_email_body(
                        decrypted_body, sender=email_from, inherited_bank=inherited_bank
                    )
                    if freshly_parsed.get("is_parsed"):
                        parsed = freshly_parsed

                fp = (
                    parsed.get("txn_fingerprint")
                    or item.get("txn_fingerprint")
                    or item.get("id")
                )
                payload_hash = item.get("payload_hash") or raw_info.get("payload_hash")

                already_exists = (
                    fp and RawEmailPayload.objects.filter(txn_fingerprint=fp).exists()
                ) or (
                    payload_hash
                    and RawEmailPayload.objects.filter(
                        payload_hash=payload_hash
                    ).exists()
                )

                if already_exists:
                    duplicates_count += 1
                    if fp:
                        committed_fps.append(fp)
                    continue

                target_last4 = parsed.get("account_last4")
                ledger_account_obj = None
                if target_last4 and LedgerAccount is not None:
                    try:
                        ledger_account_obj = LedgerAccount.objects.filter(
                            account_number__endswith=target_last4
                        ).first()
                    except Exception as e:
                        print(f"⚠️ Account lookup error during commit: {e}")

                final_account_id = ledger_account_obj.id if ledger_account_obj else None
                final_account_last4 = (
                    target_last4 if ledger_account_obj else target_last4
                )

                raw_email_date = (
                    raw_info.get("email_date")
                    or item.get("email_date")
                    or parsed.get("full_datetime")
                    or parsed.get("date")
                )
                parsed_email_date = safe_parse_datetime(raw_email_date)

                try:
                    clean_amount = Decimal(str(parsed.get("amount") or "0.00"))
                except Exception:
                    clean_amount = Decimal("0.00")

                headers_json.update(
                    {
                        "committed_via": "UI_TAB_1",
                        "committed_at": now_timestamp.isoformat(),
                        "processed_at": now_timestamp.isoformat(),
                        "account_id": (
                            str(final_account_id) if final_account_id else None
                        ),
                        "parsed_summary": {
                            "bank": parsed.get("bank_name") or inherited_bank,
                            "account": final_account_last4,
                            "amount": str(clean_amount),
                            "balance": parsed.get("balance"),
                            "upi_ref": parsed.get("upi_ref"),
                            "full_narration": parsed.get("full_narration"),
                        },
                    }
                )
                if parsed.get("metadata_json"):
                    headers_json.update(parsed["metadata_json"])

                raw_merchant = parsed.get("merchant") or "UNKNOWN VENDOR"
                raw_bank = parsed.get("bank_name") or inherited_bank or "UNKNOWN BANK"
                resolved_source = (
                    item.get("source")
                    or raw_info.get("source")
                    or headers_json.get("source")
                    or parsed.get("source")
                    or "GMAIL_API"
                )

                if not payload_hash:
                    date_str = (
                        parsed_email_date.strftime("%Y-%m-%d")
                        if parsed_email_date
                        else (parsed.get("date") or "NO_DATE")
                    )
                    hash_components = [
                        str(raw_bank),
                        str(final_account_last4 or "0000"),
                        str(clean_amount),
                        date_str,
                        str(parsed.get("upi_ref") or fp),
                    ]
                    payload_hash = generate_payload_hash("_".join(hash_components))

                try:
                    record = RawEmailPayload.objects.create(
                        txn_fingerprint=fp,
                        encrypted_payload=raw_info.get("encrypted_payload") or "BYPASS",
                        payload_hash=payload_hash,
                        source=str(resolved_source)[:50],
                        sender=str(raw_info.get("sender") or email_from or "UNKNOWN")[
                            :255
                        ],
                        email_from=str(email_from or "UNKNOWN")[:255],
                        email_date=parsed_email_date,
                        subject=str(
                            raw_info.get("subject")
                            or item.get("subject")
                            or "NO_SUBJECT"
                        )[:255],
                        decrypted_body=decrypted_body,
                        headers_json=headers_json,
                        bank_name=str(raw_bank)[:100],
                        account_last4=final_account_last4,
                        amount=clean_amount,
                        txn_type=parsed.get("txn_type") or "DEBIT",
                        merchant=str(raw_merchant)[:255],
                        upi_ref=parsed.get("upi_ref"),
                        status=RawEmailPayload.ProcessingStatus.PARSED,
                        processed_at=now_timestamp,
                    )
                    saved_records.append(str(record.id))
                except IntegrityError:
                    duplicates_count += 1

                if fp:
                    committed_fps.append(fp)

            if committed_fps:
                remove_from_staging_buffer(committed_fps)

        return Response(
            {
                "status": "SUCCESS",
                "committed_count": len(saved_records),
                "duplicates_detected": duplicates_count,
                "ids": saved_records,
            },
            status=status.HTTP_201_CREATED,
        )

    # @action(detail=False, methods=["post"], url_path="ingest")
    # def receive_email(self, request):
    #     input_data = (
    #         request.data
    #         if isinstance(request.data, dict)
    #         else {"body": str(request.data)}
    #     )
    #     serializer = IngestRequestSerializer(data=input_data)
    #     if not serializer.is_valid():
    #         return Response(
    #             {
    #                 "status": "INVALID_PAYLOAD",
    #                 "error": "Serializer validation failed.",
    #                 "details": serializer.errors,
    #             },
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )

    #     encrypted_data = serializer.validated_data.get("encrypted_payload", "")
    #     provided_hash = serializer.validated_data.get("payload_hash")
    #     source = serializer.validated_data.get("source", "IOS_SMS")
    #     bypass_crypto = (
    #         request.query_params.get("bypass_crypto", "false").lower() == "true"
    #     )
    #     raw_body_text = str(input_data.get("body") or "").strip()

    #     is_bypass_request = (
    #         bypass_crypto
    #         or str(encrypted_data).upper()
    #         in ["BYPASS", "PLAIN_TEXT_BYPASS", "DUMMY_STRING", ""]
    #         or (
    #             bool(raw_body_text)
    #             and not str(encrypted_data).startswith("==")
    #             and len(str(encrypted_data)) < 32
    #         )
    #     )

    #     if is_bypass_request:
    #         payload_json = input_data
    #         raw_body = raw_body_text
    #     else:
    #         try:
    #             payload_json = decrypt_aes_payload(encrypted_data)
    #             raw_body = str(payload_json.get("body", "")).strip()
    #         except Exception as e:
    #             if raw_body_text:
    #                 payload_json = input_data
    #                 raw_body = raw_body_text
    #             else:
    #                 return Response(
    #                     {"status": "DECRYPTION_FAILED", "error": str(e)},
    #                     status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    #                 )

    #     sender = str(
    #         payload_json.get("sender") or input_data.get("sender") or "UNKNOWN_SENDER"
    #     ).strip()[:255]
    #     email_from = str(
    #         payload_json.get("email_from")
    #         or payload_json.get("from")
    #         or input_data.get("email_from")
    #         or sender
    #     ).strip()[:255]
    #     subject = str(
    #         payload_json.get("subject") or input_data.get("subject") or "NO_SUBJECT"
    #     ).strip()[:255]

    #     parsed_data = parse_bank_email_body(raw_body, sender=email_from)
    #     raw_email_date = (
    #         payload_json.get("email_date")
    #         or payload_json.get("date")
    #         or parsed_data.get("full_datetime")
    #         or parsed_data.get("date")
    #     )
    #     parsed_email_date = safe_parse_datetime(raw_email_date)

    #     txn_fingerprint = parsed_data.get(
    #         "txn_fingerprint"
    #     ) or generate_transaction_fingerprint(parsed_data)
    #     parsed_data["txn_fingerprint"] = txn_fingerprint

    #     if not provided_hash:
    #         hash_components = [
    #             str(parsed_data.get("bank_name") or "UNKNOWN_BANK"),
    #             str(parsed_data.get("account_last4") or "0000"),
    #             str(parsed_data.get("amount") or "0.00"),
    #             str(parsed_email_date.isoformat() if parsed_email_date else "NO_DATE"),
    #             str(parsed_data.get("upi_ref") or txn_fingerprint),
    #             raw_body,
    #         ]
    #         provided_hash = generate_payload_hash("_".join(hash_components))

    #     headers_data = payload_json.get("headers") or input_data.get("headers") or {}
    #     if not isinstance(headers_data, dict):
    #         headers_data = {"raw_headers": str(headers_data)}

    #     headers_data.update(
    #         {
    #             "source": source,
    #             "sender": sender,
    #             "bypass_crypto": is_bypass_request,
    #             "extracted_date": (
    #                 parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
    #                 if parsed_email_date
    #                 else None
    #             ),
    #             "parsed_summary": {
    #                 "bank": parsed_data.get("bank_name"),
    #                 "account": parsed_data.get("account_last4"),
    #                 "amount": parsed_data.get("amount"),
    #                 "balance": parsed_data.get("balance"),
    #                 "upi_ref": parsed_data.get("upi_ref"),
    #                 "full_narration": parsed_data.get("full_narration"),
    #             },
    #         }
    #     )
    #     if parsed_data.get("metadata_json"):
    #         headers_data.update(parsed_data["metadata_json"])

    #     is_duplicate = (
    #         txn_fingerprint
    #         and RawEmailPayload.objects.filter(txn_fingerprint=txn_fingerprint).exists()
    #     ) or (
    #         provided_hash
    #         and RawEmailPayload.objects.filter(payload_hash=provided_hash).exists()
    #     )
    #     parsed_data["is_duplicate"] = is_duplicate

    #     preview_obj = {
    #         "id": str(uuid.uuid4()),
    #         "status": "DUPLICATE" if is_duplicate else "PREVIEW_ONLY",
    #         "committed": False,
    #         "is_duplicate": is_duplicate,
    #         "parsed_transaction": parsed_data,
    #         "payload_hash": provided_hash,
    #         "raw_payload": {
    #             "encrypted_payload": encrypted_data,
    #             "source": source,
    #             "sender": sender,
    #             "email_from": email_from,
    #             "email_date": (
    #                 parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")
    #                 if parsed_email_date
    #                 else None
    #             ),
    #             "subject": subject,
    #             "decrypted_body": raw_body,
    #             "headers_json": headers_data,
    #         },
    #     }

    #     add_to_staging_buffer(preview_obj)
    #     return Response(preview_obj, status=status.HTTP_200_OK)

    # @action(detail=False, methods=["post"], url_path="commit-selected")
    # def commit_selected_payloads(self, request):
    #     items_to_commit = (
    #         request.data
    #         if isinstance(request.data, list)
    #         else request.data.get("items", [])
    #     )
    #     if not items_to_commit:
    #         return Response(
    #             {"status": "ERROR", "message": "No items provided to commit."},
    #             status=status.HTTP_400_BAD_REQUEST,
    #         )

    #     saved_records = []
    #     committed_fps = []
    #     duplicates_count = 0
    #     now_timestamp = timezone.now()

    #     with transaction.atomic():
    #         for item in items_to_commit:
    #             raw_info = item.get("raw_payload") or item
    #             parsed = item.get("parsed_transaction") or {}

    #             decrypted_body = (
    #                 raw_info.get("decrypted_body")
    #                 or raw_info.get("body")
    #                 or item.get("body")
    #                 or ""
    #             )
    #             email_from = (
    #                 raw_info.get("email_from")
    #                 or raw_info.get("sender")
    #                 or item.get("email_from")
    #                 or ""
    #             )

    #             headers_json = (
    #                 raw_info.get("headers_json") or item.get("headers_json") or {}
    #             )
    #             if isinstance(headers_json, str):
    #                 try:
    #                     headers_json = json.loads(headers_json)
    #                 except Exception:
    #                     headers_json = {}
    #             elif not isinstance(headers_json, dict):
    #                 headers_json = {"raw_headers": str(headers_json)}

    #             summary = headers_json.get("parsed_summary", {})
    #             inherited_bank = (
    #                 parsed.get("bank_name")
    #                 or summary.get("bank")
    #                 or item.get("bank_name")
    #                 or ""
    #             )

    #             freshly_parsed = parse_bank_email_body(
    #                 decrypted_body, sender=email_from, inherited_bank=inherited_bank
    #             )
    #             if freshly_parsed.get("is_parsed"):
    #                 parsed = freshly_parsed

    #             fp = parsed.get("txn_fingerprint") or item.get("id")
    #             payload_hash = item.get("payload_hash") or raw_info.get("payload_hash")

    #             already_exists = (
    #                 fp and RawEmailPayload.objects.filter(txn_fingerprint=fp).exists()
    #             ) or (
    #                 payload_hash
    #                 and RawEmailPayload.objects.filter(
    #                     payload_hash=payload_hash
    #                 ).exists()
    #             )
    #             if already_exists:
    #                 duplicates_count += 1
    #                 if fp:
    #                     committed_fps.append(fp)
    #                 continue

    #             target_last4 = parsed.get("account_last4")
    #             ledger_account_obj = None
    #             if target_last4 and LedgerAccount is not None:
    #                 try:
    #                     ledger_account_obj = LedgerAccount.objects.filter(
    #                         account_number__endswith=target_last4
    #                     ).first()
    #                 except Exception as e:
    #                     print(f"⚠️ Account lookup error during commit: {e}")

    #             final_account_id = ledger_account_obj.id if ledger_account_obj else None
    #             final_account_last4 = target_last4 if ledger_account_obj else None

    #             raw_email_date = (
    #                 raw_info.get("email_date")
    #                 or item.get("email_date")
    #                 or parsed.get("full_datetime")
    #                 or parsed.get("date")
    #             )
    #             parsed_email_date = safe_parse_datetime(raw_email_date)

    #             try:
    #                 clean_amount = Decimal(str(parsed.get("amount") or "0.00"))
    #             except Exception:
    #                 clean_amount = Decimal("0.00")

    #             headers_json.update(
    #                 {
    #                     "committed_via": "UI_TAB_1",
    #                     "committed_at": now_timestamp.isoformat(),
    #                     "processed_at": now_timestamp.isoformat(),
    #                     "account_id": (
    #                         str(final_account_id) if final_account_id else None
    #                     ),
    #                     "parsed_summary": {
    #                         "bank": parsed.get("bank_name") or inherited_bank,
    #                         "account": final_account_last4,
    #                         "amount": str(clean_amount),
    #                         "balance": parsed.get("balance"),
    #                         "upi_ref": parsed.get("upi_ref"),
    #                         "full_narration": parsed.get("full_narration"),
    #                     },
    #                 }
    #             )
    #             if parsed.get("metadata_json"):
    #                 headers_json.update(parsed["metadata_json"])

    #             raw_merchant = parsed.get("merchant") or "UNKNOWN VENDOR"
    #             raw_bank = parsed.get("bank_name") or inherited_bank or "UNKNOWN BANK"
    #             resolved_source = (
    #                 item.get("source")
    #                 or raw_info.get("source")
    #                 or headers_json.get("source")
    #                 or parsed.get("source")
    #                 or "GMAIL_API"
    #             )

    #             if not payload_hash:
    #                 hash_components = [
    #                     str(raw_bank),
    #                     str(final_account_last4 or "0000"),
    #                     str(clean_amount),
    #                     str(parsed_email_date.strftime("%Y-%m-%d %H:%M:%S")),
    #                     str(parsed.get("upi_ref") or fp),
    #                     decrypted_body,
    #                 ]
    #                 payload_hash = generate_payload_hash("_".join(hash_components))

    #             try:
    #                 record = RawEmailPayload.objects.create(
    #                     txn_fingerprint=fp,
    #                     encrypted_payload=raw_info.get("encrypted_payload") or "BYPASS",
    #                     payload_hash=payload_hash,
    #                     source=str(resolved_source)[:50],
    #                     sender=str(raw_info.get("sender") or email_from or "UNKNOWN")[
    #                         :255
    #                     ],
    #                     email_from=str(email_from or "UNKNOWN")[:255],
    #                     email_date=parsed_email_date,
    #                     subject=str(
    #                         raw_info.get("subject")
    #                         or item.get("subject")
    #                         or "NO_SUBJECT"
    #                     )[:255],
    #                     decrypted_body=decrypted_body,
    #                     headers_json=headers_json,
    #                     bank_name=str(raw_bank)[:100],
    #                     account_last4=final_account_last4,
    #                     amount=clean_amount,
    #                     txn_type=parsed.get("txn_type") or "DEBIT",
    #                     merchant=str(raw_merchant)[:255],
    #                     upi_ref=parsed.get("upi_ref"),
    #                     status=RawEmailPayload.ProcessingStatus.PARSED,
    #                     processed_at=now_timestamp,
    #                 )
    #                 saved_records.append(str(record.id))
    #             except IntegrityError:
    #                 duplicates_count += 1

    #             if fp:
    #                 committed_fps.append(fp)

    #         if committed_fps:
    #             remove_from_staging_buffer(committed_fps)

    #     return Response(
    #         {
    #             "status": "SUCCESS",
    #             "committed_count": len(saved_records),
    #             "duplicates_detected": duplicates_count,
    #             "ids": saved_records,
    #         },
    #         status=status.HTTP_201_CREATED,
    #     )
