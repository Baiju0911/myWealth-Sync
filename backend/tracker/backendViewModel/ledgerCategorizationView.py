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

from ..models import (
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

from ..serviceWIP import WIPIngestionSweeper, WIPReconciliationEngine

# class AutoCategorizeStagingQueueView_older(APIView):
#     """
#     🤖 TIER 1 ISOLATION PROXY ADAPTER
#     Wraps Tier 1 outputs inside expected schema boundaries to unblock frontend loading.
#     """

#     permission_classes = [AllowAny]

#     def post(self, request, *args, **kwargs):
#         account_id = request.data.get("account_id")
#         if not account_id:
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

#         return Response(
#             {
#                 "account_id": account_id,
#                 "sweep_metrics": sweep_metrics,  # Included for backend diagnostic tracking
#                 "evaluation_summary": {
#                     "staged_for_bulk_high": total_nodes,
#                     "staged_for_bulk_medium": 0,
#                     "uncategorized_vault_zero": 0,
#                 },
#                 "workspace_queue": workspace_queue,
#                 "matrix_summary_stats": matrix_summary_stats,
#             },
#             status=status.HTTP_200_OK,
#         )


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


# def execute_bulk_sync_release_older(user, account_entity, wip_row_ids):
#     """
#     Executes an optimized, normalized double-entry release:
#     1. Generates 2 flat JournalEntry rows cross-referenced via Hex row footprints.
#     2. Inherits row_identifier directly from StatementStagingLine to avoid hash gaps.
#     3. Purges workspace sandboxes and marks source lines as COMPLETED.
#     """
#     try:
#         with transaction.atomic():
#             wip_nodes = WIPEvaluationMatrix.objects.filter(
#                 id__in=wip_row_ids, account=account_entity, processing_status="PENDING"
#             ).select_related("staging_line", "applied_rule")

#             if not wip_nodes.exists():
#                 return {
#                     "status": "error",
#                     "message": "No active staging nodes found to process.",
#                 }

#             entries_to_create = []
#             staging_line_ids_to_complete = []

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)

#                 has_debit = node.debit > 0
#                 amount_value = node.debit if has_debit else node.credit
#                 decimal_amount = Decimal(str(amount_value))

#                 # 🎯 THE FIX: Inherit the exact Hex string fingerprint directly from the source line!
#                 true_hex_anchor = node.staging_line.row_identifier

#                 # Compile the full multi-tier execution audit trace payload safely
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

#                 # ─── LEG 1: THE LIQUIDITY POOL (BANK LEGER SIDE) ───
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=account_entity,
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,  # ✅ 100% Match guaranteed
#                         debit=Decimal("0.00") if has_debit else decimal_amount,
#                         credit=decimal_amount if has_debit else Decimal("0.00"),
#                         evaluation_matrix_snapshot={"leg_context": "LIQUIDITY_CORE"},
#                     )
#                 )

#                 # ─── LEG 2: THE CONTRA MATRIX DESTINATION (TAXONOMY SIDE) ───
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=account_entity,
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,  # ✅ 100% Match guaranteed
#                         debit=decimal_amount if has_debit else Decimal("0.00"),
#                         credit=Decimal("0.00") if has_debit else decimal_amount,
#                         evaluation_matrix_snapshot=matrix_snapshot,
#                     )
#                 )

#             # 2. Bulk insert execution block
#             JournalEntry.objects.bulk_create(entries_to_create)

#             # 3. HARD PURGE: Clear out the matrix playground sandbox
#             # WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).delete()
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )

#             # 4. STATUS CLOSE: Mark matching source staging rows as COMPLETED
#             StatementStagingLine.objects.filter(
#                 id__in=staging_line_ids_to_complete
#             ).update(routing_status="COMPLETED")

#         return {"status": "success", "processed_nodes": len(wip_row_ids)}

#     except Exception as e:
#         return {"status": "error", "message": f"Database transaction aborted: {str(e)}"}


# def execute_bulk_sync_release_older1(user, account_entity, wip_row_ids):
#     """
#     Executes an optimized, normalized double-entry release using your exact models:
#     1. Generates Leg 1 (Liquidity) targeting the real physical bank Account entity.
#     2. Generates Leg 2 (Taxonomy) targeting a system-wide category accounting node.
#     3. Cross-references both entries via the identical Hex row footprint anchor.
#     """
#     try:
#         with transaction.atomic():
#             # Fetch the pending sandboxed lines
#             wip_nodes = WIPEvaluationMatrix.objects.filter(
#                 id__in=wip_row_ids, account=account_entity, processing_status="PENDING"
#             ).select_related("staging_line", "applied_rule")

#             if not wip_nodes.exists():
#                 return {
#                     "status": "error",
#                     "message": "No active staging nodes found to process.",
#                 }

#             # 🎯 GET OR CREATE THE TAXONOMY GATEWAY ACCOUNT:
#             # Spawns a single master node inside your existing Account table
#             # to handle Leg 2 classifications cleanly without a COA table.
#             taxonomy_master_account, _ = Account.objects.get_or_create(
#                 name="System Taxonomy Master",
#                 defaults={
#                     "bank": account_entity.bank,  # Inherit the bank reference context
#                     "account_type": "SYSTEM_CORE",
#                     "ifsc_code": "SYSTEM00000",
#                     "branch_name": "System Engine Core",
#                     "address": "In-Memory System Virtual Gateway",
#                 },
#             )

