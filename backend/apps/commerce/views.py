import json
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from apps.commerce.models import Order, Product
from apps.tools.mcp_dispatch import dispatch_tool_call
from apps.commerce.authorization import confirm_purchase_intent


def catalog_view(request):
    products = Product.objects.filter(active=True)
    return render(request, "commerce/catalog.html", {"products": products})


def product_detail_view(request, product_id):
    product = get_object_or_404(Product, product_id=product_id, active=True)
    related_products = Product.objects.filter(active=True).exclude(product_id=product_id)[:3]
    return render(request, "commerce/product_detail.html", {"product": product, "related_products": related_products})


@csrf_exempt
def payment_callback_view(request, order_id):
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)
    data = json.loads(request.body)
    order = get_object_or_404(Order, order_id=order_id)
    order.razorpay_payment_id = data.get("razorpay_payment_id", "")
    order.pending_signature = data.get("razorpay_signature", "")
    order.save(update_fields=["razorpay_payment_id", "pending_signature", "updated_at"])
    return JsonResponse({"status": "received"})


def payment_status_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    if order.razorpay_payment_id and order.pending_signature:
        return JsonResponse({
            "status": "ready",
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": order.razorpay_payment_id,
            "razorpay_signature": order.pending_signature,
        })
    return JsonResponse({"status": "waiting"})


def checkout_view(request, order_id):
    try:
        order = Order.objects.select_related("purchase_intent__product").get(order_id=order_id)
    except Order.DoesNotExist:
        raise Http404("Order not found")

    html = f"""<!DOCTYPE html>
<html><head><title>Checkout - {order.order_id}</title></head>
<body style="font-family: sans-serif; max-width: 480px; margin: 60px auto; text-align: center;">
  <h2>{order.purchase_intent.product.name}</h2>
  <p>Amount: {order.amount_minor / 100:.2f} {order.currency}</p>
  <button id="pay-btn" style="padding: 12px 24px; font-size: 16px;">Pay with Razorpay (Test Mode)</button>
  <pre id="result" style="text-align: left; background: #f4f4f4; padding: 12px; margin-top: 24px; white-space: pre-wrap;"></pre>
  <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
  <script>
    document.getElementById('pay-btn').onclick = function () {{
      var options = {{
        key: "{settings.RAZORPAY_KEY_ID}",
        amount: "{order.amount_minor}",
        currency: "{order.currency}",
        order_id: "{order.razorpay_order_id}",
        name: "Reference Merchant (Buildathon POC)",
        description: "{order.purchase_intent.product.name}",
        handler: function (response) {{
          fetch("/checkout/{order.order_id}/callback/", {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify(response),
          }}).then(function () {{
            document.getElementById('result').innerHTML =
              "Payment received - you can close this tab, the agent will pick it up automatically." +
              '<br><br><a href="/checkout/{order.purchase_intent.intent_id}/audit/" class="btn btn-outline-primary btn-sm">View purchase audit</a>';
          }});
        }}
      }};
      new Razorpay(options).open();
    }};
  </script>
</body></html>"""
    return HttpResponse(html)


