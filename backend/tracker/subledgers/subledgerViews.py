from decimal import Decimal
from django.db.models import Q
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

# 🏛️ Core Tracker Models Import
from tracker.models import JournalEntry

# 🏛️ Subledger Models Import
from ..models.subledger import (
    AssetCategory,
    AssetComplianceSchedule,
    AssetOperationalAccount,
    AssetSubLedger,
    AssetTransactionMapping,
)

# 🎨 Serializers Import
from .serializers import (
    AssetCategorySerializer,
    AssetComplianceScheduleSerializer,
    AssetOperationalAccountSerializer,
    AssetSubLedgerSerializer,
    BindRowRequestSerializer,
    CandidateMatchRequestSerializer,
)

# 🛠️ Services Import
from .services import AssetCandidateMatcher


class AssetSubLedgerViewSet(viewsets.ModelViewSet):
    queryset = AssetSubLedger.objects.all().prefetch_related(
        "operational_accounts", "compliance_schedules"
    )
    serializer_class = AssetSubLedgerSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        subcategory = self.request.query_params.get("subcategory")

        if subcategory:
            subcategory = subcategory.strip()

            # 🎯 Safe multi-field filter using direct fields & foreign key traversal
            q_filters = Q(name__icontains=subcategory) | Q(
                asset_code__icontains=subcategory
            )

            # Check for related category name (Foreign key or string)
            if hasattr(AssetSubLedger, "asset_category"):
                q_filters |= Q(asset_category__name__icontains=subcategory)
            if hasattr(AssetSubLedger, "category"):
                q_filters |= Q(category__icontains=subcategory)

            # Check for related GL account
            if hasattr(AssetSubLedger, "linked_gl_account"):
                # If linked_gl_account is integer/FK vs string
                q_filters |= Q(linked_gl_account__icontains=subcategory)

            queryset = queryset.filter(q_filters)

        return queryset

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
        """GET /api/subledgers/assets/{id}/mapped-transactions/

        Lists all journal entries currently bound to this specific asset.
        """
        asset = self.get_object()
        mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
            row_identifier__isnull=True
        )

        row_identifiers = mappings.values_list("row_identifier", flat=True)

        journal_entries = JournalEntry.objects.filter(
            row_identifier__in=row_identifiers, account_id=99
        ).values(
            "id",
            "row_identifier",
            "transaction_date",
            "debit",
            "credit",
            "remarks",
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
                "asset_name": asset.name,
                "mapped_transactions": results,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="unmap-transaction")
    def unmap_asset_transaction_view(self, request):
        """API endpoint to unbind/disconnect a transaction from an asset sub-ledger.

        Expects JSON: {"mapping_id": ...} or {"row_identifier": ..., "asset_id": ...}
        """
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
                    {
                        "status": "error",
                        "message": "Missing mapping parameters.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            mapping.delete()
            return Response(
                {
                    "status": "success",
                    "message": "Transaction successfully unmapped.",
                },
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


# class AssetSubLedgerViewSet(viewsets.ModelViewSet):
#     queryset = AssetSubLedger.objects.all().prefetch_related(
#         "operational_accounts", "compliance_schedules"
#     )
#     serializer_class = AssetSubLedgerSerializer

#     def get_queryset(self):
#         queryset = super().get_queryset()
#         subcategory = self.request.query_params.get("subcategory")

#         if subcategory:
#             subcategory = subcategory.strip()
#             # 🎯 Search against valid model fields (category, name, asset_code, linked_gl_account)
#             queryset = queryset.filter(
#                 Q(name__icontains=subcategory)
#                 | Q(asset_code__icontains=subcategory)
#                 | Q(
#                     category__name__icontains=subcategory
#                 )  # If category is a ForeignKey
#                 | Q(
#                     linked_gl_account__name__icontains=subcategory
#                 )  # If linked_gl_account is a ForeignKey
#             )

#         return queryset

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
#             asset_id=data.get("asset_id"),
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
#         """GET /api/subledgers/assets/{id}/mapped-transactions/

#         Lists all journal entries currently bound to this specific asset.
#         """
#         asset = self.get_object()
#         mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
#             row_identifier__isnull=True
#         )

#         row_identifiers = mappings.values_list("row_identifier", flat=True)

#         journal_entries = JournalEntry.objects.filter(
#             row_identifier__in=row_identifiers, account_id=99
#         ).values(
#             "id",
#             "row_identifier",
#             "transaction_date",
#             "debit",
#             "credit",
#             "remarks",
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
#                 "asset_name": asset.name,
#                 "mapped_transactions": results,
#             },
#             status=status.HTTP_200_OK,
#         )

#     @action(detail=False, methods=["post"], url_path="unmap-transaction")
#     def unmap_asset_transaction_view(self, request):
#         """API endpoint to unbind/disconnect a transaction from an asset sub-
#         ledger.

#         Expects JSON: {"mapping_id": ...} or {"row_identifier": ..., "asset_id":
#         ...}
#         """
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
#                     {
#                         "status": "error",
#                         "message": "Missing mapping parameters.",
#                     },
#                     status=status.HTTP_400_BAD_REQUEST,
#                 )

#             mapping.delete()
#             return Response(
#                 {
#                     "status": "success",
#                     "message": "Transaction successfully unmapped.",
#                 },
#                 status=status.HTTP_200_OK,
#             )

#         except AssetTransactionMapping.DoesNotExist:
#             return Response(
#                 {"status": "error", "message": "Mapping record not found."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )
#         except Exception as e:
#             return Response(
#                 {"status": "error", "message": str(e)},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )


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


class SubledgerMetadataView(APIView):
    """GET /api/v1/subledgers/metadata/

    Returns dynamic categories and active subledger-capable subcategories.
    """

    def get(self, request):
        categories = AssetCategory.objects.filter(is_active=True).order_by("id")
        serialized_cats = AssetCategorySerializer(categories, many=True).data

        # Unique subcategories actively backed by AssetCategory configuration
        capable_subcategories = list(
            categories.values_list("default_taxonomy_subcategory", flat=True).distinct()
        )

        return Response(
            {
                "asset_categories": serialized_cats,
                "subledger_capable_subcategories": capable_subcategories,
            },
            status=status.HTTP_200_OK,
        )


class SubledgerSubcategoryBreakdownView(APIView):
    """GET /api/v1/subledgers/subcategory-breakdown/?subcategory=Real%20Estate

    Drills into a specific taxonomy subcategory to evaluate total balance,
    mapped subledger amounts, variance, and list all assigned asset instances.
    """

    def get(self, request):
        subcategory_name = request.query_params.get("subcategory")
        if not subcategory_name:
            return Response(
                {"error": "Query parameter 'subcategory' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Calculate General Ledger Taxonomy Balance for this subcategory
        taxonomy_entries = JournalEntry.objects.filter(debit__gt=0)

        # Filter entries matching the requested subcategory
        total_taxonomy_debit = Decimal("0.00")
        for entry in taxonomy_entries.iterator():
            snapshot = entry.evaluation_matrix_snapshot or {}
            if (
                isinstance(snapshot, dict)
                and snapshot.get("resolved_subcategory") == subcategory_name
            ):
                total_taxonomy_debit += entry.debit

        # 2. Fetch all Subledger Assets linked to this taxonomy subcategory
        assets = AssetSubLedger.objects.filter(
            asset_category__default_taxonomy_subcategory=subcategory_name
        ).prefetch_related("operational_accounts", "compliance_schedules")

        # Fallback query for legacy category string matching if asset_category is null
        if not assets.exists():
            assets = AssetSubLedger.objects.filter(
                linked_gl_account__subcategory__iexact=subcategory_name
            )

        asset_summary_list = []
        total_subledger_mapped = Decimal("0.00")

        for asset in assets:
            # Sum mapped transactions bound to this specific asset
            mapped_total = AssetTransactionMapping.objects.filter(
                asset=asset
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            total_subledger_mapped += mapped_total

            asset_summary_list.append(
                {
                    "asset_id": str(asset.id),
                    "asset_code": asset.asset_code,
                    "name": asset.name,
                    "acquisition_cost": float(asset.acquisition_cost),
                    "current_valuation": float(asset.current_valuation),
                    "status": asset.status,
                    "mapped_transaction_total": float(mapped_total),
                    "mapped_count": AssetTransactionMapping.objects.filter(
                        asset=asset
                    ).count(),
                }
            )

        variance = total_taxonomy_debit - total_subledger_mapped

        return Response(
            {
                "taxonomy_subcategory": subcategory_name,
                "total_taxonomy_balance": float(total_taxonomy_debit),
                "total_subledger_mapped": float(total_subledger_mapped),
                "unmapped_variance": float(variance),
                "asset_count": len(asset_summary_list),
                "assets": asset_summary_list,
            },
            status=status.HTTP_200_OK,
        )
