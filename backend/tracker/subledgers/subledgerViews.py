from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.decorators import api_view

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

# class AssetSubLedgerViewSet(viewsets.ModelViewSet):
#     queryset = AssetSubLedger.objects.all().prefetch_related(
#         "operational_accounts", "compliance_schedules"
#     )
#     serializer_class = AssetSubLedgerSerializer

#     def create(self, request, *args, **kwargs):
#         print("\n==================================================")
#         print("📥 [ASSET CREATE] INCOMING REQUEST DATA:")
#         print(f"Payload: {request.data}")
#         print(
#             f"Type of linked_gl_account: {type(request.data.get('linked_gl_account'))}"
#         )
#         print("==================================================\n")
#         return super().create(request, *args, **kwargs)

#     def update(self, request, *args, **kwargs):
#         print("\n==================================================")
#         print("📥 [ASSET UPDATE] INCOMING REQUEST DATA:")
#         print(f"Payload: {request.data}")
#         print(
#             f"Type of linked_gl_account: {type(request.data.get('linked_gl_account'))}"
#         )
#         print("==================================================\n")
#         return super().update(request, *args, **kwargs)

#     @action(detail=False, methods=["post"], url_path="find-candidates")
#     def find_candidates(self, request):
#         print("\n==================================================")
#         print("📥 [FIND CANDIDATES] INCOMING RAW DATA:")
#         print(f"Payload: {request.data}")
#         print("==================================================")

#         serializer = CandidateMatchRequestSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         data = serializer.validated_data

#         candidates = AssetCandidateMatcher.find_candidate_rows(
#             document_date=data["document_date"],
#             target_amount=data.get("target_amount"),
#             account_id=data.get("account_id"),
#             keywords=data.get("keywords", []),
#             day_window=data.get("day_window", 10),
#             asset_id=data.get("asset_id"),  # 👈 Pass asset_id here
#         )

#         print(
#             f"✅ [FIND CANDIDATES] MATCHES RETURNED: {len(candidates)} total rows (Bound + Unmapped)"
#         )
#         print("==================================================\n")

#         return Response(
#             {
#                 "query": data,
#                 "candidate_count": len(candidates),
#                 "candidates": candidates,
#             },
#             status=status.HTTP_200_OK,
#         )

#     @action(detail=False, methods=["post"], url_path="bind-transaction")
#     def bind_transaction(self, request):
#         serializer = BindRowRequestSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         data = serializer.validated_data

#         with transaction.atomic():
#             asset = AssetSubLedger.objects.get(id=data["asset_id"])

#             schedule = None
#             if data.get("schedule_id"):
#                 schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
#                 schedule.is_paid = True
#                 schedule.paid_at = timezone.now()
#                 schedule.linked_row_identifier = data.get("row_identifier")
#                 schedule.save()

#             op_account = None
#             if data.get("operational_account_id"):
#                 op_account = AssetOperationalAccount.objects.get(
#                     id=data["operational_account_id"]
#                 )

#             mapping = AssetTransactionMapping.objects.create(
#                 asset=asset,
#                 operational_account=op_account,
#                 schedule=schedule,
#                 row_identifier=data.get("row_identifier"),
#                 is_cash_entry=data.get("is_cash_entry", False),
#                 transaction_date=data["transaction_date"],
#                 amount=data["amount"],
#                 transaction_purpose=data["transaction_purpose"],
#                 user_note=data.get("user_note", ""),
#             )

#         return Response(
#             {
#                 "status": "SUCCESS",
#                 "mapping_id": str(mapping.id),
#                 "message": "Transaction bound to sub-ledger.",
#             },
#             status=status.HTTP_201_CREATED,
#         )

#     @action(detail=True, methods=["get"], url_path="mapped-transactions")
#     def mapped_transactions(self, request, pk=None):
#         """
#         GET /api/subledgers/assets/{id}/mapped-transactions/
#         Lists all journal entries currently bound to this specific asset.
#         """
#         from tracker.models import JournalEntry

#         asset = self.get_object()
#         mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
#             row_identifier__isnull=True
#         )

#         row_identifiers = mappings.values_list("row_identifier", flat=True)

#         journal_entries = JournalEntry.objects.filter(
#             row_identifier__in=row_identifiers, account_id=99
#         ).values(
#             "id", "row_identifier", "transaction_date", "debit", "credit", "remarks"
#         )

#         mapping_lookup = {m.row_identifier: m for m in mappings}

#         results = []
#         for entry in journal_entries:
#             m_obj = mapping_lookup.get(entry["row_identifier"])
#             results.append(
#                 {
#                     "mapping_id": str(m_obj.id) if m_obj else None,
#                     "journal_id": str(entry["id"]),
#                     "row_identifier": entry["row_identifier"],
#                     "transaction_date": entry["transaction_date"].strftime("%Y-%m-%d"),
#                     "debit": float(entry["debit"]),
#                     "credit": float(entry["credit"]),
#                     "remarks": entry["remarks"],
#                     "mapped_at": (
#                         m_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
#                         if m_obj and hasattr(m_obj, "created_at")
#                         else None
#                     ),
#                 }
#             )

#         return Response(
#             {
#                 "status": "success",
#                 "asset_id": asset.id,
#                 "asset_code": asset.asset_code,
#                 "asset_name": asset.asset_name,
#                 "mapped_transactions": results,
#             },
#             status=status.HTTP_200_OK,
#         )

