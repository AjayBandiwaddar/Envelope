from datetime import timedelta

import pytest
from django.utils import timezone

from apps.agents.models import Agent
from apps.policies.models import Policy, PolicyEffect, PolicyStatus, ResourceScopeMode
from apps.tasks.models import Task
from apps.tools.models import Tool


@pytest.fixture
def agent(db):
    return Agent.objects.create(agent_id="agent-001", name="Test Agent")


@pytest.fixture
def task(db, agent):
    return Task.objects.create(
        task_id="task-001", agent=agent, expires_at=timezone.now() + timedelta(minutes=30)
    )


@pytest.fixture
def tool(db):
    return Tool.objects.create(tool_id="tool-refund-001", name="Refund Order")


@pytest.mark.django_db
def test_policy_active_by_default(agent, task, tool):
    policy = Policy.objects.create(
        policy_id="policy-001",
        name="Test Policy",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent,
        task_scope=task,
        tool_scope=tool,
        allowed_actions=["refund_order"],
    )
    assert policy.is_active() is True
    assert policy.status == PolicyStatus.ACTIVE


@pytest.mark.django_db
def test_policy_stores_resource_and_constraint_shapes(agent, task, tool):
    policy = Policy.objects.create(
        policy_id="policy-002",
        name="Test Policy",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent,
        task_scope=task,
        tool_scope=tool,
        allowed_actions=["refund_order"],
        resource_type="order",
        resource_mode=ResourceScopeMode.EXACT,
        resource_ids=["8291"],
        constraints={"amount": {"operator": "LTE", "value": 5000}},
    )
    policy.refresh_from_db()
    assert policy.resource_ids == ["8291"]
    assert policy.constraints["amount"]["value"] == 5000


@pytest.mark.django_db
def test_deny_effect_policy_can_be_created(agent, task, tool):
    policy = Policy.objects.create(
        policy_id="policy-003",
        name="Explicit Deny",
        effect=PolicyEffect.DENY,
        agent_scope=agent,
        task_scope=task,
        tool_scope=tool,
        allowed_actions=["refund_order"],
        resource_type="order",
        resource_mode=ResourceScopeMode.EXACT,
        resource_ids=["8291"],
    )
    assert policy.effect == PolicyEffect.DENY


@pytest.mark.django_db
def test_policy_id_must_be_unique(agent, task, tool):
    Policy.objects.create(
        policy_id="policy-004",
        name="First",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent,
        task_scope=task,
        tool_scope=tool,
        allowed_actions=["refund_order"],
    )
    with pytest.raises(Exception):
        Policy.objects.create(
            policy_id="policy-004",
            name="Duplicate",
            effect=PolicyEffect.ALLOW,
            agent_scope=agent,
            task_scope=task,
            tool_scope=tool,
            allowed_actions=["refund_order"],
        )
