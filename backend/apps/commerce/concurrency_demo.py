from __future__ import annotations
import threading
import time
import uuid
from datetime import timedelta
from django.utils import timezone

_races_lock = threading.Lock()
_races: dict[str, dict] = {}
# In-memory only - resets on server restart. This is a demo/visualization
# tool, not production state; the actual correctness guarantee lives in
# try_auto_confirm_via_envelope() and is proven independently by
# test_two_concurrent_purchases_never_overdraw_envelope with NO
# artificial delay. Everything here just makes that same real behavior
# watchable in a browser.

RACE_ENVELOPE_BALANCE_MINOR = 100000       # covers exactly ONE attempt
PER_ATTEMPT_AMOUNT_MINOR = 100000
NUM_CONCURRENT_ATTEMPTS = 3
VISUALIZATION_STAGGER_SECONDS = 0.6         # purely for legibility - see note above


def start_race() -> str:
    """
    Creates one fresh, disposable envelope with balance for exactly ONE
    of NUM_CONCURRENT_ATTEMPTS purchase attempts, then fires all
    attempts concurrently via real threads against the SAME
    try_auto_confirm_via_envelope() the automated test suite already
    proves is race-safe. Returns a race_id the frontend polls.
    """
    from apps.agents.models import Agent, AgentStatus
    from apps.tasks.models import Task, TaskStatus
    from apps.commerce.models import (
        Product, PurchaseIntent, PurchaseIntentStatus, Merchant,
        SpendingEnvelope, EnvelopeStatus,
    )
    from apps.commerce.envelope import try_auto_confirm_via_envelope

    race_id = uuid.uuid4().hex[:10]

    from apps.commerce.models import PurchaseMandate, Order, EnvelopeDebit

    PurchaseMandate.objects.filter(intent__intent_id__startswith="race-intent-").delete()
    Order.objects.filter(purchase_intent__intent_id__startswith="race-intent-").delete()
    EnvelopeDebit.objects.filter(intent__intent_id__startswith="race-intent-").delete()
    PurchaseIntent.objects.filter(intent_id__startswith="race-intent-").delete()
    SpendingEnvelope.objects.filter(envelope_id__startswith="race-env-").delete()
    Product.objects.filter(product_id__startswith="race-product-").delete()
    Task.objects.filter(task_id__startswith="race-task-").delete()
    Agent.objects.filter(agent_id__startswith="race-agent-").delete()

    merchant, _ = Merchant.objects.get_or_create(
        merchant_id="reference-merchant", defaults={"name": "Reference Storefront"}
    )
    agent = Agent.objects.create(
        agent_id=f"race-agent-{race_id}", name="Concurrency Demo Agent", status=AgentStatus.ACTIVE
    )
    task = Task.objects.create(
        task_id=f"race-task-{race_id}", agent=agent, user_id="race-demo-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=10),
    )
    product = Product.objects.create(
        product_id=f"race-product-{race_id}", name="Concurrency Demo Item",
        price_minor=PER_ATTEMPT_AMOUNT_MINOR, currency="INR", merchant=merchant,
        active=False,
    )
    envelope = SpendingEnvelope.objects.create(
        envelope_id=f"race-env-{race_id}", agent=agent, merchant=merchant,
        max_amount_minor=RACE_ENVELOPE_BALANCE_MINOR,
        remaining_amount_minor=RACE_ENVELOPE_BALANCE_MINOR,
        currency="INR", status=EnvelopeStatus.ACTIVE,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    intents = []
    for i in range(NUM_CONCURRENT_ATTEMPTS):
        intent = PurchaseIntent.objects.create(
            intent_id=f"race-intent-{race_id}-{i}", task=task, agent_id=agent.agent_id,
            user_id=task.user_id, product=product, quantity=1,
            canonical_amount_minor=PER_ATTEMPT_AMOUNT_MINOR, currency="INR",
            status=PurchaseIntentStatus.PENDING,
        )
        intents.append(intent)

    with _races_lock:
        _races[race_id] = {
            "envelope_id": envelope.envelope_id,
            "max_balance": RACE_ENVELOPE_BALANCE_MINOR,
            "attempts": {
                i: {"status": "PENDING", "intent_id": intents[i].intent_id}
                for i in range(NUM_CONCURRENT_ATTEMPTS)
            },
            "done": False,
            "final_remaining": None,
        }

    barrier = threading.Barrier(NUM_CONCURRENT_ATTEMPTS)

    def _attempt(index: int, intent_id: str):
        barrier.wait()
        time.sleep(index * VISUALIZATION_STAGGER_SECONDS * 0.15)
        try:
            confirmed, reason = try_auto_confirm_via_envelope(intent_id)
        except Exception as exc:
            confirmed, reason = False, f"error: {exc}"
        with _races_lock:
            _races[race_id]["attempts"][index]["status"] = "HELD" if confirmed else "DENIED"
            _races[race_id]["attempts"][index]["reason"] = reason
        time.sleep(VISUALIZATION_STAGGER_SECONDS)

    threads = [
        threading.Thread(target=_attempt, args=(i, intents[i].intent_id))
        for i in range(NUM_CONCURRENT_ATTEMPTS)
    ]
    for t in threads:
        t.start()

    def _finalize():
        for t in threads:
            t.join()
        envelope.refresh_from_db()
        with _races_lock:
            _races[race_id]["done"] = True
            _races[race_id]["final_remaining"] = envelope.remaining_amount_minor

    threading.Thread(target=_finalize, daemon=True).start()

    return race_id


def get_race_status(race_id: str) -> dict | None:
    with _races_lock:
        race = _races.get(race_id)
        if race is None:
            return None
        return {
            "envelope_id": race["envelope_id"],
            "max_balance": race["max_balance"],
            "attempts": dict(race["attempts"]),
            "done": race["done"],
            "final_remaining": race["final_remaining"],
        }