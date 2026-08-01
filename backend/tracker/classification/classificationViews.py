# tracker/classification/classficationViews.py

from rest_framework import status, views
from rest_framework.decorators import api_view
from rest_framework.response import Response

from urllib.parse import parse_qs, unquote
from django.db.models import Q

from tracker.models import JournalEntry, TaxonomyTree
from tracker.classification.engine import get_suspense_clusters, reclassify_and_learn
from tracker.classification.serializers import (
    ClassificationJournalEntrySerializer,
    ReclassifyRequestSerializer,
)
from rest_framework.pagination import PageNumberPagination
from tracker.classification.utils.upiparser import clean_payee_name


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class UpdateJournalEntryNoteView(views.APIView):
    """
    POST /api/classification/entry-note/
    Updates the 'user_note' key inside the JSON remarks column for a journal entry.
    """

    def post(self, request):
        entry_id = request.data.get("entry_id")
        user_note = request.data.get("user_note", "").strip()

        if not entry_id:
            return Response(
                {"error": "entry_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            entry = JournalEntry.objects.get(id=entry_id)

            # Retrieve or initialize the JSON object
            current_remarks = entry.remarks if isinstance(entry.remarks, dict) else {}

            # Update the user_note key
            current_remarks["user_note"] = user_note if user_note else None

            # Save back to database
            entry.remarks = current_remarks
            entry.save(update_fields=["remarks"])

            return Response(
                {"status": "success", "entry_id": entry.id, "remarks": entry.remarks},
                status=status.HTTP_200_OK,
            )

        except JournalEntry.DoesNotExist:
            return Response(
                {"error": "Journal Entry not found"}, status=status.HTTP_404_NOT_FOUND
            )


# class ClassificationPendingListView_older(views.APIView):
#     """
#     GET /api/classification/pending/
#     Returns unclassified entries (Node 99) with structured JSON remarks.
#     """

#     def get(self, request):
#         unclassified_entries = JournalEntry.objects.filter(
#             account_id=99, is_reclassified=False
#         ).order_by("-transaction_date")

#         serializer = ClassificationJournalEntrySerializer(
#             unclassified_entries, many=True
#         )
#         return Response(serializer.data, status=status.HTTP_200_OK)


class ClassificationPendingListView(views.APIView):
    """
    GET /api/classification/pending/?page=1
    Returns paginated unclassified entries (Node 99) with structured JSON remarks.
    """

    def get(self, request):
        unclassified_entries = JournalEntry.objects.filter(
            account_id=99, is_reclassified=False
        ).order_by("-transaction_date")

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(unclassified_entries, request)

        if page is not None:
            serializer = ClassificationJournalEntrySerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = ClassificationJournalEntrySerializer(
            unclassified_entries, many=True
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReclassifyEntryView(views.APIView):
    """
    POST /api/classification/reclassify/
    Handles single-row reclassification requests from the frontend modal.
    """

    def post(self, request):
        input_serializer = ReclassifyRequestSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data = input_serializer.validated_data

        try:
            # Calls atomic reclassification on JournalEntry model
            updated_entry = JournalEntry.reclassify_statement_line(
                row_identifier=data["row_identifier"],
                new_category=data["new_category"],
                new_subcategory=data["new_subcategory"],
                rule_code=data.get("rule_code", "MANUAL"),
                taxonomy_node_account_id=data.get("taxonomy_node_account_id", 99),
                user_note=data.get("user_note"),
            )

            output_serializer = ClassificationJournalEntrySerializer(updated_entry)
            return Response(output_serializer.data, status=status.HTTP_200_OK)

        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CategoryVendorDrilldownView(views.APIView):
    def get(self, request):
        target_sub = request.GET.get("subcategory")
        account_id_param = request.GET.get("account_id")

        # 🟢 1. Decode raw query string safely for ampersands
        raw_query = request.META.get("QUERY_STRING", "")
        if raw_query and "subcategory=" in raw_query:
            parsed_qs = parse_qs(raw_query)
            if "subcategory" in parsed_qs:
                target_sub = parsed_qs["subcategory"][0]

        if not target_sub or not target_sub.strip():
            return Response(
                {"error": "subcategory query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_sub = target_sub.strip()

        # 🟢 2. Fetch matching row_identifiers
        matching_row_ids = (
            JournalEntry.objects.filter(
                Q(evaluation_matrix_snapshot__resolved_subcategory__iexact=target_sub)
                | Q(remarks__target_account_name__iexact=target_sub)
            )
            .values_list("row_identifier", flat=True)
            .distinct()
        )

        entries_query = JournalEntry.objects.filter(row_identifier__in=matching_row_ids)

        if account_id_param and account_id_param.isdigit():
            entries_query = entries_query.filter(account_id=int(account_id_param))
        else:
            entries_query = entries_query.exclude(account_id=5)

        entries = list(entries_query)

        vendor_map = {}
        for entry in entries:
            remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
            raw_payee = remarks.get("payee") or ""

            # 🟢 Clean payee on-the-fly to strip residual 'TRANSFER:' or 'NACH' tokens
            payee = clean_payee_name(raw_payee) or "Unspecified Vendor"

            debit_val = float(entry.debit or 0.0)
            credit_val = float(entry.credit or 0.0)

            if payee not in vendor_map:
                vendor_map[payee] = {
                    "payee": payee,
                    "transaction_count": 0,
                    "total_outflow": 0.0,
                    "total_inflow": 0.0,
                    "sample_upi_refs": [],
                }

            vendor_map[payee]["transaction_count"] += 1
            vendor_map[payee]["total_outflow"] += debit_val
            vendor_map[payee]["total_inflow"] += credit_val

            upi_ref = remarks.get("upi_ref")
            if upi_ref and upi_ref not in vendor_map[payee]["sample_upi_refs"]:
                if len(vendor_map[payee]["sample_upi_refs"]) < 3:
                    vendor_map[payee]["sample_upi_refs"].append(upi_ref)

        vendor_list = sorted(
            vendor_map.values(), key=lambda v: v["total_outflow"], reverse=True
        )

        return Response(
            {
                "status": "success",
                "subcategory": target_sub,
                "account_id": account_id_param or "COUNTER_LEGS",
                "total_vendors": len(vendor_list),
                "vendors": vendor_list,
            },
            status=status.HTTP_200_OK,
        )


@api_view(["GET"])
def get_suspense_workbench_data(request):
    """
    Returns auto-clustered patterns for Workbench review with direction flags, inflows/outflows,
    and character/underscore-insensitive pattern search.
    """
    target_sub = request.GET.get("subcategory", "Suspense Account")
    account_id_param = request.GET.get("account_id")
    search_query = request.GET.get("q") or request.GET.get("search")

    account_id = (
        int(account_id_param)
        if account_id_param and account_id_param.isdigit()
        else None
    )

    clusters = get_suspense_clusters(
        target_subcategory=target_sub,
        account_id=account_id,
        search_query=search_query,
    )

    return Response(
        {
            "status": "success",
            "target_subcategory": target_sub,
            "total_clusters": len(clusters),
            "clusters": clusters,
        },
        status=status.HTTP_200_OK,
    )


# @api_view(["POST"])
# def apply_reclassification_and_learn_older(request):
#     """
#     Executes bulk reclassification via the classification engine and updates/creates learning rules.
#     """
#     transaction_ids = request.data.get("transaction_ids", [])
#     target_category = request.data.get("target_category")
#     target_subcategory = request.data.get("target_subcategory")

#     # Accept list of patterns or single string fallback
#     patterns = request.data.get("patterns", [])
#     single_pattern = request.data.get("pattern")

#     if not patterns and single_pattern:
#         patterns = [single_pattern]

#     save_rule = request.data.get("save_rule", True)

#     if not transaction_ids or not target_category or not target_subcategory:
#         return Response(
#             {
#                 "error": "transaction_ids, target_category, and target_subcategory are required."
#             },
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#     result = reclassify_and_learn(
#         transaction_ids=transaction_ids,
#         target_category=target_category,
#         target_subcategory=target_subcategory,
#         patterns=patterns,
#         save_rule=save_rule,
#     )

#     return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
def apply_reclassification_and_learn(request):
    """
    Executes bulk reclassification via the classification engine and updates/creates learning rules.
    """
    # Accept both 'transaction_ids' and 'row_identifiers' / 'ids'
    transaction_ids = (
        request.data.get("transaction_ids")
        or request.data.get("row_identifiers")
        or request.data.get("ids")
        or []
    )
    target_category = request.data.get("target_category")
    target_subcategory = request.data.get("target_subcategory")

    # Accept list of patterns or single string fallback
    patterns = request.data.get("patterns", [])
    single_pattern = request.data.get("pattern")

    if not patterns and single_pattern:
        patterns = [single_pattern]

    save_rule = request.data.get("save_rule", True)

    if not transaction_ids or not target_category or not target_subcategory:
        return Response(
            {
                "error": "transaction_ids (or row_identifiers), target_category, and target_subcategory are required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = reclassify_and_learn(
        transaction_ids=transaction_ids,
        target_category=target_category,
        target_subcategory=target_subcategory,
        patterns=patterns,
        save_rule=save_rule,
    )

    return Response(result, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_taxonomy_tree_view(request):
    """
    Returns active category & subcategory tree for dropdown selection in the UI.
    """
    nodes = TaxonomyTree.objects.filter(is_active=True)

    tree_dict = {}
    for node in nodes:
        if node.category not in tree_dict:
            tree_dict[node.category] = []
        tree_dict[node.category].append(node.subcategory)

    taxonomy_data = [
        {"category": cat, "subcategories": subs} for cat, subs in tree_dict.items()
    ]

    return Response({"status": "success", "taxonomy": taxonomy_data})


@api_view(["POST"])
def add_taxonomy_node(request):
    """
    Dynamically adds a new Category/Subcategory node to the taxonomy tree.
    """
    category = request.data.get("category", "").strip()
    subcategory = request.data.get("subcategory", "").strip()

    if not category or not subcategory:
        return Response(
            {"status": "error", "message": "Category and Subcategory are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    existing = TaxonomyTree.objects.filter(
        category__iexact=category, subcategory__iexact=subcategory
    ).first()

    if existing:
        return Response(
            {
                "status": "success",
                "message": "Node already exists.",
                "node": {
                    "category": existing.category,
                    "subcategory": existing.subcategory,
                },
            },
            status=status.HTTP_200_OK,
        )

    new_node = TaxonomyTree.objects.create(
        category=category, subcategory=subcategory, is_active=True, display_order=99
    )

    return Response(
        {
            "status": "success",
            "node": {
                "category": new_node.category,
                "subcategory": new_node.subcategory,
            },
        },
        status=status.HTTP_201_CREATED,
    )
