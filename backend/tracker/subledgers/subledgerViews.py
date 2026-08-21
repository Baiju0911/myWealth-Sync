from decimal import Decimal

from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

# 🏛️ Core Tracker Models Import
from tracker.models import JournalEntry, TaxonomyTree

# 🏛️ Subledger Models Import
from ..models.subledger import (
    AssetCategory,
    AssetComplianceSchedule,
    AssetOperationalAccount,
    AssetSubLedger,
    AssetTransactionMapping,
    Vendor,
    AssetStatus,
    AssetCategoryChoices,
    validate_node_is_editable,
)
from ..models.models import StatementStagingLine, TaxonomyTree

# 🎨 Serializers Import
from .serializers import (
    AssetCategorySerializer,
    AssetComplianceScheduleSerializer,
    AssetOperationalAccountSerializer,
    AssetSubLedgerSerializer,
    BindRowRequestSerializer,
    CandidateMatchRequestSerializer,
    VendorSerializer,
)
from ..ai.services.ai_rule_trainer_engine import AIRuleTrainerEngine

# 🛠️ Services Import
from .services import AssetCandidateMatcher


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer


EDITABLE_STATUSES = ["ACTIVE", "HOLDING"]


# class AssetSubLedgerViewSet(viewsets.ModelViewSet):
#     queryset = AssetSubLedger.objects.all().prefetch_related(
#         "operational_accounts", "compliance_schedules"
#     )

#     serializer_class = AssetSubLedgerSerializer

#     def get_queryset(self):
#         queryset = super().get_queryset().select_related("asset_category", "vendor")
#         subcategory = self.request.query_params.get("subcategory")

#         if subcategory:
#             subcategory = subcategory.strip()

#             # 🎯 1. Direct text fields on AssetSubLedger
#             q_filters = Q(name__icontains=subcategory) | Q(
#                 asset_code__icontains=subcategory
#             )

#             # 🎯 2. Legacy category string / enum field
#             if hasattr(AssetSubLedger, "category"):
#                 q_filters |= Q(category__icontains=subcategory)

#             # 🎯 3. Safely query AssetCategory Foreign Key relations
#             if hasattr(AssetSubLedger, "asset_category"):
#                 from ..models.subledger import AssetCategory

#                 cat_fields = [f.name for f in AssetCategory._meta.get_fields()]
#                 if "name" in cat_fields:
#                     q_filters |= Q(asset_category__name__icontains=subcategory)
#                 if "code" in cat_fields:
#                     q_filters |= Q(asset_category__code__icontains=subcategory)
#                 if "default_taxonomy_subcategory" in cat_fields:
#                     q_filters |= Q(
#                         asset_category__default_taxonomy_subcategory__icontains=subcategory
#                     )

#             # 🎯 4. Safely query linked_gl_account (CharField vs ForeignKey)
#             if hasattr(AssetSubLedger, "linked_gl_account"):
#                 gl_field = AssetSubLedger._meta.get_field("linked_gl_account")

#                 if isinstance(gl_field, (models.CharField, models.TextField)):
#                     q_filters |= Q(linked_gl_account__icontains=subcategory)
#                 elif isinstance(gl_field, models.ForeignKey):
#                     rel_model = gl_field.remote_field.model
#                     rel_field_names = [f.name for f in rel_model._meta.get_fields()]

#                     if "name" in rel_field_names:
#                         q_filters |= Q(linked_gl_account__name__icontains=subcategory)
#                     if "account_name" in rel_field_names:
#                         q_filters |= Q(
#                             linked_gl_account__account_name__icontains=subcategory
#                         )
#                     if "code" in rel_field_names:
#                         q_filters |= Q(linked_gl_account__code__icontains=subcategory)

#             queryset = queryset.filter(q_filters)

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

#     def get_user_note(self, obj):
#         if obj.metadata_payload and isinstance(obj.metadata_payload, dict):
#             return obj.metadata_payload.get("user_note", "")
#         return ""

#     def update(self, request, *args, **kwargs):
#         kwargs["partial"] = True
#         print("\n==================================================")
#         print("📥 [ASSET UPDATE] INCOMING REQUEST DATA:")
#         print(f"Payload: {request.data}")
#         print(
#             f"Type of linked_gl_account: {type(request.data.get('linked_gl_account'))}"
#         )
#         print("==================================================\n")
#         return super().update(request, *args, **kwargs)

#     @action(detail=False, methods=["get"], url_path="category-schema-keys")
#     def category_schema_keys(self, request):
#         """GET /api/v1/subledgers/assets/category-schema-keys/?category=REAL_ESTATE

#         Queries PostgreSQL for all unique JSON keys stored in metadata_payload for a given category.
#         """
#         category_code = request.query_params.get("category", "REAL_ESTATE")

#         payloads = AssetSubLedger.objects.filter(category=category_code).values_list(
#             "metadata_payload", flat=True
#         )

#         db_keys = []
#         seen_keys = set()

#         for payload in payloads:
#             if isinstance(payload, dict):
#                 for key in payload.keys():
#                     if key not in seen_keys:
#                         db_keys.append(key)
#                         seen_keys.add(key)

#         return Response(
#             {"category": category_code, "db_keys": db_keys},
#             status=status.HTTP_200_OK,
#         )

#     # @action(detail=False, methods=["post"], url_path="find-candidates")
#     # def find_candidates(self, request):
#     #     print("\n==================================================")
#     #     print("📥 [FIND CANDIDATES] INCOMING RAW DATA:")
#     #     print(f"Payload: {request.data}")
#     #     print("==================================================")

#     #     serializer = CandidateMatchRequestSerializer(data=request.data)
#     #     serializer.is_valid(raise_exception=True)
#     #     data = serializer.validated_data

