# S:\_BaijSoft\myWealth-Sync\backend\tracker\urls.py
from django.urls import path
from .views import (
    SystemConfigView,
    AccountListCreateView,
    AccountDetailView,  # 🎯 THE FIX: Import the single-resource detail handler class
    TransactionListCreateView,
    BulkTransactionSyncView,
    BankViewSet,
    BankCredentialViewSet,
    StatementIngestRouterView_older1,
    StatementStagingCommitView,
    StatementPreviewAPIView,
    StatementTemplateSaveAPIView,
    StatementIngestRouterDynamicView,
    AvailableTemplatesListView,
    StatementBulkIngestPipelineView,
)

urlpatterns = [
    # ⚙️ Configuration Properties
    path("config/", SystemConfigView.as_view(), name="system-config"),
    # 🏛️ Master Bank Collection Endpoints
    path(
        "banks/",
        BankViewSet.as_view({"get": "list", "post": "create"}),
        name="bank-list-create",
    ),
    # Individual bank resource router matching UUID strings
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
    # Resource router for individual credentials modifications
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
    # 🎯 THE FIX: Wire the detail path directly to AccountDetailView instead of AccountListCreateView!
    path("accounts/<str:pk>/", AccountDetailView.as_view(), name="account-detail"),
    # 📊 Double-Entry Transaction Data streams
    path(
        "transactions/",
        TransactionListCreateView.as_view(),
        name="transaction-list-create",
    ),
    path("transactions/sync/", BulkTransactionSyncView.as_view(), name="bulk-sync"),
    # 📂 Ingestion Router (File Drag & Drop Target Endpoint)
    # path(
    #     "statement/ingest/",
    #     StatementIngestRouterView_older.as_view(),
    #     name="statement-upload",
    # ),
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