#             entries_to_create = []
#             staging_line_ids_to_complete = []

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)

#                 # 🏦 BANK DIRECTION CONVENTION CHECK:
#                 # node.debit > 0 means money left the account (Outflow)
#                 # node.credit > 0 means money entered the account (Inflow)
#                 is_outflow = node.debit > 0
#                 amount_value = node.debit if is_outflow else node.credit
#                 decimal_amount = Decimal(str(amount_value))

#                 # Inherit the exact hex code token anchor from staging
#                 true_hex_anchor = node.staging_line.row_identifier

#                 # Compile the full multi-tier execution audit trace payload safely
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

#                 # ─── LEG 1: THE LIQUIDITY POOL (BANK LEGER SIDE) ───
#                 # Outflow: Credits the bank account (reduces cash balance)
#                 # Inflow: Debits the bank account (increases cash balance)
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=account_entity,  # HDFC / SBI physical instance
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=decimal_amount if not is_outflow else Decimal("0.00"),
#                         credit=Decimal("0.00") if not is_outflow else decimal_amount,
#                         evaluation_matrix_snapshot={"leg_context": "LIQUIDITY_CORE"},
#                     )
#                 )

#                 # ─── LEG 2: THE CONTRA MATRIX DESTINATION (TAXONOMY SIDE) ───
#                 # Outflow: Debits the taxonomy master (tracks expenses)
#                 # Inflow: Credits the taxonomy master (tracks revenue)
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=taxonomy_master_account,  # 👈 Routed to our system master node
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=decimal_amount if is_outflow else Decimal("0.00"),
#                         credit=Decimal("0.00") if is_outflow else decimal_amount,
#                         evaluation_matrix_snapshot=matrix_snapshot,  # Holds your rule classifications
#                     )
#                 )

#             # 2. Bulk insert execution block
#             JournalEntry.objects.bulk_create(entries_to_create)

#             # 3. WORKSPACE STATUS CLOSE: Flag rows as COMPLETED (ready for future purges)
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )

#             # 4. STAGING STATUS CLOSE: Mark matching staging records out of queue
#             StatementStagingLine.objects.filter(
#                 id__in=staging_line_ids_to_complete
#             ).update(routing_status="COMPLETED")

#         return {"status": "success", "processed_nodes": len(wip_row_ids)}

#     except Exception as e:
#         return {"status": "error", "message": f"Database transaction aborted: {str(e)}"}


# def execute_bulk_sync_release_older(user, account_entity, wip_row_ids):
#     """
#     Executes a structurally isolated double-entry release:
#     1. Guarantees 100% matching hex keys by anchoring directly to row_footprint_hash.
#     2. Dynamically isolates the virtual taxonomy master from physical bank accounts.
#     """
#     try:
#         with transaction.atomic():
#             wip_nodes = WIPEvaluationMatrix.objects.filter(
#                 id__in=wip_row_ids, account=account_entity, processing_status="PENDING"
#             ).select_related("staging_line", "applied_rule")

#             if not wip_nodes.exists():
#                 return {
#                     "status": "error",
#                     "message": "No active staging nodes found to process.",
#                 }

#             # 🎯 SYSTEM ACCOUNT ISOLATION SAFEGUARD:
#             # We enforce a dedicated virtual name to prevent it from overlapping
#             # with your physical bank account records (like account_id 8).
#             taxonomy_master_account, _ = Account.objects.get_or_create(
#                 name="SYSTEM_TAXONOMY_INTEGRATION_NODE",
#                 defaults={
#                     "bank": account_entity.bank,
#                     "account_type": "SYSTEM_CORE",
#                     "ifsc_code": "SYS00000000",
#                     "branch_name": "System Kernel",
#                     "address": "Virtual Ledger Gateway Node",
#                 },
#             )

#             entries_to_create = []
#             staging_line_ids_to_complete = []

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)

#                 is_outflow = node.debit > 0
#                 amount_value = node.debit if is_outflow else node.credit
#                 decimal_amount = Decimal(str(amount_value))

#                 # 🎯 CORRECTION: Use row_footprint_hash directly to guarantee 100% identical hex matching pairs
#                 true_hex_anchor = node.row_footprint_hash

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
#                         account=account_entity,  # Physical Bank (e.g., account_id 3)
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=decimal_amount if not is_outflow else Decimal("0.00"),
#                         credit=Decimal("0.00") if not is_outflow else decimal_amount,
#                         evaluation_matrix_snapshot={"leg_context": "LIQUIDITY_CORE"},
#                     )
#                 )

#                 # ─── LEG 2: THE CONTRA POOL (TAXONOMY SIDE) ───
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=taxonomy_master_account,  # Isolated Virtual Node
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=decimal_amount if is_outflow else Decimal("0.00"),
#                         credit=Decimal("0.00") if is_outflow else decimal_amount,
#                         evaluation_matrix_snapshot=matrix_snapshot,
#                     )
#                 )

