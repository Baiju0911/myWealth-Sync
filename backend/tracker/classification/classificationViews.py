# tracker/views.py (or tracker/classification/views.py)

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from tracker.classification.engine import get_suspense_clusters, reclassify_and_learn


@api_view(["GET"])
def get_suspense_workbench_data(request):
    # """
    # Returns auto-clustered patterns for Suspense Account transactions.
    # """
    # try:
    #     clusters = get_suspense_clusters()
    #     return Response(
    #         {"status": "success", "total_clusters": len(clusters), "clusters": clusters}
    #     )
    # except Exception as e:
    #     return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    # Pull subcategory from query string: ?subcategory=Shopping (defaulting to 'Suspense Account')
    target_sub = request.GET.get("subcategory", "Suspense Account")
    clusters = get_suspense_clusters(target_subcategory=target_sub)

    return Response(
        {
            "status": "success",
            "target_subcategory": target_sub,
            "total_clusters": len(clusters),
            "clusters": clusters,
        }
    )


@api_view(["POST"])
def apply_reclassification_and_learn(request):
    """
    Executes bulk reclassification and updates/creates classification rules.
    """
    transaction_ids = request.data.get("transaction_ids", [])
    target_category = request.data.get("target_category")
    target_subcategory = request.data.get("target_subcategory")
    pattern = request.data.get("pattern")
    save_rule = request.data.get("save_rule", True)

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
