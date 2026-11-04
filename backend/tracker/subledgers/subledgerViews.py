from decimal import Decimal

from django.db import models, transaction
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.apps import apps


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

        # Read from validated_data, with safety fallback to raw request.data and query_params
        bank_account_hint = (
            data.get("bank_account_hint")
            or request.data.get("bank_account_hint")
            or request.query_params.get("bank_account_hint")
        )

        asset_id = data.get("asset_id") or request.data.get("asset_id")

        # If the user chose "-- All Accounts --", bank_account_hint is "" -> treat as None
        if bank_account_hint == "":
            bank_account_hint = None

        candidates = AssetCandidateMatcher.find_candidate_rows(
            document_date=data.get("document_date"),
            target_amount=data.get("target_amount"),
            account_id=data.get("account_id"),
            keywords=data.get("keywords", []),
            day_window=data.get("day_window", 1825),
            asset_id=asset_id,
            subcategory=data.get("subcategory"),
            unmapped_only=data.get("unmapped_only", False),
            bank_account_hint=bank_account_hint,
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

            # 🛑 Cross-Folio Guard: Reject if already bound to another folio
            if data.get("row_identifier") and not data.get("is_cash_entry", False):
                existing_mapping = (
                    AssetTransactionMapping.objects.filter(
                        row_identifier=data["row_identifier"]
                    )
                    .select_related("asset")
                    .first()
                )
                if existing_mapping:
                    return Response(
                        {
                            "status": "ERROR",
                            "message": (
                                f"This transaction is already bound to "
                                f"[{existing_mapping.asset.asset_code}] {existing_mapping.asset.name}. "
                                f"Please disconnect it from that folio first."
                            ),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

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

    # @action(detail=False, methods=["post"], url_path="bind-transaction")
    # def bind_transaction(self, request):
    #     serializer = BindRowRequestSerializer(data=request.data)
    #     serializer.is_valid(raise_exception=True)
    #     data = serializer.validated_data

    #     with transaction.atomic():
    #         asset = AssetSubLedger.objects.get(id=data["asset_id"])

    #         # Guards
    #         validate_node_is_editable(asset)
    #         if asset.parent_asset:
    #             validate_node_is_editable(asset.parent_asset)

    #         # Compliance Schedule
    #         schedule = None
    #         if data.get("schedule_id"):
    #             schedule = AssetComplianceSchedule.objects.get(id=data["schedule_id"])
    #             schedule.is_paid = True
    #             schedule.paid_at = timezone.now()
    #             schedule.linked_row_identifier = data.get("row_identifier")
    #             schedule.save()

    #         # Operational Account
    #         op_account = None
    #         if data.get("operational_account_id"):
    #             op_account = AssetOperationalAccount.objects.get(
    #                 id=data["operational_account_id"]
    #             )

    #         # Mapping Line
    #         mapping = AssetTransactionMapping.objects.create(
    #             asset=asset,
    #             operational_account=op_account,
    #             schedule=schedule,
    #             row_identifier=data.get("row_identifier"),
    #             is_cash_entry=data.get("is_cash_entry", False),
    #             transaction_date=data["transaction_date"],
    #             amount=data["amount"],
    #             transaction_purpose=data["transaction_purpose"],
    #             user_note=data.get("user_note", ""),
    #         )

    #         # Auto-Sync Cost Basis & Valuation
    #         if data.get("sync_acquisition_cost", True):
    #             total_mapped = AssetTransactionMapping.objects.filter(
    #                 asset=asset
    #             ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    #             asset.acquisition_cost = total_mapped
    #             asset.current_valuation = total_mapped
    #             asset.save(update_fields=["acquisition_cost", "current_valuation"])

    #         # AI Vector Learning Pipeline
    #         raw_narration = data.get("remarks") or data.get("narration")
    #         if not raw_narration and data.get("row_identifier"):
    #             staging_line = StatementStagingLine.objects.filter(
    #                 row_identifier=data["row_identifier"]
    #             ).first()
    #             raw_narration = (
    #                 staging_line.narration if staging_line else data["row_identifier"]
    #             )

    #         target_category = (
    #             asset.linked_gl_account.category if asset.linked_gl_account else "Asset"
    #         )

    #         ai_trained = AIRuleTrainerEngine.learn_from_binding(
    #             narration=raw_narration,
    #             category=target_category,
    #             subcategory=asset.name,
    #             user_note=data.get("user_note", ""),
    #             rule_code="SUBLEDGER_MANUAL_BIND",
    #         )

    #     return Response(
    #         {
    #             "status": "SUCCESS",
    #             "mapping_id": str(mapping.id),
    #             "updated_acquisition_cost": float(asset.acquisition_cost),
    #             "ai_memory_trained": ai_trained,
    #             "message": "Transaction bound successfully and AI vector memory updated.",
    #         },
    #         status=status.HTTP_201_CREATED,
    #     )

    # @action(detail=True, methods=["get"], url_path="mapped-transactions")
    # def mapped_transactions(self, request, pk=None):
    #     asset = self.get_object()

    #     # 🟢 Include ALL mappings (Do NOT exclude row_identifier__isnull=True)
    #     mappings = AssetTransactionMapping.objects.filter(asset=asset)

    #     # Build lookup for row_identifiers linked to bank staging
    #     bank_row_ids = [m.row_identifier for m in mappings if m.row_identifier]

    #     journal_entries = JournalEntry.objects.filter(
    #         row_identifier__in=bank_row_ids, account_id=99
    #     ).values(
    #         "id",
    #         "row_identifier",
    #         "transaction_date",
    #         "debit",
    #         "credit",
    #         "remarks",
    #     )

    #     journal_lookup = {e["row_identifier"]: e for e in journal_entries}

    #     results = []
    #     for m in mappings:
    #         # Bank Staging Row
    #         if m.row_identifier and m.row_identifier in journal_lookup:
    #             entry = journal_lookup[m.row_identifier]
    #             results.append(
    #                 {
    #                     "mapping_id": str(m.id),
    #                     "journal_id": str(entry["id"]),
    #                     "row_identifier": entry["row_identifier"],
    #                     "transaction_date": entry["transaction_date"].strftime(
    #                         "%Y-%m-%d"
    #                     ),
    #                     "debit": float(entry["debit"]),
    #                     "credit": float(entry["credit"]),
    #                     "remarks": entry["remarks"],
    #                     "user_note": m.user_note or "",
    #                     "is_cash_entry": m.is_cash_entry,
    #                     "mapped_at": (
    #                         m.created_at.strftime("%Y-%m-%d %H:%M:%S")
    #                         if m.created_at
    #                         else None
    #                     ),
    #                 }
    #             )
    #         # Direct Cash / Manual Entry
    #         else:
    #             results.append(
    #                 {
    #                     "mapping_id": str(m.id),
    #                     "journal_id": f"CASH-{m.id}",
    #                     "row_identifier": None,
    #                     "transaction_date": m.transaction_date.strftime("%Y-%m-%d"),
    #                     "debit": (
    #                         float(m.amount)
    #                         if m.transaction_purpose == "OUTFLOW"
    #                         else 0.0
    #                     ),
    #                     "credit": (
    #                         float(m.amount)
    #                         if m.transaction_purpose == "INFLOW"
    #                         else 0.0
    #                     ),
    #                     "remarks": m.user_note or "Direct Cash / Manual Payment",
    #                     "user_note": m.user_note or "",
    #                     "is_cash_entry": True,
    #                     "mapped_at": (
    #                         m.created_at.strftime("%Y-%m-%d %H:%M:%S")
    #                         if m.created_at
    #                         else None
    #                     ),
    #                 }
    #             )

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

    # @action(detail=True, methods=["get"], url_path="mapped-transactions")
    # def mapped_transactions(self, request, pk=None):
    #     asset = self.get_object()
    #     print(f"\n================ [MAPPED TRANSACTIONS DEBUG] ================")
    #     print(
    #         f"|| Target Asset: ID={asset.id} | Code={asset.asset_code} | Name={asset.name}"
    #     )

    #     # 1. Inspect raw mappings in database for this asset
    #     mappings = list(AssetTransactionMapping.objects.filter(asset=asset))
    #     print(f"|| Total AssetTransactionMapping rows for this asset: {len(mappings)}")
    #     for idx, m in enumerate(mappings):
    #         print(
    #             f"   [{idx+1}] mapping_id={m.id} | row_identifier={m.row_identifier} | amount={m.amount} | is_cash={m.is_cash_entry}"
    #         )

    #     # Check if ANY mappings exist across other assets (in case bound to another asset)
    #     all_mappings_count = AssetTransactionMapping.objects.count()
    #     print(
    #         f"|| Total AssetTransactionMapping rows ACROSS ALL ASSETS in DB: {all_mappings_count}"
    #     )

    #     # 2. Extract bank row identifiers
    #     bank_row_ids = [m.row_identifier for m in mappings if m.row_identifier]
    #     print(f"|| bank_row_ids to look up: {bank_row_ids}")

    #     # 3. Inspect JournalEntry lookup
    #     journal_entries = list(
    #         JournalEntry.objects.filter(row_identifier__in=bank_row_ids).values(
    #             "id",
    #             "row_identifier",
    #             "transaction_date",
    #             "debit",
    #             "credit",
    #             "remarks",
    #         )
    #     )
    #     print(f"|| Matched JournalEntry rows found: {len(journal_entries)}")
    #     journal_lookup = {e["row_identifier"]: e for e in journal_entries}

    #     results = []
    #     for m in mappings:
    #         entry = journal_lookup.get(m.row_identifier) if m.row_identifier else None
    #         payload_item = {
    #             "mapping_id": str(m.id),
    #             "journal_id": str(entry["id"]) if entry else f"MAP-{m.id}",
    #             "row_identifier": m.row_identifier,
    #             "transaction_date": (
    #                 entry["transaction_date"].strftime("%Y-%m-%d")
    #                 if entry and entry.get("transaction_date")
    #                 else m.transaction_date.strftime("%Y-%m-%d")
    #             ),
    #             "debit": float(entry["debit"]) if entry else float(m.amount),
    #             "credit": float(entry["credit"]) if entry else 0.0,
    #             "remarks": (
    #                 entry["remarks"]
    #                 if entry
    #                 else (m.user_note or "Mapped Subledger Payment")
    #             ),
    #             "user_note": m.user_note or "",
    #             "is_cash_entry": m.is_cash_entry,
    #             "mapped_at": (
    #                 m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else None
    #             ),
    #         }
    #         results.append(payload_item)

    #     print(f"|| Final results array count being returned: {len(results)}")
    #     print(f"============================================================\n")

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

    # @action(detail=True, methods=["get"], url_path="mapped-transactions")
    # def mapped_transactions(self, request, pk=None):
    #     from decimal import Decimal
    #     from django.apps import apps

    #     AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")
    #     StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
    #     JournalEntry = apps.get_model("ledger", "JournalEntry")
    #     Account = apps.get_model("ledger", "Account")

    #     asset = self.get_object()

    #     # 1. Fetch raw mapping records for this asset
    #     mappings = list(
    #         AssetTransactionMapping.objects.filter(asset=asset)
    #         .order_by("-transaction_date")
    #         .values(
    #             "id",
    #             "row_identifier",
    #             "transaction_date",
    #             "amount",
    #             "transaction_purpose",
    #             "user_note",
    #             "is_cash_entry",
    #             "created_at",
    #         )
    #     )

    #     bank_row_ids = [m["row_identifier"] for m in mappings if m["row_identifier"]]

    #     # 2. Fetch raw statement narrations from StatementStagingLine SSOT
    #     staging_map = dict(
    #         StatementStagingLine.objects.filter(
    #             row_identifier__in=bank_row_ids
    #         ).values_list("row_identifier", "narration")
    #     )

    #     # 3. Fetch pairing bank account legs from JournalEntry (where account_id != 99)
    #     pairing_legs = list(
    #         JournalEntry.objects.filter(row_identifier__in=bank_row_ids)
    #         .exclude(account_id=99)
    #         .values("id", "row_identifier", "account_id", "debit", "credit", "remarks")
    #     )

    #     row_to_bank_leg = {p["row_identifier"]: p for p in pairing_legs}
    #     all_bank_ids = set(p["account_id"] for p in pairing_legs)

    #     # 4. Lookup Account metadata (name + last 4)
    #     account_lookup = {}
    #     if all_bank_ids:
    #         for acc in Account.objects.filter(id__in=all_bank_ids):
    #             acc_num = str(getattr(acc, "account_number", "") or "")
    #             last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
    #             account_lookup[acc.id] = {
    #                 "bank_name": getattr(acc, "name", "Bank"),
    #                 "bank_last4": last4,
    #                 "account_id": acc.id,
    #             }

    #     # 5. Domain identification (Cash Float vs Capital Asset)
    #     cat_code = str(getattr(asset, "category", "")).upper()
    #     gl_head = ""
    #     if hasattr(asset.linked_gl_account, "subcategory"):
    #         gl_head = str(asset.linked_gl_account.subcategory).lower()
    #     else:
    #         gl_head = str(asset.linked_gl_account or "").lower()

    #     is_cash_domain = (
    #         "CASH" in cat_code
    #         or "FLOAT" in cat_code
    #         or "petty cash" in gl_head
    #         or "float" in gl_head
    #     )

    #     # 6. Aggregate metrics and assemble results
    #     cumulative_inflows = Decimal("0.00")
    #     operating_outflows = Decimal("0.00")
    #     results = []

    #     for m in mappings:
    #         amt = Decimal(str(m["amount"] or 0))
    #         purpose = str(m["transaction_purpose"] or "").upper()
    #         paired_leg = row_to_bank_leg.get(m["row_identifier"])

    #         # Determine direction:
    #         # For Cash Floats, top-ups are Inflows.
    #         # Otherwise, evaluate standard capital/income markers.
    #         is_inflow = (
    #             purpose
    #             in [
    #                 "CAPITAL_CONTRIBUTION",
    #                 "SUB_LEDGER_PAYMENT",
    #                 "ACQUISITION_PAYMENT",
    #                 "INFLOW",
    #             ]
    #             or is_cash_domain
    #         )

    #         if is_inflow:
    #             cumulative_inflows += amt
    #         else:
    #             operating_outflows += amt

    #         bank_id = paired_leg["account_id"] if paired_leg else None
    #         bank_meta = account_lookup.get(bank_id, {})

    #         # Resolve statement narration with fallback
    #         raw_narration = staging_map.get(m["row_identifier"])
    #         if not raw_narration and paired_leg and paired_leg.get("remarks"):
    #             raw_rem = paired_leg["remarks"]
    #             raw_narration = (
    #                 raw_rem.get("display_text")
    #                 or raw_rem.get("narration")
    #                 or raw_rem.get("payee")
    #                 if isinstance(raw_rem, dict)
    #                 else str(raw_rem)
    #             )

    #         results.append(
    #             {
    #                 "mapping_id": str(m["id"]),
    #                 "journal_id": (
    #                     str(paired_leg["id"]) if paired_leg else f"MAP-{m['id']}"
    #                 ),
    #                 "row_identifier": m["row_identifier"],
    #                 "transaction_date": (
    #                     m["transaction_date"].strftime("%Y-%m-%d")
    #                     if m.get("transaction_date")
    #                     else ""
    #                 ),
    #                 "amount": float(amt),
    #                 "debit": (
    #                     float(paired_leg["debit"])
    #                     if paired_leg
    #                     else (0.0 if is_inflow else float(amt))
    #                 ),
    #                 "credit": (
    #                     float(paired_leg["credit"])
    #                     if paired_leg
    #                     else (float(amt) if is_inflow else 0.0)
    #                 ),
    #                 "direction": "INFLOW" if is_inflow else "OUTFLOW",
    #                 "transaction_purpose": m["transaction_purpose"]
    #                 or "SUB_LEDGER_PAYMENT",
    #                 "narration": raw_narration
    #                 or m["user_note"]
    #                 or "Mapped Subledger Payment",
    #                 "remarks": raw_narration
    #                 or m["user_note"]
    #                 or "Mapped Subledger Payment",
    #                 "user_note": m["user_note"] or "",
    #                 "is_cash_entry": m["is_cash_entry"],
    #                 "bank_account_id": bank_id,
    #                 "bank_name": bank_meta.get("bank_name"),
    #                 "bank_last4": bank_meta.get("bank_last4"),
    #                 "mapped_at": (
    #                     m["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    #                     if m.get("created_at")
    #                     else None
    #                 ),
    #             }
    #         )

    #     # 7. Carrying valuation computation
    #     if is_cash_domain:
    #         # Float balance equation: Total Inflows - Outflows
    #         carrying_valuation = cumulative_inflows - operating_outflows
    #     else:
    #         # Capital asset equation: Acquisition Cost + Inflows - Outflows
    #         carrying_valuation = (
    #             Decimal(str(asset.acquisition_cost or 0))
    #             + cumulative_inflows
    #             - operating_outflows
    #         )

    #     db_valuation = Decimal(str(asset.current_valuation or 0))
    #     is_out_of_sync = abs(carrying_valuation - db_valuation) > Decimal("0.01")

    #     return Response(
    #         {
    #             "status": "success",
    #             "asset_id": str(asset.id),
    #             "asset_code": asset.asset_code,
    #             "asset_name": asset.name,
    #             "acquisition_cost": float(asset.acquisition_cost or 0),
    #             "current_valuation": float(asset.current_valuation or 0),
    #             "carrying_valuation": float(carrying_valuation),
    #             "cumulative_inflows": float(cumulative_inflows),
    #             "operating_outflows": float(operating_outflows),
    #             "net_yield": (
    #                 float(cumulative_inflows)
    #                 if is_cash_domain
    #                 else float(cumulative_inflows - operating_outflows)
    #             ),
    #             "is_out_of_sync": is_out_of_sync,
    #             "mapped_transactions": results,
    #         },
    #         status=status.HTTP_200_OK,
    #     )

    @action(detail=True, methods=["get"], url_path="mapped-transactions")
    def mapped_transactions(self, request, pk=None):
        from decimal import Decimal
        from django.apps import apps

        AssetTransactionMapping = apps.get_model("ledger", "AssetTransactionMapping")
        StatementStagingLine = apps.get_model("ledger", "StatementStagingLine")
        JournalEntry = apps.get_model("ledger", "JournalEntry")
        Account = apps.get_model("ledger", "Account")
        bank_account_ids = list(
            Account.objects.filter(
                Q(bank__isnull=False)
                | (~Q(account_number="") & Q(account_number__isnull=False))
                | (~Q(ifsc_code="") & Q(ifsc_code__isnull=False))
            ).values_list("id", flat=True)
        )
        asset = self.get_object()

        # 1. Fetch raw mapping records for this asset
        mappings = list(
            AssetTransactionMapping.objects.filter(asset=asset)
            .order_by("-transaction_date")
            .values(
                "id",
                "row_identifier",
                "transaction_date",
                "amount",
                "transaction_purpose",
                "user_note",
                "is_cash_entry",
                "created_at",
            )
        )

        bank_row_ids = [m["row_identifier"] for m in mappings if m["row_identifier"]]

        # 2. Fetch raw statement narrations from StatementStagingLine SSOT
        staging_map = dict(
            StatementStagingLine.objects.filter(
                row_identifier__in=bank_row_ids
            ).values_list("row_identifier", "raw_narration")
        )

        # 3. Fetch pairing bank account legs from JournalEntry (where account_id != 99)
        pairing_legs = list(
            JournalEntry.objects.filter(row_identifier__in=bank_row_ids)
            .exclude(account_id=99)
            .values("id", "row_identifier", "account_id", "debit", "credit", "remarks")
        )

        row_to_bank_leg = {p["row_identifier"]: p for p in pairing_legs}
        all_bank_ids = set(p["account_id"] for p in pairing_legs)

        # 4. Lookup Account metadata (name + last 4)
        account_lookup = {}
        if all_bank_ids:
            for acc in Account.objects.filter(id__in=all_bank_ids):
                acc_num = str(getattr(acc, "account_number", "") or "")
                last4 = acc_num[-4:] if len(acc_num) >= 4 else acc_num
                account_lookup[acc.id] = {
                    "bank_name": getattr(acc, "name", "Bank"),
                    "bank_last4": last4,
                    "account_id": acc.id,
                }

        # 5. Domain identification (Cash Float vs Capital Asset)
        cat_code = str(getattr(asset, "category", "")).upper()
        gl_head = ""
        if hasattr(asset.linked_gl_account, "subcategory"):
            gl_head = str(asset.linked_gl_account.subcategory).lower()
        else:
            gl_head = str(asset.linked_gl_account or "").lower()

        is_cash_domain = (
            "CASH" in cat_code
            or "FLOAT" in cat_code
            or "petty cash" in gl_head
            or "float" in gl_head
        )

        # 6. Aggregate metrics and assemble results
        cumulative_inflows = Decimal("0.00")
        operating_outflows = Decimal("0.00")
        results = []

        for m in mappings:
            amt = Decimal(str(m["amount"] or 0))
            purpose = str(m["transaction_purpose"] or "").upper()
            paired_leg = row_to_bank_leg.get(m["row_identifier"])

            # 🎯 STRICT MATHEMATICAL DIRECTION RESOLUTION:
            if any(
                term in purpose
                for term in ["SPEND", "EXPENSE", "OUTFLOW", "OPERATING_SPEND"]
            ):
                is_inflow = False
            elif any(
                term in purpose
                for term in ["TOPUP", "CAPITAL_CONTRIBUTION", "INFLOW", "CONTRIBUTION"]
            ):
                is_inflow = True
            elif paired_leg:
                # Bank debit > 0 means money came IN (Top-up / Inflow)
                # Bank credit > 0 means money went OUT (Spend / Outflow)
                is_inflow = Decimal(str(paired_leg.get("debit") or 0)) > 0
            else:
                is_inflow = not is_cash_domain

            if is_inflow:
                cumulative_inflows += amt
            else:
                operating_outflows += amt

            bank_id = paired_leg["account_id"] if paired_leg else None
            bank_meta = account_lookup.get(bank_id, {})

            # Resolve statement narration with fallback
            raw_narration = staging_map.get(m["row_identifier"])
            if not raw_narration and paired_leg and paired_leg.get("remarks"):
                raw_rem = paired_leg["remarks"]
                raw_narration = (
                    raw_rem.get("display_text")
                    or raw_rem.get("narration")
                    or raw_rem.get("payee")
                    if isinstance(raw_rem, dict)
                    else str(raw_rem)
                )

            leg_debit = (
                float(paired_leg["debit"])
                if paired_leg
                else (0.0 if is_inflow else float(amt))
            )
            leg_credit = (
                float(paired_leg["credit"])
                if paired_leg
                else (float(amt) if is_inflow else 0.0)
            )

            results.append(
                {
                    "mapping_id": str(m["id"]),
                    "journal_id": (
                        str(paired_leg["id"]) if paired_leg else f"MAP-{m['id']}"
                    ),
                    "row_identifier": m["row_identifier"],
                    "transaction_date": (
                        m["transaction_date"].strftime("%Y-%m-%d")
                        if m.get("transaction_date")
                        else ""
                    ),
                    "amount": float(amt),
                    "debit": leg_debit,
                    "credit": leg_credit,
                    "direction": "INFLOW" if is_inflow else "OUTFLOW",
                    "transaction_purpose": m["transaction_purpose"]
                    or ("FLOAT_TOPUP" if is_inflow else "OPERATING_SPEND"),
                    "narration": raw_narration
                    or m["user_note"]
                    or "Mapped Subledger Payment",
                    "remarks": raw_narration
                    or m["user_note"]
                    or "Mapped Subledger Payment",
                    "user_note": m["user_note"] or "",
                    "is_cash_entry": m["is_cash_entry"],
                    "bank_account_id": bank_id,
                    "bank_name": bank_meta.get("bank_name"),
                    "bank_last4": bank_meta.get("bank_last4"),
                    "mapped_at": (
                        m["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                        if m.get("created_at")
                        else None
                    ),
                }
            )

        # 7. Carrying valuation computation
        if is_cash_domain:
            carrying_valuation = cumulative_inflows - operating_outflows
        else:
            carrying_valuation = (
                Decimal(str(asset.acquisition_cost or 0))
                + cumulative_inflows
                - operating_outflows
            )

        db_valuation = Decimal(str(asset.current_valuation or 0))
        is_out_of_sync = abs(carrying_valuation - db_valuation) > Decimal("0.01")
        # Inside mapped_transactions in subledgerViews.py
        print(
            f"🟢 [DEBUG MAPPING]: ID={m['id']} | Amount={amt} | Purpose={purpose} | Inflow={is_inflow}"
        )
        return Response(
            {
                "status": "success",
                "asset_id": str(asset.id),
                "asset_code": asset.asset_code,
                "asset_name": asset.name,
                "acquisition_cost": float(asset.acquisition_cost or 0),
                "current_valuation": float(asset.current_valuation or 0),
                "carrying_valuation": float(carrying_valuation),
                "cumulative_inflows": float(cumulative_inflows),
                "operating_outflows": float(operating_outflows),
                "net_yield": float(cumulative_inflows - operating_outflows),
                "is_out_of_sync": is_out_of_sync,
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

    @action(detail=False, methods=["post"], url_path="check-mapped-rows")
    def check_mapped_rows(self, request):
        row_ids = request.data.get("row_identifiers", [])
        print("\n================ [CHECK MAPPED ROWS DEBUG] ================")
        print(f"|| Total row_identifiers received from frontend: {len(row_ids)}")
        print(f"|| First 5 received keys: {row_ids[:5]}")

        # 1. Direct query on row_identifier
        direct_matches = list(
            AssetTransactionMapping.objects.filter(
                row_identifier__in=row_ids
            ).select_related("asset")
        )
        print(f"|| Direct matches on row_identifier: {len(direct_matches)}")

        # 2. Check if the received IDs are JournalEntry IDs (numeric or UUID string)
        # Often the frontend candidate item has cand.row_identifier set to journal.id!
        journal_row_ids = list(
            JournalEntry.objects.filter(
                id__in=[i for i in row_ids if str(i).isdigit() or len(str(i)) == 36]
            ).values_list("row_identifier", flat=True)
        )
        print(
            f"|| Resolved {len(journal_row_ids)} row_identifiers via JournalEntry.id lookup"
        )

        je_matches = (
            list(
                AssetTransactionMapping.objects.filter(
                    row_identifier__in=journal_row_ids
                ).select_related("asset")
            )
            if journal_row_ids
            else []
        )
        print(f"|| Extra matches via JournalEntry linkage: {len(je_matches)}")

        # 3. Check what's in the DB for Bhima/Silver Plate specifically
        sample_db = list(
            AssetTransactionMapping.objects.filter(
                row_identifier="860c66fd278672aa3ee2ca242fc7812552ca4b375334121af034ce12f9af0f3c"
            ).values(
                "id", "row_identifier", "asset_id", "asset__asset_code", "asset__name"
            )
        )
        #  print(f"|| Sanity check in DB for Silver Plate row hash: {sample_db}")
        # print("============================================================\n")

        all_matches = {m.id: m for m in (direct_matches + je_matches)}.values()

        mapped_map = {}
        for m in all_matches:
            vendor_val = (
                m.asset.vendor.name
                if getattr(m.asset, "vendor", None)
                else getattr(m.asset, "vendor_name", "")
            )
            info = {
                "mapping_id": str(m.id),
                "asset_id": str(m.asset_id),
                "asset_code": m.asset.asset_code,
                "asset_name": m.asset.name,
                "vendor_name": vendor_val or "",
            }
            if m.row_identifier:
                mapped_map[str(m.row_identifier)] = info

        # Also map all linked JournalEntry IDs back to the same info
        all_row_hashes = [m.row_identifier for m in all_matches if m.row_identifier]
        if all_row_hashes:
            for je in JournalEntry.objects.filter(
                row_identifier__in=all_row_hashes
            ).values("id", "row_identifier"):
                info = mapped_map.get(str(je["row_identifier"]))
                if info:
                    mapped_map[str(je["id"])] = info

        return Response({"mapped_map": mapped_map}, status=status.HTTP_200_OK)


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

        sub_clean = subcategory_name.strip()

        # -------------------------------------------------------------
        # 🟢 1. ROBUST ASSET MATCHING (Verified schema fields only)
        # -------------------------------------------------------------
        asset_filter = (
            Q(category__icontains=sub_clean)
            | Q(category__iexact=sub_clean)
            | Q(asset_category__name__icontains=sub_clean)
            | Q(asset_category__name__iexact=sub_clean)
            | Q(asset_category__default_taxonomy_subcategory__icontains=sub_clean)
            | Q(asset_category__default_taxonomy_subcategory__iexact=sub_clean)
        )

        assets = (
            AssetSubLedger.objects.filter(asset_filter)
            .select_related("vendor", "asset_category")
            .prefetch_related("operational_accounts", "compliance_schedules")
            .distinct()
        )

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

            mapped_count = AssetTransactionMapping.objects.filter(asset=asset).count()

            asset_summary_list.append(
                {
                    "asset_id": str(asset.id),
                    "asset_code": asset.asset_code,
                    "name": asset.name,
                    "acquisition_cost": float(asset.acquisition_cost or 0),
                    "current_valuation": float(asset.current_valuation or 0),
                    "status": asset.status,
                    "mapped_transaction_total": float(mapped_total),
                    "mapped_count": mapped_count,
                    "vendor": vendor_id,
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_name,
                    "vendor_detail": (
                        {"id": vendor_id, "name": vendor_name} if asset.vendor else None
                    ),
                }
            )

        # -------------------------------------------------------------
        # 🟢 2. ROBUST GL TAXONOMY BALANCE CALCULATION
        # -------------------------------------------------------------
        gl_filter = (
            Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=sub_clean)
            | Q(remarks__target_account_name__iexact=sub_clean)
            | Q(remarks__subcategory__iexact=sub_clean)
        )

        mapped_row_ids = list(
            AssetTransactionMapping.objects.filter(asset__in=assets).values_list(
                "row_identifier", flat=True
            )
        )

        if mapped_row_ids:
            gl_filter |= Q(row_identifier__in=mapped_row_ids)

        Account = apps.get_model("ledger", "Account")
        bank_account_ids = list(
            Account.objects.filter(
                Q(bank__isnull=False)
                | (~Q(account_number="") & Q(account_number__isnull=False))
                | (~Q(ifsc_code="") & Q(ifsc_code__isnull=False))
            ).values_list("id", flat=True)
        )

        taxonomy_agg = JournalEntry.objects.filter(gl_filter, debit__gt=0).aggregate(
            total=Sum("debit"), count=Count("row_identifier", distinct=True)
        )

        total_taxonomy_debit = taxonomy_agg["total"] or Decimal("0.00")
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

#         taxonomy_entries = JournalEntry.objects.filter(debit__gt=0)

#         total_taxonomy_debit = Decimal("0.00")
#         for entry in taxonomy_entries.iterator():
#             snapshot = entry.evaluation_matrix_snapshot or {}
#             if (
#                 isinstance(snapshot, dict)
#                 and snapshot.get("resolved_subcategory") == subcategory_name
#             ):
#                 total_taxonomy_debit += entry.debit

#         assets = (
#             AssetSubLedger.objects.filter(
#                 asset_category__default_taxonomy_subcategory=subcategory_name
#             )
#             .select_related("vendor", "asset_category")
#             .prefetch_related("operational_accounts", "compliance_schedules")
#         )

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
