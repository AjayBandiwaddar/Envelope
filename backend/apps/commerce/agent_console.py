from __future__ import annotations
import asyncio
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ============================================================================
# CONFIG - duplicated from agent/buyer.py deliberately, so this module never
# imports buyer.py as live code (buyer.py has module-level sys.exit() calls
# that would be unsafe to trigger inside a Django worker thread/import).
# ============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND = REPO_ROOT / "backend"
MANAGE_PY = BACKEND / "manage.py"

load_dotenv(REPO_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AGENT_TOKEN = os.getenv("DEMO_AGENT_TOKEN", "")
TASK_ID = os.getenv("DEMO_TASK_ID", "demo-buyer-task")
SITE_URL = os.getenv("SITE_BASE_URL", "http://127.0.0.1:8000")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
MAX_REMOTE_CALLS = int(os.getenv("GEMINI_MAX_REMOTE_CALLS", "4"))
GEMINI_CALL_SPACING_SECONDS = int(os.getenv("GEMINI_CALL_SPACING_SECONDS", "15"))


class ConfigError(Exception):
    """Raised instead of sys.exit() - safe to catch inside a background thread."""


def _require_config() -> None:
    if not GEMINI_API_KEY:
        raise ConfigError("GEMINI_API_KEY is not set in .env.")
    if not AGENT_TOKEN:
        raise ConfigError("DEMO_AGENT_TOKEN is not set in .env. Run `python manage.py seed_demo_agent` first.")


STEP1_SYSTEM_INSTRUCTION = f"""
You are an AI buyer agent for a laptop store.
Understand the user's requirements, call list_products, choose the
single best matching product, and call propose_purchase_intent.
Always use task_id "{TASK_ID}".
Do NOT call create_order, finalize_payment, or confirm_purchase_intent.
Never invent products, prices, specifications, or availability.
"""

CREATE_ORDER_SYSTEM_INSTRUCTION = f"""
You are an AI buyer agent for a laptop store, now in the ORDER CREATION
phase. The application has already authorized this purchase - through
explicit human confirmation or an existing SpendingEnvelope. Always
use task_id "{TASK_ID}". Call create_order now. You are NOT authorized
to call confirm_purchase_intent or finalize_payment. Do not invent an
order ID.
"""

FINALIZE_PAYMENT_SYSTEM_INSTRUCTION = f"""
You are an AI buyer agent for a laptop store, now in the PAYMENT
FINALIZATION phase. The application has already verified the payment
callback and will supply the exact identifiers. Always use task_id
"{TASK_ID}". Call finalize_payment now using exactly the supplied
values. Do not invent payment IDs, signatures, or status.
"""


def get_server_params() -> StdioServerParameters:
    env = os.environ.copy()
    env["AGENT_TOKEN"] = AGENT_TOKEN
    return StdioServerParameters(command=sys.executable, args=[str(MANAGE_PY), "run_mcp_server"], env=env)


async def ask_gemini(client: genai.Client, session: ClientSession, prompt: str, system_instruction: str, retries: int = 2):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "system_instruction": system_instruction,
                    "tools": [session],
                    "automatic_function_calling": {"maximum_remote_calls": MAX_REMOTE_CALLS},
                },
            )
        except Exception as exc:
            last_exc = exc
            if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                await asyncio.sleep(5)
                continue
            raise
    raise last_exc