#     @action(detail=False, methods=["post"], url_path="unmap-transaction")
#     def unmap_asset_transaction_view(request):
#         """
#         API endpoint to unbind/disconnect a transaction from an asset sub-ledger.
#         Expects JSON: {"mapping_id": ...} or {"row_identifier": ..., "asset_id": ...}
#         """
#         from tracker.models.subledger import AssetTransactionMapping

#         mapping_id = request.data.get("mapping_id")
#         row_identifier = request.data.get("row_identifier")
#         asset_id = request.data.get("asset_id")

#         try:
#             if mapping_id:
#                 mapping = AssetTransactionMapping.objects.get(id=mapping_id)
#             elif row_identifier and asset_id:
#                 mapping = AssetTransactionMapping.objects.get(
#                     row_identifier=row_identifier, asset_id=asset_id
#                 )
#             else:
#                 return Response(
#                     {"status": "error", "message": "Missing mapping parameters."},
#                     status=400,
#                 )

#             mapping.delete()
#             return Response(
#                 {"status": "success", "message": "Transaction successfully unmapped."}
#             )

#         except AssetTransactionMapping.DoesNotExist:
#             return Response(
#                 {"status": "error", "message": "Mapping record not found."}, status=404
#             )
#         except Exception as e:
#             return Response({"status": "error", "message": str(e)}, status=400)


class AssetSubLedgerViewSet(viewsets.ModelViewSet):
    queryset = AssetSubLedger.objects.all().prefetch_related(
        "operational_accounts", "compliance_schedules"
    )
    serializer_class = AssetSubLedgerSerializer

    def create(self, request, *args, **kwargs):
        print("\n==================================================")
        print("📥 [ASSET CREATE] INCOMING REQUEST DATA:")
        print(f"Payload: {request.data}")
        print(
            f"Type of linked_gl_account: {type(request.data.get('linked_gl_account'))}"
        )
        print("==================================================\n")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        print("\n==================================================")
        print("📥 [ASSET UPDATE] INCOMING REQUEST DATA:")
        print(f"Payload: {request.data}")
        print(
            f"Type of linked_gl_account: {type(request.data.get('linked_gl_account'))}"
        )
        print("==================================================\n")
        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="find-candidates")
    def find_candidates(self, request):
        print("\n==================================================")
        print("📥 [FIND CANDIDATES] INCOMING RAW DATA:")
        print(f"Payload: {request.data}")
        print("==================================================")

        serializer = CandidateMatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        candidates = AssetCandidateMatcher.find_candidate_rows(
            document_date=data["document_date"],
            target_amount=data.get("target_amount"),
            account_id=data.get("account_id"),
            keywords=data.get("keywords", []),
            day_window=data.get("day_window", 10),
            asset_id=data.get("asset_id"),
        )

        print(
            f"✅ [FIND CANDIDATES] MATCHES RETURNED: {len(candidates)} total rows (Bound + Unmapped)"
        )
        print("==================================================\n")

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

    @action(detail=True, methods=["get"], url_path="mapped-transactions")
    def mapped_transactions(self, request, pk=None):
        """
        GET /api/subledgers/assets/{id}/mapped-transactions/
        Lists all journal entries currently bound to this specific asset.
        """
        from tracker.models import JournalEntry

        asset = self.get_object()
        mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
            row_identifier__isnull=True
        )

        row_identifiers = mappings.values_list("row_identifier", flat=True)

        journal_entries = JournalEntry.objects.filter(
            row_identifier__in=row_identifiers, account_id=99
        ).values(
            "id", "row_identifier", "transaction_date", "debit", "credit", "remarks"
        )

        mapping_lookup = {m.row_identifier: m for m in mappings}

        results = []
        for entry in journal_entries:
            m_obj = mapping_lookup.get(entry["row_identifier"])
            results.append(
                {
                    "mapping_id": str(m_obj.id) if m_obj else None,
                    "journal_id": str(entry["id"]),
                    "row_identifier": entry["row_identifier"],
                    "transaction_date": entry["transaction_date"].strftime("%Y-%m-%d"),
                    "debit": float(entry["debit"]),
                    "credit": float(entry["credit"]),
                    "remarks": entry["remarks"],
                    "mapped_at": (
                        m_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        if m_obj and hasattr(m_obj, "created_at")
                        else None
                    ),
                }
            )

        return Response(
            {
                "status": "success",
                "asset_id": asset.id,
                "asset_code": asset.asset_code,
                "asset_name": asset.name,  # 👈 Fixed: asset.name instead of asset.asset_name
                "mapped_transactions": results,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="unmap-transaction")
    def unmap_asset_transaction_view(self, request):  # 👈 Fixed: Added 'self' argument
        """
        API endpoint to unbind/disconnect a transaction from an asset sub-ledger.
        Expects JSON: {"mapping_id": ...} or {"row_identifier": ..., "asset_id": ...}
        """
        from tracker.models.subledger import AssetTransactionMapping

        mapping_id = request.data.get("mapping_id")
        row_identifier = request.data.get("row_identifier")
        asset_id = request.data.get("asset_id")

        try:
            if mapping_id:
                mapping = AssetTransactionMapping.objects.get(id=mapping_id)
            elif row_identifier and asset_id:
                mapping = AssetTransactionMapping.objects.get(
                    row_identifier=row_identifier, asset_id=asset_id
                )
            else:
                return Response(
                    {"status": "error", "message": "Missing mapping parameters."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            mapping.delete()
            return Response(
                {"status": "success", "message": "Transaction successfully unmapped."},
                status=status.HTTP_200_OK,
            )

        except AssetTransactionMapping.DoesNotExist:
            return Response(
                {"status": "error", "message": "Mapping record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
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
