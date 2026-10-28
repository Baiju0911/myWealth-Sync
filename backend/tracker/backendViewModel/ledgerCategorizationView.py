# Double Entry from Staging Queue to WIP to Journal entry
# Stage 2 WIP => Stage 3 Journal Entry

import sys
import time
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
import logging
from tracker.parsers.universal_narration import UniversalNarrationExtractor

User = get_user_model()
logger = logging.getLogger(__name__)

from ..WIP import WIPIngestionSweeper, WIPReconciliationEngine


class AutoCategorizeStagingQueueView(APIView):
    """
    🤖 TIER 1 ISOLATION PROXY ADAPTER
    Wraps Tier 1-5 outputs inside expected schema boundaries using high-speed native
    JSON streaming to bypass heavy DRF serialization overhead.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        #  breakpoint()
        account_id = request.data.get("account_id")
        if not account_id:
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
#     """Executes an idempotent double-entry release with real-time console diagnostics."""
#     start_time = time.time()
#     print(
#         f"\n[SYNC_DEBUG] 🚀 Starting Bulk Release | Total WIP Nodes Received: {len(wip_row_ids)}"
#     )

#     try:
#         with transaction.atomic():
#             fetch_start = time.time()
#             wip_nodes = list(
#                 WIPEvaluationMatrix.objects.filter(
#                     id__in=wip_row_ids,
#                     account=account_entity,
#                     processing_status="PENDING",
#                 ).select_related("staging_line", "applied_rule")
#             )

#             print(
#                 f"[SYNC_DEBUG] ⏱️ Query Fetch Time: {time.time() - fetch_start:.2f}s | Active Pending Nodes: {len(wip_nodes)}"
#             )

#             if not wip_nodes:
#                 print("[SYNC_DEBUG] ⚠️ No active pending nodes found to process.")
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

#             # 🛡️ 2. FETCH ALREADY COMMITTED HASHES IN STAGE 3
#             existing_ledger_hashes = set(
#                 JournalEntry.objects.filter(account=account_entity).values_list(
#                     "row_identifier", flat=True
#                 )
#             )
#             print(
#                 f"[SYNC_DEBUG] 🔍 Pre-existing Journal Hashes in Stage 3: {len(existing_ledger_hashes)}"
#             )

#             entries_to_create = []
#             staging_line_ids_to_complete = []
#             skipped_count = 0

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)
#                 true_hex_anchor = node.row_footprint_hash

#                 # 🛑 IDEMPOTENCY GUARD: Skip duplicate commit if hash exists in Stage 3
#                 if true_hex_anchor in existing_ledger_hashes:
#                     skipped_count += 1
#                     continue

#                 is_outflow = node.debit > 0
#                 amount_value = node.debit if is_outflow else node.credit
#                 decimal_amount = Decimal(str(amount_value))
#                 float_amt = float(decimal_amount)

#                 # Extract Staging Metadata
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

#                 remarks_payload = {
#                     "narration": raw_narration,
#                     "payee": raw_payee,
#                     "upi_ref": raw_upi,
#                     "directional_prefix": direction_word,
#                     "target_account_name": target_sub,
#                     "display_text": display_text,
#                 }

#                 eval_matrix = node.matrix_evaluation or {}
#                 matrix_snapshot = {
#                     **eval_matrix,
#                     "resolved_category": node.resolved_category,
#                     "resolved_subcategory": node.resolved_subcategory,
#                     "confidence_score": node.confidence_score,
#                     "applied_rule_code": (
#                         node.applied_rule.rule_code
#                         if node.applied_rule
#                         else (
#                             "AI_VECTOR_CACHE"
#                             if node.confidence_score == 100
#                             else "MANUAL"
#                         )
#                     ),
#                 }

#                 # Leg 1: Liquidity Pool
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=account_entity,
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

#                 # Leg 2: Contra Pool
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=taxonomy_master_account,
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=(decimal_amount if is_outflow else Decimal("0.00")),
#                         credit=(Decimal("0.00") if is_outflow else decimal_amount),
#                         remarks=remarks_payload,
#                         evaluation_matrix_snapshot=matrix_snapshot,
#                     )
#                 )

#             # Print filtering breakdown
#             new_commit_count = len(entries_to_create) // 2
#             print(
#                 f"[SYNC_DEBUG] 📊 Duplicate Filter Summary: {new_commit_count} NEW transactions to insert | {skipped_count} ALREADY COMMITTED transactions skipped."
#             )

#             # 🚀 3. BULK WRITE ONLY NEW ENTRIES
#             if entries_to_create:
#                 write_start = time.time()
#                 print(
#                     f"[SYNC_DEBUG] ⚡ Executing bulk_create for {len(entries_to_create)} journal leg records (batch_size=500)..."
#                 )
#                 JournalEntry.objects.bulk_create(entries_to_create, batch_size=500)
#                 print(
#                     f"[SYNC_DEBUG] 💾 Write Success! DB Bulk Commit Time: {time.time() - write_start:.2f}s"
#                 )
#             else:
#                 print(
#                     "[SYNC_DEBUG] ℹ️ Zero new entries to insert. Skipping bulk_create execution."
#                 )

#             # 4. MARK ALL WIP AND STAGING ROWS AS COMPLETED
#             update_start = time.time()
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )
#             StatementStagingLine.objects.filter(
#                 id__in=staging_line_ids_to_complete
#             ).update(routing_status="COMPLETED")
#             print(
#                 f"[SYNC_DEBUG] 🔄 Status Update Time (WIP & Staging set to COMPLETED): {time.time() - update_start:.2f}s"
#             )

#             print(
#                 f"[SYNC_DEBUG] ✅ Batch Release Finished Successfully! Total Elapsed Time: {time.time() - start_time:.2f}s\n"
#             )

#         return {
#             "status": "success",
#             "processed_nodes": len(wip_row_ids),
#             "new_commits": new_commit_count,
#             "skipped_duplicates": skipped_count,
#         }

#     except Exception as e:
#         print(f"\n[SYNC_ERROR] ❌ CRITICAL FAILURE during commit: {str(e)}")
#         logger.error(
#             f"Database transaction aborted in bulk sync release: {str(e)}",
#             exc_info=True,
#         )
#         return {
#             "status": "error",
#             "message": f"Database transaction aborted: {str(e)}",
#         }


# def execute_bulk_sync_release(user, account_entity, wip_row_ids):
#     """Executes an idempotent double-entry release with real-time console diagnostics."""
#     start_time = time.time()
#     print(
#         f"\n[SYNC_DEBUG] 🚀 Starting Bulk Release | Total WIP Nodes Received: {len(wip_row_ids)}"
#     )

#     try:
#         with transaction.atomic():
#             fetch_start = time.time()
#             wip_nodes = list(
#                 WIPEvaluationMatrix.objects.filter(
#                     id__in=wip_row_ids,
#                     account=account_entity,
#                     processing_status="PENDING",
#                 ).select_related("staging_line", "applied_rule")
#             )

#             print(
#                 f"[SYNC_DEBUG] ⏱️ Query Fetch Time: {time.time() - fetch_start:.2f}s | Active Pending Nodes: {len(wip_nodes)}"
#             )

#             if not wip_nodes:
#                 print("[SYNC_DEBUG] ⚠️ No active pending nodes found to process.")
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

#             # 🛡️ 2. FETCH ALREADY COMMITTED HASHES IN STAGE 3
#             existing_ledger_hashes = set(
#                 JournalEntry.objects.filter(account=account_entity).values_list(
#                     "row_identifier", flat=True
#                 )
#             )
#             print(
#                 f"[SYNC_DEBUG] 🔍 Pre-existing Journal Hashes in Stage 3: {len(existing_ledger_hashes)}"
#             )

#             entries_to_create = []
#             staging_line_ids_to_complete = []
#             skipped_count = 0

#             for node in wip_nodes:
#                 staging_line_ids_to_complete.append(node.staging_line_id)
#                 true_hex_anchor = node.row_footprint_hash

#                 # 🛑 IDEMPOTENCY GUARD: Skip duplicate commit if hash exists in Stage 3
#                 if true_hex_anchor in existing_ledger_hashes:
#                     skipped_count += 1
#                     continue

#                 is_outflow = node.debit > 0
#                 amount_value = node.debit if is_outflow else node.credit
#                 decimal_amount = Decimal(str(amount_value))
#                 float_amt = float(decimal_amount)

#                 # Extract Canonical Metadata via UniversalNarrationExtractor
#                 staging_line = node.staging_line
#                 if staging_line:
#                     parsed_info = UniversalNarrationExtractor.resolve_from_staging_line(
#                         staging_line
#                     )
#                     raw_narration = parsed_info["raw_statement_narration"]
#                     raw_payee = parsed_info["suggested_payee"]
#                     raw_remark = parsed_info["suggested_remark"]
#                     raw_upi = (
#                         parsed_info["live_rrn"] or parsed_info["detected_reference"]
#                     )
#                 else:
#                     raw_narration = node.narration_normalized
#                     raw_payee = raw_narration
#                     raw_remark = None
#                     raw_upi = None

#                 direction_word = "By" if is_outflow else "To"
#                 target_sub = node.resolved_subcategory or "Suspense Account"

#                 # Build clean display text
#                 payee_display = (
#                     f"{raw_payee} ({raw_remark})" if raw_remark else raw_payee
#                 )
#                 if is_outflow:
#                     action_word = (
#                         f"Paid ₹{float_amt:,.2f} to {payee_display}"
#                         if raw_payee
#                         else f"Outflow of ₹{float_amt:,.2f}"
#                     )
#                 else:
#                     action_word = (
#                         f"Received ₹{float_amt:,.2f} from {payee_display or 'Payee'}"
#                     )

#                 ref_str = f" [Ref: {raw_upi}]" if raw_upi else ""
#                 display_text = f"{direction_word} {target_sub} | {action_word}{ref_str} | Ingested via Staging"

#                 remarks_payload = {
#                     "narration": raw_narration,
#                     "payee": raw_payee,
#                     "remark": raw_remark,
#                     "upi_ref": raw_upi,
#                     "directional_prefix": direction_word,
#                     "target_account_name": target_sub,
#                     "display_text": display_text,
#                 }

#                 eval_matrix = node.matrix_evaluation or {}
#                 matrix_snapshot = {
#                     **eval_matrix,
#                     "resolved_category": node.resolved_category,
#                     "resolved_subcategory": node.resolved_subcategory,
#                     "confidence_score": node.confidence_score,
#                     "applied_rule_code": (
#                         node.applied_rule.rule_code
#                         if node.applied_rule
#                         else (
#                             "AI_VECTOR_CACHE"
#                             if node.confidence_score == 100
#                             else "MANUAL"
#                         )
#                     ),
#                 }

#                 # Leg 1: Liquidity Pool
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=account_entity,
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

#                 # Leg 2: Contra Pool
#                 entries_to_create.append(
#                     JournalEntry(
#                         account=taxonomy_master_account,
#                         transaction_date=node.raw_statement_date,
#                         row_identifier=true_hex_anchor,
#                         debit=(decimal_amount if is_outflow else Decimal("0.00")),
#                         credit=(Decimal("0.00") if is_outflow else decimal_amount),
#                         remarks=remarks_payload,
#                         evaluation_matrix_snapshot=matrix_snapshot,
#                     )
#                 )

#             # Print filtering breakdown
#             new_commit_count = len(entries_to_create) // 2
#             print(
#                 f"[SYNC_DEBUG] 📊 Duplicate Filter Summary: {new_commit_count} NEW transactions to insert | {skipped_count} ALREADY COMMITTED transactions skipped."
#             )

#             # 🚀 3. BULK WRITE ONLY NEW ENTRIES
#             if entries_to_create:
#                 write_start = time.time()
#                 print(
#                     f"[SYNC_DEBUG] ⚡ Executing bulk_create for {len(entries_to_create)} journal leg records (batch_size=500)..."
#                 )
#                 JournalEntry.objects.bulk_create(entries_to_create, batch_size=500)
#                 print(
#                     f"[SYNC_DEBUG] 💾 Write Success! DB Bulk Commit Time: {time.time() - write_start:.2f}s"
#                 )
#             else:
#                 print(
#                     "[SYNC_DEBUG] ℹ️ Zero new entries to insert. Skipping bulk_create execution."
#                 )

#             # 4. MARK ALL WIP AND STAGING ROWS AS COMPLETED
#             update_start = time.time()
#             WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
#                 processing_status="COMPLETED"
#             )
#             StatementStagingLine.objects.filter(
#                 id__in=staging_line_ids_to_complete
#             ).update(routing_status="COMPLETED")
#             print(
#                 f"[SYNC_DEBUG] 🔄 Status Update Time (WIP & Staging set to COMPLETED): {time.time() - update_start:.2f}s"
#             )

#             print(
#                 f"[SYNC_DEBUG] ✅ Batch Release Finished Successfully! Total Elapsed Time: {time.time() - start_time:.2f}s\n"
#             )

#         return {
#             "status": "success",
#             "processed_nodes": len(wip_row_ids),
#             "new_commits": new_commit_count,
#             "skipped_duplicates": skipped_count,
#         }

#     except Exception as e:
#         print(f"\n[SYNC_ERROR] ❌ CRITICAL FAILURE during commit: {str(e)}")
#         logger.error(
#             f"Database transaction aborted in bulk sync release: {str(e)}",
#             exc_info=True,
#         )
#         return {
#             "status": "error",
#             "message": f"Database transaction aborted: {str(e)}",
#         }


def execute_bulk_sync_release(user, account_entity, wip_row_ids):
    """
    Executes an idempotent double-entry release with two-way leg checking:
      - If both Bank & Contra legs exist: Skip as duplicate.
      - If only Bank leg exists: Create and insert Contra leg.
      - If only Contra leg exists: Create and insert Bank leg.
      - If neither exists: Create and insert both legs.
    """
    start_time = time.time()
    print(
        f"\n[SYNC_DEBUG] 🚀 Starting Bulk Release | Total WIP Nodes Received: {len(wip_row_ids)}"
    )

    try:
        with transaction.atomic():
            fetch_start = time.time()
            wip_nodes = list(
                WIPEvaluationMatrix.objects.filter(
                    id__in=wip_row_ids,
                    account=account_entity,
                    processing_status="PENDING",
                ).select_related("staging_line", "applied_rule")
            )

            print(
                f"[SYNC_DEBUG] ⏱️ Query Fetch Time: {time.time() - fetch_start:.2f}s | Active Pending Nodes: {len(wip_nodes)}"
            )

            if not wip_nodes:
                print("[SYNC_DEBUG] ⚠️ No active pending nodes found to process.")
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

            # 🛡️ 2. TWO-WAY PRE-FETCH: MAP EXISTING LEGS PER ROW_IDENTIFIER
            incoming_hashes = [
                node.row_footprint_hash for node in wip_nodes if node.row_footprint_hash
            ]

            existing_legs_qs = JournalEntry.objects.filter(
                row_identifier__in=incoming_hashes,
                account_id__in=[account_entity.id, taxonomy_master_account.id],
            ).values("row_identifier", "account_id")

            existing_legs_map = {}
            for row in existing_legs_qs:
                existing_legs_map.setdefault(row["row_identifier"], set()).add(
                    row["account_id"]
                )

            print(
                f"[SYNC_DEBUG] 🔍 Pre-existing Journal Leg Hashes found in Stage 3: {len(existing_legs_map)}"
            )

            entries_to_create = []
            staging_line_ids_to_complete = []
            skipped_count = 0
            partial_fill_count = 0

            bank_acc_id = account_entity.id
            contra_acc_id = taxonomy_master_account.id

            for node in wip_nodes:
                staging_line_ids_to_complete.append(node.staging_line_id)
                true_hex_anchor = node.row_footprint_hash

                existing_accounts = existing_legs_map.get(true_hex_anchor, set())
                has_bank_leg = bank_acc_id in existing_accounts
                has_contra_leg = contra_acc_id in existing_accounts

                # 🛑 IDEMPOTENCY GUARD: Both legs exist -> skip
                if has_bank_leg and has_contra_leg:
                    skipped_count += 1
                    continue

                if has_bank_leg or has_contra_leg:
                    partial_fill_count += 1

                is_outflow = node.debit > 0
                amount_value = node.debit if is_outflow else node.credit
                decimal_amount = Decimal(str(amount_value))
                float_amt = float(decimal_amount)

                # Extract Canonical Metadata via UniversalNarrationExtractor
                staging_line = node.staging_line
                if staging_line:
                    parsed_info = UniversalNarrationExtractor.resolve_from_staging_line(
                        staging_line
                    )
                    raw_narration = parsed_info["raw_statement_narration"]
                    raw_payee = parsed_info["suggested_payee"]
                    raw_remark = parsed_info["suggested_remark"]
                    raw_upi = (
                        parsed_info["live_rrn"] or parsed_info["detected_reference"]
                    )
                else:
                    raw_narration = node.narration_normalized
                    raw_payee = raw_narration
                    raw_remark = None
                    raw_upi = None

                direction_word = "By" if is_outflow else "To"
                target_sub = node.resolved_subcategory or "Suspense Account"

                # Build clean display text
                payee_display = (
                    f"{raw_payee} ({raw_remark})" if raw_remark else raw_payee
                )
                if is_outflow:
                    action_word = (
                        f"Paid ₹{float_amt:,.2f} to {payee_display}"
                        if raw_payee
                        else f"Outflow of ₹{float_amt:,.2f}"
                    )
                else:
                    action_word = (
                        f"Received ₹{float_amt:,.2f} from {payee_display or 'Payee'}"
                    )

                ref_str = f" [Ref: {raw_upi}]" if raw_upi else ""
                display_text = f"{direction_word} {target_sub} | {action_word}{ref_str} | Ingested via Staging"

                remarks_payload = {
                    "narration": raw_narration,
                    "payee": raw_payee,
                    "remark": raw_remark,
                    "upi_ref": raw_upi,
                    "directional_prefix": direction_word,
                    "target_account_name": target_sub,
                    "display_text": display_text,
                }

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

                # 🏦 Leg 1: Liquidity Pool (Insert ONLY if missing)
                if not has_bank_leg:
                    entries_to_create.append(
                        JournalEntry(
                            account=account_entity,
                            transaction_date=node.raw_statement_date,
                            row_identifier=true_hex_anchor,
                            debit=(
                                decimal_amount if not is_outflow else Decimal("0.00")
                            ),
                            credit=(
                                Decimal("0.00") if not is_outflow else decimal_amount
                            ),
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

                # 🗂️ Leg 2: Contra Pool (Insert ONLY if missing)
                if not has_contra_leg:
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

            # Print filtering breakdown
            print(
                f"[SYNC_DEBUG] 📊 Duplicate Filter Summary: "
                f"{len(entries_to_create)} individual leg records to insert | "
                f"{partial_fill_count} single-leg gap fills | "
                f"{skipped_count} ALREADY COMMITTED complete transactions skipped."
            )

            # 🚀 3. BULK WRITE ONLY NEW LEGS
            if entries_to_create:
                write_start = time.time()
                print(
                    f"[SYNC_DEBUG] ⚡ Executing bulk_create for {len(entries_to_create)} journal leg records (batch_size=500)..."
                )
                JournalEntry.objects.bulk_create(entries_to_create, batch_size=500)
                print(
                    f"[SYNC_DEBUG] 💾 Write Success! DB Bulk Commit Time: {time.time() - write_start:.2f}s"
                )
            else:
                print(
                    "[SYNC_DEBUG] ℹ️ Zero new entries to insert. Skipping bulk_create execution."
                )

            # 4. MARK ALL WIP AND STAGING ROWS AS COMPLETED
            update_start = time.time()
            WIPEvaluationMatrix.objects.filter(id__in=wip_row_ids).update(
                processing_status="COMPLETED"
            )
            StatementStagingLine.objects.filter(
                id__in=staging_line_ids_to_complete
            ).update(routing_status="COMPLETED")
            print(
                f"[SYNC_DEBUG] 🔄 Status Update Time (WIP & Staging set to COMPLETED): {time.time() - update_start:.2f}s"
            )

            print(
                f"[SYNC_DEBUG] ✅ Batch Release Finished Successfully! Total Elapsed Time: {time.time() - start_time:.2f}s\n"
            )

        return {
            "status": "success",
            "processed_nodes": len(wip_row_ids),
            "new_legs_inserted": len(entries_to_create),
            "partial_gap_fills": partial_fill_count,
            "skipped_duplicates": skipped_count,
        }

    except Exception as e:
        print(f"\n[SYNC_ERROR] ❌ CRITICAL FAILURE during commit: {str(e)}")
        logger.error(
            f"Database transaction aborted in bulk sync release: {str(e)}",
            exc_info=True,
        )
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
