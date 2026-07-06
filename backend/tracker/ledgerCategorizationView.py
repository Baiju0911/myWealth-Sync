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


from .serviceWIP import WIPIngestionSweeper, WIPReconciliationEngine


class AutoCategorizeStagingQueueView(APIView):
    """
    🤖 HIGH-PRECISION RECONCILIATION MATCHING VIEW ENGINE
    Decoupled view proxy layer interacting cleanly with our service tier layer.
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
        sweep_metrics = WIPIngestionSweeper.execute_sweep(account_context_id=account_id)

        # ─── STEP 2: RUN THE MATCHING RECONCILIATION LOOP ENGINE ───
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        # ─── STEP 3: INSTANT SERIALIZATION FROM ENSEMBLE CACHE ───
        serialized_queue = []
        for w in engine_result["processed_rows"]:
            serialized_queue.append(
                {
                    "wip_id": str(w.id),
                    "hash": w.row_footprint_hash,
                    "date": (
                        w.raw_statement_date.strftime("%Y-%m-%d")
                        if w.raw_statement_date
                        else ""
                    ),
                    "narration": w.staging_line.narration,
                    "debit": float(w.debit),
                    "credit": float(w.credit),
                    "confidence": w.confidence_level,
                    "score": w.confidence_score,
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
                        # 🏆 Display Ensemble Winners Natively
                        "group": w.resolved_category,
                        "subcategory": w.resolved_subcategory,
                        "rule_code": (
                            w.applied_rule.rule_code
                            if w.applied_rule
                            else ("GR06" if float(w.credit) > 0 else "GR05")
                        ),
                        "rule_title": (
                            w.applied_rule.rule_title
                            if w.applied_rule
                            else (
                                "Credit all incomes and gains"
                                if float(w.credit) > 0
                                else "Debit all expenses and losses"
                            )
                        ),
                    },
                }
            )
        return Response(
            {
                "account_id": account_id,
                "sweep_metrics": sweep_metrics,
                "evaluation_summary": {
                    "staged_for_bulk_high": engine_result["staged_for_bulk_high"],
                    "uncategorized_vault_zero": engine_result[
                        "uncategorized_vault_zero"
                    ],
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
