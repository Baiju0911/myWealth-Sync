from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .subledgerViews import (
    AssetSubLedgerViewSet,
    AssetOperationalAccountViewSet,
    AssetComplianceScheduleViewSet,
    SubledgerMetadataView,
    SubledgerSubcategoryBreakdownView,
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
    # 🎯 Direct endpoints (no redundant 'subledgers/' prefix here)
    path("metadata/", SubledgerMetadataView.as_view(), name="subledger-metadata"),
    path(
        "subcategory-breakdown/",
        SubledgerSubcategoryBreakdownView.as_view(),
        name="subledger-subcategory-breakdown",
    ),
    path("", include(router.urls)),
]
