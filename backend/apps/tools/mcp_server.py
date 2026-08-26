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

Agent identity is bound once per process via the AGENT_TOKEN environment
variable (see _resolve_agent_token below), not passed as a per-call tool
argument. A stdio MCP server process is already dedicated to a single
agent connection for its whole lifetime, so this keeps the credential
out of the tool schema an LLM sees and fills in - it is not itself a
business parameter and should never look like one.
"""

from __future__ import annotations
import os
import anyio
from mcp.server.mcpserver import MCPServer
from apps.tools.mcp_dispatch import dispatch_tool_call


def _resolve_agent_token() -> str:
    token = os.environ.get("AGENT_TOKEN", "")
    if not token:
        raise RuntimeError("AGENT_TOKEN environment variable is not set for this MCP server process.")
    return token


mcp_server = MCPServer(
    name="agent-action-firewall",
    description=(
        "Task-scoped, policy-enforced tool access. Every tool call requires "
        "a valid agent identity (bound via AGENT_TOKEN at process start) and "
        "task_id, and is independently authorized against stored policy "
        "before it runs."
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
async def get_order(task_id: str, order_id: str) -> dict:
    """Look up an order. Requires authorization for action=get_order, resource=order."""
    return await _dispatch(
        tool_id="get_order",
        action="get_order",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="order",
        resource_id=order_id,
        parameters={"order_id": order_id},
    )


@mcp_server.tool()
async def refund_order(task_id: str, order_id: str, amount: float, currency: str) -> dict:
    """Refund an order. Requires authorization for action=refund_order, resource=order."""
    return await _dispatch(
        tool_id="refund_order",
        action="refund_order",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="order",
        resource_id=order_id,
        parameters={"order_id": order_id, "amount": amount, "currency": currency},
    )


@mcp_server.tool()
async def cancel_order(task_id: str, order_id: str) -> dict:
    """Cancel an order. Requires authorization for action=cancel_order, resource=order."""
    return await _dispatch(
        tool_id="cancel_order",
        action="cancel_order",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="order",
        resource_id=order_id,
        parameters={"order_id": order_id},
    )


@mcp_server.tool()
async def get_customer(task_id: str, customer_id: str) -> dict:
    """Look up a customer. Requires authorization for action=get_customer, resource=customer."""
    return await _dispatch(
        tool_id="get_customer",
        action="get_customer",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="customer",
        resource_id=customer_id,
        parameters={"customer_id": customer_id},
    )


@mcp_server.tool()
async def send_email(task_id: str, to: str, subject: str) -> dict:
    """Send an email. Requires authorization for action=send_email."""
    return await _dispatch(
        tool_id="send_email",
        action="send_email",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="",
        resource_id=None,
        parameters={"to": to, "subject": subject},
    )


@mcp_server.tool()
async def delete_customer(task_id: str, customer_id: str) -> dict:
    """Delete a customer. Requires authorization for action=delete_customer, resource=customer. High risk."""
    return await _dispatch(
        tool_id="delete_customer",
        action="delete_customer",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="customer",
        resource_id=customer_id,
        parameters={"customer_id": customer_id},
    )

@mcp_server.tool()
async def propose_purchase_intent(task_id: str, product_id: str, quantity: int = 1) -> dict:
    """Propose buying a product. No money moves and nothing is reserved - price is computed server-side."""
    return await _dispatch(
        tool_id="propose_purchase_intent",
        action="propose_purchase_intent",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="",
        resource_id=None,
        parameters={"task_id": task_id, "product_id": product_id, "quantity": quantity},
    )

@mcp_server.tool()
async def create_order(task_id: str, intent_id: str) -> dict:
    """Create the order for a confirmed purchase intent. Amount and currency are derived entirely server-side from the confirmed intent - never accepted as arguments."""
    return await _dispatch(
        tool_id="create_order",
        action="create_order",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="purchase_intent",
        resource_id=intent_id,
        parameters={"intent_id": intent_id},
    )

@mcp_server.tool()
async def finalize_payment(task_id: str, intent_id: str, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> dict:
    """Verify a completed Checkout payment and mark the order paid."""
    return await _dispatch(
        tool_id="finalize_payment",
        action="finalize_payment",
        agent_token=_resolve_agent_token(),
        task_id=task_id,
        resource_type="purchase_intent",
        resource_id=intent_id,
        parameters={
            "intent_id": intent_id,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        },
    )

@mcp_server.tool()
async def list_products(task_id: str) -> dict:
    """List the merchant's active catalog. No filtering server-side - the catalog is small, reason over it directly."""
    return await _dispatch(
        tool_id="list_products", action="list_products", agent_token=_resolve_agent_token(),
        task_id=task_id, resource_type="", resource_id=None, parameters={"task_id": task_id},
    )