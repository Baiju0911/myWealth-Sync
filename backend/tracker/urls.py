# backend/tracker/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

# ViewSets
from tracker.backendViewModel.views import (
    BankViewSet,
    BankCredentialViewSet,
    SystemConfigView,
    AccountListCreateView,
    AccountDetailView,
    TransactionListCreateView,
    BulkTransactionSyncView,
    StatementStagingCommitView,
    StatementPreviewAPIView,
    StatementTemplateSaveAPIView,
    StatementIngestRouterDynamicView,
    AvailableTemplatesListView,
    StatementBulkIngestPipelineView,
)
from tracker.backendViewModel.ledgerCategorizationView import (
    MasterFinancialCategoryViewSet,
    AccountingRuleViewSet,
    AutoCategorizeStagingQueueView,
    CommitStagingQueue,
)
from tracker.backendViewModel.workbench_groups import (
    WorkbenchGroupHierarchyViewSet,
    MasterNarrationTagRuleViewSet,
)
from tracker.backendViewModel.inbox_view import (
    EnrichedReconciliationAuditView,
    LiveStreamPayloadsView,
    LiveStreamCommitEnrichmentView,
)
from tracker.classification import classificationViews

# ==========================================
# 🚀 Unified DRF Router for all ViewSets
# ==========================================
router = DefaultRouter()
router.register(r"banks", BankViewSet, basename="banks")
router.register(r"bank-credentials", BankCredentialViewSet, basename="bank-credentials")
router.register(
    r"config/categories", MasterFinancialCategoryViewSet, basename="admin-categories"
)
router.register(r"config/rules", AccountingRuleViewSet, basename="admin-rules")
router.register(
    r"workbench-groups", WorkbenchGroupHierarchyViewSet, basename="workbench-groups"
)
router.register(
    r"master-tag-rules", MasterNarrationTagRuleViewSet, basename="master-tag-rules"
)

urlpatterns = [
    # Router ViewSets
    path("", include(router.urls)),
    # 💳 Financial Ledger Accounts
    path("accounts/", AccountListCreateView.as_view(), name="account-list-create"),
    path("accounts/<str:pk>/", AccountDetailView.as_view(), name="account-detail"),
    # 📊 Double-Entry Transactions
    path(
        "transactions/",
        TransactionListCreateView.as_view(),
        name="transaction-list-create",
    ),
    path("transactions/sync/", BulkTransactionSyncView.as_view(), name="bulk-sync"),
    # 📥 Statement Ingestion Pipeline
    path(
        "statements/available/",
        AvailableTemplatesListView.as_view(),
        name="available-templates",
    ),
    path(
        "statements/preview/",
        StatementPreviewAPIView.as_view(),
        name="statement-preview",
    ),
    path(
        "statements/save-template/",
        StatementTemplateSaveAPIView.as_view(),
        name="save-template",
    ),
    path(
        "statements/ingestDynamic/",
        StatementIngestRouterDynamicView.as_view(),
        name="statement-upload",
    ),
    path(
        "statement/commit-staging/",
        StatementStagingCommitView.as_view(),
        name="statement-commit-staging",
    ),
    path(
        "statement/ingestbulk/",
        StatementBulkIngestPipelineView.as_view(),
        name="production-ingest",
    ),
    # ⚙️ Configuration & Staging Operations
    path("config/", SystemConfigView.as_view(), name="system-config"),
    path(
        "staging/auto-categorize/",
        AutoCategorizeStagingQueueView.as_view(),
        name="auto-categorize-staging",
    ),
    path(
        "accounting/bulk-commit-ledger/",
        CommitStagingQueue,
        name="commit-staging-journal",
    ),
    # 🏷️ Classification Workbench Top-Level Actions
    path(
        "get_suspense_workbench_data/",
        classificationViews.get_suspense_workbench_data,
        name="get_suspense_workbench_data",
    ),
    path(
        "get_taxonomy_tree/",
        classificationViews.get_taxonomy_tree_view,
        name="get_taxonomy_tree",
    ),
    path(
        "get_taxonomy_nodes/",
        classificationViews.get_taxonomy_nodes_Assetview,
        name="get_taxonomy_nodes",
    ),
    path(
        "apply_reclassification_and_learn/",
        classificationViews.apply_reclassification_and_learn,
        name="apply_reclassification_and_learn",
    ),
    path(
        "add_taxonomy_node/",
        classificationViews.add_taxonomy_node,
        name="add_taxonomy_node",
    ),
    path(
        "suggest_rule_for_cluster/",
        classificationViews.suggest_rule_for_cluster,
        name="suggest_rule_for_cluster",
    ),
    # 📁 Domain Sub-Module URL Mounts (No duplicates)
    path("classification/", include("tracker.classification.urls")),
    path("subledgers/", include("tracker.subledgers.urls")),
    path("dashboard/", include("tracker.dashboard.urls")),
    path("ingest/email/", include("tracker.emailIngest.urls")),
    # ⚡ Real-Time Live Notification Stream Routes (iOS SMS & Gmail API)
    path("tracker/inbox/", include("tracker.parsers.parsers_v1.inbox.urls")),
    path(
        "inbox/live-payloads/",
        LiveStreamPayloadsView.as_view(),
        name="live-payloads-backlog",
    ),
    path(
        "inbox/live-payloads/enrich/",
        LiveStreamCommitEnrichmentView.as_view(),
        name="live-payloads-enrich-commit",
    ),
    path(
        "inbox/live-payloads/audit/",
        EnrichedReconciliationAuditView.as_view(),
        name="live-payloads-audit",
    ),
]


