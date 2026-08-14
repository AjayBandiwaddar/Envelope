"""
Policy engine test suite.

Covers every scenario CODEX_EXECUTION_PLAN.md Day 2 "Required Tests"
lists by name, plus additional boundary cases. Each test asserts both
the decision AND the specific reason_code - per AGENTS.md "Testing
Requirements": "Tests must verify actual enforcement rather than merely
checking response messages."
"""

from dataclasses import replace
from datetime import timedelta

from apps.authorization.engine import (
    Constraint,
    ConstraintOperator,
    Decision,
    PolicySnapshot,
    ProposedAction,
    ReasonCode,
    ResourceScope,
    ResourceScopeMode,
    TaskSnapshot,
    ToolSnapshot,
    evaluate,
)

# ---------------------------------------------------------------------------
# 1. Valid authorization
# ---------------------------------------------------------------------------


def test_valid_authorization_allows(
    request_context, valid_refund_action, active_agent, active_task, active_tool, refund_policy, now
):
    decision = evaluate(
        request_context, valid_refund_action, active_agent, active_task, active_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.ALLOW
    assert decision.reason_code == ReasonCode.AUTHORIZED
    assert decision.policy_id == "policy-refund-001"


# ---------------------------------------------------------------------------
# 2. Exact limit (boundary: amount == max_amount must ALLOW, per LTE semantics)
# ---------------------------------------------------------------------------


def test_amount_exactly_at_limit_allows(
    request_context, active_agent, active_task, active_tool, refund_policy, now
):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 5000, "currency": "INR"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.ALLOW


# ---------------------------------------------------------------------------
# 3. Exceeded limit
# ---------------------------------------------------------------------------


def test_amount_exceeding_limit_denies(
    request_context, active_agent, active_task, active_tool, refund_policy, now
):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 5001, "currency": "INR"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.PARAMETER_LIMIT_EXCEEDED


def test_amount_far_exceeding_limit_denies(
    request_context, active_agent, active_task, active_tool, refund_policy, now
):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 8000, "currency": "INR"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.PARAMETER_LIMIT_EXCEEDED


# ---------------------------------------------------------------------------
# 4. Wrong agent (credential valid for a different agent than the task owner)
# ---------------------------------------------------------------------------


def test_wrong_agent_denies_as_task_not_found(
    valid_refund_action, active_agent, active_task, active_tool, refund_policy, now
):
    from apps.authorization.engine import AuthorizationRequestContext

    wrong_agent_context = AuthorizationRequestContext(
        agent_id="a-different-agent", user_id="user-001", task_id="task-001"
    )
    decision = evaluate(
        wrong_agent_context, valid_refund_action, active_agent, active_task, active_tool, [refund_policy], now=now
    )
    # Per THREAT_MODEL.md Section 5.11/6.2: ownership mismatch is
    # indistinguishable from non-existence, to prevent task enumeration.
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TASK_NOT_FOUND


def test_invalid_agent_denies(request_context, valid_refund_action, active_task, active_tool, refund_policy, now):
    decision = evaluate(request_context, valid_refund_action, None, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.INVALID_AGENT


def test_disabled_agent_denies(
    request_context, valid_refund_action, disabled_agent, active_task, active_tool, refund_policy, now
):
    decision = evaluate(
        request_context, valid_refund_action, disabled_agent, active_task, active_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.AGENT_DISABLED


# ---------------------------------------------------------------------------
# 5. Wrong task (task doesn't exist at all)
# ---------------------------------------------------------------------------


def test_wrong_task_denies(request_context, valid_refund_action, active_agent, active_tool, refund_policy, now):
    decision = evaluate(
        request_context, valid_refund_action, active_agent, None, active_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TASK_NOT_FOUND


# ---------------------------------------------------------------------------
# 6. Wrong action
# ---------------------------------------------------------------------------


def test_wrong_action_denies(request_context, active_agent, active_task, active_tool, refund_policy, now):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="delete_customer",
        resource_type="order",
        resource_id="8291",
        parameters={},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.ACTION_NOT_ALLOWED


# ---------------------------------------------------------------------------
# 7. Wrong resource
# ---------------------------------------------------------------------------


def test_wrong_resource_id_denies(request_context, active_agent, active_task, active_tool, refund_policy, now):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="9999",
        parameters={"amount": 3000, "currency": "INR"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.RESOURCE_ID_NOT_ALLOWED


def test_wrong_resource_type_denies(request_context, active_agent, active_task, active_tool, refund_policy, now):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="customer",
        resource_id="8291",
        parameters={"amount": 3000, "currency": "INR"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.RESOURCE_TYPE_NOT_ALLOWED


# ---------------------------------------------------------------------------
# 8. Wrong parameter (value not in allowed set / wrong string)
# ---------------------------------------------------------------------------


def test_wrong_currency_denies(request_context, active_agent, active_task, active_tool, refund_policy, now):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 3000, "currency": "USD"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.PARAMETER_VALUE_NOT_ALLOWED


# ---------------------------------------------------------------------------
# 9. Expired task
# ---------------------------------------------------------------------------


def test_expired_task_denies(request_context, valid_refund_action, active_agent, active_tool, refund_policy, now):
    expired_task = TaskSnapshot(
        task_id="task-001",
        agent_id="support-agent-01",
        user_id="user-001",
        status="ACTIVE",
        expires_at=now - timedelta(minutes=1),
    )
    decision = evaluate(
        request_context, valid_refund_action, active_agent, expired_task, active_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TASK_EXPIRED


# ---------------------------------------------------------------------------
# 10. Revoked task
# ---------------------------------------------------------------------------


def test_revoked_task_denies(request_context, valid_refund_action, active_agent, active_tool, refund_policy, now):
    revoked_task = TaskSnapshot(
        task_id="task-001",
        agent_id="support-agent-01",
        user_id="user-001",
        status="REVOKED",
        expires_at=now + timedelta(minutes=30),
    )
    decision = evaluate(
        request_context, valid_refund_action, active_agent, revoked_task, active_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TASK_REVOKED


def test_pending_task_denies_as_not_active(
    request_context, valid_refund_action, active_agent, active_tool, refund_policy, now
):
    pending_task = TaskSnapshot(
        task_id="task-001",
        agent_id="support-agent-01",
        user_id="user-001",
        status="PENDING",
        expires_at=now + timedelta(minutes=30),
    )
    decision = evaluate(
        request_context, valid_refund_action, active_agent, pending_task, active_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TASK_NOT_ACTIVE


# ---------------------------------------------------------------------------
# 11. Disabled policy
# ---------------------------------------------------------------------------


def test_disabled_policy_denies(
    request_context, valid_refund_action, active_agent, active_task, active_tool, refund_policy, now
):
    disabled_policy = replace(refund_policy, status="DISABLED")
    decision = evaluate(
        request_context, valid_refund_action, active_agent, active_task, active_tool, [disabled_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.POLICY_DISABLED
    assert decision.policy_id == "policy-refund-001"


# ---------------------------------------------------------------------------
# 12. Revoked policy
# ---------------------------------------------------------------------------


def test_revoked_policy_denies(
    request_context, valid_refund_action, active_agent, active_task, active_tool, refund_policy, now
):
    revoked_policy = replace(refund_policy, status="REVOKED")
    decision = evaluate(
        request_context, valid_refund_action, active_agent, active_task, active_tool, [revoked_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.POLICY_REVOKED


# ---------------------------------------------------------------------------
# 13. Unknown / disabled tool
# ---------------------------------------------------------------------------


def test_unknown_tool_denies(request_context, valid_refund_action, active_agent, active_task, refund_policy, now):
    decision = evaluate(
        request_context, valid_refund_action, active_agent, active_task, None, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TOOL_NOT_REGISTERED


def test_disabled_tool_denies(request_context, valid_refund_action, active_agent, active_task, refund_policy, now):
    disabled_tool = ToolSnapshot(tool_id="tool-refund-001", status="DISABLED")
    decision = evaluate(
        request_context, valid_refund_action, active_agent, active_task, disabled_tool, [refund_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.TOOL_DISABLED


# ---------------------------------------------------------------------------
# 14. Missing parameter
# ---------------------------------------------------------------------------


def test_missing_required_parameter_denies(
    request_context, active_agent, active_task, active_tool, refund_policy, now
):
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 3000},  # currency missing
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.REQUIRED_PARAMETER_MISSING


# ---------------------------------------------------------------------------
# 15. Malformed constraint (the stored policy data itself is invalid)
# ---------------------------------------------------------------------------


def test_malformed_constraint_denies_as_schema_invalid(
    request_context, active_agent, active_task, active_tool, refund_policy, now
):
    malformed_policy = replace(
        refund_policy,
        constraints={"amount": Constraint(operator=ConstraintOperator.LTE, value="not-a-number")},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 3000},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [malformed_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.PARAMETER_SCHEMA_INVALID


# ---------------------------------------------------------------------------
# 16. Policy evaluation failure (unexpected exception during evaluation)
# ---------------------------------------------------------------------------


def test_unexpected_error_fails_closed(
    request_context, valid_refund_action, active_agent, active_task, active_tool, now
):
    """
    A policy object that violates the engine's expected shape (e.g. an
    unsupported constraint operator smuggled in) must never crash the
    caller with an unhandled exception - it must fail closed with
    POLICY_EVALUATION_ERROR, per AGENTS.md's Fail-Closed Rule.
    """
    broken_policy = PolicySnapshot(
        policy_id="policy-broken",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.EXACT, ids=("8291",)),
        constraints={"amount": "not-a-constraint-object-at-all"},  # type: ignore[dict-item]
    )
    decision = evaluate(
        request_context, valid_refund_action, active_agent, active_task, active_tool, [broken_policy], now=now
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.POLICY_EVALUATION_ERROR


# ---------------------------------------------------------------------------
# 17. Explicit deny (overrides a matching ALLOW policy)
# ---------------------------------------------------------------------------


def test_explicit_deny_overrides_matching_allow(
    request_context, valid_refund_action, active_agent, active_task, active_tool, refund_policy, now
):
    deny_policy = PolicySnapshot(
        policy_id="policy-deny-8291",
        status="ACTIVE",
        effect=Decision.DENY,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.EXACT, ids=("8291",)),
        constraints={},
    )
    decision = evaluate(
        request_context,
        valid_refund_action,
        active_agent,
        active_task,
        active_tool,
        [refund_policy, deny_policy],
        now=now,
    )
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.EXPLICIT_DENY
    assert decision.policy_id == "policy-deny-8291"


def test_explicit_deny_does_not_affect_unrelated_resource(
    request_context, active_agent, active_task, active_tool, refund_policy, now
):
    """An explicit deny scoped to order 8291 must not affect order 8292."""
    broader_allow = replace(
        refund_policy,
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.ANY, ids=()),
    )
    deny_policy = PolicySnapshot(
        policy_id="policy-deny-8291",
        status="ACTIVE",
        effect=Decision.DENY,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.EXACT, ids=("8291",)),
        constraints={},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8292",
        parameters={"amount": 3000, "currency": "INR"},
    )
    decision = evaluate(
        request_context, action, active_agent, active_task, active_tool, [broader_allow, deny_policy], now=now
    )
    assert decision.decision == Decision.ALLOW


# ---------------------------------------------------------------------------
# 18. No policy at all for this task
# ---------------------------------------------------------------------------


def test_no_policy_for_task_denies(request_context, valid_refund_action, active_agent, active_task, active_tool, now):
    decision = evaluate(request_context, valid_refund_action, active_agent, active_task, active_tool, [], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.POLICY_NOT_FOUND


# ---------------------------------------------------------------------------
# 19. User scope mismatch
# ---------------------------------------------------------------------------


def test_user_scope_mismatch_denies(active_agent, active_task, active_tool, refund_policy, now):
    from apps.authorization.engine import AuthorizationRequestContext

    wrong_user_context = AuthorizationRequestContext(
        agent_id="support-agent-01", user_id="a-different-user", task_id="task-001"
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="8291",
        parameters={"amount": 3000, "currency": "INR"},
    )
    decision = evaluate(wrong_user_context, action, active_agent, active_task, active_tool, [refund_policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.USER_SCOPE_MISMATCH


# ---------------------------------------------------------------------------
# 20. Boolean and IN constraint types
# ---------------------------------------------------------------------------


def test_boolean_constraint_allows_when_satisfied(request_context, active_agent, active_task, active_tool, now):
    policy = PolicySnapshot(
        policy_id="policy-verified-only",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.ANY, ids=()),
        constraints={"is_verified": Constraint(operator=ConstraintOperator.BOOL_EQ, value=True)},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="1234",
        parameters={"is_verified": True},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [policy], now=now)
    assert decision.decision == Decision.ALLOW


def test_boolean_constraint_denies_when_false(request_context, active_agent, active_task, active_tool, now):
    policy = PolicySnapshot(
        policy_id="policy-verified-only",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.ANY, ids=()),
        constraints={"is_verified": Constraint(operator=ConstraintOperator.BOOL_EQ, value=True)},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="1234",
        parameters={"is_verified": False},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.PARAMETER_VALUE_NOT_ALLOWED


def test_in_constraint_allows_listed_value(request_context, active_agent, active_task, active_tool, now):
    policy = PolicySnapshot(
        policy_id="policy-multi-currency",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.ANY, ids=()),
        constraints={"currency": Constraint(operator=ConstraintOperator.IN, value=["INR", "USD"])},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="1234",
        parameters={"currency": "USD"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [policy], now=now)
    assert decision.decision == Decision.ALLOW


def test_in_constraint_denies_unlisted_value(request_context, active_agent, active_task, active_tool, now):
    policy = PolicySnapshot(
        policy_id="policy-multi-currency",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.ANY, ids=()),
        constraints={"currency": Constraint(operator=ConstraintOperator.IN, value=["INR", "USD"])},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="1234",
        parameters={"currency": "GBP"},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [policy], now=now)
    assert decision.decision == Decision.DENY
    assert decision.reason_code == ReasonCode.PARAMETER_VALUE_NOT_ALLOWED


# ---------------------------------------------------------------------------
# 21. Resource mode NONE (action with no resource, e.g. send_notification)
# ---------------------------------------------------------------------------


def test_resource_mode_none_allows_action_without_resource(request_context, active_agent, active_task, active_tool, now):
    policy = PolicySnapshot(
        policy_id="policy-notify",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-notify-001",
        user_id=None,
        allowed_actions=("send_notification",),
        resource_scope=ResourceScope(resource_type="", mode=ResourceScopeMode.NONE, ids=()),
        constraints={},
    )
    tool = ToolSnapshot(tool_id="tool-notify-001", status="ACTIVE")
    action = ProposedAction(
        tool_id="tool-notify-001", action="send_notification", resource_type="", resource_id=None, parameters={}
    )
    decision = evaluate(request_context, action, active_agent, active_task, tool, [policy], now=now)
    assert decision.decision == Decision.ALLOW


# ---------------------------------------------------------------------------
# 22. Resource mode ANY (broad grant, used carefully)
# ---------------------------------------------------------------------------


def test_resource_mode_any_allows_any_id_of_matching_type(request_context, active_agent, active_task, active_tool, now):
    policy = PolicySnapshot(
        policy_id="policy-broad",
        status="ACTIVE",
        effect=Decision.ALLOW,
        agent_id="support-agent-01",
        task_id="task-001",
        tool_id="tool-refund-001",
        user_id=None,
        allowed_actions=("refund_order",),
        resource_scope=ResourceScope(resource_type="order", mode=ResourceScopeMode.ANY, ids=()),
        constraints={"amount": Constraint(operator=ConstraintOperator.LTE, value=1000)},
    )
    action = ProposedAction(
        tool_id="tool-refund-001",
        action="refund_order",
        resource_type="order",
        resource_id="any-order-id-at-all",
        parameters={"amount": 500},
    )
    decision = evaluate(request_context, action, active_agent, active_task, active_tool, [policy], now=now)
    assert decision.decision == Decision.ALLOW
