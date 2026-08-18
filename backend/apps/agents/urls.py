from django.urls import path

from .views import AgentDetailView, AgentDisableView, AgentListCreateView

urlpatterns = [
    path("", AgentListCreateView.as_view(), name="agent-list-create"),
    path("<str:agent_id>/", AgentDetailView.as_view(), name="agent-detail"),
    path("<str:agent_id>/disable/", AgentDisableView.as_view(), name="agent-disable"),
]