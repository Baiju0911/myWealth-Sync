import logging
from django.db.models import Q, Sum, FloatField, Value, Count
from django.db.models.functions import Coalesce
from rest_framework import status, views
from rest_framework.decorators import api_view
from rest_framework.response import Response
import re
import json
from django.db import transaction
from collections import Counter
from django.core.paginator import Paginator
from decimal import Decimal

from urllib.parse import parse_qs, unquote
from django.http import JsonResponse
from ..models.models import (
    JournalEntry,
    TaxonomyTree,
    ClassificationStatus,
    ClassificationRule,
    StatementStagingLine,
)
from tracker.classification.remarks_service import (
    extract_candidate_patterns_from_narrations,
)
from tracker.classification.engine import (
    get_suspense_clusters,
    reclassify_and_learn,
    fetch_cluster_line_items,
    extract_meaningful_tokens,
    match_multi_tokens,
    GENERIC_IGNORE_PATTERNS,
    get_clean_patterns,
    generate_strict_multitoken_pattern,
    extract_clean_payee_pattern,
)
from tracker.models.subledger import AssetCategory

from typing import List, Dict, Any
from ..ai.services.hybrid_classifier import push_to_vector_cache

from tracker.classification.serializers import (
    ClassificationJournalEntrySerializer,
    ReclassifyRequestSerializer,
)
from rest_framework.pagination import PageNumberPagination
from tracker.classification.utils.upiparser import clean_payee_name

from tracker.constants import (
    RULE_SAFETY_BLACKLIST,
    NOISE_KEYWORD_BLACKLIST,
    CATASTROPHIC_KEYWORDS,
)

logger = logging.getLogger(__name__)


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
            current_remarks = entry.remarks if isinstance(entry.remarks, dict) else {}
            current_remarks["user_note"] = user_note if user_note else None

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

    def post(self, request):
        input_serializer = ReclassifyRequestSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        try:
            updated_entry = JournalEntry.reclassify_statement_line(
                row_identifier=data["row_identifier"],
                new_category=data["new_category"],
                new_subcategory=data["new_subcategory"],
                rule_code=data.get("rule_code", "MANUAL"),
                taxonomy_node_account_id=data.get("taxonomy_node_account_id", 99),
                user_note=data.get("user_note"),
            )

            current_remarks = updated_entry.remarks or {}
            current_remarks["target_account_name"] = data["new_subcategory"]
            current_remarks["display_text"] = (
                f"Reclassified to {data['new_subcategory']} via Workbench"
            )

            updated_entry.remarks = current_remarks
            updated_entry.save(update_fields=["remarks"])

            output_serializer = ClassificationJournalEntrySerializer(updated_entry)
            return Response(output_serializer.data, status=status.HTTP_200_OK)

        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class CategoryVendorDrilldownView(views.APIView):
    def get(self, request):
        target_sub = request.GET.get("subcategory")
        account_id_param = request.GET.get("account_id")

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


# @api_view(["GET"])
# def get_suspense_workbench_data(request):
#     target_sub = request.GET.get("subcategory", "Suspense Account")
#     account_id_param = request.GET.get("account_id")
#     search_query = request.GET.get("q") or request.GET.get("search")

#     include_cleared_param = request.GET.get("include_cleared")
#     if include_cleared_param is not None:
#         include_cleared = include_cleared_param.lower() in ["true", "1", "yes"]
#     else:
#         include_cleared = target_sub != "Suspense Account"

#     account_id = (
#         int(account_id_param)
#         if account_id_param and account_id_param.isdigit()
#         else None
#     )

#     clusters = get_suspense_clusters(
#         target_subcategory=target_sub,
#         account_id=account_id,
#         search_query=search_query,
#         include_cleared=include_cleared,
#     )

#     return Response(
#         {
#             "status": "success",
#             "target_subcategory": target_sub,
#             "include_cleared": include_cleared,
#             "total_clusters": len(clusters),
#             "clusters": clusters,
#         },
#         status=status.HTTP_200_OK,
#     )


