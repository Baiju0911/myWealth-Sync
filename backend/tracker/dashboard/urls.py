from django.urls import path
from .dashViews import dashboard_summary_view

urlpatterns = [
    path("summary/", dashboard_summary_view, name="dashboard-summary"),
]