# # S:\_BaijSoft\myWealth-Sync\backend\tracker\urls.py
# from django.urls import path, include

# from tracker.backendViewModel.inbox_view import (
#     EnrichedReconciliationAuditView,
#     LiveStreamPayloadsView,
#     LiveStreamCommitEnrichmentView,
# )
# from .backendViewModel.views import (
#     SystemConfigView,
#     AccountListCreateView,
#     AccountDetailView,
#     TransactionListCreateView,
#     BulkTransactionSyncView,
#     BankViewSet,
#     BankCredentialViewSet,
#     StatementStagingCommitView,
#     StatementPreviewAPIView,
#     StatementTemplateSaveAPIView,
#     StatementIngestRouterDynamicView,
#     AvailableTemplatesListView,
#     StatementBulkIngestPipelineView,
# )
# from .backendViewModel.ledgerCategorizationView import (
#     AutoCategorizeStagingQueueView,
#     MasterFinancialCategoryViewSet,
#     AccountingRuleViewSet,
#     CommitStagingQueue,
# )
# from tracker.classification import classificationViews

# urlpatterns = [
#     # 🏛️ Master Bank Collection Endpoints
#     path(
#         "banks/",
#         BankViewSet.as_view({"get": "list", "post": "create"}),
#         name="bank-list-create",
#     ),
#     path(
#         "banks/<str:pk>/",
#         BankViewSet.as_view(
#             {
#                 "get": "retrieve",
#                 "put": "update",
#                 "patch": "partial_update",
#                 "delete": "destroy",
#             }
#         ),
#         name="bank-detail",
#     ),
#     # 🔐 Secure Credentials Bank Key Chains
#     path(
#         "bank-credentials/",
#         BankCredentialViewSet.as_view({"get": "list", "post": "create"}),
#         name="bank-credential-list-create",
#     ),
#     path(
#         "bank-credentials/<str:pk>/",
#         BankCredentialViewSet.as_view(
#             {
#                 "get": "retrieve",
#                 "put": "update",
#                 "patch": "partial_update",
#                 "delete": "destroy",
#             }
#         ),
#         name="bank-credential-detail",
#     ),
#     # 💳 Financial Ledger Management Collection
#     path("accounts/", AccountListCreateView.as_view(), name="account-list-create"),
#     path("accounts/<str:pk>/", AccountDetailView.as_view(), name="account-detail"),
#     # 📊 Double-Entry Transaction Data streams
#     path(
#         "transactions/",
#         TransactionListCreateView.as_view(),
#         name="transaction-list-create",
#     ),
#     path("transactions/sync/", BulkTransactionSyncView.as_view(), name="bulk-sync"),
#     # save extracted rows
#     path(
#         "statement/commit-staging/",
#         StatementStagingCommitView.as_view(),
#         name="statement-ingest-stagging",
#     ),
#     path(
#         "statements/preview/",
#         StatementPreviewAPIView.as_view(),
#         name="statement_preview_api",
#     ),
#     path(
#         "statements/save-template/",
#         StatementTemplateSaveAPIView.as_view(),
#         name="save_template",
#     ),
#     path(
#         "statements/ingestDynamic/",
#         StatementIngestRouterDynamicView.as_view(),
#         name="statement-upload",
#     ),
#     # Show extracted rows
#     path(
#         "statement/ingestbulk/",
#         StatementBulkIngestPipelineView.as_view(),
#         name="production-ingest",
#     ),
#     path(
#         "statements/available/",
#         AvailableTemplatesListView.as_view(),
#         name="available-templates",
#     ),
# ]