@api_view(["GET"])
def get_suspense_workbench_data(request):
    """
    Lightweight cluster summary endpoint. Returns aggregated metadata
    without serializing thousands of child line items upfront.
    """
    target_sub = request.GET.get("subcategory", "Suspense Account")
    account_id_param = request.GET.get("account_id")
    search_query = request.GET.get("q") or request.GET.get("search")
    page_number = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("limit", 60))

    account_id = (
        int(account_id_param)
        if account_id_param and account_id_param.isdigit()
        else None
    )

    # 🟢 RULE 1: Node 99 is strictly the Suspense account.
    # For any regular GL head (Fixed Deposits, Real Estate, etc.), drop account_id=99.
    if target_sub != "Suspense Account" and account_id == 99:
        account_id = None

    # 🟢 RULE 2: Regular GL heads ALWAYS need already-cleared/reclassified transactions.
    include_cleared_param = request.GET.get("include_cleared")
    if target_sub != "Suspense Account":
        include_cleared = True  # Must be True to fetch classified ledger entries!
    elif include_cleared_param is not None:
        include_cleared = include_cleared_param.lower() in ["true", "1", "yes"]
    else:
        include_cleared = False

    all_clusters = get_suspense_clusters(
        target_subcategory=target_sub,
        account_id=account_id,
        search_query=search_query,
        include_cleared=include_cleared,
        include_items=False,
    )

    paginator = Paginator(all_clusters, page_size)
    page_obj = paginator.get_page(page_number)

    return Response(
        {
            "status": "success",
            "target_subcategory": target_sub,
            "include_cleared": include_cleared,
            "total_clusters": len(all_clusters),
            "total_pages": paginator.num_pages,
            "current_page": page_number,
            "has_next": page_obj.has_next(),
            "clusters": list(page_obj.object_list),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def get_cluster_line_items(request):
    """
    Lazy fetch endpoint. Called on-demand when an accordion is expanded.
    """
    entry_ids = request.data.get("entry_ids") or request.data.get("transaction_ids", [])

    if not entry_ids:
        return Response(
            {
                "status": "success",
                "count": 0,
                "items": [],
            },
            status=status.HTTP_200_OK,
        )

    items = fetch_cluster_line_items(entry_ids)

    return Response(
        {
            "status": "success",
            "count": len(items),
            "items": items,
        },
        status=status.HTTP_200_OK,
    )


# @api_view(["POST"])
# def get_cluster_line_items(request):
#     """
#     Lazy fetch endpoint. Called on-demand when an accordion is expanded.
#     """
#     entry_ids = request.data.get("entry_ids") or request.data.get("transaction_ids", [])

#     if not entry_ids:
#         return Response(
#             {
#                 "status": "success",
#                 "count": 0,
#                 "items": [],
#             },
#             status=status.HTTP_200_OK,
#         )

#     items = fetch_cluster_line_items(entry_ids)

#     return Response(
#         {
#             "status": "success",
#             "count": len(items),
#             "items": items,
#         },
#         status=status.HTTP_200_OK,
#     )


# @api_view(["POST"])
# def apply_reclassification_and_learn(request):
#     transaction_ids = (
#         request.data.get("transaction_ids")
#         or request.data.get("row_identifiers")
#         or request.data.get("ids")
#         or []
#     )
#     target_category = request.data.get("target_category")
#     target_subcategory = request.data.get("target_subcategory")

#     patterns = request.data.get("patterns", [])
#     single_pattern = request.data.get("pattern")

#     if not patterns and single_pattern:
#         patterns = [single_pattern]

#     save_rule = request.data.get("save_rule", True)

#     if not transaction_ids or not target_category or not target_subcategory:
#         return Response(
#             {
#                 "error": "transaction_ids (or row_identifiers), target_category, and target_subcategory are required."
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
    transaction_ids = (
        request.data.get("transaction_ids")
        or request.data.get("row_identifiers")
        or request.data.get("ids")
        or []
    )
    target_category = request.data.get("target_category")
    target_subcategory = request.data.get("target_subcategory")

    patterns = request.data.get("patterns", [])
    single_pattern = request.data.get("pattern")

    if not patterns and single_pattern:
        patterns = [single_pattern]

    save_rule = request.data.get("save_rule", True)

    # 🎯 1. Receive the optional Subledger Folio ID from the Workbench
    subledger_asset_id = request.data.get("subledger_asset_id")

    if not transaction_ids or not target_category or not target_subcategory:
        return Response(
            {
                "error": "transaction_ids (or row_identifiers), target_category, and target_subcategory are required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Run standard classification & rule training
    result = reclassify_and_learn(
        transaction_ids=transaction_ids,
        target_category=target_category,
        target_subcategory=target_subcategory,
        patterns=patterns,
        save_rule=save_rule,
    )

    # 🎯 3. If the user intentionally chose a Subledger Folio (e.g. Petty Cash Float), bind it!
    if subledger_asset_id:
        try:
            from django.apps import apps

            AssetSubLedger = apps.get_model("ledger", "AssetSubLedger")
            AssetTransactionMapping = apps.get_model(
                "ledger", "AssetTransactionMapping"
            )

            target_asset = AssetSubLedger.objects.filter(id=subledger_asset_id).first()
            if target_asset:
                # Query the journal entries that were just reclassified
                entries_to_map = JournalEntry.objects.filter(
                    Q(id__in=transaction_ids) | Q(row_identifier__in=transaction_ids)
                )

                created_mappings = 0
                for entry in entries_to_map:
                    if not entry.row_identifier:
                        continue

                    # Avoid duplicate mappings
                    mapping, created = AssetTransactionMapping.objects.get_or_create(
                        asset=target_asset,
                        row_identifier=entry.row_identifier,
                        defaults={
                            "amount": entry.debit or entry.credit or Decimal("0.00"),
                            "transaction_date": entry.transaction_date,
                            "transaction_purpose": "OPERATING_SPEND",
                            "is_cash_entry": False,
                            "user_note": f"Classified via Workbench to {target_subcategory}",
                        },
                    )
                    if created:
                        created_mappings += 1

                logger.info(
                    f"Bound {created_mappings} transaction(s) to Subledger Folio [{target_asset.asset_code}]"
                )
                result["subledger_bound"] = True
                result["subledger_asset_code"] = target_asset.asset_code
                result["mappings_created"] = created_mappings
        except Exception as e:
            logger.error(
                f"Failed to attribute transactions to subledger {subledger_asset_id}: {e}"
            )
            result["subledger_error"] = str(e)

    return Response(result, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_taxonomy_nodes_Assetview(request):
    nodes = TaxonomyTree.objects.filter(is_active=True)

    tree_dict = {}
    for node in nodes:
        if node.category not in tree_dict:
            tree_dict[node.category] = []
        tree_dict[node.category].append(
            {"id": node.id, "subcategory": node.subcategory}
        )

    taxonomy_data = [
        {"category": cat, "subcategories": subs} for cat, subs in tree_dict.items()
    ]

    return Response({"status": "success", "taxonomy": taxonomy_data})


# @api_view(["GET"])
# def get_taxonomy_tree_view(request):
#     nodes = TaxonomyTree.objects.filter(is_active=True)

#     tree_dict = {}
#     for node in nodes:
#         if node.category not in tree_dict:
#             tree_dict[node.category] = []
#         tree_dict[node.category].append(node.subcategory)

#     taxonomy_data = [
#         {"category": cat, "subcategories": subs} for cat, subs in tree_dict.items()
#     ]

#     return Response({"status": "success", "taxonomy": taxonomy_data})


@api_view(["GET"])
def get_taxonomy_tree_view(request):
    """GET /api/get_taxonomy_tree/

    Builds an in-memory taxonomy tree grouping active subcategories under
    primary categories, complete with explicit choice/category codes.
    """
    # 🟢 1. Query TaxonomyTree nodes directly without invalid select_related
    nodes = TaxonomyTree.objects.filter(is_active=True)

    # 🟢 2. Build fast lookup map for AssetCategories by default subcategory
    cat_map = {
        cat.default_taxonomy_subcategory.strip().lower(): cat.code
        for cat in AssetCategory.objects.filter(is_active=True)
        if cat.default_taxonomy_subcategory
    }

    tree_dict = {}

    for node in nodes:
        sub_name = node.subcategory.strip()
        sub_lower = sub_name.lower()

        # Resolve category_code dynamically from cat_map or fallback to code-friendly string
        resolved_code = cat_map.get(
            sub_lower, sub_name.replace(" ", "_").replace("&", "").upper()
        )

        if node.category not in tree_dict:
            tree_dict[node.category] = []

        tree_dict[node.category].append(
            {
                "id": str(node.id),
                "subcategory": sub_name,
                "category_code": resolved_code,
            }
        )

    taxonomy_data = [
        {"category": cat, "subcategories": subs} for cat, subs in tree_dict.items()
    ]

    return Response(
        {"status": "success", "taxonomy": taxonomy_data},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def add_taxonomy_node(request):
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


@api_view(["POST"])
def preview_pattern_matches(request):
    raw_pattern = request.data.get("pattern", "")
    entry_type = request.data.get("entry_type", "Debit")

    clean_p = extract_clean_payee_pattern(raw_pattern)
    if not clean_p or len(clean_p) < 3:
        return Response({"match_count": 0, "clean_pattern": ""})

    query = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

    if entry_type.lower() == "debit":
        query = query.filter(debit__gt=0)
    else:
        query = query.filter(credit__gt=0)

    matching_rows = query.filter(
        Q(remarks__icontains=clean_p) | Q(evaluation_matrix_snapshot__icontains=clean_p)
    )

    return Response(
        {
            "clean_pattern": clean_p,
            "entry_type": entry_type,
            "match_count": matching_rows.count(),
            "matching_transaction_ids": list(
                matching_rows.values_list("id", flat=True)
            ),
        }
    )


REF_HASH_REGEX = re.compile(r"^[A-Z0-9]{9,}$")


# @api_view(["POST"])
# def validate_pattern_anchor(request):
#     raw_pattern = request.data.get("pattern", "").strip().upper()

#     if not raw_pattern:
#         return Response(
#             {
#                 "status": "CATASTROPHIC",
#                 "is_valid": False,
#                 "clean_pattern": "",
#                 "message": "Pattern anchor cannot be empty.",
#             }
#         )

#     if len(raw_pattern) < 2:
#         return Response(
#             {
#                 "status": "CATASTROPHIC",
#                 "is_valid": False,
#                 "clean_pattern": raw_pattern,
#                 "message": "🛑 Pattern must be at least 2 characters long.",
#             }
#         )

#     if raw_pattern in CATASTROPHIC_KEYWORDS:
#         return Response(
#             {
#                 "status": "CATASTROPHIC",
#                 "is_valid": False,
#                 "clean_pattern": raw_pattern,
#                 "message": f"🛑 '{raw_pattern}' is a generic system keyword.",
#             }
#         )

#     if REF_HASH_REGEX.match(raw_pattern) and any(
#         char.isdigit() for char in raw_pattern
#     ):
#         return Response(
#             {
#                 "status": "BAD",
#                 "is_valid": True,
#                 "clean_pattern": raw_pattern,
#                 "message": f"⚠️ '{raw_pattern}' looks like a temporary UPI/RRN reference hash.",
#             }
#         )

#     clean_pattern = re.sub(r"[^A-Z0-9\s]", " ", raw_pattern)
#     clean_pattern = re.sub(r"\s+", " ", clean_pattern).strip()

#     if clean_pattern != raw_pattern:
#         return Response(
#             {
#                 "status": "BAD",
#                 "is_valid": True,
#                 "clean_pattern": clean_pattern,
#                 "message": f"💡 Special characters detected. Auto-normalized to '{clean_pattern}'.",
#             }
#         )

#     return Response(
#         {
#             "status": "GOOD",
#             "is_valid": True,
#             "clean_pattern": clean_pattern,
#             "message": f"🟢 Excellent vendor anchor! Ready to auto-match future transactions.",
#         }
#     )


@api_view(["POST"])
def validate_pattern_anchor(request):
    raw_pattern = request.data.get("pattern", "").strip().upper()

    if not raw_pattern:
        return Response(
            {
                "status": "CATASTROPHIC",
                "valid": False,
                "is_valid": False,
                "clean_pattern": "",
                "message": "Pattern anchor cannot be empty.",
            },
            status=status.HTTP_200_OK,
        )

    if len(raw_pattern) < 2:
        return Response(
            {
                "status": "CATASTROPHIC",
                "valid": False,
                "is_valid": False,
                "clean_pattern": raw_pattern,
                "message": "🛑 Pattern must be at least 2 characters long.",
            },
            status=status.HTTP_200_OK,
        )

    if raw_pattern in CATASTROPHIC_KEYWORDS:
        return Response(
            {
                "status": "CATASTROPHIC",
                "valid": False,
                "is_valid": False,
                "clean_pattern": raw_pattern,
                "message": f"🛑 '{raw_pattern}' is a generic system keyword.",
            },
            status=status.HTTP_200_OK,
        )

    if REF_HASH_REGEX.match(raw_pattern) and any(
        char.isdigit() for char in raw_pattern
    ):
        return Response(
            {
                "status": "BAD",
                "valid": True,
                "is_valid": True,
                "clean_pattern": raw_pattern,
                "message": f"⚠️ '{raw_pattern}' looks like a temporary UPI/RRN reference hash.",
            },
            status=status.HTTP_200_OK,
        )

    clean_pattern = re.sub(r"[^A-Z0-9\s]", " ", raw_pattern)
    clean_pattern = re.sub(r"\s+", " ", clean_pattern).strip()

    if clean_pattern != raw_pattern:
        return Response(
            {
                "status": "BAD",
                "valid": True,
                "is_valid": True,
                "clean_pattern": clean_pattern,
                "message": f"💡 Special characters detected. Auto-normalized to '{clean_pattern}'.",
            },
            status=status.HTTP_200_OK,
        )

    return Response(
        {
            "status": "GOOD",
            "valid": True,
            "is_valid": True,
            "clean_pattern": clean_pattern,
            "message": "🟢 Excellent vendor anchor! Ready to auto-match future transactions.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def remove_pattern_from_rule(request):
    rule_code = request.data.get("rule_code")
    pattern_to_remove = request.data.get("pattern")

    if not rule_code or not pattern_to_remove:
        return Response(
            {"error": "Missing rule_code or pattern"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    clean_token = str(pattern_to_remove).strip().lstrip("#").upper()

    try:
        rule = ClassificationRule.objects.get(rule_code=rule_code)
        removed = rule.remove_pattern(clean_token)

        if removed:
            after_patterns = rule.get_patterns()
            return Response(
                {
                    "status": "success",
                    "message": f"Pattern '{clean_token}' purged from {rule_code}",
                    "remaining_patterns": after_patterns,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "info",
                "message": f"Pattern '{clean_token}' not found in {rule_code}",
            },
            status=status.HTTP_200_OK,
        )

    except ClassificationRule.DoesNotExist:
        return Response(
            {"error": f"Rule {rule_code} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["POST"])
def bulk_remove_patterns_from_rules(request):
    items = request.data.get("items", [])

    if not items or not isinstance(items, list):
        return Response(
            {"status": "error", "message": "No items provided."}, status=400
        )

    try:
        with transaction.atomic():
            rule_map = {}
            for item in items:
                rule_code = item.get("rule_code")
                pattern = str(item.get("pattern", "")).replace("#", "").strip().upper()
                if rule_code and pattern:
                    rule_map.setdefault(rule_code, set()).add(pattern)

            updated_rules = 0
            for rule_code, purge_tokens in rule_map.items():
                rule = ClassificationRule.objects.filter(rule_code=rule_code).first()

                if rule:
                    existing = rule.get_patterns()
                    new_patterns = []

                    for pat in existing:
                        pat_str = pat.strip().upper()

                        if pat_str in purge_tokens:
                            continue

                        words = pat_str.split()
                        filtered_words = [w for w in words if w not in purge_tokens]

                        if filtered_words:
                            cleaned_phrase = " ".join(filtered_words)
                            if len(cleaned_phrase) >= 3:
                                new_patterns.append(cleaned_phrase)

                    if len(new_patterns) != len(existing):
                        rule.patterns = new_patterns
                        rule.save()
                        updated_rules += 1

            return Response(
                {
                    "status": "success",
                    "message": f"Purged patterns across {updated_rules} rules.",
                    "updated_rules_count": updated_rules,
                }
            )

    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=500)


# @api_view(["GET"])
# def sweep_preview_summary(request):
#     base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

#     unclassified_entries = list(
#         base_qs.values(
#             "id",
#             "debit",
#             "credit",
#             "remarks__payee",
#             "remarks__narration",
#             "remarks__display_text",
#             "evaluation_matrix_snapshot__resolved_subcategory",
#         )
#     )

#     total_unclassified = len(unclassified_entries)
#     if total_unclassified == 0:
#         return Response({"status": "success", "rule_matches": []})

#     processed_pool = []
#     for entry in unclassified_entries:
#         debit_val = float(entry["debit"] or 0.0)
#         credit_val = float(entry["credit"] or 0.0)

#         payee = (entry.get("remarks__payee") or "").upper()
#         narration = (entry.get("remarks__narration") or "").upper()
#         display_text = (entry.get("remarks__display_text") or "").upper()

#         search_haystack = f"{payee} {narration} {display_text}"

#         processed_pool.append(
#             {
#                 "id": entry["id"],
#                 "debit": debit_val,
#                 "credit": credit_val,
#                 "total_amount": debit_val + credit_val,
#                 "haystack": search_haystack,
#             }
#         )

#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     rule_matches = []
#     seen_patterns = set()
#     claimed_entry_ids = set()

#     for rule in active_rules:
#         raw_patterns = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         if not raw_patterns:
#             continue

#         patterns_list = sorted(
#             list(raw_patterns), key=lambda p: (-len(p.split()), -len(p))
#         )
#         rule_type = (
#             rule.rule_type.lower()
#             if hasattr(rule, "rule_type") and rule.rule_type
#             else None
#         )

#         for pattern_str in patterns_list:
#             if not pattern_str or pattern_str in seen_patterns:
#                 continue

#             clean_search_str = pattern_str.lstrip("#").strip().upper()
#             if len(clean_search_str) < 2:
#                 continue

#             matched_count = 0
#             matched_amount = 0.0
#             new_claimed_ids = []

#             for row in processed_pool:
#                 if row["id"] in claimed_entry_ids:
#                     continue

#                 if rule_type == "debit" and row["debit"] <= 0:
#                     continue
#                 if rule_type == "credit" and row["credit"] <= 0:
#                     continue

#                 if clean_search_str in row["haystack"]:
#                     matched_count += 1
#                     matched_amount += row["total_amount"]
#                     new_claimed_ids.append(row["id"])

#             if matched_count > 0:
#                 claimed_entry_ids.update(new_claimed_ids)
#                 seen_patterns.add(pattern_str)

#                 rule_matches.append(
#                     {
#                         "pattern": pattern_str,
#                         "display_tag": f"#{pattern_str}",
#                         "token_breakdown": [clean_search_str],
#                         "matched_rows": matched_count,
#                         "total_amount": round(matched_amount, 2),
#                         "suggested_category": rule.target_category,
#                         "suggested_subcategory": rule.target_subcategory,
#                         "rule_code": rule.rule_code,
#                         "matched_entry_ids": new_claimed_ids,
#                     }
#                 )

#     return Response({"status": "success", "rule_matches": rule_matches})


@api_view(["GET"])
def sweep_preview_summary(request):
    base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

    entries = list(
        base_qs.only(
            "id",
            "debit",
            "credit",
            "remarks",
        )
    )

    if not entries:
        return Response({"status": "success", "rule_matches": []})

    processed_pool = []
    for entry in entries:
        debit_val = float(entry.debit or 0.0)
        credit_val = float(entry.credit or 0.0)
        rem = entry.remarks if isinstance(entry.remarks, dict) else {}

        payee = str(rem.get("payee") or "").upper()
        narration = str(
            rem.get("universal_narration") or rem.get("narration") or ""
        ).upper()
        display_text = str(rem.get("display_text") or "").upper()

        search_haystack = f"{payee} {narration} {display_text}"

        processed_pool.append(
            {
                "id": entry.id,
                "debit": debit_val,
                "credit": credit_val,
                "total_amount": debit_val + credit_val,
                "haystack": search_haystack,
            }
        )

    active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
        "-priority"
    )

    rule_matches = []
    seen_patterns = set()
    claimed_entry_ids = set()

    for rule in active_rules:
        raw_patterns = (
            rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
        )

        if not raw_patterns:
            continue

        if isinstance(raw_patterns, str):
            try:
                patterns_list = json.loads(raw_patterns)
            except Exception:
                patterns_list = [raw_patterns]
        else:
            patterns_list = list(raw_patterns)

        patterns_list = sorted(
            patterns_list, key=lambda p: (-len(str(p).split()), -len(str(p)))
        )

        rule_type = (
            rule.rule_type.lower()
            if hasattr(rule, "rule_type") and rule.rule_type
            else None
        )

        for pattern_str in patterns_list:
            if not pattern_str or pattern_str in seen_patterns:
                continue

            clean_search_str = str(pattern_str).lstrip("#").strip().upper()
            if len(clean_search_str) < 2:
                continue

            matched_count = 0
            matched_amount = 0.0
            new_claimed_ids = []

            for row in processed_pool:
                if row["id"] in claimed_entry_ids:
                    continue

                if rule_type == "debit" and row["debit"] <= 0:
                    continue
                if rule_type == "credit" and row["credit"] <= 0:
                    continue

                if clean_search_str in row["haystack"]:
                    matched_count += 1
                    matched_amount += row["total_amount"]
                    new_claimed_ids.append(row["id"])

            if matched_count > 0:
                claimed_entry_ids.update(new_claimed_ids)
                seen_patterns.add(pattern_str)

                rule_matches.append(
                    {
                        "pattern": pattern_str,
                        "display_tag": f"#{pattern_str.lstrip('#')}",
                        "token_breakdown": [clean_search_str],
                        "matched_rows": matched_count,
                        "total_amount": round(matched_amount, 2),
                        "suggested_category": rule.target_category,
                        "suggested_subcategory": rule.target_subcategory,
                        "rule_code": rule.rule_code,
                        "matched_entry_ids": new_claimed_ids,
                    }
                )

    return Response({"status": "success", "rule_matches": rule_matches})


@api_view(["POST"])
@transaction.atomic
def execute_bulk_sweep(request):
    selected_patterns = request.data.get("patterns", [])
    account_id = request.data.get("account_id", 99)

    print("\n" + "=" * 80)
    print(f"🚀 [NODE 99 BULK SWEEP STARTED] Account ID: {account_id}")
    print(f"📊 Payload Patterns Selected: {len(selected_patterns)}")
    print("=" * 80)

    base_qs = JournalEntry.objects.filter(account_id=account_id, is_reclassified=False)
    initial_pending_count = base_qs.count()

    if initial_pending_count == 0:
        print("⚠️ No unclassified entries found for this account. Exiting sweep.")
        return Response({"status": "success", "total_reclassified": 0})

    print(f"📥 Initial Unclassified Queue Depth: {initial_pending_count} rows")

    active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
        "-priority"
    )

    total_updated = 0
    claimed_entry_ids = set()
    seen_patterns = set()

    clean_selected = (
        [p.lstrip("#").strip().upper() for p in selected_patterns]
        if selected_patterns
        else []
    )

    for rule in active_rules:
        raw_patterns = (
            rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
        )
        if not raw_patterns:
            continue

        patterns_list = sorted(
            list(raw_patterns), key=lambda p: (-len(p.split()), -len(p))
        )
        rule_type = (
            rule.rule_type.lower()
            if hasattr(rule, "rule_type") and rule.rule_type
            else None
        )

        for pattern_str in patterns_list:
            if not pattern_str or pattern_str in seen_patterns:
                continue

            clean_search_str = pattern_str.lstrip("#").strip()
            if len(clean_search_str) < 2:
                continue

            if clean_selected:
                matched_selection = any(
                    clean_search_str.upper() in sel or sel in clean_search_str.upper()
                    for sel in clean_selected
                )
                if not matched_selection:
                    continue

            candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

            if rule_type == "debit":
                candidate_qs = candidate_qs.filter(debit__gt=0)
            elif rule_type == "credit":
                candidate_qs = candidate_qs.filter(credit__gt=0)

            matched_qs = candidate_qs.filter(
                Q(remarks__payee__icontains=clean_search_str)
                | Q(remarks__narration__icontains=clean_search_str)
                | Q(remarks__display_text__icontains=clean_search_str)
            )

            entries_to_update = list(matched_qs)

            if entries_to_update:
                seen_patterns.add(pattern_str)
                row_identifiers_to_sync = []
                match_count = len(entries_to_update)

                print(
                    f"\n⚡ Pattern Match: [{clean_search_str.upper()}] -> Found {match_count} row(s)"
                )
                print(
                    f"   └─ Category: {rule.target_category} | Subcategory: {rule.target_subcategory}"
                )

                for entry in entries_to_update:
                    snapshot = entry.evaluation_matrix_snapshot or {}
                    if isinstance(snapshot, str):
                        try:
                            snapshot = json.loads(snapshot)
                        except json.JSONDecodeError:
                            snapshot = {}

                    snapshot["resolved_category"] = rule.target_category
                    snapshot["resolved_subcategory"] = rule.target_subcategory
                    snapshot["applied_rule_code"] = rule.rule_code

                    entry.evaluation_matrix_snapshot = snapshot
                    entry.is_reclassified = True
                    entry.classification_status = ClassificationStatus.AUTO_SWEPT

                    if entry.row_identifier:
                        row_identifiers_to_sync.append(entry.row_identifier)

                JournalEntry.objects.bulk_update(
                    entries_to_update,
                    [
                        "evaluation_matrix_snapshot",
                        "is_reclassified",
                        "classification_status",
                    ],
                    batch_size=500,
                )

                bank_legs_updated = 0
                if row_identifiers_to_sync:
                    bank_legs_updated = (
                        JournalEntry.objects.filter(
                            row_identifier__in=row_identifiers_to_sync
                        )
                        .exclude(account_id=account_id)
                        .update(
                            is_reclassified=True,
                            classification_status=ClassificationStatus.AUTO_SWEPT,
                        )
                    )

                matched_ids = [e.id for e in entries_to_update]
                claimed_entry_ids.update(matched_ids)
                total_updated += match_count

                # -----------------------------------------------------------------
                # 🟢 REAL-TIME T5 VECTOR SEEDING AND LOGGING
                # -----------------------------------------------------------------
                try:
                    push_to_vector_cache(
                        narration=clean_search_str.upper(),
                        category=rule.target_category,
                        subcategory=rule.target_subcategory,
                        rule_code=getattr(rule, "rule_code", "NODE99_BULK_SWEEP"),
                        confidence=100,
                    )
                    print(
                        f"   └─ 🧠 T5 Vector Memory Auto-Trained: '{clean_search_str.upper()}' seeded."
                    )
                    logger.info(
                        f"T5 Auto-Seeded: {clean_search_str} -> {rule.target_subcategory}"
                    )
                except Exception as seed_err:
                    print(
                        f"   └─ ⚠️ T5 Vector Seeding Warning for '{clean_search_str}': {seed_err}"
                    )
                    logger.warning(
                        f"T5 seeding skipped for '{clean_search_str}': {seed_err}"
                    )

    print("\n" + "=" * 80)
    print(f"✨ [NODE 99 BULK SWEEP COMPLETE]")
    print(f" • Total Ledger Entries Reclassified: {total_updated}")
    print(f" • Total Unique Patterns Learned by T5: {len(seen_patterns)}")
    print(
        f" • Remaining Unclassified Rows in Queue: {initial_pending_count - total_updated}"
    )
    print("=" * 80 + "\n")

    return Response({"status": "success", "total_reclassified": total_updated})


# def extract_candidate_patterns_from_narrations(
#     narrations: list[str], max_selectable: int = 15
# ) -> dict:
#     """
#     Extracts high-precision candidate patterns from raw narrations/payees.
#     Generates multi-word n-grams (2-grams, 3-grams), full normalized phrases,
#     and distinct brand tokens so the user has optimal multi-selection options.
#     """
#     if not narrations:
#         return {"selectable_patterns": [], "disabled_patterns": []}

#     candidate_counter = Counter()
#     disabled_tokens = set()

#     for raw_text in narrations:
#         if not raw_text:
#             continue

#         raw_str = str(raw_text).upper().strip()

#         clean_str = re.sub(r"[^A-Z0-9\s]", " ", raw_str)
#         clean_str = re.sub(r"\s+", " ", clean_str).strip()

#         if not clean_str:
#             continue

#         tokens = clean_str.split()

#         valid_tokens = []
#         for token in tokens:
#             if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
#                 disabled_tokens.add(token)
#                 continue

#             if token.isdigit() or len(token) > 25:
#                 continue

#             valid_tokens.append(token)

#         if 2 <= len(valid_tokens) <= 4:
#             full_compound = " ".join(valid_tokens)
#             if len(full_compound) >= 4:
#                 candidate_counter[full_compound] += 3

#         for i in range(len(valid_tokens) - 2):
#             gram_3 = f"{valid_tokens[i]} {valid_tokens[i+1]} {valid_tokens[i+2]}"
#             candidate_counter[gram_3] += 2

#         for i in range(len(valid_tokens) - 1):
#             gram_2 = f"{valid_tokens[i]} {valid_tokens[i+1]}"
#             candidate_counter[gram_2] += 2

#         for token in valid_tokens:
#             if len(token) >= 4:
#                 candidate_counter[token] += 1

#     sorted_candidates = sorted(
#         candidate_counter.keys(),
#         key=lambda p: (-candidate_counter[p], -len(p.split()), -len(p)),
#     )

#     selectable = sorted_candidates[:max_selectable]
#     disabled = sorted(list(disabled_tokens))[:10]

#     return {
#         "selectable_patterns": selectable,
#         "disabled_patterns": disabled,
#     }


# @api_view(["POST"])
# def get_candidate_patterns_view(request):
#     transaction_ids = request.data.get("transaction_ids", [])

#     if not transaction_ids:
#         return JsonResponse({"selectable_patterns": [], "disabled_patterns": []})

#     entries = JournalEntry.objects.filter(id__in=transaction_ids)
#     if not entries.exists():
#         entries = JournalEntry.objects.filter(row_identifier__in=transaction_ids)

#     narrations = []
#     for entry in entries:
#         remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
#         narration = remarks_dict.get("narration") or str(entry.remarks or "")
#         payee = remarks_dict.get("payee") or ""

#         if payee:
#             narrations.append(payee)
#         if narration:
#             narrations.append(narration)

#     result = extract_candidate_patterns_from_narrations(narrations, max_selectable=15)
#     return JsonResponse(result)


@api_view(["POST"])
def get_candidate_patterns_view(request):
    transaction_ids = request.data.get("transaction_ids", [])
    if not transaction_ids:
        return Response(
            {"selectable_patterns": [], "disabled_patterns": []},
            status=status.HTTP_200_OK,
        )

    entries = JournalEntry.objects.filter(id__in=transaction_ids).only(
        "remarks", "row_identifier"
    )

    # Staging lookup for clean raw narration
    row_ids = [e.row_identifier for e in entries if e.row_identifier]
    staging_map = dict(
        StatementStagingLine.objects.filter(row_identifier__in=row_ids).values_list(
            "row_identifier", "narration"
        )
    )

    narrations = []
    for entry in entries:
        rem = entry.remarks if isinstance(entry.remarks, dict) else {}
        # Priority: payee -> staging raw narration -> remarks universal_narration
        narr = (
            rem.get("payee")
            or staging_map.get(entry.row_identifier)
            or rem.get("universal_narration")
            or ""
        )
        if narr:
            narrations.append(narr)

    result = extract_candidate_patterns_from_narrations(narrations)
    return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
def suggest_rule_for_cluster(request):
    raw_pattern = request.data.get("pattern", "")
    entry_type = request.data.get("entry_type", "Debit")

    clean_p = extract_clean_payee_pattern(raw_pattern)
    if not clean_p or len(clean_p) < 3:
        return Response({"has_suggestion": False})

    clean_token = str(clean_p).strip().upper()

    candidate_rules = ClassificationRule.objects.filter(
        is_active=True, rule_type__iexact=entry_type
    )

    matched_rule = None

    for rule in candidate_rules:
        patterns = rule.get_patterns()

        if clean_token in patterns or any(
            clean_token == p.strip().upper() for p in patterns
        ):
            matched_rule = rule
            break

    if matched_rule:
        return Response(
            {
                "has_suggestion": True,
                "rule_code": matched_rule.rule_code,
                "suggested_category": matched_rule.target_category,
                "suggested_subcategory": matched_rule.target_subcategory,
                "matched_pattern": clean_token,
            }
        )

    return Response({"has_suggestion": False})