def parse_tool_result(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "status" in value:
            return value
        if "result" in value:
            result = parse_tool_result(value["result"])
            if result is not None:
                return result
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
                result = parse_tool_result(decoded)
                if result is not None:
                    return result
        structured = value.get("structured_content")
        if structured is not None:
            result = parse_tool_result(structured)
            if result is not None:
                return result
        return None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            result = parse_tool_result(model_dump(exclude_none=False))
            if result is not None:
                return result
        except Exception:
            pass
    result_attr = getattr(value, "result", None)
    if result_attr is not None:
        result = parse_tool_result(result_attr)
        if result is not None:
            return result
    content_attr = getattr(value, "content", None)
    if content_attr is not None:
        for item in content_attr:
            text = getattr(item, "text", None)
            if not isinstance(text, str):
                continue
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue
            result = parse_tool_result(decoded)
            if result is not None:
                return result
    return None


def find_tool_result(response: Any, tool_name: str) -> dict[str, Any] | None:
    history = getattr(response, "automatic_function_calling_history", None)
    if not history:
        return None
    for turn in history:
        for part in getattr(turn, "parts", None) or []:
            fr = getattr(part, "function_response", None)
            if fr is None or fr.name != tool_name:
                continue
            return parse_tool_result(fr.response)
    return None


def require_success(result: dict[str, Any] | None, tool_name: str) -> dict[str, Any]:
    if not result:
        raise RuntimeError(f"Could not extract {tool_name} result from Gemini's tool-call history.")
    if result.get("status") != "ok":
        raise RuntimeError(f"{tool_name} failed: {result}")
    return result


def _ensure_django() -> None:
    import django
    backend_path = str(BACKEND)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.apps import apps as django_apps
    if not django_apps.ready:
        django.setup()


def confirm_purchase_sync(intent_id: str) -> None:
    _ensure_django()
    from apps.commerce.authorization import confirm_purchase_intent
    confirm_purchase_intent(intent_id)


async def confirm_purchase(intent_id: str) -> None:
    await sync_to_async(confirm_purchase_sync, thread_sensitive=True)(intent_id)


def abandon_intent_sync(intent_id: str) -> None:
    _ensure_django()
    from apps.commerce.models import PurchaseIntent, PurchaseIntentStatus
    PurchaseIntent.objects.filter(intent_id=intent_id).update(status=PurchaseIntentStatus.ABANDONED)


async def abandon_intent(intent_id: str) -> None:
    await sync_to_async(abandon_intent_sync, thread_sensitive=True)(intent_id)


def try_auto_confirm_via_envelope_sync(intent_id: str) -> tuple[bool, str]:
    _ensure_django()
    from apps.commerce.envelope import try_auto_confirm_via_envelope as _try
    return _try(intent_id)


async def try_auto_confirm_via_envelope(intent_id: str) -> tuple[bool, str]:
    return await sync_to_async(try_auto_confirm_via_envelope_sync, thread_sensitive=True)(intent_id)


async def _rate_limit_pause():
    await asyncio.sleep(GEMINI_CALL_SPACING_SECONDS)


async def find_product_and_propose_intent(
    client: genai.Client, session: ClientSession, user_request: str,
    excluded_product_ids: list[str] | None = None,
) -> tuple[str, str, str]:
    prompt = user_request
    if excluded_product_ids:
        prompt += (
            f"\n\nDo NOT propose these product_ids again, the human already "
            f"rejected them: {', '.join(excluded_product_ids)}. Pick the next best genuinely different match."
        )
    await _rate_limit_pause()
    response = await ask_gemini(client, session, prompt, STEP1_SYSTEM_INSTRUCTION)
    proposal = require_success(find_tool_result(response, "propose_purchase_intent"), "propose_purchase_intent")
    intent_id = proposal.get("intent_id")
    if not intent_id:
        raise RuntimeError(f"No intent_id returned.\nResult: {proposal}")
    return intent_id, proposal.get("product_id", ""), proposal.get("product_name", "the proposed product")


async def create_order(client: genai.Client, session: ClientSession, intent_id: str) -> str:
    prompt = (
        "The application has already authorized this purchase.\n\n"
        f"Confirmed purchase intent: {intent_id}\n\nCall create_order now.\n"
        f'Use task_id "{TASK_ID}".'
    )
    await _rate_limit_pause()
    response = await ask_gemini(client, session, prompt, CREATE_ORDER_SYSTEM_INSTRUCTION)
    order = require_success(find_tool_result(response, "create_order"), "create_order")
    order_id = order.get("order_id")
    if not order_id:
        raise RuntimeError(f"No order_id returned.\nResult: {order}")
    return order_id


async def wait_for_payment(order_id: str, timeout_seconds: int = 300) -> dict[str, Any]:
    url = f"{SITE_URL}/checkout/{order_id}/status/"
    deadline = time.monotonic() + timeout_seconds
    async with httpx.AsyncClient(timeout=10) as http:
        while time.monotonic() < deadline:
            try:
                response = await http.get(url)
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError):
                await asyncio.sleep(2)
                continue
            if data.get("status") == "ready":
                return data
            await asyncio.sleep(2)
    raise TimeoutError("Timed out waiting for payment.")


async def finalize_payment(client: genai.Client, session: ClientSession, intent_id: str, payment: dict[str, Any]) -> dict[str, Any]:
    razorpay_order_id = payment.get("razorpay_order_id")
    razorpay_payment_id = payment.get("razorpay_payment_id")
    razorpay_signature = payment.get("razorpay_signature")
    if not all((razorpay_order_id, razorpay_payment_id, razorpay_signature)):
        raise RuntimeError("Payment callback missing required Razorpay fields.")
    prompt = (
        "Payment has already been completed and verified.\n\n"
        f'Intent ID: "{intent_id}"\nRazorpay order ID: "{razorpay_order_id}"\n'
        f'Razorpay payment ID: "{razorpay_payment_id}"\nRazorpay signature: "{razorpay_signature}"\n'
        f'Task ID: "{TASK_ID}"\n\nCall finalize_payment now using exactly these values.'
    )
    await _rate_limit_pause()
    response = await ask_gemini(client, session, prompt, FINALIZE_PAYMENT_SYSTEM_INSTRUCTION)
    return require_success(find_tool_result(response, "finalize_payment"), "finalize_payment")


# ============================================================================
# WEB-MODE ORCHESTRATION
# ============================================================================

_runs_lock = threading.Lock()
_runs: dict[str, dict] = {}


