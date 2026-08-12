# tracker/classification/classficationViews.py
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

from urllib.parse import parse_qs, unquote
from django.db.models import Q, Count, Sum
from django.http import JsonResponse
from ..models.models import (
    JournalEntry,
    TaxonomyTree,
    ClassificationStatus,
)
from tracker.classification.engine import (
    get_suspense_clusters,
    reclassify_and_learn,
    extract_meaningful_tokens,
    match_multi_tokens,
    GENERIC_IGNORE_PATTERNS,
    get_clean_patterns,
    generate_strict_multitoken_pattern,
)
from typing import List, Dict, Any

from tracker.classification.serializers import (
    ClassificationJournalEntrySerializer,
    ReclassifyRequestSerializer,
)
from rest_framework.pagination import PageNumberPagination
from tracker.classification.utils.upiparser import clean_payee_name

from tracker.classification.engine import extract_clean_payee_pattern
from ..models.models import ClassificationRule
from tracker.constants import (
    RULE_SAFETY_BLACKLIST,
    NOISE_KEYWORD_BLACKLIST,
    CATASTROPHIC_KEYWORDS,
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


logger = logging.getLogger(__name__)


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


# class ReclassifyEntryView_older(views.APIView):
#     """
#     POST /api/classification/reclassify/
#     Handles single-row reclassification requests from the frontend modal.
#     """

#     def post(self, request):
#         input_serializer = ReclassifyRequestSerializer(data=request.data)
#         input_serializer.is_valid(raise_exception=True)

#         data = input_serializer.validated_data

#         try:
#             # Calls atomic reclassification on JournalEntry model
#             updated_entry = JournalEntry.reclassify_statement_line(
#                 row_identifier=data["row_identifier"],
#                 new_category=data["new_category"],
#                 new_subcategory=data["new_subcategory"],
#                 rule_code=data.get("rule_code", "MANUAL"),
#                 taxonomy_node_account_id=data.get("taxonomy_node_account_id", 99),
#                 user_note=data.get("user_note"),
#             )

#             output_serializer = ClassificationJournalEntrySerializer(updated_entry)
#             return Response(output_serializer.data, status=status.HTTP_200_OK)

#         except ValueError as exc:
#             return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class ReclassifyEntryView(views.APIView):

    def post(self, request):
        input_serializer = ReclassifyRequestSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        try:
            # Pass payee / narration into atomic model reclassify handler
            updated_entry = JournalEntry.reclassify_statement_line(
                row_identifier=data["row_identifier"],
                new_category=data["new_category"],
                new_subcategory=data["new_subcategory"],
                rule_code=data.get("rule_code", "MANUAL"),
                taxonomy_node_account_id=data.get("taxonomy_node_account_id", 99),
                user_note=data.get("user_note"),
            )

            # 🟢 Ensure remarks JSON carries target account display metadata
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
    Supports inspecting both pending and reclassified transactions.
    """
    target_sub = request.GET.get("subcategory", "Suspense Account")
    account_id_param = request.GET.get("account_id")
    search_query = request.GET.get("q") or request.GET.get("search")

    # Extract include_cleared parameter (defaults to True if inspecting a specific subcategory)
    include_cleared_param = request.GET.get("include_cleared")
    if include_cleared_param is not None:
        include_cleared = include_cleared_param.lower() in ["true", "1", "yes"]
    else:
        # Auto-enable include_cleared if a specific subcategory is selected (other than default Suspense Account)
        include_cleared = target_sub != "Suspense Account"

    account_id = (
        int(account_id_param)
        if account_id_param and account_id_param.isdigit()
        else None
    )

    clusters = get_suspense_clusters(
        target_subcategory=target_sub,
        account_id=account_id,
        search_query=search_query,
        include_cleared=include_cleared,  # <--- Pass flag to engine
    )

    return Response(
        {
            "status": "success",
            "target_subcategory": target_sub,
            "include_cleared": include_cleared,
            "total_clusters": len(clusters),
            "clusters": clusters,
        },
        status=status.HTTP_200_OK,
    )


# @api_view(["GET"])
# def get_suspense_workbench_data(request):
#     """
#     Returns auto-clustered patterns for Workbench review with direction flags, inflows/outflows,
#     and character/underscore-insensitive pattern search.
#     """
#     target_sub = request.GET.get("subcategory", "Suspense Account")
#     account_id_param = request.GET.get("account_id")
#     search_query = request.GET.get("q") or request.GET.get("search")

#     account_id = (
#         int(account_id_param)
#         if account_id_param and account_id_param.isdigit()
#         else None
#     )

#     clusters = get_suspense_clusters(
#         target_subcategory=target_sub,
#         account_id=account_id,
#         search_query=search_query,
#     )

#     return Response(
#         {
#             "status": "success",
#             "target_subcategory": target_sub,
#             "total_clusters": len(clusters),
#             "clusters": clusters,
#         },
#         status=status.HTTP_200_OK,
#     )


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


@api_view(["POST"])
def preview_pattern_matches(request):
    """Returns candidate unclassified Node 99 rows matching a clean pattern, split by Debit/Credit."""
    raw_pattern = request.data.get("pattern", "")
    entry_type = request.data.get(
        "entry_type", "Debit"
    )  # 'Debit' (Expense) or 'Credit' (Income)

    clean_p = extract_clean_payee_pattern(raw_pattern)
    if not clean_p or len(clean_p) < 3:
        return Response({"match_count": 0, "clean_pattern": ""})

    # Query matching direction and unclassified state
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


# @api_view(["GET"])
# def sweep_preview_summary(request):
#     """
#     Fast & Safe SQL Preview Engine for Node 99 Rules.
#     Scans unclassified Node 99 entries against active learned rules,
#     preventing double-counting using priority-ordered claim tracking
#     and compound-first pattern evaluation.
#     """
#     print(
#         "\n================================================================================"
#     )
#     print("🔍 [SWEEP PREVIEW ENGINE] STARTING NODE 99 RULE SCAN")
#     print(
#         "================================================================================"
#     )

#     base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
#     total_unclassified = base_qs.count()

#     # Filter for exact Suspense Account items to match your Audited Matrix
#     suspense_count = base_qs.filter(
#         evaluation_matrix_snapshot__resolved_subcategory="Suspense Account"
#     ).count()

#     print(
#         f"📊 [ENGINE DEBUG] Total Staging Queue: {total_unclassified} "
#         f"(Pending Suspense: {suspense_count})"
#     )

#     if total_unclassified == 0:
#         print("ℹ️ [ENGINE DEBUG] No unclassified entries found for Node 99. Exiting.")
#         return Response({"status": "success", "rule_matches": []})

#     # Order rules by highest priority first
#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )
#     print(f"⚙️ [ENGINE DEBUG] Total Active Rules Loaded: {active_rules.count()}")

#     rule_matches = []
#     seen_patterns = set()
#     claimed_entry_ids = set()

#     for rule in active_rules:
#         raw_patterns = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         if not raw_patterns:
#             continue

#         # 💡 CRITICAL FIX: Compound-First Sorting
#         # Forces multi-word compounds ('MARGIN FREE', 'AMAZON INDIA') to evaluate FIRST
#         # before loose single-word tokens ('MARGIN', 'AMAZON')
#         patterns_list = sorted(
#             list(raw_patterns), key=lambda p: (-len(p.split()), -len(p))
#         )

#         for pattern_str in patterns_list:
#             if not pattern_str or pattern_str in seen_patterns:
#                 if pattern_str in seen_patterns:
#                     print(
#                         f"   ⏭️ Skipping '{pattern_str}': Already processed by higher priority rule/pattern."
#                     )
#                 continue

#             # Strip leading hashes or formatting artifacts
#             clean_search_str = pattern_str.lstrip("#").strip()

#             # Guard against empty or ultra-short accidental 1-letter rules
#             if len(clean_search_str) < 2:
#                 print(f"   ⚠️ Skipping '{pattern_str}': Too short (< 2 characters).")
#                 continue

#             # Exclude entries already claimed by higher-priority rules/patterns
#             candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

#             # Filter by rule entry type (Debit vs Credit) if rule_type is defined
#             if hasattr(rule, "rule_type") and rule.rule_type:
#                 if rule.rule_type.lower() == "debit":
#                     candidate_qs = candidate_qs.filter(debit__gt=0)
#                 elif rule.rule_type.lower() == "credit":
#                     candidate_qs = candidate_qs.filter(credit__gt=0)

#             # ✅ MULTI-VECTOR TARGETED SEARCH: Search specific string fields only!
#             matched_qs = candidate_qs.filter(
#                 Q(remarks__payee__icontains=clean_search_str)
#                 | Q(remarks__narration__icontains=clean_search_str)
#                 | Q(remarks__display_text__icontains=clean_search_str)
#             )

#             stats = matched_qs.aggregate(
#                 row_count=Count("id"),
#                 total_amt=Coalesce(
#                     Sum("debit") + Sum("credit"),
#                     Value(0.0),
#                     output_field=FloatField(),
#                 ),
#             )

#             count = stats["row_count"] or 0

#             if count > 0:
#                 new_matched_ids = list(matched_qs.values_list("id", flat=True))
#                 claimed_entry_ids.update(new_matched_ids)
#                 seen_patterns.add(pattern_str)

#                 total_amount = float(stats["total_amt"])

#                 print(
#                     f"   ✅ MATCH FOUND | Pattern: '{clean_search_str}' -> {count} rows | Total: ₹{total_amount:,.2f}"
#                 )

#                 rule_matches.append(
#                     {
#                         "pattern": pattern_str,
#                         "display_tag": f"#{pattern_str}",
#                         "token_breakdown": [clean_search_str],
#                         "matched_rows": count,
#                         "total_amount": total_amount,
#                         "suggested_category": rule.target_category,
#                         "suggested_subcategory": rule.target_subcategory,
#                         "rule_code": rule.rule_code,
#                     }
#                 )

#     print(
#         "\n================================================================================"
#     )
#     print(
#         f"🚀 [SWEEP PREVIEW COMPLETE] Matched Cards: {len(rule_matches)} | Total Claimed Rows: {len(claimed_entry_ids)}"
#     )
#     print(
#         "================================================================================\n"
#     )

#     return Response({"status": "success", "rule_matches": rule_matches})


# Known noise/reference hash patterns
REF_HASH_REGEX = re.compile(r"^[A-Z0-9]{9,}$")


@api_view(["POST"])
def validate_pattern_anchor(request):
    raw_pattern = request.data.get("pattern", "").strip().upper()

    if not raw_pattern:
        return Response(
            {
                "status": "CATASTROPHIC",
                "is_valid": False,
                "clean_pattern": "",
                "message": "Pattern anchor cannot be empty.",
            }
        )

    # 1. Reject single characters or ultra-short strings
    if len(raw_pattern) < 2:
        return Response(
            {
                "status": "CATASTROPHIC",
                "is_valid": False,
                "clean_pattern": raw_pattern,
                "message": "🛑 Pattern must be at least 2 characters long.",
            }
        )

    # 2. Check for Catastrophic System Keywords
    if raw_pattern in CATASTROPHIC_KEYWORDS:
        return Response(
            {
                "status": "CATASTROPHIC",
                "is_valid": False,
                "clean_pattern": raw_pattern,
                "message": f"🛑 '{raw_pattern}' is a generic system keyword. Using this will cause thousands of false matches across your ledger!",
            }
        )

    # 3. Check for UPI Reference Hashes / RRNs
    if REF_HASH_REGEX.match(raw_pattern) and any(
        char.isdigit() for char in raw_pattern
    ):
        return Response(
            {
                "status": "BAD",
                "is_valid": True,  # Allowed, but warned
                "clean_pattern": raw_pattern,
                "message": f"⚠️ '{raw_pattern}' looks like a temporary UPI/RRN reference hash. It will likely never match future transactions.",
            }
        )

    # 4. Handle Normalization (e.g. 'INT.PD' -> 'INT PD')
    clean_pattern = re.sub(r"[^A-Z0-9\s]", " ", raw_pattern)
    clean_pattern = re.sub(r"\s+", " ", clean_pattern).strip()

    if clean_pattern != raw_pattern:
        return Response(
            {
                "status": "BAD",
                "is_valid": True,
                "clean_pattern": clean_pattern,
                "message": f"💡 Special characters detected. Will be auto-normalized to '{clean_pattern}' for engine matching.",
            }
        )

    # 5. Perfect Clean Anchor (Good)
    return Response(
        {
            "status": "GOOD",
            "is_valid": True,
            "clean_pattern": clean_pattern,
            "message": f"🟢 Excellent vendor anchor! Ready to auto-match future transactions.",
        }
    )


# @api_view(["GET"])
# def sweep_preview_summary(request):
#     """
#     Fast & Safe SQL Preview Engine for Node 99 Rules.
#     Scans unclassified Node 99 entries against active learned rules,
#     preventing double-counting using priority-ordered claim tracking.
#     """
#     base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

#     if not base_qs.exists():
#         return Response({"status": "success", "rule_matches": []})

#     # Order rules by highest priority first
#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     rule_matches = []
#     seen_patterns = set()
#     claimed_entry_ids = set()

#     for rule in active_rules:
#         patterns_list = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         for pattern_str in patterns_list:
#             if not pattern_str or pattern_str in seen_patterns:
#                 continue

#             # Strip leading hashes or formatting artifacts
#             clean_search_str = pattern_str.lstrip("#").strip()

#             # Guard against empty or ultra-short accidental 1-letter rules
#             if len(clean_search_str) < 2:
#                 continue

#             # Exclude entries already claimed by higher-priority rules
#             candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

#             # Multi-vector JSON & text search
#             matched_qs = candidate_qs.filter(
#                 Q(remarks__icontains=clean_search_str)
#                 | Q(remarks__payee__icontains=clean_search_str)
#                 | Q(remarks__narration__icontains=clean_search_str)
#             )

#             stats = matched_qs.aggregate(
#                 row_count=Count("id"),
#                 total_amt=Coalesce(
#                     Sum("debit") + Sum("credit"), Value(0.0), output_field=FloatField()
#                 ),
#             )

#             count = stats["row_count"] or 0

#             if count > 0:
#                 new_matched_ids = list(matched_qs.values_list("id", flat=True))
#                 claimed_entry_ids.update(new_matched_ids)
#                 seen_patterns.add(pattern_str)

#                 rule_matches.append(
#                     {
#                         "pattern": pattern_str,
#                         "display_tag": f"#{pattern_str}",
#                         "token_breakdown": [clean_search_str],
#                         "matched_rows": count,
#                         "total_amount": float(stats["total_amt"]),
#                         "suggested_category": rule.target_category,
#                         "suggested_subcategory": rule.target_subcategory,
#                         "rule_code": rule.rule_code,
#                     }
#                 )

#     return Response({"status": "success", "rule_matches": rule_matches})
# @api_view(["GET"])
# def sweep_preview_summary(request):
#     """
#     Fast & Safe SQL Preview Engine for Node 99 Rules.
#     Scans unclassified Node 99 entries against active learned rules,
#     preventing double-counting using priority-ordered claim tracking.
#     """
#     base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

#     if not base_qs.exists():
#         return Response({"status": "success", "rule_matches": []})

#     # Order rules by highest priority first
#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     rule_matches = []
#     seen_patterns = set()
#     claimed_entry_ids = set()

#     for rule in active_rules:
#         patterns_list = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         for pattern_str in patterns_list:
#             if not pattern_str or pattern_str in seen_patterns:
#                 continue

#             # Strip leading hashes or formatting artifacts
#             clean_search_str = pattern_str.lstrip("#").strip()

#             # Guard against empty or ultra-short accidental 1-letter rules
#             if len(clean_search_str) < 2:
#                 continue

#             # Exclude entries already claimed by higher-priority rules
#             candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

#             # ✅ MULTI-VECTOR TARGETED SEARCH: Search specific string fields only!
#             # Avoid Q(remarks__icontains=...) which searches JSON keys/metadata structure!
#             matched_qs = candidate_qs.filter(
#                 Q(remarks__payee__icontains=clean_search_str)
#                 | Q(remarks__narration__icontains=clean_search_str)
#                 | Q(remarks__display_text__icontains=clean_search_str)
#             )

#             stats = matched_qs.aggregate(
#                 row_count=Count("id"),
#                 total_amt=Coalesce(
#                     Sum("debit") + Sum("credit"), Value(0.0), output_field=FloatField()
#                 ),
#             )

#             count = stats["row_count"] or 0

#             if count > 0:
#                 new_matched_ids = list(matched_qs.values_list("id", flat=True))
#                 claimed_entry_ids.update(new_matched_ids)
#                 seen_patterns.add(pattern_str)

#                 rule_matches.append(
#                     {
#                         "pattern": pattern_str,
#                         "display_tag": f"#{pattern_str}",
#                         "token_breakdown": [clean_search_str],
#                         "matched_rows": count,
#                         "total_amount": float(stats["total_amt"]),
#                         "suggested_category": rule.target_category,
#                         "suggested_subcategory": rule.target_subcategory,
#                         "rule_code": rule.rule_code,
#                     }
#                 )

#     return Response({"status": "success", "rule_matches": rule_matches})


# @api_view(["GET"])
# def sweep_preview_summary(request):
#     """
#     Lightning-Fast In-Memory Vector Sweep Engine for Node 99 Rules.
#     Fetches Node 99 entries once and performs priority-ordered,
#     compound-first pattern matching entirely in Python memory.
#     """
#     print(
#         "\n================================================================================"
#     )
#     print("⚡ [SWEEP PREVIEW ENGINE] STARTING LIGHTNING NODE 99 SCAN")
#     print(
#         "================================================================================"
#     )

#     base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
#     # base_qs = JournalEntry.objects.filter(classification_status="PENDING")

#     # 1. Fetch unclassified entries in a SINGLE database hit
#     # Pulling only required fields speeds up query execution significantly
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

#     suspense_count = sum(
#         1
#         for e in unclassified_entries
#         if e.get("evaluation_matrix_snapshot__resolved_subcategory")
#         == "Suspense Account"
#     )

#     print(
#         f"📊 [ENGINE DEBUG] Total Staging Queue: {total_unclassified} "
#         f"(Pending Suspense: {suspense_count})"
#     )

#     if total_unclassified == 0:
#         print("ℹ️ [ENGINE DEBUG] No unclassified entries found for Node 99. Exiting.")
#         return Response({"status": "success", "rule_matches": []})

#     # 2. Pre-process search targets for fast case-insensitive matching
#     # Concatenating target string fields once per row avoids repeated JSON string lookups
#     processed_pool = []
#     for entry in unclassified_entries:
#         debit_val = float(entry["debit"] or 0.0)
#         credit_val = float(entry["credit"] or 0.0)

#         payee = (entry.get("remarks__payee") or "").upper()
#         narration = (entry.get("remarks__narration") or "").upper()
#         display_text = (entry.get("remarks__display_text") or "").upper()

#         # Combine vector text target once
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

#     # 3. Fetch active rules ordered by priority
#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )
#     print(f"⚙️ [ENGINE DEBUG] Total Active Rules Loaded: {active_rules.count()}")

#     rule_matches = []
#     seen_patterns = set()
#     claimed_entry_ids = set()

#     # 4. In-Memory Vector Sweep Loop
#     for rule in active_rules:
#         raw_patterns = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         if not raw_patterns:
#             continue

#         # Compound-first pattern sorting
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
#                 if pattern_str in seen_patterns:
#                     print(f"    ⏭️ Skipping '{pattern_str}': Already processed.")
#                 continue

#             clean_search_str = pattern_str.lstrip("#").strip().upper()

#             if len(clean_search_str) < 2:
#                 print(f"    ⚠️ Skipping '{pattern_str}': Too short (< 2 characters).")
#                 continue

#             matched_count = 0
#             matched_amount = 0.0
#             new_claimed_ids = []

#             # Instant in-memory pattern evaluation across candidates
#             for row in processed_pool:
#                 if row["id"] in claimed_entry_ids:
#                     continue

#                 # Direction check (Debit vs Credit)
#                 if rule_type == "debit" and row["debit"] <= 0:
#                     continue
#                 if rule_type == "credit" and row["credit"] <= 0:
#                     continue

#                 # Fast string lookup
#                 if clean_search_str in row["haystack"]:
#                     matched_count += 1
#                     matched_amount += row["total_amount"]
#                     new_claimed_ids.append(row["id"])

#             if matched_count > 0:
#                 claimed_entry_ids.update(new_claimed_ids)
#                 seen_patterns.add(pattern_str)

#                 print(
#                     f"    ✅ MATCH FOUND | Pattern: '{clean_search_str}' -> {matched_count} rows | Total: ₹{matched_amount:,.2f}"
#                 )

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
#                     }
#                 )

#     print(
#         "\n================================================================================"
#     )
#     print(
#         f"🚀 [SWEEP PREVIEW COMPLETE] Matched Cards: {len(rule_matches)} | Total Claimed Rows: {len(claimed_entry_ids)}"
#     )
#     print(
#         "================================================================================\n"
#     )

#     return Response({"status": "success", "rule_matches": rule_matches})


# @api_view(["POST"])
# def execute_bulk_sweep(request):
#     """
#     Executes bulk reclassification matching Node 99 active rules.
#     Updates evaluation_matrix_snapshot and classification_status cleanly.
#     """
#     selected_patterns = request.data.get("patterns", [])
#     account_id = request.data.get("account_id", 99)

#     base_qs = JournalEntry.objects.filter(account_id=account_id, is_reclassified=False)

#     if not base_qs.exists():
#         return Response({"status": "success", "total_reclassified": 0})

#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     total_updated = 0
#     claimed_entry_ids = set()

#     # Pre-clean selected patterns if passed
#     clean_selected = (
#         [p.lstrip("#").strip().upper() for p in selected_patterns]
#         if selected_patterns
#         else []
#     )

#     for rule in active_rules:
#         patterns_list = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         if not patterns_list:
#             continue

#         rule_type = (
#             rule.rule_type.lower()
#             if hasattr(rule, "rule_type") and rule.rule_type
#             else None
#         )

#         for pattern_str in patterns_list:
#             if not pattern_str:
#                 continue

#             clean_search_str = pattern_str.lstrip("#").strip()
#             if len(clean_search_str) < 2:
#                 continue

#             # Respect payload filter if user passed specific patterns
#             if clean_selected and clean_search_str.upper() not in clean_selected:
#                 continue

#             candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

#             # Apply direction filter matching the preview engine
#             if rule_type == "debit":
#                 candidate_qs = candidate_qs.filter(debit__gt=0)
#             elif rule_type == "credit":
#                 candidate_qs = candidate_qs.filter(credit__gt=0)

#             # SQL Match across remarks JSON keys
#             matched_qs = candidate_qs.filter(
#                 Q(remarks__payee__icontains=clean_search_str)
#                 | Q(remarks__narration__icontains=clean_search_str)
#                 | Q(remarks__display_text__icontains=clean_search_str)
#             )

#             entries_to_update = list(matched_qs)

#             if entries_to_update:
#                 for entry in entries_to_update:
#                     snapshot = entry.evaluation_matrix_snapshot or {}
#                     if isinstance(snapshot, str):
#                         try:
#                             snapshot = json.loads(snapshot)
#                         except json.JSONDecodeError:
#                             snapshot = {}

#                     snapshot["resolved_category"] = rule.target_category
#                     snapshot["resolved_subcategory"] = rule.target_subcategory
#                     snapshot["applied_rule_code"] = rule.rule_code

#                     entry.evaluation_matrix_snapshot = snapshot
#                     entry.is_reclassified = True
#                     entry.classification_status = ClassificationStatus.AUTO_SWEPT

#                 # Bulk update database records
#                 JournalEntry.objects.bulk_update(
#                     entries_to_update,
#                     [
#                         "evaluation_matrix_snapshot",
#                         "is_reclassified",
#                         "classification_status",
#                     ],
#                     batch_size=500,
#                 )

#                 matched_ids = [e.id for e in entries_to_update]
#                 claimed_entry_ids.update(matched_ids)
#                 total_updated += len(entries_to_update)

#     return Response({"status": "success", "total_reclassified": total_updated})


# @api_view(["POST"])
# def execute_bulk_sweep(request):
#     """
#     Executes bulk reclassification matching Node 99 active rules.
#     Updates evaluation_matrix_snapshot and classification_status cleanly.
#     """
#     selected_patterns = request.data.get("patterns", [])
#     account_id = request.data.get("account_id", 99)

#     base_qs = JournalEntry.objects.filter(account_id=account_id, is_reclassified=False)

#     if not base_qs.exists():
#         return Response({"status": "success", "total_reclassified": 0})

#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     total_updated = 0
#     claimed_entry_ids = set()

#     for rule in active_rules:
#         patterns_list = (
#             rule.get_patterns() if hasattr(rule, "get_patterns") else rule.patterns
#         )

#         for pattern_str in patterns_list:
#             if not pattern_str:
#                 continue

#             clean_search_str = pattern_str.lstrip("#").strip()
#             if len(clean_search_str) < 2:
#                 continue

#             # If user sent specific patterns in request payload, respect the filter
#             if (
#                 selected_patterns
#                 and pattern_str not in selected_patterns
#                 and clean_search_str not in selected_patterns
#             ):
#                 continue

#             candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

#             # Direct SQL query matching preview engine
#             matched_qs = candidate_qs.filter(
#                 Q(remarks__icontains=clean_search_str)
#                 | Q(remarks__payee__icontains=clean_search_str)
#                 | Q(remarks__narration__icontains=clean_search_str)
#             )

#             entries_to_update = list(matched_qs)

#             if entries_to_update:
#                 for entry in entries_to_update:
#                     # Maintain evaluation matrix snapshot structure
#                     snapshot = entry.evaluation_matrix_snapshot or {}
#                     if isinstance(snapshot, str):
#                         try:
#                             snapshot = json.loads(snapshot)
#                         except json.JSONDecodeError:
#                             snapshot = {}

#                     snapshot["resolved_category"] = rule.target_category
#                     snapshot["resolved_subcategory"] = rule.target_subcategory
#                     snapshot["applied_rule_code"] = rule.rule_code

#                     entry.evaluation_matrix_snapshot = snapshot
#                     entry.is_reclassified = True
#                     entry.classification_status = "SWEEP_CLEARED"

#                 # Bulk update in Python/DB memory
#                 JournalEntry.objects.bulk_update(
#                     entries_to_update,
#                     [
#                         "evaluation_matrix_snapshot",
#                         "is_reclassified",
#                         "classification_status",
#                     ],
#                     batch_size=500,
#                 )

#                 matched_ids = [e.id for e in entries_to_update]
#                 claimed_entry_ids.update(matched_ids)
#                 total_updated += len(entries_to_update)

#     return Response({"status": "success", "total_reclassified": total_updated})


# @api_view(["GET"])
# def sweep_preview_summary(request):
#     """Lightning-Fast In-Memory Vector Sweep Engine for Node 99 Rules."""
#     print(
#         "\n================================================================================"
#     )
#     print("⚡ [SWEEP PREVIEW ENGINE] STARTING LIGHTNING NODE 99 SCAN")
#     print(
#         "================================================================================"
#     )

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
#     suspense_count = sum(
#         1
#         for e in unclassified_entries
#         if e.get("evaluation_matrix_snapshot__resolved_subcategory")
#         == "Suspense Account"
#     )

#     print(
#         f"📊 [ENGINE DEBUG] Total Staging Queue: {total_unclassified} "
#         f"(Pending Suspense: {suspense_count})"
#     )

#     if total_unclassified == 0:
#         print(
#             "ℹ️ [ENGINE DEBUG] No unclassified entries found for Node 99." " Exiting."
#         )
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
#     print(f"⚙️ [ENGINE DEBUG] Total Active Rules Loaded: {active_rules.count()}")

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

#     print(
#         f"🚀 [SWEEP PREVIEW COMPLETE] Matched Cards: {len(rule_matches)} | Total Claimed Rows: {len(claimed_entry_ids)}\n"
#     )
#     return Response({"status": "success", "rule_matches": rule_matches})


# @api_view(["POST"])
# @transaction.atomic
# def execute_bulk_sweep(request):
#     """Executes bulk reclassification matching Node 99 active rules cleanly."""
#     selected_patterns = request.data.get("patterns", [])
#     account_id = request.data.get("account_id", 99)

#     base_qs = JournalEntry.objects.filter(account_id=account_id, is_reclassified=False)

#     if not base_qs.exists():
#         return Response({"status": "success", "total_reclassified": 0})

#     active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
#         "-priority"
#     )

#     total_updated = 0
#     claimed_entry_ids = set()
#     seen_patterns = set()

#     clean_selected = (
#         [p.lstrip("#").strip().upper() for p in selected_patterns]
#         if selected_patterns
#         else []
#     )

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

#             clean_search_str = pattern_str.lstrip("#").strip()
#             if len(clean_search_str) < 2:
#                 continue

#             if clean_selected and clean_search_str.upper() not in clean_selected:
#                 continue

#             candidate_qs = base_qs.exclude(id__in=claimed_entry_ids)

#             if rule_type == "debit":
#                 candidate_qs = candidate_qs.filter(debit__gt=0)
#             elif rule_type == "credit":
#                 candidate_qs = candidate_qs.filter(credit__gt=0)

#             matched_qs = candidate_qs.filter(
#                 Q(remarks__payee__icontains=clean_search_str)
#                 | Q(remarks__narration__icontains=clean_search_str)
#                 | Q(remarks__display_text__icontains=clean_search_str)
#             )

#             entries_to_update = list(matched_qs)

#             if entries_to_update:
#                 seen_patterns.add(pattern_str)
#                 row_identifiers_to_sync = []

#                 for entry in entries_to_update:
#                     snapshot = entry.evaluation_matrix_snapshot or {}
#                     if isinstance(snapshot, str):
#                         try:
#                             snapshot = json.loads(snapshot)
#                         except json.JSONDecodeError:
#                             snapshot = {}

#                     snapshot["resolved_category"] = rule.target_category
#                     snapshot["resolved_subcategory"] = rule.target_subcategory
#                     snapshot["applied_rule_code"] = rule.rule_code

#                     entry.evaluation_matrix_snapshot = snapshot
#                     entry.is_reclassified = True
#                     entry.classification_status = ClassificationStatus.AUTO_SWEPT

#                     if entry.row_identifier:
#                         row_identifiers_to_sync.append(entry.row_identifier)

#                 # 1. Update Node 99 legs
#                 JournalEntry.objects.bulk_update(
#                     entries_to_update,
#                     [
#                         "evaluation_matrix_snapshot",
#                         "is_reclassified",
#                         "classification_status",
#                     ],
#                     batch_size=500,
#                 )

#                 # 2. Sync corresponding Bank Legs across row_identifiers
#                 if row_identifiers_to_sync:
#                     JournalEntry.objects.filter(
#                         row_identifier__in=row_identifiers_to_sync
#                     ).exclude(account_id=account_id).update(
#                         is_reclassified=True,
#                         classification_status=ClassificationStatus.AUTO_SWEPT,
#                     )

#                 matched_ids = [e.id for e in entries_to_update]
#                 claimed_entry_ids.update(matched_ids)
#                 total_updated += len(entries_to_update)

#     return Response({"status": "success", "total_reclassified": total_updated})


# @api_view(["POST"])
# def remove_pattern_from_rule(request):
#     """
#     Deletes a specific token/pattern from a Classification Rule directly
#     from the Node 99 Clearance Hub modal.
#     """
#     rule_code = request.data.get("rule_code")
#     pattern_to_remove = request.data.get("pattern")

#     if not rule_code or not pattern_to_remove:
#         return Response(
#             {"error": "Missing rule_code or pattern"},
#             status=status.HTTP_400_BAD_REQUEST,
#         )

#     clean_token = str(pattern_to_remove).strip().lstrip("#").upper()

#     try:
#         rule = ClassificationRule.objects.get(rule_code=rule_code)

#         # Call model method (handles both exact string matches AND sub-token stripping)
#         removed = rule.remove_pattern(clean_token)

#         if removed:
#             return Response(
#                 {
#                     "status": "success",
#                     "message": f"Pattern '{clean_token}' purged from {rule_code}",
#                     "remaining_patterns": rule.get_patterns(),
#                 },
#                 status=status.HTTP_200_OK,
#             )

#         return Response(
#             {
#                 "status": "info",
#                 "message": f"Pattern '{clean_token}' not found in {rule_code}",
#             },
#             status=status.HTTP_200_OK,
#         )

#     except ClassificationRule.DoesNotExist:
#         return Response(
#             {"error": f"Rule {rule_code} not found"},
#             status=status.HTTP_404_NOT_FOUND,
#         )


# @api_view(["POST"])
# def bulk_remove_patterns_from_rules(request):
#     items = request.data.get("items", [])
#     if not items or not isinstance(items, list):
#         return Response(
#             {"status": "error", "message": "No items provided."}, status=400
#         )

#     try:
#         with transaction.atomic():
#             rule_map = {}
#             for item in items:
#                 rule_code = item.get("rule_code")
#                 pattern = str(item.get("pattern", "")).replace("#", "").strip().upper()
#                 if rule_code and pattern:
#                     rule_map.setdefault(rule_code, set()).add(pattern)

#             updated_rules = 0
#             for rule_code, purge_tokens in rule_map.items():
#                 rule = ClassificationRule.objects.filter(rule_code=rule_code).first()
#                 if rule:
#                     existing = rule.get_patterns()
#                     new_patterns = []

#                     for pat in existing:
#                         pat_str = pat.strip().upper()

#                         # 1. Skip if exact match to a purge token
#                         if pat_str in purge_tokens:
#                             continue

#                         # 2. Check if pat contains any of the purge tokens as a sub-word
#                         words = pat_str.split()
#                         filtered_words = [w for w in words if w not in purge_tokens]

#                         # Only keep if meaningful non-purged tokens remain
#                         if filtered_words:
#                             cleaned_phrase = " ".join(filtered_words)
#                             if len(cleaned_phrase) >= 3:
#                                 new_patterns.append(cleaned_phrase)

#                     if len(new_patterns) != len(existing):
#                         rule.patterns = new_patterns
#                         rule.save()
#                         updated_rules += 1

#         return Response(
#             {
#                 "status": "success",
#                 "message": f"Purged patterns across {updated_rules} rules.",
#                 "updated_rules_count": updated_rules,
#             }
#         )

#     except Exception as e:
#         return Response({"status": "error", "message": str(e)}, status=500)


# def extract_candidate_patterns_from_narrations(narrations: List[str]) -> Dict[str, Any]:
#     """
#     Analyzes raw narration strings and extracts clean multi-token phrases
#     for user multi-selection while flagging disabled noise tokens.
#     """
#     all_blacklisted_tokens = RULE_SAFETY_BLACKLIST.union(NOISE_KEYWORD_BLACKLIST)

#     clean_candidates = set()
#     disabled_tokens = set()

#     for text in narrations:
#         if not text:
#             continue
#         # Normalize and remove numbers/special chars
#         clean_text = re.sub(r"[^A-Z\s]", " ", str(text).upper())
#         words = [w for w in clean_text.split() if len(w) > 1]

#         # 1. Classify individual words
#         for w in words:
#             if w in all_blacklisted_tokens or re.search(r"\d", w):
#                 disabled_tokens.add(w)
#             elif len(w) >= 3:
#                 clean_candidates.add(w)

#         # 2. Extract multi-word compound phrases (e.g. "PARKING BOOTH", "LULU HYPERMARKET")
#         for i in range(len(words) - 1):
#             w1, w2 = words[i], words[i + 1]
#             # Valid compound if at least one word isn't blacklisted noise
#             if w1 not in all_blacklisted_tokens or w2 not in all_blacklisted_tokens:
#                 compound = f"{w1} {w2}".strip()
#                 if len(compound) >= 5 and not re.search(r"\d", compound):
#                     clean_candidates.add(compound)

#     # Sort so multi-word compound phrases appear at top
#     sorted_clean = sorted(list(clean_candidates), key=lambda x: (-len(x.split()), x))

#     return {
#         "selectable_patterns": sorted_clean[:8],  # Top 8 clean suggestions
#         "disabled_patterns": sorted(list(disabled_tokens))[
#             :6
#         ],  # Noise tokens shown as disabled
#     }


@api_view(["POST"])
def remove_pattern_from_rule(request):
    """Deletes a specific token/pattern from a Classification Rule directly from the Node 99 Clearance Hub modal."""
    rule_code = request.data.get("rule_code")
    pattern_to_remove = request.data.get("pattern")

    print(
        "\n================================================================================"
    )
    print("🧹 [RULE PATTERN PURGE] SINGLE PATTERN REMOVAL REQUESTED")
    print(
        "================================================================================"
    )
    print(f"🎯 [TARGET] Rule Code: '{rule_code}' | Raw Pattern: '{pattern_to_remove}'")

    if not rule_code or not pattern_to_remove:
        print("❌ [REJECTED] Missing rule_code or pattern in payload.")
        print(
            "================================================================================\n"
        )
        return Response(
            {"error": "Missing rule_code or pattern"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    clean_token = str(pattern_to_remove).strip().lstrip("#").upper()
    print(f"⚙️ [CLEAN TOKEN] Prepared token for purge: '{clean_token}'")

    try:
        rule = ClassificationRule.objects.get(rule_code=rule_code)
        before_patterns = rule.get_patterns()

        # Call model method (handles both exact string matches AND sub-token stripping)
        removed = rule.remove_pattern(clean_token)

        if removed:
            after_patterns = rule.get_patterns()
            print(
                f"✅ [PURGED] Successfully stripped '{clean_token}' from rule {rule_code}"
            )
            print(f"📊 [BEFORE] Patterns: {before_patterns}")
            print(f"📊 [AFTER]  Patterns: {after_patterns}")
            print(
                "================================================================================\n"
            )

            return Response(
                {
                    "status": "success",
                    "message": f"Pattern '{clean_token}' purged from {rule_code}",
                    "remaining_patterns": after_patterns,
                },
                status=status.HTTP_200_OK,
            )

        print(
            f"ℹ️ [NOT FOUND] Pattern '{clean_token}' was not present in rule {rule_code}"
        )
        print(f"📊 [CURRENT PATTERNS] {before_patterns}")
        print(
            "================================================================================\n"
        )

        return Response(
            {
                "status": "info",
                "message": f"Pattern '{clean_token}' not found in {rule_code}",
            },
            status=status.HTTP_200_OK,
        )

    except ClassificationRule.DoesNotExist:
        print(f"❌ [NOT FOUND] ClassificationRule {rule_code} does not exist!")
        print(
            "================================================================================\n"
        )
        return Response(
            {"error": f"Rule {rule_code} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["POST"])
def bulk_remove_patterns_from_rules(request):
    """Bulk purges patterns or sub-tokens across multiple rules in a single transaction."""
    items = request.data.get("items", [])

    print(
        "\n================================================================================"
    )
    print("🧹 [BULK PATTERN PURGE] BULK PATTERN REMOVAL ENGINE STARTED")
    print(
        "================================================================================"
    )
    print(f"📦 [PAYLOAD] Total incoming items to evaluate: {len(items)}")

    if not items or not isinstance(items, list):
        print("❌ [REJECTED] Payload empty or not a valid list.")
        print(
            "================================================================================\n"
        )
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

            print(
                f"⚙️ [ENGINE MAPPED] Distinct target rules to update: {len(rule_map)}"
            )

            updated_rules = 0
            for rule_code, purge_tokens in rule_map.items():
                print(
                    f"\n🔍 [PROCESSING RULE] Code: {rule_code} | Purge Set: {purge_tokens}"
                )
                rule = ClassificationRule.objects.filter(rule_code=rule_code).first()

                if rule:
                    existing = rule.get_patterns()
                    new_patterns = []

                    print(f"   ├─ Existing Patterns: {existing}")

                    for pat in existing:
                        pat_str = pat.strip().upper()

                        # 1. Skip if exact match to a purge token
                        if pat_str in purge_tokens:
                            print(f"   ├─ 🗑️ Purging exact match pattern: '{pat_str}'")
                            continue

                        # 2. Check if pat contains any of the purge tokens as a sub-word
                        words = pat_str.split()
                        filtered_words = [w for w in words if w not in purge_tokens]

                        # Only keep if meaningful non-purged tokens remain
                        if filtered_words:
                            cleaned_phrase = " ".join(filtered_words)
                            if len(cleaned_phrase) >= 3:
                                new_patterns.append(cleaned_phrase)
                                if cleaned_phrase != pat_str:
                                    print(
                                        f"   ├─ ✂️ Sub-token trimmed: '{pat_str}' ➔ '{cleaned_phrase}'"
                                    )
                            else:
                                print(
                                    f"   ├─ ⚠️ Dropped phrase '{cleaned_phrase}' (<3 chars after trimming)"
                                )
                        else:
                            print(
                                f"   ├─ 🗑️ Compound phrase '{pat_str}' completely emptied by sub-tokens"
                            )

                    if len(new_patterns) != len(existing):
                        rule.patterns = new_patterns
                        rule.save()
                        updated_rules += 1
                        print(
                            f"   └─ ✅ Saved rule {rule_code}. New Patterns: {new_patterns}"
                        )
                    else:
                        print(f"   └─ ℹ️ No changes required for rule {rule_code}")
                else:
                    print(f"   └─ ⚠️ Rule '{rule_code}' not found in database!")

            print(
                "\n================================================================================"
            )
            print(
                f"🚀 [BULK PURGE COMPLETE] Successfully updated {updated_rules} rules."
            )
            print(
                "================================================================================\n"
            )

            return Response(
                {
                    "status": "success",
                    "message": f"Purged patterns across {updated_rules} rules.",
                    "updated_rules_count": updated_rules,
                }
            )

    except Exception as e:
        print(f"❌ [BULK PURGE EXCEPTION] Engine crashed: {str(e)}")
        print(
            "================================================================================\n"
        )
        return Response({"status": "error", "message": str(e)}, status=500)


@api_view(["GET"])
def sweep_preview_summary(request):
    """Lightning-Fast In-Memory Vector Sweep Engine for Node 99 Rules."""
    print(
        "\n================================================================================"
    )
    print("⚡ [SWEEP PREVIEW ENGINE] STARTING LIGHTNING NODE 99 SCAN")
    print(
        "================================================================================"
    )

    base_qs = JournalEntry.objects.filter(account_id=99, is_reclassified=False)

    unclassified_entries = list(
        base_qs.values(
            "id",
            "debit",
            "credit",
            "remarks__payee",
            "remarks__narration",
            "remarks__display_text",
            "evaluation_matrix_snapshot__resolved_subcategory",
        )
    )

    total_unclassified = len(unclassified_entries)
    suspense_count = sum(
        1
        for e in unclassified_entries
        if e.get("evaluation_matrix_snapshot__resolved_subcategory")
        == "Suspense Account"
    )

    print(
        f"📊 [ENGINE DEBUG] Total Staging Queue: {total_unclassified} "
        f"(Pending Suspense: {suspense_count})"
    )

    if total_unclassified == 0:
        print(
            "ℹ️ [ENGINE DEBUG] No unclassified entries found for Node 99." " Exiting."
        )
        print(
            "================================================================================\n"
        )
        return Response({"status": "success", "rule_matches": []})

    processed_pool = []
    for entry in unclassified_entries:
        debit_val = float(entry["debit"] or 0.0)
        credit_val = float(entry["credit"] or 0.0)

        payee = (entry.get("remarks__payee") or "").upper()
        narration = (entry.get("remarks__narration") or "").upper()
        display_text = (entry.get("remarks__display_text") or "").upper()

        search_haystack = f"{payee} {narration} {display_text}"

        processed_pool.append(
            {
                "id": entry["id"],
                "debit": debit_val,
                "credit": credit_val,
                "total_amount": debit_val + credit_val,
                "haystack": search_haystack,
            }
        )

    active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
        "-priority"
    )
    print(f"⚙️ [ENGINE DEBUG] Total Active Rules Loaded: {active_rules.count()}")

    rule_matches = []
    seen_patterns = set()
    claimed_entry_ids = set()

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
                if pattern_str in seen_patterns:
                    print(f"    ⏭️ Skipping '{pattern_str}': Already processed.")
                continue

            clean_search_str = pattern_str.lstrip("#").strip().upper()
            if len(clean_search_str) < 2:
                print(f"    ⚠️ Skipping '{pattern_str}': Too short (< 2 characters).")
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

                print(
                    f"    ✅ MATCH FOUND | Pattern: '{clean_search_str}' -> {matched_count} rows | Total: ₹{matched_amount:,.2f}"
                )

                rule_matches.append(
                    {
                        "pattern": pattern_str,
                        "display_tag": f"#{pattern_str}",
                        "token_breakdown": [clean_search_str],
                        "matched_rows": matched_count,
                        "total_amount": round(matched_amount, 2),
                        "suggested_category": rule.target_category,
                        "suggested_subcategory": rule.target_subcategory,
                        "rule_code": rule.rule_code,
                        "matched_entry_ids": new_claimed_ids,
                    }
                )

    print(
        "\n================================================================================"
    )
    print(
        f"🚀 [SWEEP PREVIEW COMPLETE] Matched Cards: {len(rule_matches)} | Total Claimed Rows: {len(claimed_entry_ids)}"
    )
    print(
        "================================================================================\n"
    )
    return Response({"status": "success", "rule_matches": rule_matches})


@api_view(["POST"])
@transaction.atomic
def execute_bulk_sweep(request):
    """Executes bulk reclassification matching Node 99 active rules cleanly."""
    selected_patterns = request.data.get("patterns", [])
    account_id = request.data.get("account_id", 99)

    print(
        "\n================================================================================"
    )
    print("⚡ [EXECUTE BULK SWEEP] STARTING DB COMMIT TRANSACTION")
    print(
        "================================================================================"
    )
    print(
        f"⚙️ [COMMIT CONFIG] Target Account ID: {account_id} | Explicit Pattern Filter Count: {len(selected_patterns)}"
    )

    base_qs = JournalEntry.objects.filter(account_id=account_id, is_reclassified=False)
    initial_pending_count = base_qs.count()
    print(
        f"📊 [DATABASE QUEUE] Total Pending Records on Account #{account_id}: {initial_pending_count}"
    )

    if initial_pending_count == 0:
        print("ℹ️ [COMMIT SKIPPED] No pending records found in database.")
        print(
            "================================================================================\n"
        )
        return Response({"status": "success", "total_reclassified": 0})

    active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
        "-priority"
    )
    print(
        f"⚙️ [RULES LOADED] Evaluating {active_rules.count()} active rules against DB queue..."
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

            if clean_selected and clean_search_str.upper() not in clean_selected:
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

                # 1. Update Node 99 legs
                node99_updated = JournalEntry.objects.bulk_update(
                    entries_to_update,
                    [
                        "evaluation_matrix_snapshot",
                        "is_reclassified",
                        "classification_status",
                    ],
                    batch_size=500,
                )

                # 2. Sync corresponding Bank Legs across row_identifiers
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
                total_updated += len(entries_to_update)

                print(
                    f"    💾 [DB WRITE] Rule '{rule.rule_code}' ({rule.target_category} > {rule.target_subcategory}) | "
                    f"Pattern: '{clean_search_str}' ➔ {len(entries_to_update)} Node 99 legs + {bank_legs_updated} Bank legs updated."
                )

    print(
        "\n================================================================================"
    )
    print(
        f"🚀 [BULK SWEEP COMPLETE] Total Reclassified Entries: {total_updated} | Remaining Queue: {initial_pending_count - total_updated}"
    )
    print(
        "================================================================================\n"
    )

    return Response({"status": "success", "total_reclassified": total_updated})


def extract_candidate_patterns_from_narrations(narrations: List[str]) -> Dict[str, Any]:
    """
    Analyzes raw narration strings and extracts clean multi-token phrases
    for user multi-selection while flagging disabled noise tokens.
    """
    all_blacklisted_tokens = RULE_SAFETY_BLACKLIST.union(NOISE_KEYWORD_BLACKLIST)

    clean_candidates = set()
    disabled_tokens = set()
    used_in_compounds = set()

    for text in narrations:
        if not text:
            continue
        # Normalize and remove numbers/special chars
        clean_text = re.sub(r"[^A-Z\s]", " ", str(text).upper())
        words = [w for w in clean_text.split() if len(w) > 1]

        # 1. Collect disabled/noise tokens
        for w in words:
            if w in all_blacklisted_tokens or re.search(r"\d", w):
                disabled_tokens.add(w)

        # 2. Extract multi-word compound phrases FIRST (2-grams & 3-grams)
        # Check 3-grams first (e.g. "MARGIN FREE HYPERMAR")
        for i in range(len(words) - 2):
            w1, w2, w3 = words[i], words[i + 1], words[i + 2]
            if not (
                w1 in all_blacklisted_tokens
                and w2 in all_blacklisted_tokens
                and w3 in all_blacklisted_tokens
            ):
                triplet = f"{w1} {w2} {w3}".strip()
                if len(triplet) >= 6 and not re.search(r"\d", triplet):
                    clean_candidates.add(triplet)
                    used_in_compounds.update([w1, w2, w3])

        # Check 2-grams next (e.g. "APAN DAS", "MARGIN FREE")
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if w1 not in all_blacklisted_tokens or w2 not in all_blacklisted_tokens:
                compound = f"{w1} {w2}".strip()
                if len(compound) >= 5 and not re.search(r"\d", compound):
                    clean_candidates.add(compound)
                    used_in_compounds.update([w1, w2])

        # 3. Add single words ONLY if they are NOT part of an extracted compound phrase
        for w in words:
            if (
                w not in all_blacklisted_tokens
                and not re.search(r"\d", w)
                and len(w) >= 3
                and w not in used_in_compounds
            ):
                clean_candidates.add(w)

    # Sort so multi-word compound phrases appear at the top
    sorted_clean = sorted(list(clean_candidates), key=lambda x: (-len(x.split()), x))

    return {
        "selectable_patterns": sorted_clean[:8],  # Top 8 clean suggestions
        "disabled_patterns": sorted(list(disabled_tokens))[
            :6
        ],  # Noise tokens shown as disabled
    }


# @api_view(["POST"])
# def get_candidate_patterns_view(request):
#     """
#     API View called when user opens the Reclassification Modal in the Workbench.
#     Returns candidate pattern chips for multi-selection.
#     """
#     transaction_ids = request.data.get("transaction_ids", [])

#     if not transaction_ids:
#         return JsonResponse({"selectable_patterns": [], "disabled_patterns": []})

#     # Fetch narrations from selected entries
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

#     result = extract_candidate_patterns_from_narrations(narrations)
#     return JsonResponse(result)


def extract_candidate_patterns_from_narrations(
    narrations: list[str], max_selectable: int = 15
) -> dict:
    """
    Extracts high-precision candidate patterns from raw narrations/payees.
    Generates multi-word n-grams (2-grams, 3-grams), full normalized phrases,
    and distinct brand tokens so the user has optimal multi-selection options.
    """
    if not narrations:
        return {"selectable_patterns": [], "disabled_patterns": []}

    candidate_counter = Counter()
    disabled_tokens = set()

    for raw_text in narrations:
        if not raw_text:
            continue

        raw_str = str(raw_text).upper().strip()

        # 1. Clean non-alphanumerics but preserve spaces
        clean_str = re.sub(r"[^A-Z0-9\s]", " ", raw_str)
        clean_str = re.sub(r"\s+", " ", clean_str).strip()

        if not clean_str:
            continue

        # Split into tokens
        tokens = clean_str.split()

        # Filter tokens into valid vs noise
        valid_tokens = []
        for token in tokens:
            if token in NOISE_KEYWORD_BLACKLIST or token in RULE_SAFETY_BLACKLIST:
                disabled_tokens.add(token)
                continue

            # Skip pure numbers or ultra-long ref hashes
            if token.isdigit() or len(token) > 25:
                continue

            valid_tokens.append(token)

        # A. Full Clean Compound Phrase (if 2 to 4 words)
        if 2 <= len(valid_tokens) <= 4:
            full_compound = " ".join(valid_tokens)
            if len(full_compound) >= 4:
                candidate_counter[full_compound] += 3  # Higher weight for exact phrase

        # B. 3-Gram Compounds
        for i in range(len(valid_tokens) - 2):
            gram_3 = f"{valid_tokens[i]} {valid_tokens[i+1]} {valid_tokens[i+2]}"
            candidate_counter[gram_3] += 2

        # C. 2-Gram Compounds
        for i in range(len(valid_tokens) - 1):
            gram_2 = f"{valid_tokens[i]} {valid_tokens[i+1]}"
            candidate_counter[gram_2] += 2

        # D. Single Brand Tokens (>= 4 chars)
        for token in valid_tokens:
            if len(token) >= 4:
                candidate_counter[token] += 1

    # Sort candidates by frequency count DESC, then length DESC (longer compound phrases preferred)
    sorted_candidates = sorted(
        candidate_counter.keys(),
        key=lambda p: (-candidate_counter[p], -len(p.split()), -len(p)),
    )

    # Return expanded top options (up to 15)
    selectable = sorted_candidates[:max_selectable]
    disabled = sorted(list(disabled_tokens))[:10]

    return {
        "selectable_patterns": selectable,
        "disabled_patterns": disabled,
    }


@api_view(["POST"])
def get_candidate_patterns_view(request):
    """
    API View called when user opens the Reclassification Modal in the Workbench.
    Returns up to 15 candidate pattern chips for multi-selection.
    """
    transaction_ids = request.data.get("transaction_ids", [])

    if not transaction_ids:
        return JsonResponse({"selectable_patterns": [], "disabled_patterns": []})

    # Fetch narrations from selected entries
    entries = JournalEntry.objects.filter(id__in=transaction_ids)
    if not entries.exists():
        entries = JournalEntry.objects.filter(row_identifier__in=transaction_ids)

    narrations = []
    for entry in entries:
        remarks_dict = entry.remarks if isinstance(entry.remarks, dict) else {}
        narration = remarks_dict.get("narration") or str(entry.remarks or "")
        payee = remarks_dict.get("payee") or ""

        if payee:
            narrations.append(payee)
        if narration:
            narrations.append(narration)

    # Expanded candidate options set to 15
    result = extract_candidate_patterns_from_narrations(narrations, max_selectable=15)
    return JsonResponse(result)


@api_view(["POST"])
def suggest_rule_for_cluster(request):
    """
    Checks if an active ClassificationRule already exists for a cluster's clean payee pattern.
    Guards against substring pollution in JSON pattern arrays.
    """
    raw_pattern = request.data.get("pattern", "")
    entry_type = request.data.get("entry_type", "Debit")

    clean_p = extract_clean_payee_pattern(raw_pattern)
    if not clean_p or len(clean_p) < 3:
        return Response({"has_suggestion": False})

    clean_token = str(clean_p).strip().upper()

    # Fetch candidate rules matching the entry type
    candidate_rules = ClassificationRule.objects.filter(
        is_active=True, rule_type__iexact=entry_type
    )

    matched_rule = None

    # Perform strict exact token or exact pattern matching against rule pattern arrays
    for rule in candidate_rules:
        patterns = rule.get_patterns()  # Returns list of uppercase strings

        # Check 1: Exact match in list (e.g. "ZOMATO" == "ZOMATO")
        # Check 2: Compound phrase match (e.g. "POTHY SHOPPING" in narration)
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