#     #     candidates = AssetCandidateMatcher.find_candidate_rows(
#     #         document_date=data["document_date"],
#     #         target_amount=data.get("target_amount"),
#     #         account_id=data.get("account_id"),
#     #         keywords=data.get("keywords", []),
#     #         day_window=data.get("day_window", 10),
#     #         asset_id=data.get("asset_id"),
#     #     )

#     #     print(
#     #         f"✅ [FIND CANDIDATES] MATCHES RETURNED: {len(candidates)} total rows (Bound + Unmapped)"
#     #     )
#     #     print("==================================================\n")

#     #     return Response(
#     #         {
#     #             "query": data,
#     #             "candidate_count": len(candidates),
#     #             "candidates": candidates,
#     #         },
#     #         status=status.HTTP_200_OK,
#     #     )

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

#     # @action(detail=False, methods=["post"], url_path="bind-transaction")
#     # def bind_transaction(self, request):
#     #     serializer = BindRowRequestSerializer(data=request.data)
#     #     serializer.is_valid(raise_exception=True)
#     #     data = serializer.validated_data

#     #     with transaction.atomic():
#     #         # Fetch Target Asset Node
#     #         asset = AssetSubLedger.objects.get(id=data["asset_id"])

#     #         # Guard 1: Check node status
#     #         validate_node_is_editable(asset)

#     #         # Guard 2: Check parent asset status
#     #         if asset.parent_asset:
#     #             validate_node_is_editable(asset.parent_asset)

#     #         # Handle Compliance Schedule
#     #         schedule = None
#     #         if data.get("schedule_id"):
#     #             schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
#     #             schedule.is_paid = True
#     #             schedule.paid_at = timezone.now()
#     #             schedule.linked_row_identifier = data.get("row_identifier")
#     #             schedule.save()

#     #         # Handle Operational Utility Account
#     #         op_account = None
#     #         if data.get("operational_account_id"):
#     #             op_account = AssetOperationalAccount.objects.get(
#     #                 id=data["operational_account_id"]
#     #             )

#     #         # Create Transaction Mapping Line
#     #         mapping = AssetTransactionMapping.objects.create(
#     #             asset=asset,
#     #             operational_account=op_account,
#     #             schedule=schedule,
#     #             row_identifier=data.get("row_identifier"),
#     #             is_cash_entry=data.get("is_cash_entry", False),
#     #             transaction_date=data["transaction_date"],
#     #             amount=data["amount"],
#     #             transaction_purpose=data["transaction_purpose"],
#     #             user_note=data.get("user_note", ""),
#     #         )

#     #         # Auto-Sync Cost Basis & Valuation
#     #         if data.get("sync_acquisition_cost", True):
#     #             total_mapped = AssetTransactionMapping.objects.filter(
#     #                 asset=asset
#     #             ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

#     #             asset.acquisition_cost = total_mapped
#     #             asset.current_valuation = total_mapped
#     #             asset.save(update_fields=["acquisition_cost", "current_valuation"])

#     #     return Response(
#     #         {
#     #             "status": "SUCCESS",
#     #             "mapping_id": str(mapping.id),
#     #             "updated_acquisition_cost": float(asset.acquisition_cost),
#     #             "message": "Transaction bound successfully.",
#     #         },
#     #         status=status.HTTP_201_CREATED,
#     #     )

#     @action(detail=False, methods=["post"], url_path="bind-transaction")
#     def bind_transaction(self, request):
#         serializer = BindRowRequestSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         data = serializer.validated_data

#         with transaction.atomic():
#             # Fetch Target Asset Node
#             asset = AssetSubLedger.objects.get(id=data["asset_id"])

#             # Guard 1: Check node status
#             validate_node_is_editable(asset)

#             # Guard 2: Check parent asset status
#             if asset.parent_asset:
#                 validate_node_is_editable(asset.parent_asset)

#             # Handle Compliance Schedule
#             schedule = None
#             if data.get("schedule_id"):
#                 schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
#                 schedule.is_paid = True
#                 schedule.paid_at = timezone.now()
#                 schedule.linked_row_identifier = data.get("row_identifier")
#                 schedule.save()

#             # Handle Operational Utility Account
#             op_account = None
#             if data.get("operational_account_id"):
#                 op_account = AssetOperationalAccount.objects.get(
#                     id=data["operational_account_id"]
#                 )

#             # Create Transaction Mapping Line
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

#             # Auto-Sync Cost Basis & Valuation
#             if data.get("sync_acquisition_cost", True):
#                 total_mapped = AssetTransactionMapping.objects.filter(
#                     asset=asset
#                 ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

#                 asset.acquisition_cost = total_mapped
#                 asset.current_valuation = total_mapped
#                 asset.save(update_fields=["acquisition_cost", "current_valuation"])

#             # 🟢 🚀 AI LEARNING: DIRECT READ FROM PAYLOAD (NO DB ROUND-TRIP)
#             raw_narration = data.get("remarks") or data.get("narration")

#             # Fallback ONLY if frontend payload didn't include remarks
#             if not raw_narration and data.get("row_identifier"):
#                 staging_line = StatementStagingLine.objects.filter(
#                     row_identifier=data["row_identifier"]
#                 ).first()
#                 raw_narration = (
#                     staging_line.narration if staging_line else data["row_identifier"]
#                 )

#             target_category = (
#                 asset.linked_gl_account.category if asset.linked_gl_account else "Asset"
#             )

#             ai_trained = AIRuleTrainerEngine.learn_from_binding(
#                 narration=raw_narration,
#                 category=target_category,
#                 subcategory=asset.name,
#                 user_note=data.get("user_note", ""),
#                 rule_code="SUBLEDGER_MANUAL_BIND",
#             )

#         return Response(
#             {
#                 "status": "SUCCESS",
#                 "mapping_id": str(mapping.id),
#                 "updated_acquisition_cost": float(asset.acquisition_cost),
#                 "ai_memory_trained": ai_trained,
#                 "message": "Transaction bound successfully and AI vector memory updated.",
#             },
#             status=status.HTTP_201_CREATED,
#         )

