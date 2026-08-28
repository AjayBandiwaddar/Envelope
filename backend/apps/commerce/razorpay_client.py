from __future__ import annotations
import razorpay
from django.conf import settings

_client: razorpay.Client | None = None


def get_client() -> razorpay.Client:
    global _client
    if _client is None:
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not configured.")
        _client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return _client


# Process-local demo/test instrumentation only - counts real Razorpay
# order-creation calls made through this module. Not a production metrics
# system (resets on restart, not shared across workers); its only job is
# letting the security-demo page and its tests prove "the provider was
# never invoked" from an actual counter, not inferred from the absence
# of an Order row.
_order_create_call_count = 0


def get_order_create_call_count() -> int:
    return _order_create_call_count


def reset_order_create_call_count() -> None:
    global _order_create_call_count
    _order_create_call_count = 0


def create_razorpay_order(payload: dict) -> dict:
    """The only path through which real Razorpay order creation happens -
    create_order's handler calls this instead of the client directly, so
    every actual provider invocation is countable at one single point."""
    global _order_create_call_count
    _order_create_call_count += 1
    return get_client().order.create(payload)