from django.urls import path

from .views import AuditEventDetailView, AuditEventListView

urlpatterns = [
    path("", AuditEventListView.as_view(), name="audit-event-list"),
    path("<int:event_id>/", AuditEventDetailView.as_view(), name="audit-event-detail"),
]