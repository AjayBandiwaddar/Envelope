from django.urls import path

from .views import ToolDetailView, ToolDisableView, ToolListCreateView

urlpatterns = [
    path("", ToolListCreateView.as_view(), name="tool-list-create"),
    path("<str:tool_id>/", ToolDetailView.as_view(), name="tool-detail"),
    path("<str:tool_id>/disable/", ToolDisableView.as_view(), name="tool-disable"),
]