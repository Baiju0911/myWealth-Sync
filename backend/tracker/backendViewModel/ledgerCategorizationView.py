# Double Entry from Staging Queue to WIP to Journal entry

import re
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from django.contrib.auth import get_user_model

from ..models.models import (
    StatementStagingLine,
    MasterFinancialCategory,
    AccountingRule,
    WIPEvaluationMatrix,
    TransactionHeader,
    JournalEntry,
    JournalEntryMapping,
    Account,
)
from ..serializers import (
    MasterFinancialCategoryAdminSerializer,
    AccountingRuleAdminSerializer,
)
import json
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework import status

User = get_user_model()

from ..WIP import WIPIngestionSweeper, WIPReconciliationEngine

# class AutoCategorizeStagingQueueView(APIView):
#     """
#     🤖 TIER 1 ISOLATION PROXY ADAPTER
#     Wraps Tier 1 outputs inside expected schema boundaries using high-speed native
#     JSON streaming to bypass heavy DRF serialization overhead.
#     """

#     permission_classes = [AllowAny]

#     def post(self, request, *args, **kwargs):
#         account_id = request.data.get("account_id")
#         if not account_id:
#             # Short error payload is fine to keep as standard DRF Response since it's small
#             from rest_framework.response import Response

#             return Response(
#                 {"error": "Missing parameter tracking field: account_id"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # 🎯 STEP 1: Execute the sweep harvester loop phase first!
#         # This shifts cold PENDING rows into the active WIP sandbox table seamlessly.
#         sweep_metrics = WIPIngestionSweeper.execute_sweep(account_context_id=account_id)

#         # 🎯 STEP 2: Run your isolated multi-track evaluation matrix engine rules
#         # Now the engine has rows in WIPEvaluationMatrix to calculate matches on!
#         engine_result = WIPReconciliationEngine.evaluate_account_queue(
#             account_id=account_id
#         )

#         workspace_queue = engine_result.get("workspace_queue", [])
#         total_nodes = len(workspace_queue)

#         # Pull the matrix stats calculated by the parallel threads
#         matrix_summary_stats = engine_result.get(
#             "matrix_summary_stats",
#             {
#                 "t1_system": {"real": 0, "suspense": 0},
#                 "t2_internal": {"real": 0, "suspense": 0},
#                 "t3_layout": {"real": 0, "suspense": 0},
#                 "t4_rulebook": {"real": 0, "suspense": 0},
#                 "total_processed": total_nodes,
#             },
#         )

#         # ─── 🎯 THE SPEED BYPASS LAYER ───
#         # Package the exact dictionary shape your frontend expects
#         response_data = {
#             "account_id": account_id,
#             "sweep_metrics": sweep_metrics,
#             "evaluation_summary": {
#                 "staged_for_bulk_high": total_nodes,
#                 "staged_for_bulk_medium": 0,
#                 "uncategorized_vault_zero": 0,
#             },
#             "workspace_queue": workspace_queue,
#             "matrix_summary_stats": matrix_summary_stats,
#         }

#         # Dump using native C-optimized json engine and stream directly into network buffers
#         json_payload = json.dumps(response_data)

#         return HttpResponse(json_payload, content_type="application/json", status=200)


