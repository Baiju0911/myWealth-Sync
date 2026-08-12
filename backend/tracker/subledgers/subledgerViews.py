from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models.subledger import (
    AssetSubLedger,
    AssetOperationalAccount,
    AssetComplianceSchedule,
    AssetTransactionMapping,
)
from .serializers import (
    AssetSubLedgerSerializer,
    AssetOperationalAccountSerializer,
    AssetComplianceScheduleSerializer,
    CandidateMatchRequestSerializer,
    BindRowRequestSerializer,
)
from .services import AssetCandidateMatcher


class AssetSubLedgerViewSet(viewsets.ModelViewSet):
    queryset = AssetSubLedger.objects.all().prefetch_related(
        "operational_accounts", "compliance_schedules"
    )
    serializer_class = AssetSubLedgerSerializer

    @action(detail=False, methods=["post"], url_path="find-candidates")
    def find_candidates(self, request):
        serializer = CandidateMatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        candidates = AssetCandidateMatcher.find_candidate_rows(
            document_date=data["document_date"],
            target_amount=data["target_amount"],
            account_id=data.get("account_id"),
            keywords=data.get("keywords", []),
            day_window=data.get("day_window", 10),
        )

        return Response(
            {
                "query": data,
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="bind-transaction")
    def bind_transaction(self, request):
        serializer = BindRowRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            asset = AssetSubLedger.objects.get(id=data["asset_id"])

            schedule = None
            if data.get("schedule_id"):
                schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
                schedule.is_paid = True
                schedule.paid_at = timezone.now()
                schedule.linked_row_identifier = data.get("row_identifier")
                schedule.save()

            op_account = None
            if data.get("operational_account_id"):
                op_account = AssetOperationalAccount.objects.get(
                    id=data["operational_account_id"]
                )

            mapping = AssetTransactionMapping.objects.create(
                asset=asset,
                operational_account=op_account,
                schedule=schedule,
                row_identifier=data.get("row_identifier"),
                is_cash_entry=data.get("is_cash_entry", False),
                transaction_date=data["transaction_date"],
                amount=data["amount"],
                transaction_purpose=data["transaction_purpose"],
                user_note=data.get("user_note", ""),
            )

        return Response(
            {
                "status": "SUCCESS",
                "mapping_id": str(mapping.id),
                "message": "Transaction bound to sub-ledger.",
            },
            status=status.HTTP_201_CREATED,
        )


class AssetOperationalAccountViewSet(viewsets.ModelViewSet):
    queryset = AssetOperationalAccount.objects.all()
    serializer_class = AssetOperationalAccountSerializer


class AssetComplianceScheduleViewSet(viewsets.ModelViewSet):
    queryset = AssetComplianceSchedule.objects.all()
    serializer_class = AssetComplianceScheduleSerializer

    @action(detail=False, methods=["get"], url_path="pending-dues")
    def pending_dues(self, request):
        schedules = self.queryset.filter(is_paid=False).order_by("due_date")
        serializer = self.get_serializer(schedules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
