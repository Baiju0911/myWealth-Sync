from rest_framework.routers import DefaultRouter
from tracker.backendViewModel.emailViews import (
    CloudflareTunnelViewSet,
    EmailIngestStagingViewSet,
    RawEmailPayloadVaultViewSet,
    BalanceCheckViewSet,
)

router = DefaultRouter()
router.register(r"staging", EmailIngestStagingViewSet, basename="email-staging")
router.register(r"payloads", RawEmailPayloadVaultViewSet, basename="email-vault")
router.register(r"tunnel", CloudflareTunnelViewSet, basename="email-tunnel")
router.register(r"balance-check", BalanceCheckViewSet, basename="balance-check")

urlpatterns = router.urls
