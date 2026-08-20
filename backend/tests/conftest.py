from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agents.models import Agent, AgentStatus
from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode
from apps.tasks.models import Task, TaskStatus
from apps.tools.models import Tool

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def admin_token_setting(settings):
    settings.ADMIN_API_TOKEN = ADMIN_TOKEN


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_client(api_client):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {ADMIN_TOKEN}")
    return api_client


@pytest.fixture
def refund_tool(db):
    return Tool.objects.create(tool_id="refund_order", name="Refund Order")


@pytest.fixture
def agent_with_token(db):
    agent = Agent.objects.create(agent_id="support-agent-01", name="Support Agent", status=AgentStatus.ACTIVE)
    raw_token = agent.issue_token()
    return agent, raw_token


@pytest.fixture
def agent_client(api_client, agent_with_token):
    _, raw_token = agent_with_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_token}")
    return api_client


@pytest.fixture
def active_task(db, agent_with_token):
    agent, _ = agent_with_token
    return Task.objects.create(
        task_id="task-001",
        agent=agent,
        user_id="user-001",
        status=TaskStatus.ACTIVE,
        expires_at=timezone.now() + timedelta(minutes=30),
    )


@pytest.fixture
def refund_policy(db, agent_with_token, active_task, refund_tool):
    agent, _ = agent_with_token
    return Policy.objects.create(
        policy_id="policy-refund-001",
        name="Support Refund Policy",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent,
        task_scope=active_task,
        tool_scope=refund_tool,
        allowed_actions=["refund_order"],
        resource_type="order",
        resource_mode=ResourceScopeMode.EXACT,
        resource_ids=["8291"],
        constraints={
            "amount": {"operator": "LTE", "value": 5000},
            "currency": {"operator": "EQ", "value": "INR"},
        },
    )