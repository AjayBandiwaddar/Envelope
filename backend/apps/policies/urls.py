from django.urls import path

from .views import PolicyDetailView, PolicyListCreateView, PolicyRevokeView

urlpatterns = [
    path("", PolicyListCreateView.as_view(), name="policy-list-create"),
    path("<str:policy_id>/", PolicyDetailView.as_view(), name="policy-detail"),
    path("<str:policy_id>/revoke/", PolicyRevokeView.as_view(), name="policy-revoke"),
]