def _new_run_state(run_id: str) -> dict:
    return {
        "run_id": run_id, "stage": "STARTING", "log": [],
        "product_name": None, "checkout_url": None, "audit_url": None,
        "error": None, "done": False,
        "pending_decision": None, "decision_event": threading.Event(), "decision_value": None,
    }


def _log(run_id: str, message: str, stage: str | None = None):
    with _runs_lock:
        run = _runs[run_id]
        run["log"].append(message)
        if stage:
            run["stage"] = stage


def start_run(prompt: str) -> str:
    run_id = uuid.uuid4().hex[:10]
    with _runs_lock:
        _runs[run_id] = _new_run_state(run_id)
    threading.Thread(target=_run_pipeline_thread, args=(run_id, prompt), daemon=True).start()
    return run_id


def get_run_status(run_id: str) -> dict | None:
    with _runs_lock:
        run = _runs.get(run_id)
        if run is None:
            return None
        return {k: v for k, v in run.items() if k != "decision_event"}


def submit_decision(run_id: str, decision: str) -> bool:
    with _runs_lock:
        run = _runs.get(run_id)
        if run is None or run["pending_decision"] is None:
            return False
        run["decision_value"] = decision
        run["pending_decision"] = None
    run["decision_event"].set()
    return True


def _wait_for_decision(run_id: str, kind: str) -> str:
    with _runs_lock:
        run = _runs[run_id]
        run["pending_decision"] = kind
        run["decision_event"].clear()
    run["decision_event"].wait()
    with _runs_lock:
        return _runs[run_id]["decision_value"]


def _run_pipeline_thread(run_id: str, prompt: str):
    try:
        asyncio.run(_run_pipeline_async(run_id, prompt))
    except Exception as exc:
        _log(run_id, f"Failed: {exc}", stage="ERROR")
        with _runs_lock:
            _runs[run_id]["error"] = str(exc)
            _runs[run_id]["done"] = True


async def _run_pipeline_async(run_id: str, prompt: str):
    try:
        _require_config()
    except ConfigError as exc:
        _log(run_id, str(exc), stage="ERROR")
        with _runs_lock:
            _runs[run_id]["error"] = str(exc)
            _runs[run_id]["done"] = True
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    _log(run_id, "Starting merchant MCP server...", stage="STARTING")

    try:
        async with stdio_client(get_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                excluded_product_ids: list[str] = []
                intent_id = None
                attempts = 0
                while intent_id is None and attempts < 4:
                    attempts += 1
                    _log(run_id, f"Searching catalog (attempt {attempts})...", stage="SEARCHING")
                    candidate_intent_id, candidate_product_id, product_name = (
                        await find_product_and_propose_intent(client, session, prompt, excluded_product_ids)
                    )
                    with _runs_lock:
                        _runs[run_id]["product_name"] = product_name
                    _log(run_id, f"Agent suggests: {product_name}", stage="FIT_CHECK")

                    decision = _wait_for_decision(run_id, "fit")
                    if decision == "yes":
                        intent_id = candidate_intent_id
                    else:
                        excluded_product_ids.append(candidate_product_id)
                        _log(run_id, "Not a fit - searching again...", stage="SEARCHING")
                        await abandon_intent(candidate_intent_id)

                if intent_id is None:
                    _log(run_id, "No fit found after 4 attempts.", stage="ERROR")
                    with _runs_lock:
                        _runs[run_id]["done"] = True
                    return

                _log(run_id, "Checking SpendingEnvelope authorization...", stage="AUTHORIZING")
                auto_confirmed, reason = await try_auto_confirm_via_envelope(intent_id)

                if auto_confirmed:
                    _log(run_id, "Auto-confirmed via SpendingEnvelope - no human approval needed.", stage="AUTHORIZED")
                else:
                    _log(run_id, f"No envelope coverage ({reason}) - manual approval required.", stage="CONFIRM_CHECK")
                    decision = _wait_for_decision(run_id, "confirm")
                    if decision != "yes":
                        _log(run_id, "Purchase declined by user.", stage="DECLINED")
                        with _runs_lock:
                            _runs[run_id]["done"] = True
                        return
                    await confirm_purchase(intent_id)
                    _log(run_id, "Manually confirmed.", stage="AUTHORIZED")

                _log(run_id, "Creating order...", stage="CREATING_ORDER")
                order_id = await create_order(client, session, intent_id)

                checkout_url = f"{SITE_URL}/checkout/{order_id}/"
                with _runs_lock:
                    _runs[run_id]["checkout_url"] = checkout_url
                _log(run_id, "Order created - complete payment in the checkout tab.", stage="AWAITING_PAYMENT")

                payment = await wait_for_payment(order_id)
                _log(run_id, "Payment received - finalizing...", stage="FINALIZING")

                await finalize_payment(client, session, intent_id, payment)

                audit_url = f"{SITE_URL}/checkout/{intent_id}/audit/"
                with _runs_lock:
                    _runs[run_id]["audit_url"] = audit_url
                    _runs[run_id]["done"] = True
                _log(run_id, "Purchase complete.", stage="COMPLETE")
    finally:
        await client.aio.aclose()