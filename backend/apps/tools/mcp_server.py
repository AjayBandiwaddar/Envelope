"""
MCP-compatible tool server.

Registers the same six tools as apps.tools.handlers as MCP tools, using
the mcp SDK's MCPServer. Every tool function here is a thin wrapper
around apps.tools.mcp_dispatch.dispatch_tool_call() - see that module's
docstring for why policy logic is never duplicated per-tool.

ARCHITECTURE.md Section 13 / AGENTS.md: "The authorization gateway must
remain protocol-independent internally." This module is the ONLY place
in the codebase that imports the mcp package - the authorization
service and policy engine have no idea MCP exists.

Run via: python manage.py run_mcp_server
"""

from __future__ import annotations

import anyio
from mcp.server.mcpserver import MCPServer

from apps.tools.mcp_dispatch import dispatch_tool_call

mcp_server = MCPServer(
    name="agent-action-firewall",
    description=(
        "Task-scoped, policy-enforced tool access. Every tool call requires "
        "a valid agent_token and task_id and is independently authorized "
        "against stored policy before it runs."
    ),
)


async def _dispatch(**kwargs) -> dict:
    """
    dispatch_tool_call() does synchronous Django ORM work. Every tool
    wrapper below is declared `async def` and routes through this
    helper so that sync ORM code always runs in a worker thread via
    anyio.to_thread.run_sync - never inline on the event loop thread,
    regardless of how a given MCP SDK version chooses to invoke tool
    functions internally. This is the correct way to bridge sync
    Django code into an async server, not a workaround for a specific
    test failure - it protects real stdio/SSE usage too.
    """
    return await anyio.to_thread.run_sync(lambda: dispatch_tool_call(**kwargs))


@mcp_server.tool()
async def get_order(agent_token: str, task_id: str, order_id: str) -> dict:
    """Look up an order. Requires authorization for action=get_order, resource=order."""
    return await _dispatch(
        tool_id="get_order",
        action="get_order",
        agent_token=agent_token,
        task_id=task_id,
        resource_type="order",
        resource_id=order_id,
        parameters={"order_id": order_id},
    )


@mcp_server.tool()
async def refund_order(agent_token: str, task_id: str, order_id: str, amount: float, currency: str) -> dict:
    """Refund an order. Requires authorization for action=refund_order, resource=order."""
    return await _dispatch(
        tool_id="refund_order",
        action="refund_order",
        agent_token=agent_token,
        task_id=task_id,
        resource_type="order",
        resource_id=order_id,
        parameters={"order_id": order_id, "amount": amount, "currency": currency},
    )


@mcp_server.tool()
async def cancel_order(agent_token: str, task_id: str, order_id: str) -> dict:
    """Cancel an order. Requires authorization for action=cancel_order, resource=order."""
    return await _dispatch(
        tool_id="cancel_order",
        action="cancel_order",
        agent_token=agent_token,
        task_id=task_id,
        resource_type="order",
        resource_id=order_id,
        parameters={"order_id": order_id},
    )


@mcp_server.tool()
async def get_customer(agent_token: str, task_id: str, customer_id: str) -> dict:
    """Look up a customer. Requires authorization for action=get_customer, resource=customer."""
    return await _dispatch(
        tool_id="get_customer",
        action="get_customer",
        agent_token=agent_token,
        task_id=task_id,
        resource_type="customer",
        resource_id=customer_id,
        parameters={"customer_id": customer_id},
    )


@mcp_server.tool()
async def send_email(agent_token: str, task_id: str, to: str, subject: str) -> dict:
    """Send an email. Requires authorization for action=send_email."""
    return await _dispatch(
        tool_id="send_email",
        action="send_email",
        agent_token=agent_token,
        task_id=task_id,
        resource_type="",
        resource_id=None,
        parameters={"to": to, "subject": subject},
    )


@mcp_server.tool()
async def delete_customer(agent_token: str, task_id: str, customer_id: str) -> dict:
    """Delete a customer. Requires authorization for action=delete_customer, resource=customer. High risk."""
    return await _dispatch(
        tool_id="delete_customer",
        action="delete_customer",
        agent_token=agent_token,
        task_id=task_id,
        resource_type="customer",
        resource_id=customer_id,
        parameters={"customer_id": customer_id},
    )