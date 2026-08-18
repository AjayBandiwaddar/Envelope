"""Views for the Audit API (API_SPEC.md Section 16-17). Read-only, administrative."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.authentication import AdminTokenAuthentication

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventListView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        events = AuditEvent.objects.all()

        agent_id = request.query_params.get("agent_id")
        task_id = request.query_params.get("task_id")
        decision = request.query_params.get("decision")
        action = request.query_params.get("action")
        reason_code = request.query_params.get("reason_code")

        if agent_id:
            events = events.filter(agent_id=agent_id)
        if task_id:
            events = events.filter(task_id=task_id)
        if decision:
            events = events.filter(decision=decision)
        if action:
            events = events.filter(action=action)
        if reason_code:
            events = events.filter(reason_code=reason_code)

        # API_SPEC.md §21: bounded page size, never an unlimited result set.
        page_size = min(int(request.query_params.get("page_size", 50)), 100)
        events = events[:page_size]

        data = AuditEventSerializer(events, many=True).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")})


class AuditEventDetailView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        event = AuditEvent.objects.filter(id=event_id).first()
        if event is None:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Audit event not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        return Response({"data": AuditEventSerializer(event).data, "request_id": getattr(request, "request_id", "")})