class AutoCategorizeStagingQueueView(APIView):
    """
    🤖 TIER 1 ISOLATION PROXY ADAPTER
    Wraps Tier 1-5 outputs inside expected schema boundaries using high-speed native
    JSON streaming to bypass heavy DRF serialization overhead.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        if not account_id:
            from rest_framework.response import Response

            return Response(
                {"error": "Missing parameter tracking field: account_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🎯 STEP 1: Execute the sweep harvester loop phase first!
        sweep_metrics = WIPIngestionSweeper.execute_sweep(account_context_id=account_id)

        # 🎯 STEP 2: Run multi-track evaluation matrix engine rules (T1 -> T5 AI)
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        workspace_queue = engine_result.get("workspace_queue", [])
        total_nodes = len(workspace_queue)

        # Pull matrix stats calculated by reconciliation engine
        matrix_summary_stats = engine_result.get(
            "matrix_summary_stats",
            {
                "t1_system": {"real": 0, "suspense": 0},
                "t2_internal": {"real": 0, "suspense": 0},
                "t3_layout": {"real": 0, "suspense": 0},
                "t4_rulebook": {"real": 0, "suspense": 0},
                "t5_ai": {"real": 0, "suspense": 0},
                "total_processed": total_nodes,
            },
        )

        # Package payload expected by StagingQueueEvaluator frontend
        response_data = {
            "account_id": account_id,
            "sweep_metrics": sweep_metrics,
            "evaluation_summary": {
                "staged_for_bulk_high": total_nodes,
                "staged_for_bulk_medium": 0,
                "uncategorized_vault_zero": 0,
            },
            "workspace_queue": workspace_queue,
            "matrix_summary_stats": matrix_summary_stats,
        }

        json_payload = json.dumps(response_data)
        return HttpResponse(json_payload, content_type="application/json", status=200)


class MasterFinancialCategoryViewSet(viewsets.ModelViewSet):
    """
    💼 REST ENDPOINT CRUD FOR MATRIX CATEGORIES
    """

    queryset = MasterFinancialCategory.objects.all()
    serializer_class = MasterFinancialCategoryAdminSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = MasterFinancialCategory.objects.all()
        category_type = self.request.query_params.get("category_type")
        act_category = self.request.query_params.get("act_category")

        if category_type:
            queryset = queryset.filter(category_type=category_type)
        if act_category:
            queryset = queryset.filter(act_category__icontains=act_category)
        return queryset


class AccountingRuleViewSet(viewsets.ModelViewSet):
    """
    💼 REST ENDPOINT CRUD FOR TIERED GOLDEN RULES
    """

    queryset = AccountingRule.objects.all()
    serializer_class = AccountingRuleAdminSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = AccountingRule.objects.all()
        entry_type = self.request.query_params.get("entry_type")
        is_active = self.request.query_params.get("is_active")

        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        if is_active:
            queryset = queryset.filter(is_active=str(is_active).lower() == "true")
        return queryset


# def execute_bulk_sync_release(user, account_entity, wip_row_ids):
#     """Executes a structurally isolated double-entry release:

#     1. Guarantees 100% matching hex keys by anchoring directly to
#     row_footprint_hash.
#     2. Guarantees Node 99 binding for the virtual taxonomy master account.
#     3. Attaches fully structured JSON remarks (directional_prefix, display_text)
#     to both double-entry legs.
#     4. Flips WIP & Staging rows to COMPLETED without issuing DELETE queries.
#     """
#     try:
#         with transaction.atomic():
#             wip_nodes = WIPEvaluationMatrix.objects.filter(
#                 id__in=wip_row_ids,
#                 account=account_entity,
#                 processing_status="PENDING",
#             ).select_related("staging_line", "applied_rule")

#             if not wip_nodes.exists():
#                 return {
#                     "status": "error",
#                     "message": "No active staging nodes found to process.",
#                 }

#             # 🎯 1. GUARANTEE TAXONOMY INTEGRATION NODE HAS ID 99
#             taxonomy_master_account = Account.objects.filter(id=99).first()
#             if not taxonomy_master_account:
#                 taxonomy_master_account = Account.objects.create(
#                     id=99,
#                     name="SYSTEM_TAXONOMY_INTEGRATION_NODE",
#                     bank=account_entity.bank,
#                     account_type="SYSTEM_CORE",
#                     ifsc_code="SYS00000000",
#                     branch_name="System Kernel",
#                     address="Virtual Ledger Gateway Node",
#                 )

#             entries_to_create = []
#             staging_line_ids_to_complete = []

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)

