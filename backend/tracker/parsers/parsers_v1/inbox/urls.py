from django.urls import path
from tracker.backendViewModel.inbox_view import (
    PendingInboxItemsView,
    InboxItemPreviewView,
    InboxItemCommitView,
    LiveStreamPayloadsView,
    LiveStreamCommitEnrichmentView,
)

urlpatterns = [
    path("pending/", PendingInboxItemsView.as_view(), name="inbox-pending-list"),
    path(
        "<uuid:item_id>/preview/",
        InboxItemPreviewView.as_view(),
        name="inbox-item-preview",
    ),
    path(
        "<uuid:item_id>/commit/",
        InboxItemCommitView.as_view(),
        name="inbox-item-commit",
    ),
    path(
        "live-payloads/",
        LiveStreamPayloadsView.as_view(),
        name="inbox-live-payloads",
    ),
    path(
        "live-payloads/commit-enrichment/",
        LiveStreamCommitEnrichmentView.as_view(),
        name="inbox-live-commit-enrichment",
    ),
]
