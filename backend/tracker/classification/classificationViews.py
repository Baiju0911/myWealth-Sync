# tracker/views.py (or tracker/classification/views.py)

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import TaxonomyTree

from tracker.classification.engine import get_suspense_clusters, reclassify_and_learn

# @api_view(["GET"])
# def get_suspense_workbench_data1(request):
#     # """
#     # Returns auto-clustered patterns for Suspense Account transactions.
#     # """
#     # try:
#     #     clusters = get_suspense_clusters()
#     #     return Response(
#     #         {"status": "success", "total_clusters": len(clusters), "clusters": clusters}
#     #     )
#     # except Exception as e:
#     #     return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#     # Pull subcategory from query string: ?subcategory=Shopping (defaulting to 'Suspense Account')
#     target_sub = request.GET.get("subcategory", "Suspense Account")
#     clusters = get_suspense_clusters(target_subcategory=target_sub)

#     return Response(
#         {
#             "status": "success",
#             "target_subcategory": target_sub,
#             "total_clusters": len(clusters),
#             "clusters": clusters,
#         }
#     )


@api_view(["GET"])
def get_suspense_workbench_data(request):
    """
    Returns auto-clustered patterns for Workbench review with direction flags and inflows/outflows.
    """
    target_sub = request.GET.get("subcategory", "Suspense Account")

    account_id_param = request.GET.get("account_id")
    account_id = (
        int(account_id_param)
        if account_id_param and account_id_param.isdigit()
        else None
    )
    clusters = get_suspense_clusters(
        target_subcategory=target_sub, account_id=account_id
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


@api_view(["GET"])
def get_taxonomy_tree_view(request):
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
def apply_reclassification_and_learn_older(request):
    """
    Executes bulk reclassification and updates/creates classification rules.
    """
    transaction_ids = request.data.get("transaction_ids", [])
    target_category = request.data.get("target_category")
    target_subcategory = request.data.get("target_subcategory")
    pattern = request.data.get("pattern")
    save_rule = request.data.get("save_rule", True)
    print(f"🔍 RECLASSIFY REQUEST: pattern='{pattern}', save_rule={save_rule}")

    if not transaction_ids or not target_category or not target_subcategory:
        return Response(
            {
                "error": "transaction_ids, target_category, and target_subcategory are required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = reclassify_and_learn(
        transaction_ids=transaction_ids,
        target_category=target_category,
        target_subcategory=target_subcategory,
        pattern=pattern,
        save_rule=save_rule,
    )

    return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
def apply_reclassification_and_learn(request):
    transaction_ids = request.data.get("transaction_ids", [])
    target_category = request.data.get("target_category")
    target_subcategory = request.data.get("target_subcategory")

    # 🟢 Accept list of patterns or single string fallback
    patterns = request.data.get("patterns", [])
    single_pattern = request.data.get("pattern")

    if not patterns and single_pattern:
        patterns = [single_pattern]

    save_rule = request.data.get("save_rule", True)

    result = reclassify_and_learn(
        transaction_ids=transaction_ids,
        target_category=target_category,
        target_subcategory=target_subcategory,
        patterns=patterns,
        save_rule=save_rule,
    )

    return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
def add_taxonomy_node(request):
    category = request.data.get("category", "").strip()
    subcategory = request.data.get("subcategory", "").strip()

    if not category or not subcategory:
        return Response(
            {"status": "error", "message": "Category and Subcategory are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if this exact pair already exists
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

    # Create new Taxonomy Tree entry
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
