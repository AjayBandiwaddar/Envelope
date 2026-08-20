"""
POST /api/authorize/ - the most important endpoint in the system
(API_SPEC.md Section 10).

Decision-only: this view never executes a tool. It authenticates the
caller as a registered agent, validates the request body, cross-checks
the body's agent_id against the authenticated identity, delegates to
apps.authorization.service.authorize(), and returns the structured
decision. Per API_SPEC.md Section 6, both ALLOW and DENY are HTTP 200 -
only genuine authentication/validation failures use 401/400.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.authentication import AgentBearerTokenAuthentication
from apps.authorization import service
from apps.authorization.engine import Decision, ReasonCode
from apps.authorization.serializers import AuthorizeRequestSerializer


class AuthorizeView(APIView):
    authentication_classes = [AgentBearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AuthorizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        request_id = getattr(request, "request_id", "")
        authenticated_agent_id = request.user.agent_id

        # API_SPEC.md Section 26: never trust agent_id without validating
        # it against the authenticated identity. A mismatch is not a
        # 401 (the credential itself was valid) - it's an authorization
        # outcome, denied via the normal decision channel, so it can't
        # be used to probe which agent_ids exist.
        if data["agent_id"] != authenticated_agent_id:
            decision_data = {
                "decision": Decision.DENY.value,
                "reason_code": ReasonCode.INVALID_AGENT.value,
                "reason": "The request's agent_id does not match the authenticated credential.",
                "policy_id": None,
                "request_id": request_id,
            }
            return Response({"data": decision_data, "request_id": request_id}, status=200)

        resource = data.get("resource") or {}
        decision = service.authorize(
            agent_id=authenticated_agent_id,
            user_id=data.get("user_id") or None,
            task_id=data["task_id"],
            tool_id=data["tool"],
            action=data["action"],
            resource_type=resource.get("type", ""),
            resource_id=resource.get("id"),
            parameters=data.get("parameters") or {},
            request_id=request_id,
        )

        decision_data = {
            "decision": decision.decision.value,
            "reason_code": decision.reason_code.value,
            "reason": decision.reason,
            "policy_id": decision.policy_id,
            "request_id": request_id,
        }
        return Response({"data": decision_data, "request_id": request_id}, status=200)