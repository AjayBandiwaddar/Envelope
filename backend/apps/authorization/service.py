"""
The service layer that bridges Django ORM models to the pure policy
engine, and persists the resulting decision as an audit event.

This is the ONLY module in the authorization flow permitted to import
both the Django ORM and the engine package - it is the translation
boundary described in ARCHITECTURE.md Section 5.4's Repository ->
Service -> Engine layering. The engine package itself must remain pure
(see apps/authorization/engine/ and its structural test).
"""

from __future__ import annotations

import time

from django.utils import timezone

from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.authorization import engine as eng
from apps.authorization.rate_limit import is_rate_limited
from apps.policies.models import Policy
from apps.tasks.models import Task
from apps.tools.models import Tool


def _agent_snapshot(agent: Agent | None) -> eng.AgentSnapshot | None:
    if agent is None:
        return None
    return eng.AgentSnapshot(agent_id=agent.agent_id, status=agent.status)


def _task_snapshot(task: Task | None) -> eng.TaskSnapshot | None:
    if task is None:
        return None
    return eng.TaskSnapshot(
        task_id=task.task_id,
        agent_id=task.agent.agent_id,
        user_id=task.user_id,
        status=task.status,
        expires_at=task.expires_at,
    )


def _tool_snapshot(tool: Tool | None) -> eng.ToolSnapshot | None:
    if tool is None:
        return None
    return eng.ToolSnapshot(tool_id=tool.tool_id, status=tool.status)


def _constraint_snapshot(raw: dict) -> dict[str, eng.Constraint]:
    result = {}
    for name, spec in raw.items():
        try:
            operator = eng.ConstraintOperator(spec["operator"])
            result[name] = eng.Constraint(operator=operator, value=spec["value"])
        except (KeyError, ValueError, TypeError):
            # A malformed stored constraint becomes an EQ constraint
            # against a sentinel value that can never match any real
            # request parameter, so evaluation fails closed (DENY /
            # PARAMETER_VALUE_NOT_ALLOWED) rather than raising or,
            # worse, silently widening the granted scope by skipping
            # the constraint entirely.
            result[name] = eng.Constraint(operator=eng.ConstraintOperator.EQ, value=object())
    return result


def _policy_snapshot(policy: Policy) -> eng.PolicySnapshot:
    return eng.PolicySnapshot(
        policy_id=policy.policy_id,
        status=policy.status,
        effect=eng.Decision(policy.effect),
        agent_id=policy.agent_scope.agent_id,
        task_id=policy.task_scope.task_id,
        tool_id=policy.tool_scope.tool_id,
        user_id=policy.user_scope or None,
        allowed_actions=tuple(policy.allowed_actions),
        resource_scope=eng.ResourceScope(
            resource_type=policy.resource_type,
            mode=eng.ResourceScopeMode(policy.resource_mode),
            ids=tuple(policy.resource_ids),
        ),
        constraints=_constraint_snapshot(policy.constraints),
    )


def authorize(
    agent_id: str,
    user_id: str | None,
    task_id: str,
    tool_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    parameters: dict,
    request_id: str = "",
) -> eng.AuthorizationDecision:
    """
    Look up the relevant Agent/Task/Tool/Policy rows, delegate to the
    pure engine, and persist an AuditEvent for the outcome.

    Per THREAT_MODEL.md Section 5.12 ('fail-open on infrastructure
    failure'): if the audit record cannot be persisted, the returned
    decision is downgraded to DENY / POLICY_EVALUATION_ERROR regardless
    of what the engine computed - callers (e.g. the Tool Gateway) must
    never execute on a decision whose audit trail doesn't actually exist.
    """
    start = time.perf_counter()

    context = eng.AuthorizationRequestContext(agent_id=agent_id, user_id=user_id, task_id=task_id)
    proposed_action = eng.ProposedAction(
        tool_id=tool_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        parameters=parameters or {},
    )

    if is_rate_limited(agent_id):
        decision = eng.AuthorizationDecision(
            decision=eng.Decision.DENY,
            reason_code=eng.ReasonCode.RATE_LIMIT_EXCEEDED,
            reason=eng.DEFAULT_REASON_TEXT[eng.ReasonCode.RATE_LIMIT_EXCEEDED],
            policy_id=None,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return _persist_audit_event(
            decision=decision,
            request_id=request_id,
            agent_id=agent_id,
            user_id=user_id,
            task_id=task_id,
            tool_id=tool_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            parameters=parameters or {},
            latency_ms=latency_ms,
        )

    agent = Agent.objects.filter(agent_id=agent_id).first()
    task = Task.objects.select_related("agent").filter(task_id=task_id).first()
    tool = Tool.objects.filter(tool_id=tool_id).first()

    policies = []
    if task is not None:
        policies = [
            _policy_snapshot(p)
            for p in Policy.objects.filter(task_scope=task).select_related(
                "agent_scope", "task_scope", "tool_scope"
            )
        ]

    decision = eng.evaluate(
        context,
        proposed_action,
        _agent_snapshot(agent),
        _task_snapshot(task),
        _tool_snapshot(tool),
        policies,
        now=timezone.now(),
    )

    latency_ms = (time.perf_counter() - start) * 1000

    decision = _persist_audit_event(
        decision=decision,
        request_id=request_id,
        agent_id=agent_id,
        user_id=user_id,
        task_id=task_id,
        tool_id=tool_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        parameters=parameters or {},
        latency_ms=latency_ms,
    )

    return decision


def _persist_audit_event(
    *,
    decision: eng.AuthorizationDecision,
    request_id: str,
    agent_id: str,
    user_id: str | None,
    task_id: str,
    tool_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    parameters: dict,
    latency_ms: float,
) -> eng.AuthorizationDecision:
    try:
        AuditEvent.objects.create(
            request_id=request_id,
            agent_id=agent_id,
            user_id=user_id or "",
            task_id=task_id,
            tool_id=tool_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id or "",
            parameters=parameters,
            policy_id=decision.policy_id or "",
            decision=decision.decision.value,
            reason_code=decision.reason_code.value,
            reason=decision.reason,
            latency_ms=latency_ms,
        )
    except Exception:  # noqa: BLE001 - fail closed on audit persistence failure
        return eng.AuthorizationDecision(
            decision=eng.Decision.DENY,
            reason_code=eng.ReasonCode.POLICY_EVALUATION_ERROR,
            reason="Authorization could not be completed because the audit record could not be persisted.",
            policy_id=None,
        )

    return decision