from django.urls import path
from tracker.classification.classificationViews import (
    CategoryVendorDrilldownView,
    ClassificationPendingListView,
    ReclassifyEntryView,
    UpdateJournalEntryNoteView,
    execute_bulk_sweep,
    suggest_rule_for_cluster,
    sweep_preview_summary,
)

urlpatterns = [
    # GET list of pending Node 99 items with structured JSON remarks
    path(
        "pending/",
        ClassificationPendingListView.as_view(),
        name="classification-pending",
    ),
    # POST endpoint for reclassifying from the frontend modal
    path(
        "reclassify/",
        ReclassifyEntryView.as_view(),
        name="classification-reclassify",
    ),
    path(
        "entry-note/",
        UpdateJournalEntryNoteView.as_view(),
        name="update-entry-note",
    ),
    path(
        "vendor-drilldown/",
        CategoryVendorDrilldownView.as_view(),
        name="vendor-drilldown",
    ),
    # 🟢 Cleaned endpoints (removed duplicate "api/" prefix)
    path(
        "staging/sweep-preview/",
        sweep_preview_summary,
        name="sweep_preview_summary",
    ),
    path(
        "staging/execute-bulk-sweep/",
        execute_bulk_sweep,
        name="execute_bulk_sweep",
    ),
    path(
        "suggest_rule_for_cluster/",
        suggest_rule_for_cluster,
        name="suggest_rule_for_cluster",
    ),
]
