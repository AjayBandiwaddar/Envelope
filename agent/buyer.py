from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================================
# CONFIG
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
MANAGE_PY = BACKEND / "manage.py"

load_dotenv(ROOT / ".env")


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AGENT_TOKEN = os.getenv("DEMO_AGENT_TOKEN", "")

TASK_ID = os.getenv(
    "DEMO_TASK_ID",
    "demo-buyer-task",
)

SITE_URL = os.getenv(
    "SITE_BASE_URL",
    "http://127.0.0.1:8000",
)

# You can change this in .env without modifying this file.
#
# Example:
#
# GEMINI_MODEL=gemini-3.6-flash
#
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)

MAX_REMOTE_CALLS = int(
    os.getenv(
        "GEMINI_MAX_REMOTE_CALLS",
        "4",
    )
)


if not GEMINI_API_KEY:
    sys.exit(
        "GEMINI_API_KEY is not set in .env."
    )


if not AGENT_TOKEN:
    sys.exit(
        "DEMO_AGENT_TOKEN is not set in .env. "
        "Run `python manage.py seed_demo_agent` first."
    )


# ============================================================================
# GEMINI SYSTEM INSTRUCTIONS
#
# IMPORTANT:
#
# There are intentionally THREE different system instructions.
#
# STEP 1:
#   Gemini can search and propose.
#   Gemini cannot create an order or finalize payment.
#
# STEP 3:
#   Python has already received explicit human confirmation
#   OR an active SpendingEnvelope auto-confirmed the intent.
#   Gemini is allowed to call create_order.
#
# STEP 6:
#   Python has independently received the payment callback.
#   Gemini is allowed to call finalize_payment.
#
# This avoids the contradiction in the original implementation where the
# same SYSTEM_INSTRUCTION said "do NOT call create_order" while the Python
# prompt simultaneously said "call create_order now".
# ============================================================================


STEP1_SYSTEM_INSTRUCTION = f"""
You are an AI buyer agent for a laptop store.

Your job in this phase is to understand the user's laptop requirements,
search the real product catalog, choose the single best matching product,
and propose a purchase intent.

Every MCP tool call requires task_id.

Always use exactly:

"{TASK_ID}"

For the initial user request:

1. Understand the user's requirements.
2. Call list_products.
3. Evaluate the real catalog results.
4. Choose the single best matching product.
5. Call propose_purchase_intent.

After propose_purchase_intent succeeds, STOP.

IMPORTANT:
You are NOT authorized to create an order in this phase.

Do NOT call:
- create_order
- finalize_payment
- confirm_purchase_intent

A human must explicitly confirm the purchase outside the model, unless
an existing SpendingEnvelope already covers it - either way, that
decision happens outside the model, never inside it.

After proposing the purchase, report:
- product name
- price
- why it matches the user's requirements

Use only information from the real catalog.

Never invent:
- products
- prices
- specifications
- availability
- discounts

Do not claim an order was created.

Do not claim payment was completed.
"""


CREATE_ORDER_SYSTEM_INSTRUCTION = f"""
You are an AI buyer agent for a laptop store.

You are now in the ORDER CREATION phase.

The application has already authorized the purchase intent - either
through explicit human confirmation, or automatically through an
existing SpendingEnvelope (delegated spending authority) that already
covered this exact agent, merchant, and amount.

That authorization decision was made entirely outside the model, by
the application's authorization layer.

Every MCP tool call requires task_id.

Always use exactly:

"{TASK_ID}"

Your job in this phase is:

1. Call create_order for the already-confirmed purchase intent.
2. Return the result of create_order.
3. Do not ask the human for confirmation again.

IMPORTANT:

The application has already handled authorization, by whichever path
applied.

You ARE authorized to call:
- create_order

You are NOT authorized to call:
- confirm_purchase_intent
- finalize_payment

Do not invent an order ID.

Do not claim that an order was created unless the create_order
tool actually returns a successful result.

Do not attempt payment in this phase.
"""


