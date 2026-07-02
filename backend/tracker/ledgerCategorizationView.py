import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import StatementStagingLine, MasterFinancialCategory, AccountingRule
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from .models import MasterFinancialCategory, AccountingRule
from .serializers import (
    MasterFinancialCategoryAdminSerializer,
    AccountingRuleAdminSerializer,
)


class AutoCategorizeStagingQueueView(APIView):
    """
    🤖 HIGH-PRECISION RECONCILIATION MATCHING VIEW ENGINE
    Evaluates raw statement lines text strings against our unified pattern taxonomy.
    """

    permission_classes = [
        AllowAny
    ]  # Open access for internal processing; adjust as needed

    def post(self, request, *args, **kwargs):
        # 1. Grab all pending staging lines for the active account context
        account_id = request.data.get("account_id")
        if not account_id:
            return Response(
                {"error": "Missing parameter tracking field: account_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        staging_rows = StatementStagingLine.objects.filter(
            account_id=account_id, routing_status="PENDING"
        )

        # 2. Extract our master lookup rules into local memory arrays for ultra-fast matching
        self_transfers = list(
            MasterFinancialCategory.objects.filter(category_type="SELF_TRANSFER")
        )
        known_defaults = list(
            MasterFinancialCategory.objects.filter(category_type="KNOWN_DEFAULT")
        )
        accounting_rules = list(
            AccountingRule.objects.filter(is_active=True).ordering("-rule_priority")
        )

        processed_payloads = []

        # 3. Spin through our transaction queue loop
        for row in staging_rows:
            # Clean and normalize the description string target
            narration_clean = " ".join(row.narration.strip().lower().split())

            matched_category = None
            matched_rule = None
            prediction_confidence = "LOW"

            # ─── CHALLENGE TIER 1: INTER-BANK OWN ACCOUNT MOVEMENTS ───
            for st in self_transfers:
                if st.match_key1 and st.match_key1 in narration_clean:
                    if not st.match_key2 or (st.match_key2 in narration_clean):
                        matched_category = st
                        prediction_confidence = "HIGH"
                        # Auto-associate traditional transfer rules if applicable
                        matched_rule = next(
                            (
                                r
                                for r in accounting_rules
                                if r.entry_type == "Debit"
                                and "transfer" in r.rule_title.lower()
                            ),
                            None,
                        )
                        break

            # ─── CHALLENGE TIER 2: GENERAL DESCRIPTIVE TOKENS ───
            if not matched_category:
                for kd in known_defaults:
                    if kd.match_key1 and kd.match_key1 in narration_clean:
                        if not kd.match_key2 or (kd.match_key2 in narration_clean):
                            matched_category = kd
                            prediction_confidence = "HIGH"
                            break

            # ─── CHALLENGE TIER 3: TIERED GENERAL ACCOUNTING POLICIES ───
            # If no direct category matched, see if any golden rule keywords trigger a match
            if not matched_category or not matched_rule:
                for rule in accounting_rules:
                    # Look inside your compressed metadata block or description tags array
                    tags = (
                        rule.description_tags
                        if isinstance(rule.description_tags, list)
                        else []
                    )
                    if any(tag.lower() in narration_clean for tag in tags):
                        matched_rule = rule
                        if prediction_confidence != "HIGH":
                            prediction_confidence = "MEDIUM"
                        break

            # ─── FALLBACK COMPLIANCE TIER: ROUTE TO SUSPENSE SAFE VAULT ───
            if not matched_category:
                # Safely bind to row 1773 or search via fallback key title strings
                matched_category = MasterFinancialCategory.objects.filter(
                    categories_items__icontains="Suspense"
                ).first()
                matched_rule = next(
                    (r for r in accounting_rules if r.rule_code == "GR37"), None
                )
                prediction_confidence = "LOW"

            # Append the smart suggestion footprint back to your viewport layer array
            processed_payloads.append(
                {
                    "staging_line_id": str(row.id),
                    "raw_date": row.raw_statement_date,
                    "narration": row.narration,
                    "amount": float(row.amount),
                    "predictions": {
                        "confidence": prediction_confidence,
                        "category_item": (
                            matched_category.categories_items
                            if matched_category
                            else "Suspense-E"
                        ),
                        "category_id": (
                            matched_category.id if matched_category else None
                        ),
                        "assigned_type": (
                            matched_category.act_category
                            if matched_category
                            else "Expenses"
                        ),
                        "assigned_subcategory": (
                            matched_category.act_subcategory
                            if matched_category
                            else "Suspense"
                        ),
                        "applied_rule_code": (
                            matched_rule.rule_code if matched_rule else "MANUAL"
                        ),
                        "applied_rule_title": (
                            matched_rule.rule_title
                            if matched_rule
                            else "Manual Entry Blueprint"
                        ),
                    },
                }
            )

        return Response(
            {
                "account_id": account_id,
                "total_evaluated": len(processed_payloads),
                "suggestions_queue": processed_payloads,
            },
            status=status.HTTP_200_OK,
        )


class MasterFinancialCategoryViewSet(viewsets.ModelViewSet):
    """
    💼 REST ENDPOINT CRUD FOR MATRIX CATEGORIES
    Handles GET, POST, PUT, PATCH, and DELETE operations.
    """

    queryset = MasterFinancialCategory.objects.all()
    serializer_class = MasterFinancialCategoryAdminSerializer
    permission_classes = [
        AllowAny
    ]  # Open access for internal processing; adjust as needed

    # Enable filtering variants over your collection query lists
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
    Handles GET, POST, PUT, PATCH, and DELETE operations.
    """

    queryset = AccountingRule.objects.all()
    serializer_class = AccountingRuleAdminSerializer
    permission_classes = [
        AllowAny
    ]  # Open access for internal processing; adjust as needed

    def get_queryset(self):
        queryset = AccountingRule.objects.all()
        entry_type = self.request.query_params.get("entry_type")
        is_active = self.request.query_params.get("is_active")

        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        if is_active:
            # Handle string variant interpretations from query headers safely
            queryset = queryset.filter(is_active=str(is_active).lower() == "true")
        return queryset
