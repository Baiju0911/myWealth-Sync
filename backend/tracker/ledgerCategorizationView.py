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


class AutoCategorizeStagingQueueView1(APIView):
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

        # Execute your isolated Tier 1 script
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        # 🎯 FIX: Inject expected structural summaries so React tables don't crash
        queue_data = engine_result.get("workspace_queue", [])
        total_nodes = len(queue_data)

        return Response(
            {
                "account_id": account_id,
                "evaluation_summary": {
                    "staged_for_bulk_high": total_nodes,
                    "staged_for_bulk_medium": 0,
                    "uncategorized_vault_zero": 0,
                },
                "workspace_queue": queue_data,  # Delivers Tier 1 payload block smoothly
            },
            status=status.HTTP_200_OK,
        )


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

        # Run your isolated Tier 1 engine script
        engine_result = WIPReconciliationEngine.evaluate_account_queue(
            account_id=account_id
        )

        # 🎯 FIX: Pull directly from 'workspace_queue' keys safely inside the engine return dictionary
        workspace_queue = engine_result.get("workspace_queue", [])
        total_nodes = len(workspace_queue)

        return Response(
            {
                "account_id": account_id,
                "evaluation_summary": {
                    "staged_for_bulk_high": total_nodes,
                    "staged_for_bulk_medium": 0,
                    "uncategorized_vault_zero": 0,  # Keeps both tabs active for data visualization
                },
                "workspace_queue": workspace_queue,  # Delivers Tier 1 payload block smoothly
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
