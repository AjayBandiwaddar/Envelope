"""Views for the Agents API (API_SPEC.md Section 7). Administrative endpoints only."""

from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.authentication import AdminTokenAuthentication
from apps.agents.models import Agent, AgentStatus
from apps.agents.serializers import AgentCreateSerializer, AgentSerializer


class AgentListCreateView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agents = Agent.objects.all()
        data = AgentSerializer(agents, many=True).data
        return Response({"data": data, "request_id": getattr(request, "request_id", "")})

    def post(self, request):
        serializer = AgentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = serializer.save()

        # The raw bearer token is generated and returned exactly once,
        # here, at creation time. It is never stored in plaintext
        # (Agent.issue_token hashes it before saving) and never appears
        # in any subsequent API response or log line.
        raw_token = agent.issue_token()

        data = AgentSerializer(agent).data
        data["token"] = raw_token
        return Response({"data": data, "request_id": getattr(request, "request_id", "")}, status=201)


class AgentDetailView(RetrieveAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Agent.objects.all()
    serializer_class = AgentSerializer
    lookup_field = "agent_id"

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"data": response.data, "request_id": getattr(request, "request_id", "")})


class AgentDisableView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, agent_id):
        agent = Agent.objects.filter(agent_id=agent_id).first()
        if agent is None:
            return Response(
                {"error": {"code": "INVALID_AGENT", "message": "Agent not found.", "details": {}},
                 "request_id": getattr(request, "request_id", "")},
                status=404,
            )
        agent.status = AgentStatus.DISABLED
        agent.save(update_fields=["status", "updated_at"])
        return Response(
            {"data": {"agent_id": agent.agent_id, "status": agent.status},
             "request_id": getattr(request, "request_id", "")}
        )