# urlpatterns += [
#     # ⚙️ Configuration Properties
#     path("config/", SystemConfigView.as_view(), name="system-config"),
#     # 🛠️ NEW ADMINISTRATIVE CRUD ENDPOINTS
#     # Master Categories CRUD Matrix Lookups
#     path(
#         "config/categories/",
#         MasterFinancialCategoryViewSet.as_view({"get": "list", "post": "create"}),
#         name="admin-categories-list-create",
#     ),
#     path(
#         "config/categories/<int:pk>/",
#         MasterFinancialCategoryViewSet.as_view(
#             {
#                 "get": "retrieve",
#                 "put": "update",
#                 "patch": "partial_update",
#                 "delete": "destroy",
#             }
#         ),
#         name="admin-categories-detail",
#     ),
#     # Golden Accounting Rules CRUD Matrix Lookups
#     path(
#         "config/rules/",
#         AccountingRuleViewSet.as_view({"get": "list", "post": "create"}),
#         name="admin-rules-list-create",
#     ),
#     path(
#         "config/rules/<int:pk>/",
#         AccountingRuleViewSet.as_view(
#             {
#                 "get": "retrieve",
#                 "put": "update",
#                 "patch": "partial_update",
#                 "delete": "destroy",
#             }
#         ),
#         name="admin-rules-detail",
#     ),
#     path(
#         "staging/auto-categorize/",
#         AutoCategorizeStagingQueueView.as_view(),
#         name="auto-categorize-staging",
#     ),
#     path(
#         "accounting/bulk-commit-ledger/",
#         CommitStagingQueue,
#         name="commit-staging-journal",
#     ),
# ]


# urlpatterns += [
#     path("dashboard/", include("tracker.dashboard.urls")),
# ]

# urlpatterns += [
#     path(
#         "get_suspense_workbench_data/",
#         classificationViews.get_suspense_workbench_data,
#         name="get_suspense_workbench_data",
#     ),
#     path(
#         "get_taxonomy_tree/",
#         classificationViews.get_taxonomy_tree_view,
#         name="get_taxonomy_tree",
#     ),
#     path(
#         "get_taxonomy_nodes/",
#         classificationViews.get_taxonomy_nodes_Assetview,
#         name="get_taxonomy_nodes",
#     ),
#     path(
#         "apply_reclassification_and_learn/",
#         classificationViews.apply_reclassification_and_learn,
#         name="apply_reclassification_and_learn",
#     ),
#     path(
#         "add_taxonomy_node/",
#         classificationViews.add_taxonomy_node,
#         name="add_taxonomy_node",
#     ),
#     path("classification/", include("tracker.classification.urls")),
#     path(
#         "suggest_rule_for_cluster/",
#         classificationViews.suggest_rule_for_cluster,
#         name="suggest_rule_for_cluster",
#     ),
# ]

# # urlpatterns += [
# #     path("tracker/inbox/", include("tracker.parsers.parsers_v1.inbox.urls")),
# #     path(
# #         "inbox/live-payloads/audit/",
# #         EnrichedReconciliationAuditView.as_view(),
# #         name="live-payloads-audit",
# #     ),
# # ]

# urlpatterns += [
#     path("tracker/inbox/", include("tracker.parsers.parsers_v1.inbox.urls")),
#     # ⚡ Real-Time Live Notification Stream Routes (iOS SMS & Gmail API)
#     path(
#         "inbox/live-payloads/",
#         LiveStreamPayloadsView.as_view(),
#         name="live-payloads-backlog",
#     ),
#     path(
#         "inbox/live-payloads/enrich/",
#         LiveStreamCommitEnrichmentView.as_view(),
#         name="live-payloads-enrich-commit",
#     ),
#     path(
#         "inbox/live-payloads/audit/",
#         EnrichedReconciliationAuditView.as_view(),
#         name="live-payloads-audit",
#     ),
# ]