#                 is_outflow = node.debit > 0
#                 amount_value = node.debit if is_outflow else node.credit
#                 decimal_amount = Decimal(str(amount_value))
#                 float_amt = float(decimal_amount)

#                 true_hex_anchor = node.row_footprint_hash

#                 # 🟢 2. EXTRACT RAW STAGING METADATA
#                 staging_line = node.staging_line
#                 raw_narration = (
#                     staging_line.narration
#                     if staging_line
#                     else node.narration_normalized
#                 )
#                 raw_payee = (
#                     getattr(staging_line, "payee", None) or raw_narration
#                     if staging_line
#                     else raw_narration
#                 )
#                 raw_upi = (
#                     getattr(staging_line, "upi_ref", None) if staging_line else None
#                 )

#                 direction_word = "By" if is_outflow else "To"
#                 target_sub = node.resolved_subcategory or "Suspense Account"

#                 if is_outflow:
#                     action_word = (
#                         f"Paid ₹{float_amt:,.2f} to {raw_payee}"
#                         if raw_payee
#                         else f"Outflow of ₹{float_amt:,.2f}"
#                     )
#                 else:
#                     action_word = (
#                         f"Received ₹{float_amt:,.2f} from {raw_payee or 'Payee'}"
#                     )

#                 ref_str = f" [Ref: {raw_upi}]" if raw_upi else ""
#                 display_text = f"{direction_word} {target_sub} | {action_word}{ref_str} | Ingested via Staging"

#                 # 🟢 3. STRUCTURED REMARKS PAYLOAD (WORKBENCH COMPATIBLE)
#                 remarks_payload = {
#                     "narration": raw_narration,
#                     "payee": raw_payee,
#                     "upi_ref": raw_upi,
#                     "directional_prefix": direction_word,
#                     "target_account_name": target_sub,
#                     "display_text": display_text,
#                 }

#                 # 🟢 4. BUILD EVALUATION MATRIX SNAPSHOT PAYLOAD
#                 matrix_snapshot = {
#                     "t1_category": node.t1_category,
#                     "t1_subcategory": node.t1_subcategory,
#                     "t2_category": node.t2_category,
#                     "t2_subcategory": node.t2_subcategory,
#                     "t3_category": node.t3_category,
#                     "t3_subcategory": node.t3_subcategory,
#                     "resolved_category": node.resolved_category,
#                     "resolved_subcategory": node.resolved_subcategory,
#                     "confidence_score": node.confidence_score,
#                     "applied_rule_code": (
#                         node.applied_rule.rule_code if node.applied_rule else "MANUAL"
#                     ),
#                 }

#                 # ─── LEG 1: THE LIQUIDITY POOL (BANK SIDE) ───
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=account_entity,  # Physical Bank (e.g., Account ID 4)
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=(decimal_amount if not is_outflow else Decimal("0.00")),
#                         credit=(Decimal("0.00") if not is_outflow else decimal_amount),
#                         remarks={
#                             **remarks_payload,
#                             "target_account_name": account_entity.name,
#                         },
#                         evaluation_matrix_snapshot={
#                             "leg_context": "LIQUIDITY_CORE",
#                             "resolved_category": node.resolved_category,
#                             "resolved_subcategory": node.resolved_subcategory,
#                         },
#                     )
#                 )

#                 # ─── LEG 2: THE CONTRA POOL (TAXONOMY SIDE - NODE 99) ───
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=taxonomy_master_account,  # Strictly Node ID 99
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=(decimal_amount if is_outflow else Decimal("0.00")),
#                         credit=(Decimal("0.00") if is_outflow else decimal_amount),
#                         remarks=remarks_payload,
#                         evaluation_matrix_snapshot=matrix_snapshot,  # Full 4-Tier Snapshot
#                     )
#                 )

#             # 5. Bulk create double-entry transactions
#             JournalEntry.objects.bulk_create(entries_to_create)

