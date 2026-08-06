from django.urls import path
from tracker.classification.classificationViews import (
    CategoryVendorDrilldownView,
    ClassificationPendingListView,
    ReclassifyEntryView,
    UpdateJournalEntryNoteView,
    execute_bulk_sweep,
    suggest_rule_for_cluster,
    sweep_preview_summary,
    remove_pattern_from_rule,
    bulk_remove_patterns_from_rules,
    get_candidate_patterns_view,
    validate_pattern_anchor,
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
    path(
        "staging/remove_pattern_from_rule/",
        remove_pattern_from_rule,
        name="remove_pattern_from_rule",
    ),
    path(
        "staging/bulk_remove_patterns_from_rules/",
        bulk_remove_patterns_from_rules,
        name="bulk_remove_patterns",
    ),
    path(
        "staging/get_candidate_patterns/",
        get_candidate_patterns_view,
        name="get_candidate_patterns",
    ),
    path(
        "staging/validate_pattern/",
        validate_pattern_anchor,
        name="validate_pattern",
    ),
]
