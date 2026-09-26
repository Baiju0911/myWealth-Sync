import logging
import time

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tracker.models import DocumentInboxItem, StatementStagingLine, RawEmailPayload
from tracker.constants import (
    EnrichmentMetadata,
    SystemDefaults,
    BankNames,
    ACTIVE_STAGED_PAYLOAD_STATUSES,
)
from .InboxHelper import LiveStreamEnrichmentService
from .InboxHelper.inbox_serializer import LiveStreamPayloadSerializer

logger = logging.getLogger(__name__)


class PendingInboxItemsView(APIView):
    def get(self, request):
        try:
            pending_items = (
                DocumentInboxItem.objects.filter(
                    status__in=["INBOX", "PENDING", "PROCESSING", "FAILED"]
                )
                .order_by("-received_date", "-created_at")
                .values(
                    "id",
                    "filename",
                    "account_hint",
                    "bank_name",
                    "period_start",
                    "period_end",
                    "status",
                    "received_date",
                    "file_path",
                )
            )
            return Response(list(pending_items), status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Error fetching pending inbox items: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class InboxItemPreviewView(APIView):
    def post(self, request, item_id):
        from tracker.parsers.parsers_v1.inbox.inbox_service import InboxStatementService

        try:
            preview_data = InboxStatementService.preview_inbox_item(str(item_id))
            return Response(preview_data, status=status.HTTP_200_OK)
        except PermissionError as perm_err:
            return Response(
                {
                    "status": "DECRYPTION_FAILED",
                    "inbox_item_id": str(item_id),
                    "error": str(perm_err),
                    "requires_password": True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FileNotFoundError as fnf_err:
            return Response(
                {
                    "status": "FILE_NOT_FOUND",
                    "inbox_item_id": str(item_id),
                    "error": str(fnf_err),
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.exception(f"Error previewing inbox item {item_id}: {str(e)}")
            return Response(
                {"status": "ERROR", "inbox_item_id": str(item_id), "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class InboxItemCommitView(APIView):
    def post(self, request, item_id):
        from tracker.parsers.parsers_v1.inbox.inbox_service import InboxStatementService

        try:
            preview_dataset = request.data.get("preview_dataset", [])
            meta_summary = request.data.get("meta_summary", {})
            commit_result = InboxStatementService.commit_inbox_item(
                inbox_item_id=str(item_id),
                preview_dataset=preview_dataset,
                meta_summary=meta_summary,
            )
            return Response(commit_result, status=status.HTTP_200_OK)
        except ValueError as val_err:
            return Response({"error": str(val_err)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(f"Error committing inbox item {item_id}: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# class LiveStreamPayloadsView(APIView):
#     def get(self, request):
#         try:
#             active_statuses = ACTIVE_STAGED_PAYLOAD_STATUSES + ["PREVIEW_ONLY"]
#             base_qs = RawEmailPayload.objects.filter(
#                 status__in=active_statuses,
#                 is_completed=0,
#             ).order_by("-created_at")

#             total_staged_count = base_qs.count()
#             limit = int(request.query_params.get("limit", 200))
#             records = base_qs[:limit]

#             results = []
#             for r in records:
#                 headers = r.headers_json or {}
#                 parsed = headers.get("parsed_summary", {})
#                 merchant_name = (
#                     parsed.get("merchant")
#                     or headers.get("merge_details", {}).get("resolved_narration")
#                     or parsed.get("full_narration")
#                     or r.subject
#                 )
#                 results.append(
#                     {
#                         "id": str(r.id),
#                         "source": r.source
#                         or headers.get("source", EnrichmentMetadata.DEFAULT_SOURCE),
#                         "sender": r.sender,
#                         "amount": (
#                             r.amount if r.amount is not None else parsed.get("amount")
#                         ),
#                         "balance": parsed.get("balance"),
#                         "account_last4": r.account_last4 or parsed.get("account"),
#                         "bank_name": parsed.get("bank") or BankNames.SOUTH_INDIAN.value,
#                         "upi_ref": (
#                             r.upi_ref
#                             or headers.get("merge_details", {}).get("matched_rrn")
#                             or parsed.get("upi_ref")
#                             or parsed.get("utr_no")
#                         ),
#                         "status": r.status,
#                         "created_at": (
#                             r.created_at.isoformat() if r.created_at else None
#                         ),
#                         "full_narration": parsed.get("full_narration")
#                         or r.decrypted_body,
#                         "merchant": merchant_name,
#                     }
#                 )

#             return Response(
#                 {"total_count": total_staged_count, "results": results},
#                 status=status.HTTP_200_OK,
#             )
#         except Exception as e:
#             logger.exception(f"Error fetching live stream payloads: {str(e)}")
#             return Response(
#                 {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


class LiveStreamPayloadsView(APIView):
    def get(self, request):
        try:
            active_statuses = ACTIVE_STAGED_PAYLOAD_STATUSES + ["PREVIEW_ONLY"]
            base_qs = RawEmailPayload.objects.filter(
                status__in=active_statuses,
                is_completed=0,
            ).order_by("-created_at")

            total_staged_count = base_qs.count()
            limit = int(request.query_params.get("limit", 200))
            records = base_qs[:limit]

            results = [LiveStreamPayloadSerializer.serialize_record(r) for r in records]

            return Response(
                {"total_count": total_staged_count, "results": results},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception(f"Error fetching live stream payloads: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LiveStreamCommitEnrichmentView(APIView):
    """
    HTTP controller invoking LiveStreamEnrichmentService within a single database transaction.
    """

    @transaction.atomic
    def post(self, request):
        start_time = time.perf_counter()
        try:
            result = LiveStreamEnrichmentService.execute_pipeline()
            result["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
            result["status"] = "SUCCESS"
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Error in LiveStreamCommitEnrichmentView: {str(e)}")
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnrichedReconciliationAuditView(APIView):
    def get(self, request):
        limit = int(request.query_params.get("limit", 200))
        stmt_qs = (
            StatementStagingLine.objects.filter(is_enriched_from_live=1)
            .select_related("account", "bank", "account__bank")
            .order_by("-raw_statement_date")
        )
        total_count = stmt_qs.count()
        stmt_records = list(stmt_qs[:limit])

        payload_id_map = {}
        for line in stmt_records:
            meta = line.live_metadata or {}
            raw_id = meta.get("raw_payload_id")
            if raw_id:
                payload_id_map[line.id] = str(raw_id).strip()

        raw_ids = list(set(payload_id_map.values()))
        donor_payloads = {
            str(p.id): p for p in RawEmailPayload.objects.filter(id__in=raw_ids)
        }

        results = []
        for line in stmt_records:
            donor_id = payload_id_map.get(line.id)
            donor = donor_payloads.get(donor_id)
            meta = line.live_metadata or {}
            bank_obj = line.bank or (line.account.bank if line.account else None)
            resolved_bank_name = (
                getattr(bank_obj, "display_name", None)
                or getattr(bank_obj, "bank_name", None)
                or getattr(bank_obj, "name", None)
                or (donor.bank_name if donor else None)
                or SystemDefaults.BANK.value
            )

            results.append(
                {
                    "statement_id": str(line.id),
                    "statement_date": line.raw_statement_date.isoformat(),
                    "statement_amount": float(line.amount),
                    "raw_narration": meta.get("original_narration") or line.narration,
                    "account_last4": (
                        line.account.account_number[-4:]
                        if line.account and line.account.account_number
                        else SystemDefaults.EMPTY_STRING.value
                    ),
                    "bank_name": resolved_bank_name,
                    "payload_id": donor_id,
                    "stream_source": (
                        donor.source
                        if donor
                        else meta.get("source", EnrichmentMetadata.DEFAULT_SOURCE)
                    ),
                    "resolved_merchant": (
                        donor.merchant
                        if donor
                        else meta.get("merchant", EnrichmentMetadata.DEFAULT_MERCHANT)
                    ),
                    "live_upi_rrn": line.live_upi_rrn
                    or (donor.upi_ref if donor else None)
                    or SystemDefaults.DASH.value,
                    "enriched_at": meta.get("enriched_at"),
                    "completed_at": (
                        donor.completed_at.isoformat()
                        if (donor and donor.completed_at)
                        else None
                    ),
                    "has_warning": meta.get("has_amount_discrepancy", False),
                    "discrepancy_details": meta.get("discrepancy_details"),
                }
            )

        return Response(
            {"total_count": total_count, "results": results}, status=status.HTTP_200_OK
        )
