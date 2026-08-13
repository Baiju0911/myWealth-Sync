from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..dashboard.selectors import DashboardSelectors
from ..dashboard.serializers import (
    DashboardSummaryResponseSerializer,
    CategoryBreakdownSerializer,
)


@api_view(["GET"])
def dashboard_summary_view(request):
    bank_account_id = int(request.GET.get("bank_account_id", 3))
    taxonomy_account_id = int(request.GET.get("taxonomy_account_id", 99))

    # 1. Fetch natural date boundaries from the database
    bounds = DashboardSelectors.get_date_bounds(bank_account_id)

    # 2. Extract requested parameters or fall back to full boundaries
    from_date = request.GET.get("from_date") or bounds["min_date"]
    to_date = request.GET.get("to_date") or bounds["max_date"]

    # 3. Query aggregated metrics using date filters (🎯 Added bank_account_id)
    category_qs = DashboardSelectors.get_category_breakdowns(
        bank_account_id=bank_account_id,
        taxonomy_account_id=taxonomy_account_id,
        from_date=from_date,
        to_date=to_date,
    )
    symmetry_data = DashboardSelectors.get_ledger_symmetry(
        bank_account_id=bank_account_id,
        taxonomy_account_id=taxonomy_account_id,
        from_date=from_date,
        to_date=to_date,
    )

    serialized_categories = CategoryBreakdownSerializer(category_qs, many=True).data

    # 4. Compute KPIs for filtered period
    kpis = {
        "net_liquidity": symmetry_data["bank_net"],
        "total_income": 0.0,
        "total_expense": 0.0,
        "suspense_count": 0,
        "suspense_amount": 0.0,
    }

    for row in serialized_categories:
        cat = row.get("category") or "Uncategorized"
        subcat = row.get("subcategory") or "Suspense Account"
        debit = float(row.get("total_debit") or 0.0)
        credit = float(row.get("total_credit") or 0.0)
        count = int(row.get("transaction_count") or 0)

        if cat == "Income":
            kpis["total_income"] += credit
        elif cat == "Expense":
            kpis["total_expense"] += debit
            if subcat == "Suspense Account":
                kpis["suspense_count"] += count
                kpis["suspense_amount"] += debit

    # Payload matching DashboardSummaryResponseSerializer structure exactly
    payload = {
        "date_bounds": {
            "min_date": bounds["min_date"],
            "max_date": bounds["max_date"],
            "applied_from_date": from_date,
            "applied_to_date": to_date,
        },
        "kpis": kpis,
        "symmetry_proof": symmetry_data,
        "category_breakdown": serialized_categories,
    }

    response_serializer = DashboardSummaryResponseSerializer(data=payload)
    response_serializer.is_valid(raise_exception=True)
    return Response(response_serializer.data)


@api_view(["GET"])
def asset_mapped_transactions_view(request, asset_id):
    """
    API endpoint to list all transactions bound to a specific asset sub-ledger.
    """
    from tracker.models import JournalEntry
    from tracker.models.subledger import AssetTransactionMapping

    try:
        mappings = AssetTransactionMapping.objects.filter(asset_id=asset_id).exclude(
            row_identifier__isnull=True
        )

        row_identifiers = mappings.values_list("row_identifier", flat=True)

        journal_entries = JournalEntry.objects.filter(
            row_identifier__in=row_identifiers, account_id=99
        ).values(
            "id", "row_identifier", "transaction_date", "debit", "credit", "remarks"
        )

        mapping_lookup = {m.row_identifier: m for m in mappings}

        results = []
        for entry in journal_entries:
            m_obj = mapping_lookup.get(entry["row_identifier"])
            results.append(
                {
                    "mapping_id": str(m_obj.id) if m_obj else None,
                    "journal_id": str(entry["id"]),
                    "row_identifier": entry["row_identifier"],
                    "transaction_date": entry["transaction_date"].strftime("%Y-%m-%d"),
                    "debit": float(entry["debit"]),
                    "credit": float(entry["credit"]),
                    "remarks": entry["remarks"],
                    "mapped_at": (
                        m_obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        if m_obj and hasattr(m_obj, "created_at")
                        else None
                    ),
                }
            )

        return Response(
            {"status": "success", "asset_id": asset_id, "mapped_transactions": results}
        )
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=400)