def audit_trail_view(request, intent_id):
    """
    Server-rendered decision timeline for one purchase. Re-verifies the
    mandate signature live on every load - this page is independent
    proof, not a cached claim. A missing or corrupted mandate must never
    crash this page; every failure path resolves to an explicit status
    instead of an unhandled exception.
    """
    from apps.commerce.models import PurchaseIntent
    from apps.commerce.mandate import verify_mandate, MandateError
    from datetime import datetime
    from apps.audit.models import AuditEvent

    intent = get_object_or_404(
        PurchaseIntent.objects.select_related("task__agent", "product"), intent_id=intent_id
    )
    events = AuditEvent.objects.filter(resource_id=intent_id).order_by("timestamp")
    order = getattr(intent, "order", None)
    mandate = getattr(intent, "mandate", None)

    from apps.commerce.mandate import verify_signature_only

    mandate_status = "UNAVAILABLE"
    mandate_detail = None
    signature_valid = None
    not_expired = None
    if mandate is not None:
        signature_valid = verify_signature_only(mandate)
        expires_at_raw = mandate.payload.get("expires_at")
        not_expired = bool(expires_at_raw) and timezone.now() <= datetime.fromisoformat(expires_at_raw)
        try:
            verify_mandate(mandate, intent_id)
            mandate_status = "VERIFIED"
        except MandateError as exc:
            mandate_status = "VERIFICATION_FAILED"
            mandate_detail = str(exc)
        except Exception as exc:  # noqa: BLE001 - this page must never 500, fail to a visible state instead
            mandate_status = "UNAVAILABLE"
            mandate_detail = str(exc)

    return render(request, "commerce/audit_trail.html", {
        "intent": intent,
        "events": events,
        "order": order,
        "mandate": mandate,
        "mandate_status": mandate_status,
        "mandate_detail": mandate_detail,
        "signature_valid": signature_valid,
        "not_expired": not_expired,
    })


def start_purchase_view(request, product_id):
    """
    Fixed-identity stand-in for the AI buyer agent (System 3, not built
    yet). Calls the same MCP-gated tools an autonomous agent would call,
    through the same authorization checks - the only difference from the
    "real" version is who's deciding to click it.
    """
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)
    if not settings.DEMO_AGENT_TOKEN:
        return HttpResponse(
            "Demo agent isn't set up yet - run `python manage.py seed_demo_agent` "
            "and add the printed DEMO_AGENT_TOKEN to .env.", status=503,
        )

    task_id = settings.DEMO_TASK_ID
    propose = dispatch_tool_call(
        tool_id="propose_purchase_intent", action="propose_purchase_intent",
        agent_token=settings.DEMO_AGENT_TOKEN, task_id=task_id,
        resource_type="", resource_id=None,
        parameters={"task_id": task_id, "product_id": product_id, "quantity": 1},
    )
    if propose["decision"] != "ALLOW" or propose["result"].get("status") != "ok":
        return HttpResponse(f"Could not start purchase: {propose}", status=400)

    intent_id = propose["result"]["intent_id"]
    confirm_purchase_intent(intent_id)

    create = dispatch_tool_call(
        tool_id="create_order", action="create_order",
        agent_token=settings.DEMO_AGENT_TOKEN, task_id=task_id,
        resource_type="purchase_intent", resource_id=intent_id,
        parameters={"intent_id": intent_id},
    )
    if create["decision"] != "ALLOW" or create["result"].get("status") != "ok":
        return HttpResponse(f"Could not create order: {create}", status=400)

    return redirect("checkout", order_id=create["result"]["order_id"])

def security_demo_view(request):
    """
    Runs one of three real attack scenarios against the actual
    dispatch_tool_call() path, using fresh disposable Agent/Task/Intent
    data each time - safe to click repeatedly, never touches real
    storefront demo data.
    """
    scenario = request.POST.get("scenario") if request.method == "POST" else None
    result = _run_security_scenario(scenario) if scenario else None
    return render(request, "commerce/security_demo.html", {"result": result, "scenario": scenario})


