from django.urls import path, include
from rest_framework.routers import DefaultRouter


from .subledgerViews import (
    AssetSubLedgerViewSet,
    AssetOperationalAccountViewSet,
    AssetComplianceScheduleViewSet,
)

router = DefaultRouter()
router.register(r"assets", AssetSubLedgerViewSet, basename="subledger-assets")
router.register(
    r"operational-accounts",
    AssetOperationalAccountViewSet,
    basename="subledger-opaccounts",
)
router.register(
    r"schedules",
    AssetComplianceScheduleViewSet,
    basename="subledger-schedules",
)

urlpatterns = [
    path("", include(router.urls)),
]
