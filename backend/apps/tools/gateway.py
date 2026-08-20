"""
The Tool Gateway - the only place a mock tool can actually execute.

Critical rule, per AGENTS.md and API_SPEC.md Section 14:
"Tools must not execute without a successful authorization decision."

This module is deliberately NOT exposed as a public HTTP endpoint - per
docs/SPEC_REVIEW.md Section 3.4, tool execution is an internal Python
function call, reachable only from code that already holds a persisted
AuthorizationDecision, not a URL a client could hit directly. There is
no `/api/internal/tools/{tool_id}/execute/` route anywhere in urls.py.
"""

from __future__ import annotations

from apps.authorization.engine import AuthorizationDecision, Decision
from apps.tools.handlers import TOOL_HANDLERS
from apps.tools.models import Tool, ToolExecution, ToolStatus


class ToolExecutionDenied(Exception):
    """
    Raised whenever execution is refused. Never raised for reasons a
    caller could use to distinguish *why* in a way that leaks policy
    detail beyond what the AuthorizationDecision already exposed -
    THREAT_MODEL.md Section 6.2.
    """


def execute_tool(
    tool_id: str,
    action: str,
    arguments: dict,
    decision: AuthorizationDecision,
    request_id: str = "",
) -> dict:
    """
    Execute a mock tool. Raises ToolExecutionDenied and creates NO
    ToolExecution record if:
      - decision.decision is not ALLOW (AGENTS.md 'Tools must not
        execute without a successful authorization decision.')
      - the tool is not registered or is disabled (defense in depth -
        the policy engine already checked this, but the gateway does
        not trust that check happened correctly upstream)
      - no handler is registered for tool_id
    """
    if decision.decision != Decision.ALLOW:
        raise ToolExecutionDenied(
            "Refusing to execute: authorization decision was not ALLOW."
        )

    try:
        tool = Tool.objects.get(tool_id=tool_id)
    except Tool.DoesNotExist:
        raise ToolExecutionDenied(f"Refusing to execute: tool '{tool_id}' is not registered.")

    if tool.status != ToolStatus.ACTIVE:
        raise ToolExecutionDenied(f"Refusing to execute: tool '{tool_id}' is disabled.")

    handler = TOOL_HANDLERS.get(tool_id)
    if handler is None:
        raise ToolExecutionDenied(f"Refusing to execute: no handler registered for '{tool_id}'.")

    result = handler(arguments)

    ToolExecution.objects.create(
        tool_id=tool_id,
        action=action,
        request_id=request_id,
        arguments=arguments,
        result=result,
    )

    return result