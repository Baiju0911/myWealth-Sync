from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

# from tracker.backendViewModel.emailViews import RawEmailPayloadViewSet
from tracker.backendViewModel.ledgerCategorizationView import (
    AccountingRuleViewSet,
    MasterFinancialCategoryViewSet,
)
from tracker.backendViewModel.views import BankCredentialViewSet

router = DefaultRouter()
router.register(r"bank-credentials", BankCredentialViewSet, basename="bank-credentials")
router.register(
    r"config/categories",
    MasterFinancialCategoryViewSet,
    basename="admin-categories",
)
router.register(r"config/rules", AccountingRuleViewSet, basename="admin-rules")
# Registered directly under api/
# router.register(
#     r"ingest/email/payloads",
#     RawEmailPayloadViewSet,
#     basename="email-payloads",
# )

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/login/", obtain_auth_token, name="api-token-auth"),
    path("api/", include(router.urls)),
    path("api/", include("tracker.urls")),
    path("api/classification/", include("tracker.classification.urls")),
    path("api/subledgers/", include("tracker.subledgers.urls")),
    path("api/ingest/email/", include("tracker.emailIngest.urls")),
]


# from django.contrib import admin
# from django.shortcuts import redirect
# from django.urls import path, include
# from rest_framework.authtoken.views import obtain_auth_token
# from rest_framework.routers import DefaultRouter
# from tracker.backendViewModel.ledgerCategorizationView import (
#     AccountingRuleViewSet,
#     MasterFinancialCategoryViewSet,
# )
# from tracker.backendViewModel.views import BankCredentialViewSet

# router = DefaultRouter()
# router.register(r"bank-credentials", BankCredentialViewSet, basename="bank-credentials")
# router.register(
#     r"config/categories", MasterFinancialCategoryViewSet, basename="admin-categories"
# )
# router.register(r"config/rules", AccountingRuleViewSet, basename="admin-rules")

# urlpatterns = [
#     # Redirect root domain (/) directly to Django Admin
#     path("", lambda request: redirect("admin/", permanent=False)),
#     path("admin/", admin.site.urls),
#     path("api/login/", obtain_auth_token, name="api-token-auth"),
#     # 🚀 Dynamic Router Endpoints (Handles /api/bank-credentials/, /api/config/categories/, etc.)
#     path("api/", include(router.urls)),
#     # Fallback to internal tracker routes for manual views if needed
#     path("api/", include("tracker.urls")),
#     path("api/classification/", include("tracker.classification.urls")),
#     path("api/subledgers/", include("tracker.subledgers.urls")),
# ]
