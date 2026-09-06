import os
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from tracker.models.emailModels import DocumentInboxItem
from tracker.emailIngest.attachment_harvester import AttachmentHarvesterService
from .emailViewhelper import safe_parse_datetime
from tracker.emailIngest.serializers import DocumentInboxItemSerializer


class DocumentInboxViewSet(viewsets.ModelViewSet):
    """Manages harvested PDF attachments (Bank Statements and Term Deposit

    Advices).

    Serves the document inbox for Step 1 Statement Ingestion and Step 2
    Auto-Sweep.
    """

    queryset = DocumentInboxItem.objects.all().order_by("-received_date", "-created_at")
    serializer_class = DocumentInboxItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status", "INBOX")
        doc_type = self.request.query_params.get("doc_type")
        account = self.request.query_params.get(
            "account"
        ) or self.request.query_params.get("account_last4")

        if status_param and status_param != "ALL":
            qs = qs.filter(status=status_param)

        if doc_type and doc_type != "ALL":
            qs = qs.filter(doc_type=doc_type)

        if account and account != "ALL":
            qs = qs.filter(account_hint=account)

        return qs

    def list(self, request, *args, **kwargs):
        """Returns list of documents formatted cleanly using DocumentInboxItemSerializer."""
        qs = self.get_queryset()
        # Delegate serialization directly to DocumentInboxItemSerializer
        serializer = self.get_serializer(qs, many=True)

        return Response(
            {
                "status": "SUCCESS",
                "count": qs.count(),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="harvest")
    def trigger_harvest(self, request):
        """Scans Gmail API for bank emails with PDF attachments and stages them

        into media/documents/inbox/.
        """
        max_results = int(request.data.get("max_results", 25))
        try:
            service = AttachmentHarvesterService()
            harvested_items = service.harvest_bank_attachments(max_results=max_results)

            # Use DocumentInboxItemSerializer to serialize harvested items
            serializer = self.get_serializer(harvested_items, many=True)

            return Response(
                {
                    "status": "SUCCESS",
                    "message": f"Harvested {len(harvested_items)} new attachment(s).",
                    "downloaded_count": len(harvested_items),
                    "items": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "status": "ERROR",
                    "message": f"Attachment harvesting failed: {str(e)}",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="mark-completed")
    def complete_item(self, request, pk=None):
        """Moves the physical file from inbox/ to completed/ and marks status as

        COMPLETED.
        """
        try:
            item = self.get_object()
            item.mark_completed()
            return Response(
                {
                    "status": "SUCCESS",
                    "message": f"'{item.filename}' marked as completed and moved to archive storage.",
                    "new_path": item.file_path,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "ERROR", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="discard")
    def discard_item(self, request, pk=None):
        """Marks document as ARCHIVED or purges unneeded statement from

        inbox.
        """
        try:
            item = self.get_object()
            item.mark_archived()
            return Response(
                {
                    "status": "SUCCESS",
                    "message": f"'{item.filename}' discarded from active inbox.",
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "ERROR", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
