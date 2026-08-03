# S:\_BaijSoft\myWealth-Sync\backend\tracker\urls.py
from django.urls import path, include
from .backendViewModel.views import (
    SystemConfigView,
    AccountListCreateView,
    AccountDetailView,
    TransactionListCreateView,
    BulkTransactionSyncView,
    BankViewSet,
    BankCredentialViewSet,
    StatementStagingCommitView,
    StatementPreviewAPIView,
    StatementTemplateSaveAPIView,
    StatementIngestRouterDynamicView,
    AvailableTemplatesListView,
    StatementBulkIngestPipelineView,
)
from .backendViewModel.ledgerCategorizationView import (
    AutoCategorizeStagingQueueView,
    MasterFinancialCategoryViewSet,
    AccountingRuleViewSet,
    CommitStagingQueue,
)
from tracker.classification import classificationViews

urlpatterns = [
    # 🏛️ Master Bank Collection Endpoints
    path(
        "banks/",
        BankViewSet.as_view({"get": "list", "post": "create"}),
        name="bank-list-create",
    ),
    path(
        "banks/<str:pk>/",
        BankViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="bank-detail",
    ),
    # 🔐 Secure Credentials Bank Key Chains
    path(
        "bank-credentials/",
        BankCredentialViewSet.as_view({"get": "list", "post": "create"}),
        name="bank-credential-list-create",
    ),
    path(
        "bank-credentials/<str:pk>/",
        BankCredentialViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="bank-credential-detail",
    ),
    # 💳 Financial Ledger Management Collection
    path("accounts/", AccountListCreateView.as_view(), name="account-list-create"),
    path("accounts/<str:pk>/", AccountDetailView.as_view(), name="account-detail"),
    # 📊 Double-Entry Transaction Data streams
    path(
        "transactions/",
        TransactionListCreateView.as_view(),
        name="transaction-list-create",
    ),
    path("transactions/sync/", BulkTransactionSyncView.as_view(), name="bulk-sync"),
    # save extracted rows
    path(
        "statement/commit-staging/",
        StatementStagingCommitView.as_view(),
        name="statement-ingest-stagging",
    ),
    path(
        "statements/preview/",
        StatementPreviewAPIView.as_view(),
        name="statement_preview_api",
    ),
    path(
        "statements/save-template/",
        StatementTemplateSaveAPIView.as_view(),
        name="save_template",
    ),
    path(
        "statements/ingestDynamic/",
        StatementIngestRouterDynamicView.as_view(),
        name="statement-upload",
    ),
    # Show extracted rows
    path(
        "statement/ingestbulk/",
        StatementBulkIngestPipelineView.as_view(),
        name="production-ingest",
    ),
    path(
        "statements/available/",
        AvailableTemplatesListView.as_view(),
        name="available-templates",
    ),
]

urlpatterns += [
    # ⚙️ Configuration Properties
    path("config/", SystemConfigView.as_view(), name="system-config"),
    # 🛠️ NEW ADMINISTRATIVE CRUD ENDPOINTS
    # Master Categories CRUD Matrix Lookups
    path(
        "config/categories/",
        MasterFinancialCategoryViewSet.as_view({"get": "list", "post": "create"}),
        name="admin-categories-list-create",
    ),
    path(
        "config/categories/<int:pk>/",
        MasterFinancialCategoryViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="admin-categories-detail",
    ),
    # Golden Accounting Rules CRUD Matrix Lookups
    path(
        "config/rules/",
        AccountingRuleViewSet.as_view({"get": "list", "post": "create"}),
        name="admin-rules-list-create",
    ),
    path(
        "config/rules/<int:pk>/",
        AccountingRuleViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="admin-rules-detail",
    ),
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
]


urlpatterns += [
    path("dashboard/", include("tracker.dashboard.urls")),
]

urlpatterns += [
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
        "apply_reclassification_and_learn/",
        classificationViews.apply_reclassification_and_learn,
        name="apply_reclassification_and_learn",
    ),
    path(
        "add_taxonomy_node/",
        classificationViews.add_taxonomy_node,
        name="add_taxonomy_node",
    ),
    path("classification/", include("tracker.classification.urls")),
    path(
        "suggest_rule_for_cluster/",
        classificationViews.suggest_rule_for_cluster,
        name="suggest_rule_for_cluster",
    ),
]