#             # 2. Bulk create transactions simultaneously
#             JournalEntry.objects.bulk_create(entries_to_create)

#             # 3. Close out the workspace sandbox rows
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )

#             # 4. Mark source staging rows out of the pending queue
#             StatementStagingLine.objects.filter(
#                 id__in=staging_line_ids_to_complete
#             ).update(routing_status="COMPLETED")

#         return {"status": "success", "processed_nodes": len(wip_row_ids)}

#     except Exception as e:
#         return {"status": "error", "message": f"Database transaction aborted: {str(e)}"}


# def execute_bulk_sync_release(user, account_entity, wip_row_ids):
#     """Executes a structurally isolated double-entry release:

#     1. Guarantees 100% matching hex keys by anchoring directly to
#     row_footprint_hash.
#     2. Dynamically isolates the virtual taxonomy master from physical bank
#     accounts.
#     3. Attaches parsed staging remarks (narration, payee, upi_ref) to both double-entry legs.
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

#             # 🎯 SYSTEM ACCOUNT ISOLATION SAFEGUARD:
#             taxonomy_master_account, _ = Account.objects.get_or_create(
#                 name="SYSTEM_TAXONOMY_INTEGRATION_NODE",
#                 defaults={
#                     "bank": account_entity.bank,
#                     "account_type": "SYSTEM_CORE",
#                     "ifsc_code": "SYS00000000",
#                     "branch_name": "System Kernel",
#                     "address": "Virtual Ledger Gateway Node",
#                 },
#             )

#             entries_to_create = []
#             staging_line_ids_to_complete = []

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)

#                 is_outflow = node.debit > 0
#                 amount_value = node.debit if is_outflow else node.credit
#                 decimal_amount = Decimal(str(amount_value))

#                 true_hex_anchor = node.row_footprint_hash

#                 # 🟢 1. BUILD REMARKS PAYLOAD FROM STAGING LINE
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

#                 remarks_payload = {
#                     "narration": raw_narration,
#                     "payee": raw_payee,
#                     "upi_ref": raw_upi,
#                 }

#                 # 🟢 2. BUILD EVALUATION MATRIX SNAPSHOT PAYLOAD
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
#                         account=account_entity,  # Physical Bank (e.g., account_id 4)
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=(decimal_amount if not is_outflow else Decimal("0.00")),
#                         credit=Decimal("0.00") if not is_outflow else decimal_amount,
#                         remarks=remarks_payload,  # 🟢 ADDED REMARKS HERE
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
#                         account=taxonomy_master_account,  # Isolated Virtual Node
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=decimal_amount if is_outflow else Decimal("0.00"),
#                         credit=(Decimal("0.00") if is_outflow else decimal_amount),
#                         remarks=remarks_payload,  # 🟢 ADDED REMARKS HERE
#                         evaluation_matrix_snapshot=matrix_snapshot,  # 🟢 FULL 4-TIER SNAPSHOT
#                     )
#                 )

#             # 2. Bulk create transactions simultaneously
#             JournalEntry.objects.bulk_create(entries_to_create)

#             # 3. Close out the workspace sandbox rows
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )

#             # 4. Mark source staging rows out of the pending queue
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

    1. Guarantees 100% matching hex keys by anchoring directly to
    row_footprint_hash.
    2. Guarantees Node 99 binding for the virtual taxonomy master account.
    3. Attaches fully structured JSON remarks (directional_prefix, display_text)
    to both double-entry legs.
    4. Flips WIP & Staging rows to COMPLETED without issuing DELETE queries.
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

                # 🟢 3. STRUCTURED REMARKS PAYLOAD (WORKBENCH COMPATIBLE)
                remarks_payload = {
                    "narration": raw_narration,
                    "payee": raw_payee,
                    "upi_ref": raw_upi,
                    "directional_prefix": direction_word,
                    "target_account_name": target_sub,
                    "display_text": display_text,
                }

                # 🟢 4. BUILD EVALUATION MATRIX SNAPSHOT PAYLOAD
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

                # ─── LEG 1: THE LIQUIDITY POOL (BANK SIDE) ───
                entries_to_create.append(
                    JournalEntry(
                        account=account_entity,  # Physical Bank (e.g., Account ID 4)
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

                # ─── LEG 2: THE CONTRA POOL (TAXONOMY SIDE - NODE 99) ───
                entries_to_create.append(
                    JournalEntry(
                        account=taxonomy_master_account,  # Strictly Node ID 99
                        transaction_date=node.raw_statement_date,
                        row_identifier=true_hex_anchor,
                        debit=(decimal_amount if is_outflow else Decimal("0.00")),
                        credit=(Decimal("0.00") if is_outflow else decimal_amount),
                        remarks=remarks_payload,
                        evaluation_matrix_snapshot=matrix_snapshot,  # Full 4-Tier Snapshot
                    )
                )

            # 5. Bulk create double-entry transactions
            JournalEntry.objects.bulk_create(entries_to_create)

            # 6. Mark WIP sandbox rows as COMPLETED (NO DELETE!)
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
