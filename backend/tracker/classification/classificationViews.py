# tracker/classification/classficationViews.py

from rest_framework import status, views
from rest_framework.decorators import api_view
from rest_framework.response import Response
import re
import json

from urllib.parse import parse_qs, unquote
from django.db.models import Q, Count, Sum

from tracker.models import JournalEntry, TaxonomyTree
from tracker.classification.engine import (
    get_suspense_clusters,
    reclassify_and_learn,
    extract_meaningful_tokens,
    match_multi_tokens,
    GENERIC_IGNORE_PATTERNS,
    get_clean_patterns,
    generate_strict_multitoken_pattern,
)

from tracker.classification.serializers import (
    ClassificationJournalEntrySerializer,
    ReclassifyRequestSerializer,
)
from rest_framework.pagination import PageNumberPagination
from tracker.classification.utils.upiparser import clean_payee_name

from tracker.classification.engine import extract_clean_payee_pattern
from tracker.models import ClassificationRule


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


@api_view(["POST"])
def suggest_rule_for_cluster(request):
    raw_pattern = request.data.get("pattern", "")
    entry_type = request.data.get("entry_type", "Debit")

    # 1. Clean the pattern (remove underscores and hashtags)
    clean_p = extract_clean_payee_pattern(raw_pattern)
    base_word = re.sub(
        r"[^A-Za-z0-9]", "", clean_p
    )  # "FA_MILY" -> "FAMILY", "#FAMILY" -> "FAMILY"

    if not base_word or len(base_word) < 3:
        return Response({"has_suggestion": False})

    # 2. Search for any active rule containing key parts of the word
    # Checks if "FAMILY" matches "FA_MILY" or vice versa
    existing_rules = ClassificationRule.objects.filter(
        is_active=True, rule_type__iexact=entry_type
    )

    matched_rule = None
    for rule in existing_rules:
        # Check JSON pattern list stored in rule.patterns
        for rule_p in rule.patterns or []:
            clean_rule_p = re.sub(r"[^A-Za-z0-9]", "", str(rule_p))
            if (
                base_word in clean_rule_p
                or clean_rule_p in base_word
                or base_word[:4] == clean_rule_p[:4]
            ):
                matched_rule = rule
                break
        if matched_rule:
            break

    if matched_rule:
        return Response(
            {
                "has_suggestion": True,
                "rule_code": matched_rule.rule_code,
                "suggested_category": matched_rule.target_category,
                "suggested_subcategory": matched_rule.target_subcategory,
                "matched_pattern": raw_pattern,
            }
        )

    return Response({"has_suggestion": False})


# @api_view(["GET"])
# def sweep_preview_summary(request):
#     """
#     Scans Node 99 entries and groups them by active matching learned rules
#     using strict Multi-Token validation from engine.
#     """
#     queryset = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
#     active_rules = ClassificationRule.objects.filter(is_active=True)

#     rule_matches = []
#     seen_patterns = set()

#     # Pre-fetch for faster in-memory token evaluation
#     entries_pool = list(queryset.values("id", "remarks", "debit", "credit"))

#     for rule in active_rules:
#         # Assuming get_clean_patterns is available or rule.patterns is parsed
#         raw_patterns = (
#             rule.patterns if isinstance(rule.patterns, list) else [rule.patterns]
#         )

#         for pattern_str in raw_patterns:
#             if not pattern_str or pattern_str in seen_patterns:
#                 continue

#             pattern_tokens = extract_meaningful_tokens(pattern_str)

#             # 🛡️ GUARDRAIL: Require at least 2 distinct meaningful tokens in pattern
#             if len(pattern_tokens) < 2:
#                 continue

#             matched_entry_ids = []
#             total_amt = 0.0

#             for entry in entries_pool:
#                 remarks_str = str(entry.get("remarks", ""))

#                 # Enforce multi-token match (at least 2 tokens)
#                 if match_multi_tokens(remarks_str, pattern_str, min_required_tokens=2):
#                     matched_entry_ids.append(entry["id"])
#                     deb = float(entry["debit"] or 0.0)
#                     cred = float(entry["credit"] or 0.0)
#                     total_amt += deb + cred

#             count = len(matched_entry_ids)

#             if count > 0:
#                 rule_matches.append(
#                     {
#                         "pattern": pattern_str,
#                         "token_breakdown": pattern_tokens,
#                         "matched_rows": count,
#                         "total_amount": float(total_amt),
#                         "suggested_category": rule.target_category,
#                         "suggested_subcategory": rule.target_subcategory,
#                         "rule_code": rule.rule_code,
#                     }
#                 )
#                 seen_patterns.add(pattern_str)

#     return Response({"status": "success", "rule_matches": rule_matches})


