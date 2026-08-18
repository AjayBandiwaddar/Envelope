from django.urls import path

from .views import TaskDetailView, TaskListCreateView, TaskRevokeView

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list-create"),
    path("<str:task_id>/", TaskDetailView.as_view(), name="task-detail"),
    path("<str:task_id>/revoke/", TaskRevokeView.as_view(), name="task-revoke"),
]