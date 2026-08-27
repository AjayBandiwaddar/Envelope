import pytest
from django.utils import timezone
from datetime import timedelta

from apps.agents.models import Agent, AgentStatus
from apps.tasks.models import Task, TaskStatus
from apps.tools.models import Tool
from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode
from apps.tools.mcp_dispatch import dispatch_tool_call
from apps.audit.models import AuditEvent


@pytest.fixture
def propose_intent_tool(db):
    return Tool.objects.create(
        tool_id="propose_purchase_intent", name="Propose Purchase Intent",
        input_schema={"task_id": {}, "product_id": {}, "quantity": {}},
    )


@pytest.fixture
def agent_task_with_propose_policy(db, propose_intent_tool):
    agent = Agent.objects.create(agent_id="audit-link-agent", name="Audit Link Agent", status=AgentStatus.ACTIVE)
    raw_token = agent.issue_token()
    task = Task.objects.create(
        task_id="audit-link-task", agent=agent, user_id="audit-link-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=30),
    )
    Policy.objects.create(
        policy_id="policy-audit-link-propose",
        name="Standing: propose purchase intent (audit link test)",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent,
        task_scope=task,
        tool_scope=propose_intent_tool,
        allowed_actions=["propose_purchase_intent"],
        resource_mode=ResourceScopeMode.NONE,
    )
    return agent, task, raw_token


class TestAuditResourceLinkage:
    def test_propose_purchase_intent_patches_audit_event_with_real_intent_id(
        self, agent_task_with_propose_policy, mandate_test_product
    ):
        agent, task, raw_token = agent_task_with_propose_policy

        result = dispatch_tool_call(
            tool_id="propose_purchase_intent", action="propose_purchase_intent",
            agent_token=raw_token, task_id=task.task_id,
            resource_type="", resource_id=None,
            parameters={"task_id": task.task_id, "product_id": mandate_test_product.product_id, "quantity": 1},
        )
        assert result["decision"] == "ALLOW"
        intent_id = result["result"]["intent_id"]

        # The private linkage keys must never leak into the actual result.
        assert "_audit_resource_type" not in result["result"]
        assert "_audit_resource_id" not in result["result"]

        event = AuditEvent.objects.get(request_id=result["request_id"])
        assert event.resource_type == "purchase_intent"
        assert event.resource_id == intent_id