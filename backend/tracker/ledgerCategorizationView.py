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

        # Run your isolated multi-track evaluation matrix engine script
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        workspace_queue = engine_result.get("workspace_queue", [])
        total_nodes = len(workspace_queue)

        # 🎯 THE VIEW COUPLING RESOLUTION: Pull the matrix stats calculated by the parallel threads
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
                "evaluation_summary": {
                    "staged_for_bulk_high": total_nodes,
                    "staged_for_bulk_medium": 0,
                    "uncategorized_vault_zero": 0,  # Keeps both tabs active for data visualization
                },
                "workspace_queue": workspace_queue,  # Delivers matrix payload block smoothly
                "matrix_summary_stats": matrix_summary_stats,  # 🎯 THE FIX: Sends the complete Real vs Suspense matrix structure down to the frontend!
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