#     # @action(detail=False, methods=["post"], url_path="bind-transaction")
#     # def bind_transaction(self, request):
#     #     serializer = BindRowRequestSerializer(data=request.data)
#     #     serializer.is_valid(raise_exception=True)
#     #     data = serializer.validated_data

#     #     with transaction.atomic():
#     #         asset = AssetSubLedger.objects.get(id=data["asset_id"])

#     #         schedule = None
#     #         if data.get("schedule_id"):
#     #             schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
#     #             schedule.is_paid = True
#     #             schedule.paid_at = timezone.now()
#     #             schedule.linked_row_identifier = data.get("row_identifier")
#     #             schedule.save()

#     #         op_account = None
#     #         if data.get("operational_account_id"):
#     #             op_account = AssetOperationalAccount.objects.get(
#     #                 id=data["operational_account_id"]
#     #             )

#     #         mapping = AssetTransactionMapping.objects.create(
#     #             asset=asset,
#     #             operational_account=op_account,
#     #             schedule=schedule,
#     #             row_identifier=data.get("row_identifier"),
#     #             is_cash_entry=data.get("is_cash_entry", False),
#     #             transaction_date=data["transaction_date"],
#     #             amount=data["amount"],
#     #             transaction_purpose=data["transaction_purpose"],
#     #             user_note=data.get("user_note", ""),
#     #         )

#     #         if data.get("sync_acquisition_cost", True):
#     #             total_mapped = AssetTransactionMapping.objects.filter(
#     #                 asset=asset
#     #             ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

#     #             asset.acquisition_cost = total_mapped
#     #             asset.current_valuation = total_mapped
#     #             asset.save(update_fields=["acquisition_cost", "current_valuation"])

#     #     return Response(
#     #         {
#     #             "status": "SUCCESS",
#     #             "mapping_id": str(mapping.id),
#     #             "updated_acquisition_cost": float(asset.acquisition_cost),
#     #             "message": "Transaction bound and asset acquisition cost updated successfully.",
#     #         },
#     #         status=status.HTTP_201_CREATED,
#     #     )

#     # @action(detail=False, methods=["post"], url_path="bind-transaction")
#     # def bind_transaction(self, request):
#     #     serializer = BindRowRequestSerializer(data=request.data)
#     #     serializer.is_valid(raise_exception=True)
#     #     data = serializer.validated_data

#     #     with transaction.atomic():
#     #         # Fetch Asset Node
#     #         asset = AssetSubLedger.objects.get(id=data["asset_id"])

#     #         # 🎯 GUARD 1: Prevent binding if the subledger node itself is non-active
#     #         if asset.status not in EDITABLE_STATUSES:
#     #             raise ValidationError(
#     #                 {
#     #                     "detail": f"Sub-ledger node '{asset.name}' ({asset.asset_code}) is in '{asset.status}' status. "
#     #                     "Binding new transactions is locked for matured, closed, or written-off nodes."
#     #                 }
#     #             )

#     #         # 🎯 GUARD 2: Prevent binding if the parent asset is non-active
#     #         if (
#     #             asset.parent_asset
#     #             and asset.parent_asset.status not in EDITABLE_STATUSES
#     #         ):
#     #             raise ValidationError(
#     #                 {
#     #                     "detail": f"Cannot bind transaction. Parent asset '{asset.parent_asset.name}' "
#     #                     f"is in '{asset.parent_asset.status}' status."
#     #                 }
#     #             )

#     #         # Handle Compliance Schedule
#     #         schedule = None
#     #         if data.get("schedule_id"):
#     #             schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
#     #             schedule.is_paid = True
#     #             schedule.paid_at = timezone.now()
#     #             schedule.linked_row_identifier = data.get("row_identifier")
#     #             schedule.save()

#     #         # Handle Operational Utility Account
#     #         op_account = None
#     #         if data.get("operational_account_id"):
#     #             op_account = AssetOperationalAccount.objects.get(
#     #                 id=data["operational_account_id"]
#     #             )

#     #         # Create Transaction Mapping Line
#     #         mapping = AssetTransactionMapping.objects.create(
#     #             asset=asset,
#     #             operational_account=op_account,
#     #             schedule=schedule,
#     #             row_identifier=data.get("row_identifier"),
#     #             is_cash_entry=data.get("is_cash_entry", False),
#     #             transaction_date=data["transaction_date"],
#     #             amount=data["amount"],
#     #             transaction_purpose=data["transaction_purpose"],
#     #             user_note=data.get("user_note", ""),
#     #         )

#     #         # 🎯 Auto-Sync Cost Basis & Valuation (Only for Active Nodes)
#     #         if data.get("sync_acquisition_cost", True):
#     #             total_mapped = AssetTransactionMapping.objects.filter(
#     #                 asset=asset
#     #             ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

#     #             asset.acquisition_cost = total_mapped

#     #             # Only sync valuation if asset is actively held
#     #             if asset.status in EDITABLE_STATUSES:
#     #                 asset.current_valuation = total_mapped
#     #                 update_fields = ["acquisition_cost", "current_valuation"]
#     #             else:
#     #                 update_fields = ["acquisition_cost"]

#     #             asset.save(update_fields=update_fields)

#     #     return Response(
#     #         {
#     #             "status": "SUCCESS",
#     #             "mapping_id": str(mapping.id),
#     #             "updated_acquisition_cost": float(asset.acquisition_cost),
#     #             "message": "Transaction bound successfully.",
#     #         },
#     #         status=status.HTTP_201_CREATED,
#     #     )

#     @action(detail=True, methods=["get"], url_path="mapped-transactions")
#     def mapped_transactions(self, request, pk=None):
#         asset = self.get_object()
#         mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
#             row_identifier__isnull=True
#         )