#             # 6. Mark WIP sandbox rows as COMPLETED (NO DELETE!)
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )

#             # 7. Mark source Staging rows as COMPLETED
#             StatementStagingLine.objects.filter(
#                 id__in=staging_line_ids_to_complete
#             ).update(routing_status="COMPLETED")

#         return {"status": "success", "processed_nodes": len(wip_row_ids)}

#     except Exception as e:
#         return {
#             "status": "error",
#             "message": f"Database transaction aborted: {str(e)}",
#         }


def execute_bulk_sync_release(user, account_entity, wip_row_ids):
    """Executes a structurally isolated double-entry release:

    1. Guarantees 100% matching hex keys by anchoring directly to row_footprint_hash.
    2. Guarantees Node 99 binding for the virtual taxonomy master account.
    3. Attaches fully structured JSON remarks to both double-entry legs.
    4. Preserves full T1->T5 evaluation matrix JSON snapshots without data loss.
    5. Flips WIP & Staging rows to COMPLETED without issuing DELETE queries.
    """
    try:
        with transaction.atomic():
            wip_nodes = WIPEvaluationMatrix.objects.filter(
                id__in=wip_row_ids,
                account=account_entity,
                processing_status="PENDING",
            ).select_related("staging_line", "applied_rule")

            if not wip_nodes.exists():
                return {
                    "status": "error",
                    "message": "No active staging nodes found to process.",
                }

            # 🎯 1. GUARANTEE TAXONOMY INTEGRATION NODE HAS ID 99
            taxonomy_master_account = Account.objects.filter(id=99).first()
            if not taxonomy_master_account:
                taxonomy_master_account = Account.objects.create(
                    id=99,
                    name="SYSTEM_TAXONOMY_INTEGRATION_NODE",
                    bank=account_entity.bank,
                    account_type="SYSTEM_CORE",
                    ifsc_code="SYS00000000",
                    branch_name="System Kernel",
                    address="Virtual Ledger Gateway Node",
                )

            entries_to_create = []
            staging_line_ids_to_complete = []

            for node in wip_nodes:
                staging_line_ids_to_complete.append(node.staging_line_id)

                is_outflow = node.debit > 0
                amount_value = node.debit if is_outflow else node.credit
                decimal_amount = Decimal(str(amount_value))
                float_amt = float(decimal_amount)

                true_hex_anchor = node.row_footprint_hash

                # 🟢 2. EXTRACT RAW STAGING METADATA
                staging_line = node.staging_line
                raw_narration = (
                    staging_line.narration
                    if staging_line
                    else node.narration_normalized
                )
                raw_payee = (
                    getattr(staging_line, "payee", None) or raw_narration
                    if staging_line
                    else raw_narration
                )
                raw_upi = (
                    getattr(staging_line, "upi_ref", None) if staging_line else None
                )

                direction_word = "By" if is_outflow else "To"
                target_sub = node.resolved_subcategory or "Suspense Account"

                if is_outflow:
                    action_word = (
                        f"Paid ₹{float_amt:,.2f} to {raw_payee}"
                        if raw_payee
                        else f"Outflow of ₹{float_amt:,.2f}"
                    )
                else:
                    action_word = (
                        f"Received ₹{float_amt:,.2f} from {raw_payee or 'Payee'}"
                    )

                ref_str = f" [Ref: {raw_upi}]" if raw_upi else ""
                display_text = f"{direction_word} {target_sub} | {action_word}{ref_str} | Ingested via Staging"

                # 🟢 3. STRUCTURED REMARKS PAYLOAD
                remarks_payload = {
                    "narration": raw_narration,
                    "payee": raw_payee,
                    "upi_ref": raw_upi,
                    "directional_prefix": direction_word,
                    "target_account_name": target_sub,
                    "display_text": display_text,
                }

                # 🟢 4. BUILD EVALUATION MATRIX SNAPSHOT PAYLOAD (SAFE JSON MERGE)
                # Unpacks node.matrix_evaluation (contains t1..t5 AI breakdown)
                eval_matrix = node.matrix_evaluation or {}
                matrix_snapshot = {
                    **eval_matrix,
                    "resolved_category": node.resolved_category,
                    "resolved_subcategory": node.resolved_subcategory,
                    "confidence_score": node.confidence_score,
                    "applied_rule_code": (
                        node.applied_rule.rule_code
                        if node.applied_rule
                        else (
                            "AI_VECTOR_CACHE"
                            if node.confidence_score == 100
                            else "MANUAL"
                        )
                    ),
                }

                # ─── LEG 1: LIQUIDITY POOL (BANK SIDE) ───
                entries_to_create.append(
                    JournalEntry(
                        account=account_entity,
                        transaction_date=node.raw_statement_date,
                        row_identifier=true_hex_anchor,
                        debit=(decimal_amount if not is_outflow else Decimal("0.00")),
                        credit=(Decimal("0.00") if not is_outflow else decimal_amount),
                        remarks={
                            **remarks_payload,
                            "target_account_name": account_entity.name,
                        },
                        evaluation_matrix_snapshot={
                            "leg_context": "LIQUIDITY_CORE",
                            "resolved_category": node.resolved_category,
                            "resolved_subcategory": node.resolved_subcategory,
                        },
                    )
                )

                # ─── LEG 2: CONTRA POOL (TAXONOMY SIDE - NODE 99) ───
                entries_to_create.append(
                    JournalEntry(
                        account=taxonomy_master_account,
                        transaction_date=node.raw_statement_date,
                        row_identifier=true_hex_anchor,
                        debit=(decimal_amount if is_outflow else Decimal("0.00")),
                        credit=(Decimal("0.00") if is_outflow else decimal_amount),
                        remarks=remarks_payload,
                        evaluation_matrix_snapshot=matrix_snapshot,
                    )
                )

            # 5. Bulk create double-entry transactions
            JournalEntry.objects.bulk_create(entries_to_create)

            # 6. Mark WIP sandbox rows as COMPLETED
            WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
                processing_status="COMPLETED"
            )

            # 7. Mark source Staging rows as COMPLETED
            StatementStagingLine.objects.filter(
                id__in=staging_line_ids_to_complete
            ).update(routing_status="COMPLETED")

        return {"status": "success", "processed_nodes": len(wip_row_ids)}

    except Exception as e:
        return {
            "status": "error",
            "message": f"Database transaction aborted: {str(e)}",
        }


@api_view(["POST"])
@permission_classes([AllowAny])
def CommitStagingQueue(request):
    """
    Open API endpoint for rapid local prototyping of the matrix release.
    Bypasses token auth validation layers.
    """
    # 📥 1. Extract inputs from the payload request object block
    account_id = request.data.get("account_id")
    wip_row_ids = request.data.get("wip_ids", [])

    if not account_id:
        return Response(
            {
                "status": "error",
                "message": "Missing account_id parameter string vector.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # 🏛️ 2. Resolve account_entity from database vector
        account_entity = Account.objects.get(id=account_id)

        # 👤 3. Fallback User Provider: Fetch the platform developer identity context
        user = User.objects.first()
        if not user:
            return Response(
                {
                    "status": "error",
                    "message": "No identity records found in database auth tables.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    except Account.DoesNotExist:
        return Response(
            {
                "status": "error",
                "message": f"Target Account identity '{account_id}' not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 🚀 4. Execute the atomic transaction with the resolved variables
    sync_result = execute_bulk_sync_release(
        user=user, account_entity=account_entity, wip_row_ids=wip_row_ids
    )

    if sync_result["status"] == "success":
        return Response(sync_result, status=status.HTTP_200_OK)
    else:
        return Response(sync_result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
