from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
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
          document.getElementById('result').textContent =
            "intent_id: {order.purchase_intent.intent_id}\\n" +
            "razorpay_order_id: " + response.razorpay_order_id + "\\n" +
            "razorpay_payment_id: " + response.razorpay_payment_id + "\\n" +
            "razorpay_signature: " + response.razorpay_signature +
            "\\n\\nCopy these into finalize_payment.";
        }}
      }};
      new Razorpay(options).open();
    }};
  </script>
</body></html>"""
    return HttpResponse(html)


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
        parameters={
            "intent_id": intent_id,
            "amount": propose["result"]["canonical_amount_minor"],
            "currency": propose["result"]["currency"],
        },
    )
    if create["decision"] != "ALLOW" or create["result"].get("status") != "ok":
        return HttpResponse(f"Could not create order: {create}", status=400)

    return redirect("checkout", order_id=create["result"]["order_id"])