def _run_security_scenario(scenario: str) -> dict:
    import uuid
    from django.utils import timezone
    from datetime import timedelta
    from apps.agents.models import Agent, AgentStatus
    from apps.tasks.models import Task, TaskStatus
    from apps.policies.models import Policy, PolicyEffect, ResourceScopeMode
    from apps.tools.models import Tool
    from apps.commerce.models import Product, PurchaseMandate
    from apps.commerce.authorization import confirm_purchase_intent
    from apps.tools.mcp_dispatch import dispatch_tool_call
    from apps.commerce.razorpay_client import get_order_create_call_count

    suffix = uuid.uuid4().hex[:8]
    product = Product.objects.filter(active=True).first()
    if not product:
        return {"error": "No products found - run `python manage.py seed_products` first."}

    agent = Agent.objects.create(agent_id=f"secdemo-agent-{suffix}", name="Security Demo Agent", status=AgentStatus.ACTIVE)
    task = Task.objects.create(
        task_id=f"secdemo-task-{suffix}", agent=agent, user_id="secdemo-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=30),
    )
    raw_token = agent.issue_token()

    Policy.objects.create(
        policy_id=f"policy-{task.task_id}-propose-intent",
        name="Standing: propose purchase intent (security demo)",
        effect=PolicyEffect.ALLOW,
        agent_scope=agent, task_scope=task,
        tool_scope=Tool.objects.get(tool_id="propose_purchase_intent"),
        allowed_actions=["propose_purchase_intent"],
        resource_mode=ResourceScopeMode.NONE,
    )

    propose = dispatch_tool_call(
        tool_id="propose_purchase_intent", action="propose_purchase_intent",
        agent_token=raw_token, task_id=task.task_id, resource_type="", resource_id=None,
        parameters={"task_id": task.task_id, "product_id": product.product_id, "quantity": 1},
    )
    intent_id = propose["result"]["intent_id"]
    before_count = get_order_create_call_count()

    if scenario == "skip_confirmation":
        label = "Skip Confirmation"
        explanation = "Attempting create_order on a proposed but never-confirmed intent - no Policy exists yet for this tool."
        response = dispatch_tool_call(
            tool_id="create_order", action="create_order",
            agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id,
            parameters={"intent_id": intent_id},
        )

    elif scenario == "unknown_parameter":
        label = "Unknown Parameter Injection"
        explanation = "Confirming normally, then attempting create_order with an extra, undeclared parameter."
        confirm_purchase_intent(intent_id)
        response = dispatch_tool_call(
            tool_id="create_order", action="create_order",
            agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id,
            parameters={"intent_id": intent_id, "override_policy": True},
        )

    elif scenario == "tampered_mandate":
        label = "Tampered Mandate"
        explanation = "Confirming normally (signs a real mandate), then editing the stored payload directly before attempting create_order."
        confirm_purchase_intent(intent_id)
        mandate = PurchaseMandate.objects.get(intent__intent_id=intent_id)
        mandate.payload["amount_minor"] = 100
        mandate.save()
        response = dispatch_tool_call(
            tool_id="create_order", action="create_order",
            agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id,
            parameters={"intent_id": intent_id},
        )
    elif scenario == "tampered_amount_parameter":
        label = "Tampered Amount Parameter"
        explanation = (
            "Confirming normally, then attempting create_order with a "
            "forged 'amount' parameter (a fraction of the real price) "
            "smuggled into the call - simulating a client that lies "
            "about what it wants to pay."
        )
        confirm_purchase_intent(intent_id)
        response = dispatch_tool_call(
            tool_id="create_order", action="create_order",
            agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id,
            parameters={"intent_id": intent_id, "amount": 100, "currency": "INR"},
        )
    else:
        return {"error": f"Unknown scenario '{scenario}'."}

    after_count = get_order_create_call_count()

    return {
        "label": label,
        "explanation": explanation,
        "decision": response.get("decision"),
        "reason_code": response.get("reason_code"),
        "reason": response.get("reason"),
        "result": response.get("result"),
        "razorpay_calls_made": after_count - before_count,
    }

def concurrency_demo_view(request):
    return render(request, "commerce/concurrency_demo.html", {})


@csrf_exempt
def start_concurrency_race_view(request):
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)
    from apps.commerce.concurrency_demo import start_race
    race_id = start_race()
    return JsonResponse({"race_id": race_id})


def concurrency_race_status_view(request, race_id):
    from apps.commerce.concurrency_demo import get_race_status
    status = get_race_status(race_id)
    if status is None:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(status)