FINALIZE_PAYMENT_SYSTEM_INSTRUCTION = f"""
You are an AI buyer agent for a laptop store.

You are now in the PAYMENT FINALIZATION phase.

The application has already received and independently verified
the payment callback from the checkout system.

The application will provide the payment identifiers needed
for finalization.

Every MCP tool call requires task_id.

Always use exactly:

"{TASK_ID}"

Your job in this phase is:

1. Call finalize_payment using the payment information supplied
   by the application.
2. Return the actual result from finalize_payment.

You ARE authorized to call:
- finalize_payment

You are NOT authorized to call:
- create_order
- confirm_purchase_intent

Do not ask the human for payment confirmation again.

Do not invent:
- payment IDs
- signatures
- order IDs
- payment status

Do not claim payment was finalized unless the finalize_payment
tool actually returns a successful result.
"""


# ============================================================================
# MCP SERVER
# ============================================================================


def get_server_params() -> StdioServerParameters:
    """
    Build the MCP stdio server configuration.
    """

    env = os.environ.copy()

    # The merchant MCP server uses this token to authorize the agent.
    env["AGENT_TOKEN"] = AGENT_TOKEN

    return StdioServerParameters(
        command=sys.executable,
        args=[
            str(MANAGE_PY),
            "run_mcp_server",
        ],
        env=env,
    )


# ============================================================================
# GEMINI
# ============================================================================


async def ask_gemini(
    client: genai.Client,
    session: ClientSession,
    prompt: str,
    system_instruction: str,
):
    """
    Send a request to Gemini with the live MCP session.

    The system instruction is supplied per phase so that:
      STEP 1  -> discovery only
      STEP 3  -> create_order allowed
      STEP 6  -> finalize_payment allowed

    We intentionally pass a plain dictionary as config.
    """

    print(
        f"AFC is enabled with max remote calls: "
        f"{MAX_REMOTE_CALLS}."
    )

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "system_instruction": system_instruction,
                "tools": [session],
                "automatic_function_calling": {
                    "maximum_remote_calls": MAX_REMOTE_CALLS,
                },
            },
        )

        return response

    except Exception as exc:
        print()
        print(
            f"Gemini request failed using model "
            f"{GEMINI_MODEL}:"
        )
        print(f"{type(exc).__name__}: {exc}")
        print()

        raise


# ============================================================================
# MCP RESULT PARSING
# ============================================================================


def parse_tool_result(
    value: Any,
) -> dict[str, Any] | None:
    """
    Parse the MCP response shape used by this project.

    The server may return nested structures such as:

        FunctionResponse
            response
                result
                    CallToolResult
                        content
                            text
                                JSON string
                                    {
                                        "status": "ok",
                                        ...
                                    }

    This function recursively unwraps the possible layers.
    """

    if value is None:
        return None

    # ------------------------------------------------------------------------
    # Dictionary
    # ------------------------------------------------------------------------

    if isinstance(value, dict):

        # Final result:
        #
        # {
        #     "status": "ok",
        #     ...
        # }
        #
        if "status" in value:
            return value

        # Wrapper:
        #
        # {
        #     "result": ...
        # }
        #
        if "result" in value:

            result = parse_tool_result(
                value["result"]
            )

            if result is not None:
                return result

        # MCP content:
        #
        # {
        #     "content": [
        #         {
        #             "type": "text",
        #             "text": "..."
        #         }
        #     ]
        # }
        #
        content = value.get("content")

        if isinstance(content, list):

            for item in content:

                if not isinstance(item, dict):
                    continue

                text = item.get("text")

                if not isinstance(text, str):
                    continue

                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError:
                    continue

                result = parse_tool_result(
                    decoded
                )

                if result is not None:
                    return result

        # Possible structured content.
        structured = value.get(
            "structured_content"
        )

        if structured is not None:

            result = parse_tool_result(
                structured
            )

            if result is not None:
                return result

        return None

    # ------------------------------------------------------------------------
    # Pydantic / MCP object
    # ------------------------------------------------------------------------

    model_dump = getattr(
        value,
        "model_dump",
        None,
    )

    if callable(model_dump):

        try:

            dumped = model_dump(
                exclude_none=False
            )

            result = parse_tool_result(
                dumped
            )

            if result is not None:
                return result

        except Exception:
            pass

    # ------------------------------------------------------------------------
    # Generic object with .result
    # ------------------------------------------------------------------------

    result_attr = getattr(
        value,
        "result",
        None,
    )

    if result_attr is not None:

        result = parse_tool_result(
            result_attr
        )

        if result is not None:
            return result

    # ------------------------------------------------------------------------
    # Generic object with .content
    # ------------------------------------------------------------------------

    content_attr = getattr(
        value,
        "content",
        None,
    )

    if content_attr is not None:

        for item in content_attr:

            text = getattr(
                item,
                "text",
                None,
            )

            if not isinstance(text, str):
                continue

            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue

            result = parse_tool_result(
                decoded
            )

            if result is not None:
                return result

    return None


