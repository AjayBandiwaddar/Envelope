"""Views for the Tasks API (API_SPEC.md Section 8). Administrative endpoints only."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.authentication import AdminTokenAuthentication

from .models import Task, TaskStatus
from .serializers import TaskCreateSerializer, TaskSerializer


class TaskListCreateView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tasks = Task.objects.select_related("agent").all()
        agent_id = request.query_params.get("agent_id")
        status_filter = request.query_params.get("status")
        if agent_id:
            tasks = tasks.filter(agent__agent_id=agent_id)
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        data = TaskSerializer(tasks, many=True).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")})

    def post(self, request):
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        data = TaskSerializer(task).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")}, status=201)


class TaskDetailView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        task = Task.objects.select_related("agent").filter(task_id=task_id).first()
        if task is None:
            return Response(
                {"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        return Response({"data": TaskSerializer(task).data, "request_id": getattr(request, "request_id", "")})


class TaskRevokeView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        task = Task.objects.filter(task_id=task_id).first()
        if task is None:
            return Response(
                {"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        task.status = TaskStatus.REVOKED
        task.save(update_fields=["status", "updated_at"])
        return Response(
            {"data": {"task_id": task.task_id, "status": task.status},
             "request_id": getattr(request, "request_id", "")}
        )