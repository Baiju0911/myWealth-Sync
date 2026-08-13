from django.urls import path
from ..backendViewModel.dashViews import (
    asset_mapped_transactions_view,
    dashboard_summary_view,
)

urlpatterns = [
    path("summary/", dashboard_summary_view, name="dashboard-summary"),
    path(
        "api/subledgers/assets/<int:asset_id>/mapped-transactions/",
        asset_mapped_transactions_view,
        name="asset-mapped-transactions",
    ),
    path(
        "api/subledgers/assets/<int:asset_id>/mapped-transactions/",
        asset_mapped_transactions_view,
        name="asset-mapped-transactions",
    ),
]
