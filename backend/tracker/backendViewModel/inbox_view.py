import logging
import time

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tracker.models import (
    DocumentInboxItem,
    StatementStagingLine,
    RawEmailPayload,
    JournalEntry,
)
from tracker.constants import (
    EnrichmentMetadata,
    SystemDefaults,
    BankNames,
    ACTIVE_STAGED_PAYLOAD_STATUSES,
)
from .InboxHelper import LiveStreamEnrichmentService
from .InboxHelper.inbox_serializer import LiveStreamPayloadSerializer
from tracker.parsers.universal_narration import UniversalNarrationExtractor

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
        row_identifiers = []
        for line in stmt_records:
            meta = line.live_metadata or {}
            raw_id = meta.get("raw_payload_id")
            if raw_id:
                payload_id_map[line.id] = str(raw_id).strip()
            if line.row_identifier:
                row_identifiers.append(line.row_identifier)

        raw_ids = list(set(payload_id_map.values()))
        donor_payloads = {
            str(p.id): p for p in RawEmailPayload.objects.filter(id__in=raw_ids)
        }

        # Bulk fetch counter legs for auto-sweep classification footprint
        counter_legs = {}
        if row_identifiers:
            for je in JournalEntry.objects.filter(
                row_identifier__in=row_identifiers
            ).select_related("account"):
                counter_legs[je.row_identifier] = je

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

            # Build classification footprint if journal leg exists
            je_leg = counter_legs.get(line.row_identifier)
            classification_data = None
            if je_leg:
                snap = je_leg.evaluation_matrix_snapshot or {}
                cat = (
                    snap.get("resolved_category")
                    or (
                        je_leg.account.category
                        if hasattr(je_leg.account, "category")
                        else None
                    )
                    or "Node 99"
                )
                subcat = (
                    snap.get("resolved_subcategory")
                    or (
                        je_leg.account.subcategory
                        if hasattr(je_leg.account, "subcategory")
                        else None
                    )
                    or "Suspense"
                )
                rule_code = snap.get("applied_rule_code") or "AUTO_SWEEP_INITIAL"
                classification_data = {
                    "target_account": f"{cat} > {subcat}",
                    "rule_code": rule_code,
                    "status": getattr(je_leg, "classification_status", "PARKED"),
                    "user_note": snap.get("user_note", ""),
                }

            # 🛡️ Invoke Authoritative Universal Extractor
            parsed_info = UniversalNarrationExtractor.resolve_from_staging_line(line)
            resolved_merchant = parsed_info["suggested_payee"]
            clean_remark = parsed_info["suggested_remark"]
            synthesized_narration = (
                f"{resolved_merchant} ({clean_remark})"
                if clean_remark
                else resolved_merchant
            )

            results.append(
                {
                    "statement_id": str(line.id),
                    "statement_date": line.raw_statement_date.isoformat(),
                    "statement_amount": float(line.amount),
                    "running_balance": (
                        float(line.running_balance)
                        if line.running_balance is not None
                        else None
                    ),
                    "debit": float(line.debit) if line.debit is not None else None,
                    "credit": float(line.credit) if line.credit is not None else None,
                    "raw_narration": parsed_info["raw_statement_narration"],
                    "account_last4": (
                        line.account.account_number[-4:]
                        if line.account and line.account.account_number
                        else SystemDefaults.EMPTY_STRING.value
                    ),
                    "bank_name": resolved_bank_name,
                    "payload_id": meta.get("raw_payload_id") or donor_id,
                    "stream_source": (
                        donor.source
                        if donor
                        else meta.get("source", EnrichmentMetadata.DEFAULT_SOURCE)
                    ),
                    "resolved_merchant": resolved_merchant,
                    "remark": clean_remark,
                    "resolved_narration": synthesized_narration,
                    "live_upi_rrn": (
                        line.live_upi_rrn
                        or (donor.upi_ref if donor else None)
                        or SystemDefaults.DASH.value
                    ),
                    "enriched_at": meta.get("enriched_at"),
                    "completed_at": (
                        donor.completed_at.isoformat()
                        if (donor and donor.completed_at)
                        else None
                    ),
                    "match_tier": meta.get(
                        "matched_tier",
                        (
                            "TIER 1 (RRN Exact Match)"
                            if line.live_upi_rrn
                            else "TIER 2 (Hex Fingerprint)"
                        ),
                    ),
                    "donor_raw_snippet": (
                        meta.get("donor_raw_snippet")
                        or (
                            donor.snippet
                            if donor and hasattr(donor, "snippet")
                            else None
                        )
                        or (
                            donor.body_text[:120]
                            if donor and hasattr(donor, "body_text") and donor.body_text
                            else None
                        )
                        or (donor.subject if donor else None)
                    ),
                    "routing_status": getattr(line, "routing_status", "PENDING"),
                    "classification": classification_data,
                    "has_warning": meta.get("has_amount_discrepancy", False),
                    "discrepancy_details": meta.get("discrepancy_details"),
                    # New full telemetry package for modals
                    "parsed_narration": parsed_info,
                }
            )

        return Response(
            {"total_count": total_count, "results": results}, status=status.HTTP_200_OK
        )
