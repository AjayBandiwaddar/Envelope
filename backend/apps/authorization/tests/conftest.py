"""
Shared fixtures for policy engine tests.

Deliberately built from pure dataclasses, not Django models - these
tests exercise apps.authorization.engine in isolation, with no database
involved, per the engine's own zero-ORM-dependency design.
"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.authorization.engine import (
    AgentSnapshot,
    AuthorizationRequestContext,
    Constraint,
    ConstraintOperator,
    Decision,
    PolicySnapshot,
    ProposedAction,
    ResourceScope,
    ResourceScopeMode,
    TaskSnapshot,
    ToolSnapshot,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def active_agent():
    return AgentSnapshot(agent_id="support-agent-01", status="ACTIVE")


@pytest.fixture
def disabled_agent():
    return AgentSnapshot(agent_id="support-agent-01", status="DISABLED")


@pytest.fixture
def active_task():
    return TaskSnapshot(
        task_id="task-001",
        agent_id="support-agent-01",
        user_id="user-001",
        status="ACTIVE",
        expires_at=NOW + timedelta(minutes=30),
    )


@pytest.fixture
def active_tool():
    return ToolSnapshot(tool_id="tool-refund-001", status="ACTIVE")


@pytest.fixture
def refund_policy():
    return PolicySnapshot(
        policy_id="policy-refund-001",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(
            resource_type="order", mode=ResourceScopeMode.EXACT, ids=("8291",)
        ),
        constraints={
            "amount": Constraint(operator=ConstraintOperator.LTE, value=5000),
            "currency": Constraint(operator=ConstraintOperator.EQ, value="INR"),
        },
    )


@pytest.fixture
def request_context():
    return AuthorizationRequestContext(
        agent_id="support-agent-01", user_id="user-001", task_id="task-001"
    )


@pytest.fixture
def valid_refund_action():
    return ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 3000, "currency": "INR"},
    )
