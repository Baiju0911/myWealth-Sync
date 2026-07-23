from rest_framework.decorators import api_view
from rest_framework.response import Response
from .selectors import DashboardSelectors
from .serializers import CategoryBreakdownSerializer, DashboardSummaryResponseSerializer


@api_view(["GET"])
def dashboard_summary_view(request):
    """
    Dashboard API View: Fetch double-entry summaries using ORM Selectors.
    """
    bank_account_id = int(request.GET.get("bank_account_id", 3))
    taxonomy_account_id = int(request.GET.get("taxonomy_account_id", 99))

    # Fetch via ORM Selectors
    category_qs = DashboardSelectors.get_category_breakdowns(taxonomy_account_id)
    symmetry_data = DashboardSelectors.get_ledger_symmetry(
        bank_account_id, taxonomy_account_id
    )

    # Compute KPIs
    kpis = {
        "net_liquidity": symmetry_data["bank_net"],
        "total_income": 0.0,
        "total_expense": 0.0,
        "suspense_count": 0,
        "suspense_amount": 0.0,
    }

    serialized_categories = CategoryBreakdownSerializer(category_qs, many=True).data

    for row in serialized_categories:
        cat = row["category"]
        subcat = row["subcategory"]
        debit = float(row["total_debit"])
        credit = float(row["total_credit"])
        count = row["transaction_count"]

        if cat == "Income":
            kpis["total_income"] += credit
        elif cat == "Expense":
            kpis["total_expense"] += debit
            if subcat == "Suspense Account":
                kpis["suspense_count"] += count
                kpis["suspense_amount"] += debit

    payload = {
        "kpis": kpis,
        "symmetry_proof": symmetry_data,
        "category_breakdown": serialized_categories,
    }

    response_serializer = DashboardSummaryResponseSerializer(payload)
    return Response(response_serializer.data)
