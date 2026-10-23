from django.urls import path

from tracker.classification import classificationRuleViews
from tracker.classification.classificationViews import (
    # Class-based views
    CategoryVendorDrilldownView,
    ClassificationPendingListView,
    ReclassifyEntryView,
    UpdateJournalEntryNoteView,
    # Workbench core
    get_suspense_workbench_data,
    get_cluster_line_items,
    apply_reclassification_and_learn,
    get_taxonomy_tree_view,
    add_taxonomy_node,
    # Rule evaluation & sweep
    execute_bulk_sweep,
    sweep_preview_summary,
    suggest_rule_for_cluster,
    remove_pattern_from_rule,
    bulk_remove_patterns_from_rules,
    get_candidate_patterns_view,
    validate_pattern_anchor,
    preview_pattern_matches,
)

app_name = "classification"

urlpatterns = [
    # -------------------------------------------------------------------------
    # 1. Suspense Workbench Core
    # -------------------------------------------------------------------------
    path("workbench/data/", get_suspense_workbench_data, name="workbench-data"),
    path(
        "workbench/cluster-items/",
        get_cluster_line_items,
        name="workbench-cluster-items",
    ),
    path(
        "workbench/reclassify-and-learn/",
        apply_reclassification_and_learn,
        name="workbench-reclassify-learn",
    ),
    path(
        "workbench/taxonomy-tree/",
        get_taxonomy_tree_view,
        name="workbench-taxonomy-tree",
    ),
    path(
        "workbench/taxonomy-node/add/", add_taxonomy_node, name="workbench-taxonomy-add"
    ),
    # -------------------------------------------------------------------------
    # 2. Journal Entry Actions & Line Item Audit
    # -------------------------------------------------------------------------
    path(
        "pending/",
        ClassificationPendingListView.as_view(),
        name="classification-pending",
    ),
    path(
        "reclassify/", ReclassifyEntryView.as_view(), name="classification-reclassify"
    ),
    path("entry-note/", UpdateJournalEntryNoteView.as_view(), name="update-entry-note"),
    path(
        "vendor-drilldown/",
        CategoryVendorDrilldownView.as_view(),
        name="vendor-drilldown",
    ),
    # -------------------------------------------------------------------------
    # 3. Pattern Matching & Rule Suggestions
    # -------------------------------------------------------------------------
    path(
        "patterns/candidates/", get_candidate_patterns_view, name="patterns-candidates"
    ),
    path("patterns/validate/", validate_pattern_anchor, name="patterns-validate"),
    path(
        "patterns/preview-matches/",
        preview_pattern_matches,
        name="patterns-preview-matches",
    ),
    path(
        "patterns/suggest-rule/", suggest_rule_for_cluster, name="patterns-suggest-rule"
    ),
    path(
        "patterns/remove-from-rule/",
        remove_pattern_from_rule,
        name="patterns-remove-from-rule",
    ),
    path(
        "patterns/bulk-remove/",
        bulk_remove_patterns_from_rules,
        name="patterns-bulk-remove",
    ),
    # -------------------------------------------------------------------------
    # 4. Sweep Engine (Node 99 Automation)
    # -------------------------------------------------------------------------
    path(
        "staging/validate_pattern/",
        validate_pattern_anchor,
        name="compat-staging-validate-pattern",
    ),
    path("sweep/preview/", sweep_preview_summary, name="sweep-preview"),
    path(
        "staging/sweep-preview/", sweep_preview_summary, name="staging-sweep-preview"
    ),  # Added compatibility alias
    path("sweep/execute/", execute_bulk_sweep, name="sweep-execute"),
    path(
        "staging/execute-bulk-sweep/",
        execute_bulk_sweep,
        name="staging-execute-bulk-sweep",
    ),  # Added compatibility alias
    # -------------------------------------------------------------------------
    # 5. Classification Rules CRUD
    # -------------------------------------------------------------------------
    path(
        "rules/", classificationRuleViews.list_classification_rules, name="list-rules"
    ),
    path(
        "rules/create/",
        classificationRuleViews.create_classification_rule,
        name="create-rule",
    ),
    path(
        "rules/<str:rule_code>/",
        classificationRuleViews.update_classification_rule,
        name="update-rule",
    ),
    path(
        "rules/<str:rule_code>/toggle/",
        classificationRuleViews.toggle_rule_active_status,
        name="toggle-rule",
    ),
    path(
        "rules/<str:rule_code>/delete/",
        classificationRuleViews.delete_classification_rule,
        name="delete-rule",
    ),
    # -------------------------------------------------------------------------
    # Compatibility Aliases (Retain only active frontend callers)
    # -------------------------------------------------------------------------
    path(
        "staging/get_candidate_patterns/",
        get_candidate_patterns_view,
        name="compat-staging-get-candidate-patterns",
    ),
    path(
        "suggest_rule_for_cluster/",
        suggest_rule_for_cluster,
        name="compat-suggest-rule-for-cluster",
    ),
    path(
        "get_cluster_line_items/",
        get_cluster_line_items,
        name="compat-get-cluster-line-items",
    ),
    path("get_taxonomy_tree/", get_taxonomy_tree_view, name="compat-get-taxonomy-tree"),
]


