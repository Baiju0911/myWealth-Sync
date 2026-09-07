import os
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import pypdf
import io
from django.http import HttpResponse, FileResponse

from tracker.models.emailModels import DocumentInboxItem
from tracker.emailIngest.attachment_harvester import AttachmentHarvesterService
from tracker.emailIngest.serializers import DocumentInboxItemSerializer


class DocumentInboxViewSet(viewsets.ModelViewSet):
    """Manages harvested PDF attachments.

    Provides a two-step workflow:
      1. Harvesting attachments into media/documents/staged_inbox.json.
      2. Reviewing staged items and committing selected items to the database.
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
        """Returns list of documents committed in the database."""
        qs = self.get_queryset()
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
        """Scans Gmail API and stages attachments into staged_inbox.json without writing to DB."""
        max_results = int(request.data.get("max_results", 25))
        try:
            service = AttachmentHarvesterService()
            staged_items = service.harvest_bank_attachments(max_results=max_results)

            return Response(
                {
                    "status": "SUCCESS",
                    "message": f"Harvested and staged {len(staged_items)} attachment(s) to JSON manifest.",
                    "staged_count": len(staged_items),
                    "items": staged_items,  # 👈 Return plain list of dicts directly
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

    @action(detail=False, methods=["post"], url_path="preview-staged")
    def preview_staged_pdf(self, request):
        """Streams a staged PDF file for browser viewing.

        If the PDF is encrypted, attempts decryption with the provided password.
        Returns 423 Locked if password is missing or incorrect.
        """
        file_path = request.data.get("file_path")
        password = request.data.get("password", "")

        if not file_path or not os.path.exists(file_path):
            return Response(
                {"error": "File not found on disk"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            reader = pypdf.PdfReader(file_path)
            if reader.is_encrypted:
                if not password:
                    return Response(
                        {
                            "is_encrypted": True,
                            "error": "Password required to view this statement.",
                        },
                        status=status.HTTP_423_LOCKED,
                    )

                # Attempt decrypt
                decrypt_success = reader.decrypt(password)
                if not decrypt_success:
                    return Response(
                        {"is_encrypted": True, "error": "Incorrect password."},
                        status=status.HTTP_423_LOCKED,
                    )

                # Write decrypted stream into memory to serve
                writer = pypdf.PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)

                out_buffer = io.BytesIO()
                writer.write(out_buffer)
                out_buffer.seek(0)
                return FileResponse(out_buffer, content_type="application/pdf")

            # Not encrypted -> stream direct file
            return FileResponse(open(file_path, "rb"), content_type="application/pdf")

        except Exception as e:
            return Response(
                {"error": f"Failed to read PDF: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="staged")
    def list_staged(self, request):
        """Returns all uncommitted items from staged_inbox.json for UI review."""
        service = AttachmentHarvesterService()
        items = service.load_staged_manifest()
        return Response(
            {
                "status": "SUCCESS",
                "count": len(items),
                "results": items,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="commit")
    def commit_selected(self, request):
        """Commits selected staged items from staged_inbox.json into DocumentInboxItem DB records."""
        selected_ids = request.data.get("selected_ids", [])
        overrides = request.data.get("overrides", {})

        if not selected_ids:
            return Response(
                {
                    "status": "ERROR",
                    "message": "No stage IDs provided for commitment.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = AttachmentHarvesterService()
        committed_records = service.commit_staged_items(selected_ids, overrides)
        serializer = self.get_serializer(committed_records, many=True)

        return Response(
            {
                "status": "SUCCESS",
                "message": f"Successfully committed {len(committed_records)} items to the database.",
                "committed_items": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="mark-completed")
    def complete_item(self, request, pk=None):
        """Moves the physical file from inbox/ to completed/ and marks status as COMPLETED."""
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
        """Marks document as ARCHIVED or purges unneeded statement from inbox."""
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
