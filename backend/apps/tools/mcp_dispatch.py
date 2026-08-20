"""
The single dispatch path shared by every MCP tool wrapper.

Per CODEX_EXECUTION_PLAN.md Day 4: "Never duplicate policy logic inside
individual MCP tools." This module is the only place MCP tool calls
touch authentication or authorization - apps/tools/mcp_server.py's six
tool functions are thin wrappers that all call dispatch_tool_call()
with their own tool_id/action baked in and nothing else. No tool
function contains an if/else about what's allowed; that logic lives
exactly once, in apps.authorization.service and apps.authorization.engine,
same as the REST API path (apps/authorization/views.py).

Flow, per the Day 4 required flow:
    MCP request -> validation -> authentication -> authorization -> tool execution
"""

from __future__ import annotations

import uuid

from apps.agents.models import Agent
from apps.authorization import service
from apps.authorization.engine import Decision
from apps.tools.gateway import ToolExecutionDenied, execute_tool


def dispatch_tool_call(
    *,
    tool_id: str,
    action: str,
    agent_token: str,
    task_id: str,
    resource_type: str = "",
    resource_id: str | None = None,
    parameters: dict | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Authenticate, authorize, and (only if ALLOW) execute a single tool
    call arriving over MCP. Returns a JSON-serializable dict describing
    the outcome - never raises for ordinary denial paths, so an MCP
    client always gets a clear, structured answer rather than a
    transport-level error for something as ordinary as "not authorized".
    """
    request_id = f"req-mcp-{uuid.uuid4().hex[:12]}"

    # --- validation ---
    if not agent_token:
        return _denied_response("INVALID_AGENT", "No agent credential supplied.", request_id)
    if not task_id:
        return _denied_response("TASK_NOT_FOUND", "No task_id supplied.", request_id)

    # --- authentication ---
    # Same hashed-token lookup as AgentBearerTokenAuthentication
    # (apps/agents/authentication.py) - a second, independent
    # implementation is deliberately avoided; both call Agent.hash_token.
    token_hash = Agent.hash_token(agent_token)
    agent = Agent.objects.filter(token_hash=token_hash).first()
    if agent is None:
        return _denied_response("INVALID_AGENT", "Invalid agent credential.", request_id)

    # --- authorization ---
    # The ENTIRE decision is delegated to the same service function the
    # REST API uses. This function does not know or care what "allowed"
    # means for any tool - it only asks.
    decision = service.authorize(
        agent_id=agent.agent_id,
        user_id=user_id,
        task_id=task_id,
        tool_id=tool_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        parameters=parameters or {},
        request_id=request_id,
    )

    if decision.decision != Decision.ALLOW:
        return {
            "decision": decision.decision.value,
            "reason_code": decision.reason_code.value,
            "reason": decision.reason,
            "request_id": request_id,
        }

    # --- tool execution (only ever reached after a persisted ALLOW) ---
    try:
        result = execute_tool(
            tool_id,
            action,
            {**(parameters or {}), "resource_id": resource_id},
            decision,
            request_id=request_id,
        )
    except ToolExecutionDenied as exc:
        # Defense in depth: the gateway independently re-checked tool
        # registration/status and refused anyway. Surface this exactly
        # like any other denial - the MCP caller never sees a stack
        # trace or an ambiguous transport error for a security decision.
        return _denied_response("POLICY_EVALUATION_ERROR", str(exc), request_id)

    return {
        "decision": "ALLOW",
        "reason_code": decision.reason_code.value,
        "request_id": request_id,
        "result": result,
    }


def _denied_response(reason_code: str, reason: str, request_id: str) -> dict:
    return {
        "decision": "DENY",
        "reason_code": reason_code,
        "reason": reason,
        "request_id": request_id,
    }