#         row_identifiers = list(mappings.values_list("row_identifier", flat=True))

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
#                         if m_obj and hasattr(m_obj, "created_at") and m_obj.created_at
#                         else None
#                     ),
#                 }
#             )

#         return Response(
#             {
#                 "status": "success",
#                 "asset_id": str(asset.id),
#                 "asset_code": asset.asset_code,
#                 "asset_name": asset.name,
#                 "mapped_transactions": results,
#             },
#             status=status.HTTP_200_OK,
#         )

#     @action(detail=False, methods=["post"], url_path="unmap-transaction")
#     def unmap_asset_transaction_view(self, request):
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


class AssetSubLedgerViewSet(viewsets.ModelViewSet):
    queryset = AssetSubLedger.objects.all().prefetch_related(
        "operational_accounts", "compliance_schedules"
    )
    serializer_class = AssetSubLedgerSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related("asset_category", "vendor")
        subcategory = self.request.query_params.get("subcategory")

        if subcategory:
            subcategory = subcategory.strip()

            # 🎯 1. Direct text fields on AssetSubLedger
            q_filters = Q(name__icontains=subcategory) | Q(
                asset_code__icontains=subcategory
            )

            # 🎯 2. Legacy category string / enum field
            if hasattr(AssetSubLedger, "category"):
                q_filters |= Q(category__icontains=subcategory)

            # 🎯 3. Safely query AssetCategory Foreign Key relations
            if hasattr(AssetSubLedger, "asset_category"):
                from ..models.subledger import AssetCategory

                cat_fields = [f.name for f in AssetCategory._meta.get_fields()]
                if "name" in cat_fields:
                    q_filters |= Q(asset_category__name__icontains=subcategory)
                if "code" in cat_fields:
                    q_filters |= Q(asset_category__code__icontains=subcategory)
                if "default_taxonomy_subcategory" in cat_fields:
                    q_filters |= Q(
                        asset_category__default_taxonomy_subcategory__icontains=subcategory
                    )

            # 🎯 4. Safely query linked_gl_account (CharField vs ForeignKey)
            if hasattr(AssetSubLedger, "linked_gl_account"):
                gl_field = AssetSubLedger._meta.get_field("linked_gl_account")

                if isinstance(gl_field, (models.CharField, models.TextField)):
                    q_filters |= Q(linked_gl_account__icontains=subcategory)
                elif isinstance(gl_field, models.ForeignKey):
                    rel_model = gl_field.remote_field.model
                    rel_field_names = [f.name for f in rel_model._meta.get_fields()]

                    if "name" in rel_field_names:
                        q_filters |= Q(linked_gl_account__name__icontains=subcategory)
                    if "subcategory" in rel_field_names:
                        q_filters |= Q(
                            linked_gl_account__subcategory__icontains=subcategory
                        )
                    if "account_name" in rel_field_names:
                        q_filters |= Q(
                            linked_gl_account__account_name__icontains=subcategory
                        )
                    if "code" in rel_field_names:
                        q_filters |= Q(linked_gl_account__code__icontains=subcategory)

            queryset = queryset.filter(q_filters)

        return queryset

    @action(detail=False, methods=["get"], url_path="category-choices")
    def get_category_choices(self, request):
        """Exposes model AssetCategoryChoices dynamically."""
        choices = [
            {"code": value, "label": label}
            for value, label in AssetCategoryChoices.choices
        ]
        return Response(choices)

    # =========================================================================
    # HELPER: RESOLVE GL ACCOUNT STRING TO FOREIGNKEY ID
    # =========================================================================
    def _resolve_gl_account_payload(self, request_data):
        """Resolves raw GL string names or ID lookups to the expected TaxonomyTree subcategory string."""
        data = request_data.copy()
        raw_gl = data.get("linked_gl_account")

        if isinstance(raw_gl, str) and raw_gl.strip():
            # Query TaxonomyTree by subcategory or UUID
            gl_node = TaxonomyTree.objects.filter(
                Q(subcategory__iexact=raw_gl.strip()) | Q(id__iexact=raw_gl.strip())
            ).first()

            # 🟢 Pass the subcategory string name expected by the serializer/model
            if gl_node:
                data["linked_gl_account"] = gl_node.subcategory
            else:
                data["linked_gl_account"] = raw_gl.strip()

        return data

    # def create(self, request, *args, **kwargs):
    #     data = self._resolve_gl_account_payload(request.data)
    #     serializer = self.get_serializer(data=data)
    #     serializer.is_valid(raise_exception=True)
    #     self.perform_create(serializer)
    #     headers = self.get_success_headers(serializer.data)
    #     return Response(
    #         serializer.data, status=status.HTTP_201_CREATED, headers=headers
    #     )

    # def update(self, request, *args, **kwargs):
    #     kwargs["partial"] = True
    #     data = self._resolve_gl_account_payload(request.data)
    #     instance = self.get_object()
    #     serializer = self.get_serializer(instance, data=data, partial=True)
    #     serializer.is_valid(raise_exception=True)
    #     self.perform_update(serializer)
    #     return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        print("\n" + "🔥" * 30)
        print("📥 VIEW INCOMING CREATE PAYLOAD (RAW):", request.data)
        print(
            "📥 INCOMING FUNDING SOURCE:",
            request.data.get("acquisition_funding_source"),
        )
        print("🔥" * 30 + "\n")

        data = self._resolve_gl_account_payload(request.data)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        print("\n" + "🛠️" * 30)
        print("📥 VIEW INCOMING UPDATE PAYLOAD (RAW):", request.data)
        print(
            "📥 INCOMING FUNDING SOURCE:",
            request.data.get("acquisition_funding_source"),
        )
        print("🛠️" * 30 + "\n")

        kwargs["partial"] = True
        data = self._resolve_gl_account_payload(request.data)
        instance = self.get_object()

        print(
            f"📦 EXISTING DB FUNDING SOURCE BEFORE SAVE: {instance.acquisition_funding_source}"
        )

        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        instance.refresh_from_db()
        print(
            f"✅ SAVED DB FUNDING SOURCE AFTER SAVE: {instance.acquisition_funding_source}"
        )
        print(f"✅ SAVED DB IS_BANK_ROW_MISSING: {instance.is_bank_row_missing}")
        print("🛠️" * 30 + "\n")

        return Response(serializer.data)

    def get_user_note(self, obj):
        if obj.metadata_payload and isinstance(obj.metadata_payload, dict):
            return obj.metadata_payload.get("user_note", "")
        return ""

    @action(detail=False, methods=["get"], url_path="category-schema-keys")
    def category_schema_keys(self, request):
        category_code = request.query_params.get("category", "REAL_ESTATE")

        payloads = AssetSubLedger.objects.filter(category=category_code).values_list(
            "metadata_payload", flat=True
        )

        db_keys = []
        seen_keys = set()

        for payload in payloads:
            if isinstance(payload, dict):
                for key in payload.keys():
                    if key not in seen_keys:
                        db_keys.append(key)
                        seen_keys.add(key)

        return Response(
            {"category": category_code, "db_keys": db_keys},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="find-candidates")
    def find_candidates(self, request):
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

            # Guards
            validate_node_is_editable(asset)
            if asset.parent_asset:
                validate_node_is_editable(asset.parent_asset)

            # Compliance Schedule
            schedule = None
            if data.get("schedule_id"):
                schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
                schedule.is_paid = True
                schedule.paid_at = timezone.now()
                schedule.linked_row_identifier = data.get("row_identifier")
                schedule.save()

            # Operational Account
            op_account = None
            if data.get("operational_account_id"):
                op_account = AssetOperationalAccount.objects.get(
                    id=data["operational_account_id"]
                )

            # Mapping Line
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

            # Auto-Sync Cost Basis & Valuation
            if data.get("sync_acquisition_cost", True):
                total_mapped = AssetTransactionMapping.objects.filter(
                    asset=asset
                ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

                asset.acquisition_cost = total_mapped
                asset.current_valuation = total_mapped
                asset.save(update_fields=["acquisition_cost", "current_valuation"])

            # AI Vector Learning Pipeline
            raw_narration = data.get("remarks") or data.get("narration")
            if not raw_narration and data.get("row_identifier"):
                staging_line = StatementStagingLine.objects.filter(
                    row_identifier=data["row_identifier"]
                ).first()
                raw_narration = (
                    staging_line.narration if staging_line else data["row_identifier"]
                )

            target_category = (
                asset.linked_gl_account.category if asset.linked_gl_account else "Asset"
            )

            ai_trained = AIRuleTrainerEngine.learn_from_binding(
                narration=raw_narration,
                category=target_category,
                subcategory=asset.name,
                user_note=data.get("user_note", ""),
                rule_code="SUBLEDGER_MANUAL_BIND",
            )

        return Response(
            {
                "status": "SUCCESS",
                "mapping_id": str(mapping.id),
                "updated_acquisition_cost": float(asset.acquisition_cost),
                "ai_memory_trained": ai_trained,
                "message": "Transaction bound successfully and AI vector memory updated.",
            },
            status=status.HTTP_201_CREATED,
        )

    # @action(detail=True, methods=["get"], url_path="mapped-transactions")
    # def mapped_transactions(self, request, pk=None):
    #     asset = self.get_object()
    #     mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
    #         row_identifier__isnull=True
    #     )

    #     row_identifiers = list(mappings.values_list("row_identifier", flat=True))

    #     journal_entries = JournalEntry.objects.filter(
    #         row_identifier__in=row_identifiers, account_id=99
    #     ).values(
    #         "id",
    #         "row_identifier",
    #         "transaction_date",
    #         "debit",
    #         "credit",
    #         "remarks",
    #     )

    #     mapping_lookup = {m.row_identifier: m for m in mappings}

    #     results = []
    #     for entry in journal_entries:
    #         m_obj = mapping_lookup.get(entry["row_identifier"])
    #         results.append(
    #             {
    #                 "mapping_id": str(m_obj.id) if m_obj else None,
    #                 "journal_id": str(entry["id"]),
    #                 "row_identifier": entry["row_identifier"],
    #                 "transaction_date": entry["transaction_date"].strftime("%Y-%m-%d"),
    #                 "debit": float(entry["debit"]),
    #                 "credit": float(entry["credit"]),
    #                 "remarks": entry["remarks"],
    #                 "mapped_at": (
    #                     m_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
    #                     if m_obj and hasattr(m_obj, "created_at") and m_obj.created_at
    #                     else None
    #                 ),
    #             }
    #         )

    #     return Response(
    #         {
    #             "status": "success",
    #             "asset_id": str(asset.id),
    #             "asset_code": asset.asset_code,
    #             "asset_name": asset.name,
    #             "mapped_transactions": results,
    #         },
    #         status=status.HTTP_200_OK,
    #     )

    @action(detail=True, methods=["get"], url_path="mapped-transactions")
    def mapped_transactions(self, request, pk=None):
        asset = self.get_object()

        # 🟢 Include ALL mappings (Do NOT exclude row_identifier__isnull=True)
        mappings = AssetTransactionMapping.objects.filter(asset=asset)

        # Build lookup for row_identifiers linked to bank staging
        bank_row_ids = [m.row_identifier for m in mappings if m.row_identifier]

        journal_entries = JournalEntry.objects.filter(
            row_identifier__in=bank_row_ids, account_id=99
        ).values(
            "id",
            "row_identifier",
            "transaction_date",
            "debit",
            "credit",
            "remarks",
        )

        journal_lookup = {e["row_identifier"]: e for e in journal_entries}

        results = []
        for m in mappings:
            # Bank Staging Row
            if m.row_identifier and m.row_identifier in journal_lookup:
                entry = journal_lookup[m.row_identifier]
                results.append(
                    {
                        "mapping_id": str(m.id),
                        "journal_id": str(entry["id"]),
                        "row_identifier": entry["row_identifier"],
                        "transaction_date": entry["transaction_date"].strftime(
                            "%Y-%m-%d"
                        ),
                        "debit": float(entry["debit"]),
                        "credit": float(entry["credit"]),
                        "remarks": entry["remarks"],
                        "user_note": m.user_note or "",
                        "is_cash_entry": m.is_cash_entry,
                        "mapped_at": (
                            m.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            if m.created_at
                            else None
                        ),
                    }
                )
            # Direct Cash / Manual Entry
            else:
                results.append(
                    {
                        "mapping_id": str(m.id),
                        "journal_id": f"CASH-{m.id}",
                        "row_identifier": None,
                        "transaction_date": m.transaction_date.strftime("%Y-%m-%d"),
                        "debit": (
                            float(m.amount)
                            if m.transaction_purpose == "OUTFLOW"
                            else 0.0
                        ),
                        "credit": (
                            float(m.amount)
                            if m.transaction_purpose == "INFLOW"
                            else 0.0
                        ),
                        "remarks": m.user_note or "Direct Cash / Manual Payment",
                        "user_note": m.user_note or "",
                        "is_cash_entry": True,
                        "mapped_at": (
                            m.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            if m.created_at
                            else None
                        ),
                    }
                )

        return Response(
            {
                "status": "success",
                "asset_id": str(asset.id),
                "asset_code": asset.asset_code,
                "asset_name": asset.name,
                "mapped_transactions": results,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="unmap-transaction")
    def unmap_asset_transaction_view(self, request):
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


# class SubledgerMetadataView(APIView):
#     """GET /api/v1/subledgers/metadata/

#     Returns dynamic categories and active subledger-capable subcategories.
#     """

#     def get(self, request):
#         categories = AssetCategory.objects.filter(is_active=True).order_by("id")
#         serialized_cats = AssetCategorySerializer(categories, many=True).data

#         capable_subcategories = list(
#             categories.values_list("default_taxonomy_subcategory", flat=True).distinct()
#         )

#         return Response(
#             {
#                 "asset_categories": serialized_cats,
#                 "subledger_capable_subcategories": capable_subcategories,
#             },
#             status=status.HTTP_200_OK,
#         )


class SubledgerMetadataView(APIView):
    """GET /api/v1/subledgers/metadata/

    Returns ONLY subcategories that have actual registered Subledger nodes in the DB.
    """

    def get(self, request):
        categories = AssetCategory.objects.filter(is_active=True).order_by("id")
        serialized_cats = AssetCategorySerializer(categories, many=True).data

        valid_statuses = [AssetStatus.ACTIVE, AssetStatus.MATURED]

        # 1. Fetch subcategories ONLY from actual created AssetSubLedger records
        linked_gl_subcategories = set(
            AssetSubLedger.objects.filter(
                status__in=valid_statuses, linked_gl_account__isnull=False
            )
            .values_list("linked_gl_account__subcategory", flat=True)
            .distinct()
        )

        # 2. Fetch direct category values ONLY from actual created AssetSubLedger records
        node_categories = set(
            AssetSubLedger.objects.filter(status__in=valid_statuses)
            .values_list("category", flat=True)
            .distinct()
        )

        # Combine ONLY actual existing node subcategories
        combined_set = {
            item.strip()
            for item in (linked_gl_subcategories | node_categories)
            if item and item.strip()
        }

        return Response(
            {
                "asset_categories": serialized_cats,
                "subledger_capable_subcategories": list(combined_set),
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

        taxonomy_entries = JournalEntry.objects.filter(debit__gt=0)

        total_taxonomy_debit = Decimal("0.00")
        for entry in taxonomy_entries.iterator():
            snapshot = entry.evaluation_matrix_snapshot or {}
            if (
                isinstance(snapshot, dict)
                and snapshot.get("resolved_subcategory") == subcategory_name
            ):
                total_taxonomy_debit += entry.debit

        assets = (
            AssetSubLedger.objects.filter(
                asset_category__default_taxonomy_subcategory=subcategory_name
            )
            .select_related("vendor", "asset_category")
            .prefetch_related("operational_accounts", "compliance_schedules")
        )

        if not assets.exists():
            assets = AssetSubLedger.objects.filter(
                linked_gl_account__subcategory__iexact=subcategory_name
            ).select_related("vendor", "asset_category")

        asset_summary_list = []
        total_subledger_mapped = Decimal("0.00")

        for asset in assets:
            mapped_total = AssetTransactionMapping.objects.filter(
                asset=asset
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            total_subledger_mapped += mapped_total

            vendor_id = str(asset.vendor.id) if asset.vendor else None
            vendor_name = (
                asset.vendor.name if asset.vendor else "Independent / Uncategorized"
            )

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
                    "vendor": vendor_id,
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_name,
                    "vendor_detail": (
                        {
                            "id": vendor_id,
                            "name": vendor_name,
                        }
                        if asset.vendor
                        else None
                    ),
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


# from decimal import Decimal

# from django.db import models, transaction
# from django.db.models import Q, Sum
# from django.utils import timezone
# from rest_framework import status, viewsets
# from rest_framework.decorators import action, api_view
# from rest_framework.response import Response
# from rest_framework.views import APIView

# # 🏛️ Core Tracker Models Import
# from tracker.models import JournalEntry

# # 🏛️ Subledger Models Import
# from ..models.subledger import (
#     AssetCategory,
#     AssetComplianceSchedule,
#     AssetOperationalAccount,
#     AssetSubLedger,
#     AssetTransactionMapping,
#     Vendor,
# )

# # 🎨 Serializers Import
# from .serializers import (
#     AssetCategorySerializer,
#     AssetComplianceScheduleSerializer,
#     AssetOperationalAccountSerializer,
#     AssetSubLedgerSerializer,
#     BindRowRequestSerializer,
#     CandidateMatchRequestSerializer,
#     VendorSerializer,
# )

# # 🛠️ Services Import
# from .services import AssetCandidateMatcher


# class VendorViewSet(viewsets.ModelViewSet):
#     queryset = Vendor.objects.all()
#     serializer_class = VendorSerializer


# class AssetSubLedgerViewSet(viewsets.ModelViewSet):
#     queryset = AssetSubLedger.objects.all().prefetch_related(
#         "operational_accounts", "compliance_schedules"
#     )
#     serializer_class = AssetSubLedgerSerializer

#     def get_queryset(self):
#         queryset = super().get_queryset().select_related("asset_category", "vendor")
#         subcategory = self.request.query_params.get("subcategory")

#         if subcategory:
#             subcategory = subcategory.strip()

#             # 🎯 1. Direct text fields on AssetSubLedger
#             q_filters = Q(name__icontains=subcategory) | Q(
#                 asset_code__icontains=subcategory
#             )

#             # 🎯 2. Legacy category string / enum field
#             if hasattr(AssetSubLedger, "category"):
#                 q_filters |= Q(category__icontains=subcategory)

#             # 🎯 3. Safely query AssetCategory Foreign Key relations
#             if hasattr(AssetSubLedger, "asset_category"):
#                 # Safely check fields on AssetCategory model
#                 from ..models.subledger import AssetCategory

#                 cat_fields = [f.name for f in AssetCategory._meta.get_fields()]
#                 if "name" in cat_fields:
#                     q_filters |= Q(asset_category__name__icontains=subcategory)
#                 if "code" in cat_fields:
#                     q_filters |= Q(asset_category__code__icontains=subcategory)
#                 if "default_taxonomy_subcategory" in cat_fields:
#                     q_filters |= Q(
#                         asset_category__default_taxonomy_subcategory__icontains=subcategory
#                     )

#             # 🎯 4. Safely query linked_gl_account (CharField vs ForeignKey)
#             if hasattr(AssetSubLedger, "linked_gl_account"):
#                 gl_field = AssetSubLedger._meta.get_field("linked_gl_account")

#                 if isinstance(gl_field, (models.CharField, models.TextField)):
#                     q_filters |= Q(linked_gl_account__icontains=subcategory)
#                 elif isinstance(gl_field, models.ForeignKey):
#                     # Inspect the related model to prevent invalid field lookups
#                     rel_model = gl_field.remote_field.model
#                     rel_field_names = [f.name for f in rel_model._meta.get_fields()]

#                     if "name" in rel_field_names:
#                         q_filters |= Q(linked_gl_account__name__icontains=subcategory)
#                     if "account_name" in rel_field_names:
#                         q_filters |= Q(
#                             linked_gl_account__account_name__icontains=subcategory
#                         )
#                     if "code" in rel_field_names:
#                         q_filters |= Q(linked_gl_account__code__icontains=subcategory)

#             queryset = queryset.filter(q_filters)

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

#     def get_user_note(self, obj):
#         if obj.metadata_payload and isinstance(obj.metadata_payload, dict):
#             return obj.metadata_payload.get("user_note", "")
#         return ""

#     def update(self, request, *args, **kwargs):
#         kwargs["partial"] = True
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

#     # @action(detail=False, methods=["post"], url_path="bind-transaction")
#     # def bind_transaction(self, request):
#     #     serializer = BindRowRequestSerializer(data=request.data)
#     #     serializer.is_valid(raise_exception=True)
#     #     data = serializer.validated_data

#     #     with transaction.atomic():
#     #         asset = AssetSubLedger.objects.get(id=data["asset_id"])

#     #         schedule = None
#     #         if data.get("schedule_id"):
#     #             schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
#     #             schedule.is_paid = True
#     #             schedule.paid_at = timezone.now()
#     #             schedule.linked_row_identifier = data.get("row_identifier")
#     #             schedule.save()

#     #         op_account = None
#     #         if data.get("operational_account_id"):
#     #             op_account = AssetOperationalAccount.objects.get(
#     #                 id=data["operational_account_id"]
#     #             )

#     #         mapping = AssetTransactionMapping.objects.create(
#     #             asset=asset,
#     #             operational_account=op_account,
#     #             schedule=schedule,
#     #             row_identifier=data.get("row_identifier"),
#     #             is_cash_entry=data.get("is_cash_entry", False),
#     #             transaction_date=data["transaction_date"],
#     #             amount=data["amount"],
#     #             transaction_purpose=data["transaction_purpose"],
#     #             user_note=data.get("user_note", ""),
#     #         )

#     #     return Response(
#     #         {
#     #             "status": "SUCCESS",
#     #             "mapping_id": str(mapping.id),
#     #             "message": "Transaction bound to sub-ledger.",
#     #         },
#     #         status=status.HTTP_201_CREATED,
#     #     )

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

#             # 1. Create Transaction Mapping Record
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

#             # 🎯 2. Sync Acquisition Cost & Current Valuation if requested
#             if data.get("sync_acquisition_cost", True):
#                 # Calculate total bound outflows for this asset
#                 total_mapped = AssetTransactionMapping.objects.filter(
#                     asset=asset
#                 ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

#                 # Update baseline acquisition cost and valuation to reflect bound outflows
#                 asset.acquisition_cost = total_mapped
#                 asset.current_valuation = total_mapped
#                 asset.save(update_fields=["acquisition_cost", "current_valuation"])

#         return Response(
#             {
#                 "status": "SUCCESS",
#                 "mapping_id": str(mapping.id),
#                 "updated_acquisition_cost": float(asset.acquisition_cost),
#                 "message": "Transaction bound and asset acquisition cost updated successfully.",
#             },
#             status=status.HTTP_201_CREATED,
#         )

#     @action(detail=True, methods=["get"], url_path="mapped-transactions")
#     def mapped_transactions(self, request, pk=None):
#         asset = self.get_object()
#         mappings = AssetTransactionMapping.objects.filter(asset=asset).exclude(
#             row_identifier__isnull=True
#         )

#         row_identifiers = list(mappings.values_list("row_identifier", flat=True))

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
#                         if m_obj and hasattr(m_obj, "created_at") and m_obj.created_at
#                         else None
#                     ),
#                 }
#             )

#         return Response(
#             {
#                 "status": "success",
#                 "asset_id": str(asset.id),
#                 "asset_code": asset.asset_code,
#                 "asset_name": asset.name,
#                 "mapped_transactions": results,
#             },
#             status=status.HTTP_200_OK,
#         )

#     @action(detail=False, methods=["post"], url_path="unmap-transaction")
#     def unmap_asset_transaction_view(self, request):
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


# class AssetOperationalAccountViewSet(viewsets.ModelViewSet):
#     queryset = AssetOperationalAccount.objects.all()
#     serializer_class = AssetOperationalAccountSerializer


# class AssetComplianceScheduleViewSet(viewsets.ModelViewSet):
#     queryset = AssetComplianceSchedule.objects.all()
#     serializer_class = AssetComplianceScheduleSerializer

#     @action(detail=False, methods=["get"], url_path="pending-dues")
#     def pending_dues(self, request):
#         schedules = self.queryset.filter(is_paid=False).order_by("due_date")
#         serializer = self.get_serializer(schedules, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)


# class SubledgerMetadataView(APIView):
#     """GET /api/v1/subledgers/metadata/

#     Returns dynamic categories and active subledger-capable subcategories.
#     """

#     def get(self, request):
#         categories = AssetCategory.objects.filter(is_active=True).order_by("id")
#         serialized_cats = AssetCategorySerializer(categories, many=True).data

#         # Unique subcategories actively backed by AssetCategory configuration
#         capable_subcategories = list(
#             categories.values_list("default_taxonomy_subcategory", flat=True).distinct()
#         )

#         return Response(
#             {
#                 "asset_categories": serialized_cats,
#                 "subledger_capable_subcategories": capable_subcategories,
#             },
#             status=status.HTTP_200_OK,
#         )


# class SubledgerSubcategoryBreakdownView(APIView):
#     """GET /api/v1/subledgers/subcategory-breakdown/?subcategory=Real%20Estate

#     Drills into a specific taxonomy subcategory to evaluate total balance,
#     mapped subledger amounts, variance, and list all assigned asset instances.
#     """

#     def get(self, request):
#         subcategory_name = request.query_params.get("subcategory")
#         if not subcategory_name:
#             return Response(
#                 {"error": "Query parameter 'subcategory' is required."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # 1. Calculate General Ledger Taxonomy Balance for this subcategory
#         taxonomy_entries = JournalEntry.objects.filter(debit__gt=0)

#         total_taxonomy_debit = Decimal("0.00")
#         for entry in taxonomy_entries.iterator():
#             snapshot = entry.evaluation_matrix_snapshot or {}
#             if (
#                 isinstance(snapshot, dict)
#                 and snapshot.get("resolved_subcategory") == subcategory_name
#             ):
#                 total_taxonomy_debit += entry.debit

#         # 2. Fetch all Subledger Assets linked to this taxonomy subcategory + Join Vendor details
#         assets = (
#             AssetSubLedger.objects.filter(
#                 asset_category__default_taxonomy_subcategory=subcategory_name
#             )
#             .select_related("vendor", "asset_category")
#             .prefetch_related("operational_accounts", "compliance_schedules")
#         )

#         # Fallback query for legacy category string matching if asset_category is null
#         if not assets.exists():
#             assets = AssetSubLedger.objects.filter(
#                 linked_gl_account__subcategory__iexact=subcategory_name
#             ).select_related("vendor", "asset_category")

#         asset_summary_list = []
#         total_subledger_mapped = Decimal("0.00")

#         for asset in assets:
#             mapped_total = AssetTransactionMapping.objects.filter(
#                 asset=asset
#             ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

#             total_subledger_mapped += mapped_total

#             # 🎯 Extract vendor information cleanly
#             vendor_id = str(asset.vendor.id) if asset.vendor else None
#             vendor_name = (
#                 asset.vendor.name if asset.vendor else "Independent / Uncategorized"
#             )

#             asset_summary_list.append(
#                 {
#                     "asset_id": str(asset.id),
#                     "asset_code": asset.asset_code,
#                     "name": asset.name,
#                     "acquisition_cost": float(asset.acquisition_cost),
#                     "current_valuation": float(asset.current_valuation),
#                     "status": asset.status,
#                     "mapped_transaction_total": float(mapped_total),
#                     "mapped_count": AssetTransactionMapping.objects.filter(
#                         asset=asset
#                     ).count(),
#                     # 🟢 RESTORED VENDOR PAYLOAD KEYS FOR FRONTEND GROUPING:
#                     "vendor": vendor_id,
#                     "vendor_id": vendor_id,
#                     "vendor_name": vendor_name,
#                     "vendor_detail": (
#                         {
#                             "id": vendor_id,
#                             "name": vendor_name,
#                         }
#                         if asset.vendor
#                         else None
#                     ),
#                 }
#             )

#         variance = total_taxonomy_debit - total_subledger_mapped

#         return Response(
#             {
#                 "taxonomy_subcategory": subcategory_name,
#                 "total_taxonomy_balance": float(total_taxonomy_debit),
#                 "total_subledger_mapped": float(total_subledger_mapped),
#                 "unmapped_variance": float(variance),
#                 "asset_count": len(asset_summary_list),
#                 "assets": asset_summary_list,
#             },
#             status=status.HTTP_200_OK,
#         )