# from django.urls import path

# from tracker.classification import classificationRuleViews
# from tracker.classification.classificationViews import (
#     # Class-based views
#     CategoryVendorDrilldownView,
#     ClassificationPendingListView,
#     ReclassifyEntryView,
#     UpdateJournalEntryNoteView,
#     # Workbench core endpoints
#     get_suspense_workbench_data,
#     get_cluster_line_items,
#     apply_reclassification_and_learn,
#     get_taxonomy_tree_view,
#     add_taxonomy_node,
#     # Rule evaluation & sweep endpoints
#     execute_bulk_sweep,
#     sweep_preview_summary,
#     suggest_rule_for_cluster,
#     remove_pattern_from_rule,
#     bulk_remove_patterns_from_rules,
#     get_candidate_patterns_view,
#     validate_pattern_anchor,
#     preview_pattern_matches,
# )

# app_name = "classification"

# urlpatterns = [
#     # -------------------------------------------------------------------------
#     # 1. Suspense Workbench Core (High-Performance Engine)
#     # -------------------------------------------------------------------------
#     path(
#         "workbench/data/",
#         get_suspense_workbench_data,
#         name="workbench-data",
#     ),
#     path(
#         "workbench/cluster-items/",
#         get_cluster_line_items,
#         name="workbench-cluster-items",
#     ),
#     path(
#         "workbench/reclassify-and-learn/",
#         apply_reclassification_and_learn,
#         name="workbench-reclassify-learn",
#     ),
#     path(
#         "workbench/taxonomy-tree/",
#         get_taxonomy_tree_view,
#         name="workbench-taxonomy-tree",
#     ),
#     path(
#         "workbench/taxonomy-node/add/",
#         add_taxonomy_node,
#         name="workbench-taxonomy-add",
#     ),
#     # Legacy aliases
#     path(
#         "get_suspense_workbench_data/",
#         get_suspense_workbench_data,
#         name="legacy-get-suspense-workbench-data",
#     ),
#     path(
#         "get_cluster_line_items/",
#         get_cluster_line_items,
#         name="legacy-get-cluster-line-items",
#     ),
#     path(
#         "get_taxonomy_tree/",
#         get_taxonomy_tree_view,
#         name="legacy-get-taxonomy-tree",
#     ),
#     path(
#         "apply_reclassification_and_learn/",
#         apply_reclassification_and_learn,
#         name="legacy-apply-reclassification-and-learn",
#     ),
#     # -------------------------------------------------------------------------
#     # 2. Journal Entry Actions & Line Item Audit
#     # -------------------------------------------------------------------------
#     path(
#         "pending/",
#         ClassificationPendingListView.as_view(),
#         name="classification-pending",
#     ),
#     path(
#         "reclassify/",
#         ReclassifyEntryView.as_view(),
#         name="classification-reclassify",
#     ),
#     path(
#         "entry-note/",
#         UpdateJournalEntryNoteView.as_view(),
#         name="update-entry-note",
#     ),
#     path(
#         "vendor-drilldown/",
#         CategoryVendorDrilldownView.as_view(),
#         name="vendor-drilldown",
#     ),
#     # -------------------------------------------------------------------------
#     # 3. Pattern Matching & Rule Learning Assistants
#     # -------------------------------------------------------------------------
#     # Candidate Patterns
#     path(
#         "patterns/candidates/",
#         get_candidate_patterns_view,
#         name="get-candidate-patterns",
#     ),
#     path(
#         "staging/get_candidate_patterns/",
#         get_candidate_patterns_view,
#         name="staging-get-candidate-patterns-underscore",
#     ),
#     path(
#         "staging/get-candidate-patterns/",
#         get_candidate_patterns_view,
#         name="staging-get-candidate-patterns-hyphen",
#     ),
#     # Pattern Validation
#     path(
#         "patterns/validate/",
#         validate_pattern_anchor,
#         name="patterns-validate",
#     ),
#     path(
#         "staging/validate/",
#         validate_pattern_anchor,
#         name="staging-validate",
#     ),
#     path(
#         "staging/validate_pattern/",
#         validate_pattern_anchor,
#         name="staging-validate-pattern-underscore",
#     ),
#     path(
#         "staging/validate-pattern/",
#         validate_pattern_anchor,
#         name="staging-validate-pattern-hyphen",
#     ),
#     # Matches Preview & Suggestions
#     path(
#         "patterns/preview-matches/",
#         preview_pattern_matches,
#         name="patterns-preview-matches",
#     ),
#     path(
#         "staging/preview-matches/",
#         preview_pattern_matches,
#         name="staging-preview-matches-hyphen",
#     ),
#     path(
#         "staging/preview_matches/",
#         preview_pattern_matches,
#         name="staging-preview-matches-underscore",
#     ),
#     path(
#         "patterns/suggest-rule/",
#         suggest_rule_for_cluster,
#         name="patterns-suggest-rule",
#     ),
#     path(
#         "staging/suggest-rule/",
#         suggest_rule_for_cluster,
#         name="staging-suggest-rule-hyphen",
#     ),
#     path(
#         "staging/suggest_rule/",
#         suggest_rule_for_cluster,
#         name="staging-suggest-rule-underscore",
#     ),
#     path(
#         "suggest_rule_for_cluster/",
#         suggest_rule_for_cluster,
#         name="suggest-rule-for-cluster",
#     ),
#     # Pattern Deletion & Purging (Single)
#     path(
#         "patterns/remove-from-rule/",
#         remove_pattern_from_rule,
#         name="patterns-remove-from-rule",
#     ),
#     path(
#         "staging/remove-from-rule/",
#         remove_pattern_from_rule,
#         name="staging-remove-from-rule-hyphen",
#     ),
#     path(
#         "staging/remove_pattern_from_rule/",
#         remove_pattern_from_rule,
#         name="staging-remove-pattern-from-rule-underscore",
#     ),
#     # Pattern Deletion & Purging (Bulk)
#     path(
#         "patterns/bulk-remove/",
#         bulk_remove_patterns_from_rules,
#         name="patterns-bulk-remove",
#     ),
#     path(
#         "staging/bulk-remove/",
#         bulk_remove_patterns_from_rules,
#         name="staging-bulk-remove-hyphen",
#     ),
#     path(
#         "staging/bulk_remove_patterns/",
#         bulk_remove_patterns_from_rules,
#         name="staging-bulk-remove-patterns-underscore",
#     ),
#     path(
#         "staging/bulk_remove_patterns_from_rules/",
#         bulk_remove_patterns_from_rules,
#         name="staging-bulk-remove-patterns-from-rules-underscore",
#     ),
#     path(
#         "staging/purge_selected/",
#         bulk_remove_patterns_from_rules,
#         name="staging-purge-selected-underscore",
#     ),
#     # -------------------------------------------------------------------------
#     # 4. Sweep Engine (Node 99 Automation)
#     # -------------------------------------------------------------------------
#     path(
#         "sweep/preview/",
#         sweep_preview_summary,
#         name="sweep-preview-summary",
#     ),
#     path(
#         "sweep/execute/",
#         execute_bulk_sweep,
#         name="execute-bulk-sweep",
#     ),
#     path(
#         "staging/sweep-preview/",
#         sweep_preview_summary,
#         name="staging-sweep-preview-hyphen",
#     ),
#     path(
#         "staging/sweep_preview/",
#         sweep_preview_summary,
#         name="staging-sweep-preview-underscore",
#     ),
#     path(
#         "staging/execute-bulk-sweep/",
#         execute_bulk_sweep,
#         name="staging-execute-bulk-sweep-hyphen",
#     ),
#     path(
#         "staging/execute_bulk_sweep/",
#         execute_bulk_sweep,
#         name="staging-execute-bulk-sweep-underscore",
#     ),
#     # -------------------------------------------------------------------------
#     # 5. Classification Rules CRUD
#     # -------------------------------------------------------------------------
#     path(
#         "rules/",
#         classificationRuleViews.list_classification_rules,
#         name="list-rules",
#     ),
#     path(
#         "rules/create/",
#         classificationRuleViews.create_classification_rule,
#         name="create-rule",
#     ),
#     path(
#         "rules/<str:rule_code>/",
#         classificationRuleViews.update_classification_rule,
#         name="update-rule",
#     ),
#     path(
#         "rules/<str:rule_code>/toggle/",
#         classificationRuleViews.toggle_rule_active_status,
#         name="toggle-rule",
#     ),
#     path(
#         "rules/<str:rule_code>/delete/",
#         classificationRuleViews.delete_classification_rule,
#         name="delete-rule",
#     ),
# ]
