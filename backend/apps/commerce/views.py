from django.http import HttpResponse, Http404
from django.conf import settings
from apps.commerce.models import Order


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