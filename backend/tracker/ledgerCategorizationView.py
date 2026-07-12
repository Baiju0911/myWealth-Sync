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

from .models import (
    StatementStagingLine,
    MasterFinancialCategory,
    AccountingRule,
    WIPEvaluationMatrix,
    TransactionHeader,
    JournalEntry,
    JournalEntryMapping,
    Account,
)
from .serializers import (
    MasterFinancialCategoryAdminSerializer,
    AccountingRuleAdminSerializer,
)
import json
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework import status

User = get_user_model()

from .serviceWIP import WIPIngestionSweeper, WIPReconciliationEngine


class AutoCategorizeStagingQueueView_older(APIView):
    """
    🤖 TIER 1 ISOLATION PROXY ADAPTER
    Wraps Tier 1 outputs inside expected schema boundaries to unblock frontend loading.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        if not account_id:
            return Response(
                {"error": "Missing parameter tracking field: account_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🎯 STEP 1: Execute the sweep harvester loop phase first!
        # This shifts cold PENDING rows into the active WIP sandbox table seamlessly.
        sweep_metrics = WIPIngestionSweeper.execute_sweep(account_context_id=account_id)

        # 🎯 STEP 2: Run your isolated multi-track evaluation matrix engine rules
        # Now the engine has rows in WIPEvaluationMatrix to calculate matches on!
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        workspace_queue = engine_result.get("workspace_queue", [])
        total_nodes = len(workspace_queue)

        # Pull the matrix stats calculated by the parallel threads
        matrix_summary_stats = engine_result.get(
            "matrix_summary_stats",
            {
                "t1_system": {"real": 0, "suspense": 0},
                "t2_internal": {"real": 0, "suspense": 0},
                "t3_layout": {"real": 0, "suspense": 0},
                "t4_rulebook": {"real": 0, "suspense": 0},
                "total_processed": total_nodes,
            },
        )

        return Response(
            {
                "account_id": account_id,
                "sweep_metrics": sweep_metrics,  # Included for backend diagnostic tracking
                "evaluation_summary": {
                    "staged_for_bulk_high": total_nodes,
                    "staged_for_bulk_medium": 0,
                    "uncategorized_vault_zero": 0,
                },
                "workspace_queue": workspace_queue,
                "matrix_summary_stats": matrix_summary_stats,
            },
            status=status.HTTP_200_OK,
        )


class AutoCategorizeStagingQueueView(APIView):
    """
    🤖 TIER 1 ISOLATION PROXY ADAPTER
    Wraps Tier 1 outputs inside expected schema boundaries using high-speed native
    JSON streaming to bypass heavy DRF serialization overhead.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        if not account_id:
            # Short error payload is fine to keep as standard DRF Response since it's small
            from rest_framework.response import Response

            return Response(
                {"error": "Missing parameter tracking field: account_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🎯 STEP 1: Execute the sweep harvester loop phase first!
        # This shifts cold PENDING rows into the active WIP sandbox table seamlessly.
        sweep_metrics = WIPIngestionSweeper.execute_sweep(account_context_id=account_id)

        # 🎯 STEP 2: Run your isolated multi-track evaluation matrix engine rules
        # Now the engine has rows in WIPEvaluationMatrix to calculate matches on!
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        workspace_queue = engine_result.get("workspace_queue", [])
        total_nodes = len(workspace_queue)

        # Pull the matrix stats calculated by the parallel threads
        matrix_summary_stats = engine_result.get(
            "matrix_summary_stats",
            {
                "t1_system": {"real": 0, "suspense": 0},
                "t2_internal": {"real": 0, "suspense": 0},
                "t3_layout": {"real": 0, "suspense": 0},
                "t4_rulebook": {"real": 0, "suspense": 0},
                "total_processed": total_nodes,
            },
        )

        # ─── 🎯 THE SPEED BYPASS LAYER ───
        # Package the exact dictionary shape your frontend expects
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

        # Dump using native C-optimized json engine and stream directly into network buffers
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


def execute_bulk_sync_release(user, account_entity, wip_row_ids):
    """
    Executes an optimized, normalized double-entry release:
    1. Generates 2 flat JournalEntry rows cross-referenced via Hex row footprints.
    2. Inherits row_identifier directly from StatementStagingLine to avoid hash gaps.
    3. Purges workspace sandboxes and marks source lines as COMPLETED.
    """
    try:
        with transaction.atomic():
            wip_nodes = WIPEvaluationMatrix.objects.filter(
                id__in=wip_row_ids, account=account_entity, processing_status="PENDING"
            ).select_related("staging_line", "applied_rule")

            if not wip_nodes.exists():
                return {
                    "status": "error",
                    "message": "No active staging nodes found to process.",
                }

            entries_to_create = []
            staging_line_ids_to_complete = []

            for node in wip_nodes:
                staging_line_ids_to_complete.append(node.staging_line_id)

                has_debit = node.debit > 0
                amount_value = node.debit if has_debit else node.credit
                decimal_amount = Decimal(str(amount_value))

                # 🎯 THE FIX: Inherit the exact Hex string fingerprint directly from the source line!
                true_hex_anchor = node.staging_line.row_identifier

                # Compile the full multi-tier execution audit trace payload safely
                matrix_snapshot = {
                    "t1_category": node.t1_category,
                    "t1_subcategory": node.t1_subcategory,
                    "t2_category": node.t2_category,
                    "t2_subcategory": node.t2_subcategory,
                    "t3_category": node.t3_category,
                    "t3_subcategory": node.t3_subcategory,
                    "resolved_category": node.resolved_category,
                    "resolved_subcategory": node.resolved_subcategory,
                    "confidence_score": node.confidence_score,
                    "applied_rule_code": (
                        node.applied_rule.rule_code if node.applied_rule else "MANUAL"
                    ),
                }

                # ─── LEG 1: THE LIQUIDITY POOL (BANK LEGER SIDE) ───
                entries_to_create.append(
                    JournalEntry(
                        account=account_entity,
                        transaction_date=node.raw_statement_date,
                        row_identifier=true_hex_anchor,  # ✅ 100% Match guaranteed
                        debit=Decimal("0.00") if has_debit else decimal_amount,
                        credit=decimal_amount if has_debit else Decimal("0.00"),
                        evaluation_matrix_snapshot={"leg_context": "LIQUIDITY_CORE"},
                    )
                )

                # ─── LEG 2: THE CONTRA MATRIX DESTINATION (TAXONOMY SIDE) ───
                entries_to_create.append(
                    JournalEntry(
                        account=account_entity,
                        transaction_date=node.raw_statement_date,
                        row_identifier=true_hex_anchor,  # ✅ 100% Match guaranteed
                        debit=decimal_amount if has_debit else Decimal("0.00"),
                        credit=Decimal("0.00") if has_debit else decimal_amount,
                        evaluation_matrix_snapshot=matrix_snapshot,
                    )
                )

            # 2. Bulk insert execution block
            JournalEntry.objects.bulk_create(entries_to_create)

            # 3. HARD PURGE: Clear out the matrix playground sandbox
            # WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).delete()
            WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
                processing_status="COMPLETED"
            )

            # 4. STATUS CLOSE: Mark matching source staging rows as COMPLETED
            StatementStagingLine.objects.filter(
                id__in=staging_line_ids_to_complete
            ).update(routing_status="COMPLETED")

        return {"status": "success", "processed_nodes": len(wip_row_ids)}

    except Exception as e:
        return {"status": "error", "message": f"Database transaction aborted: {str(e)}"}


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
