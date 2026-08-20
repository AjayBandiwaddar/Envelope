"""
Integration tests for POST /api/authorize/, exercising the real Django
stack (real ORM, real DRF authentication, real URL routing) - not the
pure engine directly (that's apps/authorization/tests/test_evaluator.py).

Covers every scenario CODEX_EXECUTION_PLAN.md Day 3 'Required Tests'
names: valid authorization API request, denied authorization API
request, wrong resource, wrong action, wrong parameter, unknown tool,
disabled tool, invalid agent, disabled agent, expired task, missing
authentication, malformed request, audit event creation, request ID
propagation.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.agents.models import AgentStatus
from apps.audit.models import AuditEvent
from apps.tools.models import ToolStatus

AUTHORIZE_URL = "/api/authorize/"


def _authorize_body(agent_id, task_id, **overrides):
    body = {
        "agent_id": agent_id,
        "user_id": "user-001",
        "task_id": task_id,
        "tool": "refund_order",
        "action": "refund_order",
        "resource": {"type": "order", "id": "8291"},
        "parameters": {"amount": 3000, "currency": "INR"},
    }
    body.update(overrides)
    return body


@pytest.mark.django_db
class TestValidAuthorization:
    def test_valid_request_allows(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        response = agent_client.post(
            AUTHORIZE_URL, _authorize_body(agent.agent_id, active_task.task_id), format="json"
        )
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "ALLOW"
        assert response.data["data"]["reason_code"] == "AUTHORIZED"
        assert response.data["data"]["policy_id"] == "policy-refund-001"


@pytest.mark.django_db
class TestDeniedAuthorization:
    def test_excessive_amount_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id, parameters={"amount": 8000, "currency": "INR"})
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "PARAMETER_LIMIT_EXCEEDED"

    def test_wrong_resource_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id, resource={"type": "order", "id": "9999"})
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "RESOURCE_ID_NOT_ALLOWED"

    def test_wrong_action_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id, action="delete_customer")
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "ACTION_NOT_ALLOWED"

    def test_wrong_parameter_value_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id, parameters={"amount": 3000, "currency": "USD"})
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "PARAMETER_VALUE_NOT_ALLOWED"

    def test_unknown_tool_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id, tool="nonexistent-tool")
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "TOOL_NOT_REGISTERED"

    def test_disabled_tool_denies(self, agent_client, agent_with_token, active_task, refund_policy, refund_tool):
        refund_tool.status = ToolStatus.DISABLED
        refund_tool.save()
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id)
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "TOOL_DISABLED"

    def test_unknown_agent_id_in_body_denies(self, agent_client, active_task, refund_policy):
        """
        Body claims a different agent_id than the authenticated token -
        must DENY as INVALID_AGENT, never trust the body (API_SPEC.md
        Section 26).
        """
        body = _authorize_body("a-different-agent", active_task.task_id)
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "INVALID_AGENT"

    def test_disabled_agent_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        agent.status = AgentStatus.DISABLED
        agent.save()
        body = _authorize_body(agent.agent_id, active_task.task_id)
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "AGENT_DISABLED"

    def test_expired_task_denies(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        active_task.expires_at = timezone.now() - timedelta(minutes=1)
        active_task.save()
        body = _authorize_body(agent.agent_id, active_task.task_id)
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 200
        assert response.data["data"]["decision"] == "DENY"
        assert response.data["data"]["reason_code"] == "TASK_EXPIRED"


@pytest.mark.django_db
class TestAuthenticationAndValidation:
    def test_missing_authentication_returns_401(self, api_client, active_task):
        response = api_client.post(AUTHORIZE_URL, _authorize_body("x", active_task.task_id), format="json")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, api_client, active_task):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        response = api_client.post(AUTHORIZE_URL, _authorize_body("x", active_task.task_id), format="json")
        assert response.status_code == 401

    def test_malformed_request_missing_required_field_returns_400(self, agent_client):
        # Missing task_id, tool, action entirely.
        response = agent_client.post(AUTHORIZE_URL, {"agent_id": "support-agent-01"}, format="json")
        assert response.status_code == 400

    def test_malformed_request_wrong_type_returns_400(self, agent_client, agent_with_token):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, "task-001", parameters="not-a-dict")
        response = agent_client.post(AUTHORIZE_URL, body, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestAuditAndRequestId:
    def test_audit_event_created_for_every_decision(
        self, agent_client, agent_with_token, active_task, refund_policy
    ):
        agent, _ = agent_with_token
        assert AuditEvent.objects.count() == 0
        agent_client.post(AUTHORIZE_URL, _authorize_body(agent.agent_id, active_task.task_id), format="json")
        assert AuditEvent.objects.count() == 1
        event = AuditEvent.objects.first()
        assert event.decision == "ALLOW"
        assert event.agent_id == agent.agent_id
        assert event.task_id == active_task.task_id
        assert event.policy_id == "policy-refund-001"

    def test_audit_event_created_for_deny_too(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        body = _authorize_body(agent.agent_id, active_task.task_id, parameters={"amount": 9999, "currency": "INR"})
        agent_client.post(AUTHORIZE_URL, body, format="json")
        event = AuditEvent.objects.first()
        assert event.decision == "DENY"
        assert event.reason_code == "PARAMETER_LIMIT_EXCEEDED"

    def test_supplied_request_id_is_propagated(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        response = agent_client.post(
            AUTHORIZE_URL,
            _authorize_body(agent.agent_id, active_task.task_id),
            format="json",
            HTTP_X_REQUEST_ID="req-custom-12345",
        )
        assert response.headers["X-Request-ID"] == "req-custom-12345"
        assert response.data["data"]["request_id"] == "req-custom-12345"
        event = AuditEvent.objects.first()
        assert event.request_id == "req-custom-12345"

    def test_request_id_generated_when_absent(self, agent_client, agent_with_token, active_task, refund_policy):
        agent, _ = agent_with_token
        response = agent_client.post(
            AUTHORIZE_URL, _authorize_body(agent.agent_id, active_task.task_id), format="json"
        )
        assert response.headers["X-Request-ID"].startswith("req-")