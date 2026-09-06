from rest_framework.routers import DefaultRouter

from tracker.backendViewModel.emailViews import EmailIngestStagingViewSet
from tracker.backendViewModel.emailViewsutils import (
    CloudflareTunnelViewSet,
    RawEmailPayloadVaultViewSet,
    BalanceCheckViewSet,
    DocumentInboxViewSet,
)

router = DefaultRouter()
router.register(r"staging", EmailIngestStagingViewSet, basename="email-staging")
router.register(r"payloads", RawEmailPayloadVaultViewSet, basename="email-vault")
router.register(r"tunnel", CloudflareTunnelViewSet, basename="email-tunnel")
router.register(r"balance-check", BalanceCheckViewSet, basename="balance-check")
router.register(r"documents/inbox", DocumentInboxViewSet, basename="document-inbox")
urlpatterns = router.urls
