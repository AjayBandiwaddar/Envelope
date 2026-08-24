"""
The deterministic policy engine.

This module is the enforcement point described in AGENTS.md's Core
Security Principle: "LLM for intent/action proposal. Deterministic code
for authorization." It has no dependency on Django, HTTP, or any LLM
client - see THREAT_MODEL.md Section 3.6 for the structural test that
protects this invariant.

Evaluation order follows POLICY_SPEC.md Section 23 "Policy Evaluation
Algorithm" as closely as a relational, multi-policy system allows. That
section describes the check order for a *single* candidate policy; it
does not fully specify how to choose among *multiple* policies attached
to the same task. This module documents its own resolution strategy
explicitly below, per AGENTS.md's "when requirements are ambiguous,
prefer the safest interpretation and document the ambiguity":

    1. Validate agent and task first (steps 2-6 of Section 23);
       these are prerequisites for evaluating any policy at all.
    2. Validate the tool is registered and active (Section 23 step 11,
       moved earlier here because tool registration is a *global*
       property, not something scoped to a single policy - see
       POLICY_SPEC.md Section 10, which states this as a standalone
       rule rather than a per-policy check).
    3. Among ACTIVE policies scoped to this task: any EXPLICIT DENY
       policy whose agent/user/action/tool/resource scope matches this
       request wins immediately (POLICY_SPEC.md Section 21: "Explicit
       deny overrides allow" - checked before any ALLOW policy is
       considered at all, and DENY scope-matching does not evaluate
       parameter constraints, matching the spec's own example of a
       constraint-free explicit deny).
    4. Otherwise, take the FIRST ACTIVE ALLOW policy (by the order the
       caller supplies - the service layer is expected to order
       candidates by `priority` descending, then by policy_id, to keep
       this deterministic) whose agent/user/action/tool/resource scope
       fully matches. Evaluate that policy's parameter constraints and
       return its result (ALLOW, or a parameter-related DENY) as final -
       this module does NOT fall through to try a second scope-matching
       policy once one is found, since POLICY_SPEC.md's evaluation
       order treats constraint checking as a late, sequential step
       against the identified policy rather than a retry loop.
    5. If no ACTIVE policy's scope fully matches, produce the most
       specific available diagnostic reason code by locating the
       closest partial match (see `_best_diagnostic`), falling back to
       POLICY_NOT_FOUND if nothing scoped to this task references the
       requested tool at all.

Per POLICY_SPEC.md Section 22, every path through this module that is
not an explicit, fully-matched ALLOW must return DENY. There is no
implicit-ALLOW branch anywhere in this file.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone

from .constraints import ConstraintEvaluationError, evaluate_constraint
from .reason_codes import DEFAULT_REASON_TEXT, ReasonCode
from .types import (
    AgentSnapshot,
    AuthorizationDecision,
    AuthorizationRequestContext,
    Decision,
    PolicySnapshot,
    ProposedAction,
    ResourceScopeMode,
    TaskSnapshot,
    ToolSnapshot,
)


def _deny(reason_code: ReasonCode, policy_id: str | None = None, detail: str | None = None) -> AuthorizationDecision:
    return AuthorizationDecision(
        decision=Decision.DENY,
        reason_code=reason_code,
        reason=detail or DEFAULT_REASON_TEXT[reason_code],
        policy_id=policy_id,
    )


def _allow(policy_id: str) -> AuthorizationDecision:
    return AuthorizationDecision(
        decision=Decision.ALLOW,
        reason_code=ReasonCode.AUTHORIZED,
        reason=DEFAULT_REASON_TEXT[ReasonCode.AUTHORIZED],
        policy_id=policy_id,
    )


def evaluate(
    context: AuthorizationRequestContext,
    action: ProposedAction,
    agent: AgentSnapshot | None,
    task: TaskSnapshot | None,
    tool: ToolSnapshot | None,
    policies: list[PolicySnapshot],
    now: datetime | None = None,
) -> AuthorizationDecision:
    """
    Evaluate a single proposed action against the supplied snapshots and
    return a structured AuthorizationDecision. Never raises for ordinary
    denial paths; unexpected internal errors are caught and converted to
    POLICY_EVALUATION_ERROR / DENY (AGENTS.md Fail-Closed Rule).
    """
    try:
        return _evaluate(context, action, agent, task, tool, policies, now)
    except Exception as exc:  # noqa: BLE001 - intentional catch-all, fail closed
        return _deny(
            ReasonCode.POLICY_EVALUATION_ERROR,
            detail=f"Unexpected error during policy evaluation: {exc}",
        )


def _evaluate(
    context: AuthorizationRequestContext,
    action: ProposedAction,
    agent: AgentSnapshot | None,
    task: TaskSnapshot | None,
    tool: ToolSnapshot | None,
    policies: list[PolicySnapshot],
    now: datetime | None,
) -> AuthorizationDecision:
    now = now or datetime.now(dt_timezone.utc)

    # --- Steps 2-3: agent ---
    if agent is None:
        return _deny(ReasonCode.INVALID_AGENT)
    if not agent.is_active:
        return _deny(ReasonCode.AGENT_DISABLED)

    # --- Steps 4-6: task existence, ownership, lifecycle ---
    if task is None:
        return _deny(ReasonCode.TASK_NOT_FOUND)

    # Confused-deputy protection (THREAT_MODEL.md Section 5.11): a task
    # that exists but belongs to a different agent is indistinguishable,
    # from this agent's perspective, from a task that doesn't exist at
    # all (THREAT_MODEL.md Section 6.2 - avoid enumeration).
    if task.agent_id != context.agent_id:
        return _deny(ReasonCode.TASK_NOT_FOUND)

    if task.is_expired(now):
        return _deny(ReasonCode.TASK_EXPIRED)
    if task.status == "REVOKED":
        return _deny(ReasonCode.TASK_REVOKED)
    if task.status != "ACTIVE":
        return _deny(ReasonCode.TASK_NOT_ACTIVE)

    # --- Step 9 (moved up): task-level user binding ---
    if task.user_id and context.user_id and task.user_id != context.user_id:
        return _deny(ReasonCode.USER_SCOPE_MISMATCH)

    # --- Step 11 (moved up, see module docstring): tool registration ---
    if tool is None:
        return _deny(ReasonCode.TOOL_NOT_REGISTERED)
    if not tool.is_active:
        return _deny(ReasonCode.TOOL_DISABLED)
    if tool.input_schema:
        extra = set(action.parameters.keys()) - set(tool.input_schema.keys())
        if extra:
            return _deny(
                ReasonCode.UNKNOWN_PARAMETER,
                detail=f"Unknown parameter(s): {', '.join(sorted(extra))}.",
            )

    # --- Gather policies scoped to this task ---
    task_policies = [p for p in policies if p.task_id == task.task_id]
    if not task_policies:
        return _deny(ReasonCode.POLICY_NOT_FOUND)

    active_policies = [p for p in task_policies if p.is_active]

    # --- Explicit DENY pass (POLICY_SPEC.md Section 21) ---
    for policy in active_policies:
        if policy.effect != Decision.DENY:
            continue
        if _scope_matches(policy, context, action):
            return _deny(ReasonCode.EXPLICIT_DENY, policy_id=policy.policy_id)

    # --- ALLOW pass: first full scope match wins ---
    for policy in active_policies:
        if policy.effect != Decision.ALLOW:
            continue
        if _scope_matches(policy, context, action):
            return _evaluate_constraints(policy, action)

    # --- No active policy matched: produce the best available diagnostic ---
    return _best_diagnostic(task_policies, context, action)


def _scope_matches(
    policy: PolicySnapshot, context: AuthorizationRequestContext, action: ProposedAction
) -> bool:
    """
    Check agent/user/action/tool/resource scope only - NOT parameter
    constraints. Used for both the DENY pass and the ALLOW pass, since
    POLICY_SPEC.md's own explicit-deny example matches on scope alone.
    """
    if policy.agent_id != context.agent_id:
        return False
    if policy.user_id and context.user_id and policy.user_id != context.user_id:
        return False
    if action.action not in policy.allowed_actions:
        return False
    if policy.tool_id != action.tool_id:
        return False
    if not _resource_matches(policy, action):
        return False
    return True


def _resource_matches(policy: PolicySnapshot, action: ProposedAction) -> bool:
    scope = policy.resource_scope
    if scope.mode == ResourceScopeMode.NONE:
        return not action.resource_id
    if scope.resource_type and scope.resource_type != action.resource_type:
        return False
    if scope.mode == ResourceScopeMode.ANY:
        return True
    if scope.mode == ResourceScopeMode.EXACT:
        return action.resource_id in scope.ids
    return False


def _evaluate_constraints(policy: PolicySnapshot, action: ProposedAction) -> AuthorizationDecision:
    """
    Evaluate every constraint on the matched policy against the request's
    supplied parameters. Per POLICY_SPEC.md Section 17-18: a missing
    required parameter denies; extra, unconstrained parameters never
    grant additional authority (they're simply not checked - the tool's
    own input_schema validation, not this engine, is responsible for
    rejecting genuinely unknown parameters before this point).
    """
    for param_name, constraint in policy.constraints.items():
        if param_name not in action.parameters:
            return _deny(
                ReasonCode.REQUIRED_PARAMETER_MISSING,
                policy_id=policy.policy_id,
                detail=f"Missing required parameter '{param_name}'.",
            )

        actual_value = action.parameters[param_name]
        try:
            satisfied = evaluate_constraint(constraint, actual_value)
        except ConstraintEvaluationError as exc:
            return _deny(
                ReasonCode.PARAMETER_SCHEMA_INVALID,
                policy_id=policy.policy_id,
                detail=str(exc),
            )

        if not satisfied:
            reason_code = (
                ReasonCode.PARAMETER_LIMIT_EXCEEDED
                if constraint.operator.value in ("LTE", "GTE")
                else ReasonCode.PARAMETER_VALUE_NOT_ALLOWED
            )
            return _deny(
                reason_code,
                policy_id=policy.policy_id,
                detail=f"Parameter '{param_name}' value {actual_value!r} does not satisfy the authorized constraint.",
            )

    return _allow(policy.policy_id)


def _best_diagnostic(
    task_policies: list[PolicySnapshot],
    context: AuthorizationRequestContext,
    action: ProposedAction,
) -> AuthorizationDecision:
    """
    No active policy fully matched. Walk the candidates (including
    inactive ones) to produce the most specific, honest diagnostic reason
    code, without ever implying a match exists where the agent/user scope
    itself doesn't match (that would leak information about policies
    belonging to other agents/users - THREAT_MODEL.md Section 6.2).
    """
    own_scope_policies = [
        p
        for p in task_policies
        if p.agent_id == context.agent_id
        and not (p.user_id and context.user_id and p.user_id != context.user_id)
    ]
    if not own_scope_policies:
        return _deny(ReasonCode.POLICY_NOT_FOUND)

    # Inactive policy that otherwise fully matches (action/tool/resource)?
    for policy in own_scope_policies:
        if policy.is_active:
            continue
        if action.action in policy.allowed_actions and policy.tool_id == action.tool_id and _resource_matches(policy, action):
            if policy.status == "REVOKED":
                return _deny(ReasonCode.POLICY_REVOKED, policy_id=policy.policy_id)
            return _deny(ReasonCode.POLICY_DISABLED, policy_id=policy.policy_id)

    active_own = [p for p in own_scope_policies if p.is_active]

    # Active policy for this tool, but not this action?
    for policy in active_own:
        if policy.tool_id == action.tool_id and action.action not in policy.allowed_actions:
            return _deny(ReasonCode.ACTION_NOT_ALLOWED, policy_id=policy.policy_id)

    # Active policy for this action+tool, but wrong resource?
    for policy in active_own:
        if policy.tool_id == action.tool_id and action.action in policy.allowed_actions:
            if policy.resource_scope.resource_type and policy.resource_scope.resource_type != action.resource_type:
                return _deny(ReasonCode.RESOURCE_TYPE_NOT_ALLOWED, policy_id=policy.policy_id)
            return _deny(ReasonCode.RESOURCE_ID_NOT_ALLOWED, policy_id=policy.policy_id)

    return _deny(ReasonCode.POLICY_NOT_FOUND)