@api_view(["GET"])
def sweep_preview_summary(request):
    """
    Scans Node 99 entries and groups them by active matching learned rules
    using strict Multi-Token validation and native JSON pattern retrieval.
    """
    queryset = JournalEntry.objects.filter(account_id=99, is_reclassified=False)
    active_rules = ClassificationRule.objects.filter(is_active=True).order_by(
        "-priority"
    )

    rule_matches = []
    seen_patterns = set()

    # Pre-fetch for fast in-memory evaluation
    entries_pool = list(queryset.values("id", "remarks", "debit", "credit"))

    for rule in active_rules:
        # Cleanly retrieve array of pattern strings from JSONField
        patterns_list = (
            rule.get_patterns()
            if hasattr(rule, "get_patterns")
            else get_clean_patterns(rule)
        )

        for pattern_str in patterns_list:
            if not pattern_str or pattern_str in seen_patterns:
                continue

            pattern_tokens = extract_meaningful_tokens(pattern_str)

            # 🛡️ GUARDRAIL: Allow 1-token matches ONLY if token is long/significant (e.g. >= 6 chars like 'ZOMATO')
            # Otherwise require at least 2 distinct tokens.
            if len(pattern_tokens) < 1:
                continue
            if len(pattern_tokens) == 1 and len(pattern_tokens[0]) < 5:
                continue

            matched_entry_ids = []
            total_amt = 0.0

            for entry in entries_pool:
                # Extract narration or display text safely from remarks dict/string
                remarks_raw = entry.get("remarks")
                if isinstance(remarks_raw, dict):
                    remarks_str = (
                        remarks_raw.get("narration")
                        or remarks_raw.get("display_text")
                        or str(remarks_raw)
                    )
                else:
                    remarks_str = str(remarks_raw or "")

                # Enforce multi-token match
                if match_multi_tokens(remarks_str, pattern_str):
                    matched_entry_ids.append(entry["id"])
                    deb = float(entry["debit"] or 0.0)
                    cred = float(entry["credit"] or 0.0)
                    total_amt += deb + cred

            count = len(matched_entry_ids)

            if count > 0:
                rule_matches.append(
                    {
                        "pattern": pattern_str,
                        "display_tag": f"#{pattern_str}",  # UI pill header format
                        "token_breakdown": pattern_tokens,
                        "matched_rows": count,
                        "total_amount": float(total_amt),
                        "suggested_category": rule.target_category,
                        "suggested_subcategory": rule.target_subcategory,
                        "rule_code": rule.rule_code,
                    }
                )
                seen_patterns.add(pattern_str)

    return Response({"status": "success", "rule_matches": rule_matches})


@api_view(["POST"])
def execute_bulk_sweep(request):
    """Executes bulk reclassification using engine multi-token matching."""
    selected_patterns = request.data.get("patterns", [])

    if not selected_patterns:
        return Response(
            {"status": "error", "message": "No patterns selected"}, status=400
        )

    total_updated = 0
    unclassified_entries = JournalEntry.objects.filter(
        account_id=99, is_reclassified=False
    )

    for pattern in selected_patterns:
        pattern_tokens = extract_meaningful_tokens(pattern)
        if len(pattern_tokens) < 2 or pattern.upper() in GENERIC_IGNORE_PATTERNS:
            continue

        rule = ClassificationRule.objects.filter(
            is_active=True, patterns__icontains=pattern
        ).first()

        if rule:
            # Re-evaluate entries against multi-token engine
            for entry in unclassified_entries:
                remarks_str = str(entry.remarks or "")

                if match_multi_tokens(remarks_str, pattern, min_required_tokens=2):
                    snapshot = entry.evaluation_matrix_snapshot or {}
                    if isinstance(snapshot, str):
                        import json

                        try:
                            snapshot = json.loads(snapshot)
                        except json.JSONDecodeError:
                            snapshot = {}

                    snapshot["resolved_category"] = rule.target_category
                    snapshot["resolved_subcategory"] = rule.target_subcategory
                    snapshot["applied_rule_code"] = rule.rule_code

                    entry.evaluation_matrix_snapshot = snapshot
                    entry.is_reclassified = True
                    entry.classification_status = "SWEEP_CLEARED"
                    entry.save()

                    total_updated += 1

    return Response({"status": "success", "total_reclassified": total_updated})


# @api_view(["POST"])
# def suggest_rule_for_cluster(request):
#     """Checks if an active ClassificationRule already exists for a cluster's clean payee pattern."""
#     raw_pattern = request.data.get("pattern", "")
#     entry_type = request.data.get("entry_type", "Debit")

#     clean_p = extract_clean_payee_pattern(raw_pattern)
#     if not clean_p or len(clean_p) < 3:
#         return Response({"has_suggestion": False})

#     # Search for active rules matching the pattern & direction vector
#     existing_rule = ClassificationRule.objects.filter(
#         is_active=True, rule_type__iexact=entry_type, patterns__icontains=clean_p
#     ).first()

#     if existing_rule:
#         return Response(
#             {
#                 "has_suggestion": True,
#                 "rule_code": existing_rule.rule_code,
#                 "suggested_category": existing_rule.target_category,
#                 "suggested_subcategory": existing_rule.target_subcategory,
#                 "matched_pattern": clean_p,
#             }
#         )

#     return Response({"has_suggestion": False})
