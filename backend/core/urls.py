from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter
from tracker.views import BankCredentialViewSet

router = DefaultRouter()
router.register(r"bank-credentials", BankCredentialViewSet, basename="bank-credentials")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/login/", obtain_auth_token, name="api-token-auth"),
    # 🚀 Dynamic Router Endpoints (This handles /api/bank-credentials/ cleanly)
    path("api/", include(router.urls)),
    # Fallback to internal tracker routes for manual views if needed
    path("api/", include("tracker.urls")),
]