def find_tool_result(
    response: Any,
    tool_name: str,
) -> dict[str, Any] | None:
    """
    Find a particular MCP function response inside Gemini's
    automatic function-calling history.
    """

    history = getattr(
        response,
        "automatic_function_calling_history",
        None,
    )

    if not history:
        return None

    for turn in history:

        parts = getattr(
            turn,
            "parts",
            None,
        ) or []

        for part in parts:

            function_response = getattr(
                part,
                "function_response",
                None,
            )

            if function_response is None:
                continue

            if function_response.name != tool_name:
                continue

            return parse_tool_result(
                function_response.response
            )

    return None


# ============================================================================
# DJANGO SETUP (shared)
# ============================================================================


def _ensure_django() -> None:
    """
    Idempotent Django bootstrap shared by every sync helper below.
    Safe to call more than once per process - django.apps.apps.ready
    guards against re-running django.setup().
    """

    import django

    backend_path = str(BACKEND)

    if backend_path not in sys.path:
        sys.path.insert(
            0,
            backend_path,
        )

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "config.settings.dev",
    )

    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()


# ============================================================================
# DJANGO AUTHORIZATION
# ============================================================================


def confirm_purchase_sync(
    intent_id: str,
) -> None:
    """
    Perform the Django authorization operation.

    IMPORTANT:

    Gemini never receives this function as a tool.

    Python calls it only after the human explicitly enters "y".
    """

    _ensure_django()

    from apps.commerce.authorization import (
        confirm_purchase_intent,
    )

    confirm_purchase_intent(
        intent_id
    )


async def confirm_purchase(
    intent_id: str,
) -> None:
    """
    Run synchronous Django ORM work safely outside
    the asyncio event loop.
    """

    await sync_to_async(
        confirm_purchase_sync,
        thread_sensitive=True,
    )(intent_id)


def try_auto_confirm_via_envelope_sync(
    intent_id: str,
) -> bool:
    """
    Attempt automatic confirmation via an existing SpendingEnvelope.

    IMPORTANT:

    Gemini never receives this function as a tool, and never receives
    any tool that could create, extend, or revoke a SpendingEnvelope -
    that authority is structurally unreachable from inside the model,
    same as confirm_purchase_intent itself. This function only ever
    checks whether a human/operator has ALREADY delegated bounded
    spending authority ahead of time; it never grants any authority
    itself.

    Returns True if the intent was auto-confirmed (an active envelope
    with matching agent+merchant+currency had enough remaining balance,
    and confirm_purchase_intent has already run for real). Returns
    False if nothing was touched at all - the intent stays PENDING and
    the caller must fall back to the existing manual human-confirm gate
    unchanged.
    """

    _ensure_django()

    from apps.commerce.envelope import try_auto_confirm_via_envelope

    return try_auto_confirm_via_envelope(intent_id)


async def try_auto_confirm_via_envelope(
    intent_id: str,
) -> bool:
    """
    Async wrapper, run outside the asyncio event loop, same pattern as
    confirm_purchase().
    """

    return await sync_to_async(
        try_auto_confirm_via_envelope_sync,
        thread_sensitive=True,
    )(intent_id)


