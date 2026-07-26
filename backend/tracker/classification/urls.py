from django.urls import path
from tracker.classification.classificationViews import (
    ClassificationPendingListView,
    ReclassifyEntryView,
    UpdateJournalEntryNoteView,
)

urlpatterns = [
    # GET list of pending Node 99 items with structured JSON remarks
    path(
        "pending/",
        ClassificationPendingListView.as_view(),
        name="classification-pending",
    ),
    # POST endpoint for reclassifying from the frontend modal
    path(
        "reclassify/", ReclassifyEntryView.as_view(), name="classification-reclassify"
    ),
    path("entry-note/", UpdateJournalEntryNoteView.as_view(), name="update-entry-note"),
]
