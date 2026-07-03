import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from django.db.models import Q

from .models import (
    StatementStagingLine,
    MasterFinancialCategory,
    AccountingRule,
    WIPEvaluationMatrix,
)
from .serializers import (
    MasterFinancialCategoryAdminSerializer,
    AccountingRuleAdminSerializer,
)

# 🧠 Import our locked-in transactional hash-based loader
from .serviceWIP import WIPIngestionSweeper


class AutoCategorizeStagingQueueView(APIView):
    """
    🤖 HIGH-PRECISION RECONCILIATION MATCHING VIEW ENGINE
    Enforces our strict, locked-in Source of Truth ASCII pipeline:
    Tier 1 (Pattern) ──> Tier 2 (Balance Sheet Placement) ──> Tier 3 (Golden Rule Compliance).
    Requires 100% verification across all gates to earn a 'HIGH' confidence score.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        if not account_id:
            return Response(
                {"error": "Missing parameter tracking field: account_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ─── STEP 1: EXECUTE SANDBOX WORKSPACE SWEEP ───
        # Automatically imports fresh staging rows into the WIP table via hash keys
        sweep_metrics = WIPIngestionSweeper.execute_sweep(account_context_id=account_id)

        # ─── STEP 2: LOAD REFERENCE VECTOR ARRAYS INTO CACHE MEMORY ───
        master_categories = list(MasterFinancialCategory.objects.all())
        accounting_rules = list(
            AccountingRule.objects.filter(is_active=True).order_by("-rule_priority")
        )

        # Fetch only the unresolved active workspace records for this account context
        active_wip_rows = WIPEvaluationMatrix.objects.filter(
            account_id=account_id,
            is_split_component=False,  # Only evaluate root records directly
        )

        total_promoted_to_high = 0
        total_failed_to_zero = 0

        # ─── STEP 3: RUN THE EVALUATION ENGINE ENGINE LOOP ───
        for wip_row in active_wip_rows:
            # Re-initialize clean state flags
            t1_pass = False
            t2_pass = False
            t3_pass = False
            errors_list = []

            matched_cat = None
            matched_rule = None

            narration_clean = wip_row.narration_normalized

            # 🧩 TIER 1: CORE PATTERN MATCHING GATE
            # Scan matching tokens inside keys JSON payload fields
            for cat in master_categories:
                # Support custom compact json structures or explicit fields securely
                k1 = (
                    cat.keys.get("key1", "").strip().lower()
                    if isinstance(cat.keys, dict)
                    else ""
                )
                k2 = (
                    cat.keys.get("key2", "").strip().lower()
                    if isinstance(cat.keys, dict)
                    else ""
                )

                if k1 and k1 in narration_clean:
                    if not k2 or (k2 in narration_clean):
                        matched_cat = cat
                        t1_pass = True
                        break

            if not t1_pass:
                errors_list.append("UNMAPPED_PATTERN")

            # 📊 TIER 2: BALANCE SHEET MATRIX HEADER VALIDATION GATE
            if t1_pass and matched_cat:
                # Must possess a valid, non-empty structural dashboard placement tag
                if matched_cat.dashboard_cat and matched_cat.dashboard_cat.strip():
                    t2_pass = True
                else:
                    errors_list.append("MISSING_BALANCE_SHEET_CONTEXT")

            # 📜 TIER 3: GOLDEN RULE DOUBLE-ENTRY COMPLIANCE CHECK
            if t1_pass and t2_pass and matched_cat:
                # Evaluate against our prioritized accounting rules matrix
                for rule in accounting_rules:
                    tags = (
                        rule.description_tags
                        if isinstance(rule.description_tags, list)
                        else []
                    )

                    # Verify vector direction match (DR table values vs Rule definitions)
                    is_debit_txn = wip_row.debit > 0
                    is_correct_direction = (
                        rule.entry_type == "Debit" and is_debit_txn
                    ) or (rule.entry_type == "Credit" and not is_debit_txn)

                    if is_correct_direction and any(
                        tag.strip().lower() in narration_clean for tag in tags
                    ):
                        matched_rule = rule
                        t3_pass = True
                        break

                if not t3_pass:
                    errors_list.append("RULE_COMPLIANCE_FAILED")

            # ─── VERDICT EVALUATION INTERCEPTOR ───
            # Strict Gate Protocol: 100% unbroken chain required to unlock Bulk Queue
            if t1_pass and t2_pass and t3_pass:
                wip_row.confidence_level = "HIGH"
                wip_row.evaluation_errors = []
                total_promoted_to_high += 1
            else:
                wip_row.confidence_level = (
                    "ZERO"  # Sent to Uncategorized Vault Container
                )
                wip_row.evaluation_errors = errors_list
                total_failed_to_zero += 1

            # Bind matched references safely
            wip_row.matched_category = matched_cat
            wip_row.applied_rule = matched_rule
            wip_row.tier_1_passed = t1_pass
            wip_row.tier_2_passed = t2_pass
            wip_row.tier_3_passed = t3_pass

            # Atomic save back to workspace sandbox
            wip_row.save()

        # ─── STEP 4: PACKAGE JSON RESPONSE FOR FRONTEND WORKSPACE TABS ───
        # Output split payload segments back to viewport layers
        refreshed_wip_set = WIPEvaluationMatrix.objects.filter(account_id=account_id)

        serialized_queue = []
        for w in refreshed_wip_set:
            serialized_queue.append(
                {
                    "wip_id": str(w.id),
                    "hash": w.row_footprint_hash,
                    "date": w.raw_statement_date.strftime("%Y-%m-%d"),
                    "narration": w.staging_line.narration,  # Pull raw uncleaned rendering format
                    "debit": float(w.debit),
                    "credit": float(w.credit),
                    "confidence": w.confidence_level,
                    "errors": w.evaluation_errors,
                    "routing_status": w.staging_line.routing_status,
                    "analysis": {
                        "category_id": (
                            w.matched_category.id if w.matched_category else None
                        ),
                        "category_item": (
                            w.matched_category.categories_items
                            if w.matched_category
                            else "Unassigned"
                        ),
                        "dashboard_cat": (
                            w.matched_category.dashboard_cat
                            if w.matched_category
                            else "None"
                        ),
                        "group": (
                            w.matched_category.act_category
                            if w.matched_category
                            else "None"
                        ),
                        "rule_code": (
                            w.applied_rule.rule_code if w.applied_rule else "MANUAL"
                        ),
                        "rule_title": (
                            w.applied_rule.rule_title
                            if w.applied_rule
                            else "Manual Override State"
                        ),
                    },
                }
            )

        return Response(
            {
                "account_id": account_id,
                "sweep_metrics": sweep_metrics,
                "evaluation_summary": {
                    "staged_for_bulk_high": total_promoted_to_high,
                    "uncategorized_vault_zero": total_failed_to_zero,
                },
                "workspace_queue": serialized_queue,
            },
            status=status.HTTP_200_OK,
        )


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