# ============================================================================
# PAYMENT
# ============================================================================


async def wait_for_payment(
    order_id: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """
    Poll the local checkout status endpoint until payment is ready.
    """

    url = (
        f"{SITE_URL}"
        f"/checkout/{order_id}/status/"
    )

    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    print()
    print("=" * 70)
    print("WAITING FOR PAYMENT")
    print("=" * 70)
    print()
    print(
        f"Payment status: {url}"
    )
    print()

    async with httpx.AsyncClient(
        timeout=10,
    ) as http:

        while time.monotonic() < deadline:

            try:

                response = await http.get(
                    url
                )

                response.raise_for_status()

                data = response.json()

            except (
                httpx.HTTPError,
                ValueError,
            ) as exc:

                print(
                    f"Payment status error: {exc}"
                )

                await asyncio.sleep(2)

                continue

            if data.get("status") == "ready":

                print(
                    "Payment callback received."
                )

                return data

            print(
                "Waiting for Razorpay payment..."
            )

            await asyncio.sleep(2)

    raise TimeoutError(
        "Timed out waiting for payment."
    )


# ============================================================================
# HELPERS
# ============================================================================


def print_agent_response(
    response: Any,
) -> None:
    """
    Safely print Gemini's textual response.
    """

    print(
        "Agent:"
    )

    text = getattr(
        response,
        "text",
        None,
    )

    if text:
        print(text)
    else:
        print(
            "[No textual response returned. "
            "The model may have completed the operation "
            "through tool calls.]"
        )

    print()


def require_success(
    result: dict[str, Any] | None,
    tool_name: str,
) -> dict[str, Any]:
    """
    Validate a tool result.
    """

    if not result:
        raise RuntimeError(
            f"Could not extract "
            f"{tool_name} result from Gemini's "
            f"automatic function-calling history."
        )

    if result.get("status") != "ok":
        raise RuntimeError(
            f"{tool_name} failed: {result}"
        )

    return result


# ============================================================================
# STEP 1
# ============================================================================


async def find_product_and_propose_intent(
    client: genai.Client,
    session: ClientSession,
    user_request: str,
) -> str:
    """
    Step 1:
      User request
        -> Gemini
        -> list_products
        -> propose_purchase_intent
        -> intent_id
    """

    print()
    print("=" * 70)
    print("STEP 1: FINDING PRODUCT")
    print("=" * 70)
    print()

    response = await ask_gemini(
        client,
        session,
        user_request,
        STEP1_SYSTEM_INSTRUCTION,
    )

    print_agent_response(
        response
    )

    proposal = find_tool_result(
        response,
        "propose_purchase_intent",
    )

    proposal = require_success(
        proposal,
        "propose_purchase_intent",
    )

    intent_id = proposal.get(
        "intent_id"
    )

    if not intent_id:
        raise RuntimeError(
            "Purchase proposal succeeded "
            "but returned no intent_id.\n"
            f"Result: {proposal}"
        )

    print(
        f"Purchase intent: {intent_id}"
    )

    return intent_id


# ============================================================================
# STEP 2
# ============================================================================


async def require_human_confirmation(
    intent_id: str,
) -> None:
    """
    Step 2:
      Authorize the purchase intent, either:

      (a) automatically, if an active SpendingEnvelope already covers
          this agent + merchant + currency + amount (checked FIRST,
          before ever prompting the human), or

      (b) via the existing, unchanged manual human-confirmation gate,
          if (a) does not apply.

    HARD SECURITY BOUNDARY, unchanged from before this feature existed:
    Gemini is never given either confirm_purchase_intent or the
    envelope auto-confirm path as a tool. Both are called only by
    Python, never by the model - one after a human explicitly enters
    "y", the other only after checking a pre-existing, human-created
    SpendingEnvelope. The agent cannot expand its own authority either
    way.
    """

    print()
    print("=" * 70)
    print("AUTHORIZATION")
    print("=" * 70)
    print()

    print(
        "Checking for an existing SpendingEnvelope covering this "
        "agent and merchant..."
    )

    auto_confirmed, reason = await try_auto_confirm_via_envelope(
        intent_id
    )

    if auto_confirmed:

        print()
        print(
            "Auto-confirmed via SpendingEnvelope - within a "
            "pre-authorized spending limit, so no human confirmation "
            "was required for this specific purchase."
        )

        return

    if reason == "insufficient_balance":
        print(
            "The pre-authorized spending envelope has been exhausted "
            "for this purchase amount - proceeding to manual "
            "confirmation."
        )
    elif reason == "no_envelope":
        print(
            "No pre-authorized spending envelope covers this purchase "
            "(none exists, expired, or wrong merchant) - proceeding "
            "to manual confirmation."
        )
    else:
        print(
            "Envelope auto-confirmation did not apply - proceeding "
            "to manual confirmation."
        )

    print()
    print("=" * 70)
    print("HUMAN CONFIRMATION REQUIRED")
    print("=" * 70)
    print()

    answer = input(
        f"Confirm purchase "
        f"(intent {intent_id})? [y/N]: "
    ).strip().lower()

    if answer != "y":

        print()
        print(
            "Purchase not confirmed."
        )
        print(
            "Stopping."
        )

        raise SystemExit(0)

    print()
    print(
        "Confirming purchase..."
    )

    # HARD SECURITY BOUNDARY:
    #
    # Python performs the authorization only after
    # the human explicitly entered "y".
    #
    # Gemini cannot call this function.

    await confirm_purchase(
        intent_id
    )

    print(
        "Purchase confirmed."
    )

    print(
        "Authorization policy written."
    )


# ============================================================================
# STEP 3
# ============================================================================


async def create_order(
    client: genai.Client,
    session: ClientSession,
    intent_id: str,
) -> str:
    """
    Step 3:
      Already-authorized intent
        -> Gemini
        -> create_order
        -> order_id
    """

    print()
    print("=" * 70)
    print("STEP 3: CREATING ORDER")
    print("=" * 70)
    print()

    prompt = (
        "The application has already authorized the purchase, either "
        "through explicit human confirmation or an existing "
        "SpendingEnvelope.\n\n"
        f"Confirmed purchase intent: {intent_id}\n\n"
        "Call create_order now.\n"
        f'Use task_id "{TASK_ID}".'
    )

    response = await ask_gemini(
        client,
        session,
        prompt,
        CREATE_ORDER_SYSTEM_INSTRUCTION,
    )

    print_agent_response(
        response
    )

    order = find_tool_result(
        response,
        "create_order",
    )

    order = require_success(
        order,
        "create_order",
    )

    order_id = order.get(
        "order_id"
    )

    if not order_id:
        raise RuntimeError(
            "create_order succeeded "
            "but returned no order_id.\n"
            f"Result: {order}"
        )

    print(
        f"Order created: {order_id}"
    )

    return order_id


# ============================================================================
# STEP 4
# ============================================================================


def open_checkout(
    order_id: str,
) -> None:
    """
    Open the checkout page in the user's browser.
    """

    checkout_url = (
        f"{SITE_URL}"
        f"/checkout/{order_id}/"
    )

    print()
    print("=" * 70)
    print("STEP 4: OPENING CHECKOUT")
    print("=" * 70)
    print()

    print(
        f"Checkout: {checkout_url}"
    )

    print()

    opened = webbrowser.open(
        checkout_url
    )

    if not opened:

        print(
            "Could not open browser automatically."
        )

        print(
            f"Open manually: {checkout_url}"
        )


# ============================================================================
# STEP 5
# ============================================================================


async def get_verified_payment(
    order_id: str,
) -> dict[str, Any]:
    """
    Step 5:
      Wait for the checkout application to report
      a completed payment callback.
    """

    return await wait_for_payment(
        order_id
    )


# ============================================================================
# STEP 6
# ============================================================================


async def finalize_payment(
    client: genai.Client,
    session: ClientSession,
    intent_id: str,
    payment: dict[str, Any],
) -> dict[str, Any]:
    """
    Step 6:
      Verified payment callback
        -> Gemini
        -> finalize_payment
        -> final result
    """

    print()
    print("=" * 70)
    print("STEP 6: FINALIZING PAYMENT")
    print("=" * 70)
    print()

    razorpay_order_id = payment.get(
        "razorpay_order_id"
    )

    razorpay_payment_id = payment.get(
        "razorpay_payment_id"
    )

    razorpay_signature = payment.get(
        "razorpay_signature"
    )

    if not all(
        (
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
        )
    ):
        raise RuntimeError(
            "Payment callback is missing "
            "one or more required Razorpay fields."
        )

    prompt = (
        "Payment has already been completed and the "
        "application has received the payment callback.\n\n"
        f'Intent ID: "{intent_id}"\n'
        f'Razorpay order ID: "{razorpay_order_id}"\n'
        f'Razorpay payment ID: "{razorpay_payment_id}"\n'
        f'Razorpay signature: "{razorpay_signature}"\n'
        f'Task ID: "{TASK_ID}"\n\n'
        "Call finalize_payment now using exactly these values."
    )

    response = await ask_gemini(
        client,
        session,
        prompt,
        FINALIZE_PAYMENT_SYSTEM_INSTRUCTION,
    )

    print_agent_response(
        response
    )

    final = find_tool_result(
        response,
        "finalize_payment",
    )

    final = require_success(
        final,
        "finalize_payment",
    )

    return final


# ============================================================================
# MAIN BUYER FLOW
# ============================================================================


async def run(
    user_request: str,
) -> None:

    print()
    print("=" * 70)
    print("AI BUYER AGENT")
    print("=" * 70)
    print()

    print(
        f"User request: {user_request}"
    )

    print()

    print(
        f"Gemini model: {GEMINI_MODEL}"
    )

    print()

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    try:

        # ====================================================================
        # MCP SESSION
        # ====================================================================

        print(
            "Starting merchant MCP server..."
        )

        print()

        async with stdio_client(
            get_server_params()
        ) as (read, write):

            async with ClientSession(
                read,
                write,
            ) as session:

                print(
                    "Initializing MCP session..."
                )

                await session.initialize()

                print(
                    "MCP session initialized."
                )

                # ============================================================
                # STEP 1
                # ============================================================

                intent_id = (
                    await find_product_and_propose_intent(
                        client,
                        session,
                        user_request,
                    )
                )

                # ============================================================
                # STEP 2
                # ============================================================

                await require_human_confirmation(
                    intent_id
                )

                # ============================================================
                # STEP 3
                # ============================================================

                order_id = await create_order(
                    client,
                    session,
                    intent_id,
                )

                # ============================================================
                # STEP 4
                # ============================================================

                open_checkout(
                    order_id
                )

                # ============================================================
                # STEP 5
                # ============================================================

                payment = await get_verified_payment(
                    order_id
                )

                # ============================================================
                # STEP 6
                # ============================================================

                final = await finalize_payment(
                    client,
                    session,
                    intent_id,
                    payment,
                )

                # ============================================================
                # SUCCESS
                # ============================================================

                print()
                print("=" * 70)
                print("PURCHASE COMPLETE")
                print("=" * 70)
                print()

                print(
                    f"Intent: {intent_id}"
                )

                print(
                    f"Order:  {order_id}"
                )

                print(
                    "Payment successfully finalized."
                )

                print()

                print(
                    "Final payment result:"
                )

                print(
                    json.dumps(
                        final,
                        indent=2,
                        default=str,
                    )
                )

                print()

    except SystemExit:
        raise

    except KeyboardInterrupt:

        print()
        print(
            "Interrupted by user."
        )

    except Exception as exc:

        print()
        print("=" * 70)
        print("BUYER AGENT FAILED")
        print("=" * 70)
        print()

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print()

        # Re-raise so the process still has a non-zero exit code.
        raise

    finally:

        await client.aio.aclose()


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == "__main__":

    request = (
        " ".join(sys.argv[1:])
        or
        "Find me the best laptop under 60000 rupees "
        "with at least 16GB RAM"
    )

    asyncio.run(
        run(request)
    )