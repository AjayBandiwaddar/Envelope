"""Views for the Policies API (API_SPEC.md Section 9). Administrative endpoints only."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.authentication import AdminTokenAuthentication

from .models import Policy, PolicyStatus
from .serializers import PolicyCreateSerializer, PolicySerializer


class PolicyListCreateView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        policies = Policy.objects.select_related("agent_scope", "task_scope", "tool_scope").all()
        agent_id = request.query_params.get("agent_id")
        task_id = request.query_params.get("task_id")
        status_filter = request.query_params.get("status")
        if agent_id:
            policies = policies.filter(agent_scope__agent_id=agent_id)
        if task_id:
            policies = policies.filter(task_scope__task_id=task_id)
        if status_filter:
            policies = policies.filter(status=status_filter)
        data = PolicySerializer(policies, many=True).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")})

    def post(self, request):
        serializer = PolicyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = serializer.save()
        data = PolicySerializer(policy).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")}, status=201)


class PolicyDetailView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, policy_id):
        policy = Policy.objects.select_related("agent_scope", "task_scope", "tool_scope").filter(
            policy_id=policy_id
        ).first()
        if policy is None:
            return Response(
                {"error": {"code": "POLICY_NOT_FOUND", "message": "Policy not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        return Response({"data": PolicySerializer(policy).data, "request_id": getattr(request, "request_id", "")})


class PolicyRevokeView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, policy_id):
        policy = Policy.objects.filter(policy_id=policy_id).first()
        if policy is None:
            return Response(
                {"error": {"code": "POLICY_NOT_FOUND", "message": "Policy not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        policy.status = PolicyStatus.REVOKED
        policy.save(update_fields=["status", "updated_at"])
        return Response(
            {"data": {"policy_id": policy.policy_id, "status": policy.status},
             "request_id": getattr(request, "request_id", "")}
        )