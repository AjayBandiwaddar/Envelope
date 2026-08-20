import pytest


@pytest.mark.django_db
class TestAgentsApi:
    def test_create_agent_returns_token_once(self, admin_client):
        response = admin_client.post("/api/agents/", {"name": "Test Agent"}, format="json")
        assert response.status_code == 201
        assert "token" in response.data["data"]
        assert response.data["data"]["status"] == "ACTIVE"

    def test_admin_endpoint_rejects_agent_token(self, agent_client):
        """An agent's execution token must not work on admin endpoints (THREAT_MODEL.md 5.13)."""
        response = agent_client.post("/api/agents/", {"name": "Should Not Work"}, format="json")
        assert response.status_code == 401

    def test_list_agents(self, admin_client, agent_with_token):
        response = admin_client.get("/api/agents/")
        assert response.status_code == 200
        assert len(response.data["data"]) == 1

    def test_disable_agent(self, admin_client, agent_with_token):
        agent, _ = agent_with_token
        response = admin_client.post(f"/api/agents/{agent.agent_id}/disable/")
        assert response.status_code == 200
        assert response.data["data"]["status"] == "DISABLED"


@pytest.mark.django_db
class TestTasksApi:
    def test_create_task_defaults_to_active_with_expiry(self, admin_client, agent_with_token):
        agent, _ = agent_with_token
        response = admin_client.post(
            "/api/tasks/", {"agent_id": agent.agent_id, "user_id": "user-001"}, format="json"
        )
        assert response.status_code == 201
        assert response.data["data"]["status"] == "ACTIVE"
        assert response.data["data"]["expires_at"] is not None

    def test_create_task_rejects_unknown_agent(self, admin_client):
        response = admin_client.post("/api/tasks/", {"agent_id": "no-such-agent"}, format="json")
        assert response.status_code == 400

    def test_revoke_task(self, admin_client, active_task):
        response = admin_client.post(f"/api/tasks/{active_task.task_id}/revoke/")
        assert response.status_code == 200
        assert response.data["data"]["status"] == "REVOKED"


@pytest.mark.django_db
class TestToolsApi:
    def test_register_tool(self, admin_client):
        response = admin_client.post(
            "/api/tools/",
            {"tool_id": "custom_tool", "name": "Custom Tool", "risk_level": "LOW"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["data"]["status"] == "ACTIVE"

    def test_disable_tool(self, admin_client, refund_tool):
        response = admin_client.post(f"/api/tools/{refund_tool.tool_id}/disable/")
        assert response.status_code == 200
        assert response.data["data"]["status"] == "DISABLED"


@pytest.mark.django_db
class TestPoliciesApi:
    def test_create_policy_with_nested_scope(self, admin_client, agent_with_token, active_task, refund_tool):
        agent, _ = agent_with_token
        response = admin_client.post(
            "/api/policies/",
            {
                "name": "Test Policy",
                "agent_scope": {"agent_id": agent.agent_id},
                "task_scope": {"task_id": active_task.task_id},
                "tool_scope": {"tool": refund_tool.tool_id},
                "allowed_actions": ["refund_order"],
                "resource_scope": {"type": "order", "mode": "EXACT", "ids": ["8291"]},
                "constraints": {"amount": {"operator": "LTE", "value": 5000}},
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["data"]["status"] == "ACTIVE"

    def test_create_policy_rejects_unknown_task(self, admin_client, agent_with_token, refund_tool):
        agent, _ = agent_with_token
        response = admin_client.post(
            "/api/policies/",
            {
                "name": "Bad Policy",
                "agent_scope": {"agent_id": agent.agent_id},
                "task_scope": {"task_id": "no-such-task"},
                "tool_scope": {"tool": refund_tool.tool_id},
                "allowed_actions": ["refund_order"],
            },
            format="json",
        )
        assert response.status_code == 400

    def test_revoke_policy(self, admin_client, refund_policy):
        response = admin_client.post(f"/api/policies/{refund_policy.policy_id}/revoke/")
        assert response.status_code == 200
        assert response.data["data"]["status"] == "REVOKED"


@pytest.mark.django_db
class TestAuditApi:
    def test_list_audit_events_requires_admin(self, agent_client):
        response = agent_client.get("/api/audit-events/")
        assert response.status_code == 401

    def test_list_audit_events_as_admin(self, admin_client):
        response = admin_client.get("/api/audit-events/")
        assert response.status_code == 200
        assert response.data["data"] == []