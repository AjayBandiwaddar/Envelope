"""
Live demo: sign a real purchase mandate, verify it (valid), tamper one
field, verify again (rejected). Run from backend/ with the venv active:

    python scripts/demo_tampered_mandate.py

Safe to run repeatedly - creates a fresh Agent/Task/Intent each time
rather than depending on demo data left over from anything else.
"""
import os
import sys
import uuid
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.utils import timezone
from datetime import timedelta
from apps.agents.models import Agent, AgentStatus
from apps.tasks.models import Task, TaskStatus
from apps.commerce.models import Product, PurchaseIntent, PurchaseIntentStatus
from apps.commerce.authorization import confirm_purchase_intent
from apps.commerce.mandate import verify_mandate, MandateError


def main():
    suffix = uuid.uuid4().hex[:8]
    product = Product.objects.filter(active=True).first()
    if not product:
        sys.exit("No products found - run `python manage.py seed_products` first.")

    agent = Agent.objects.create(agent_id=f"demo-mandate-agent-{suffix}", name="Demo Mandate Agent", status=AgentStatus.ACTIVE)
    task = Task.objects.create(
        task_id=f"demo-mandate-task-{suffix}", agent=agent, user_id="demo-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=30),
    )
    intent = PurchaseIntent.objects.create(
        intent_id=f"demo-mandate-intent-{suffix}", task=task, agent_id=agent.agent_id, user_id=task.user_id,
        product=product, quantity=1, canonical_amount_minor=product.price_minor,
        currency=product.currency, status=PurchaseIntentStatus.PENDING,
    )

    print("=" * 70)
    print(f"Signing a purchase mandate for: {product.name} - {product.price_minor / 100:.2f} {product.currency}")
    print("=" * 70)
    confirm_purchase_intent(intent.intent_id)
    mandate = intent.mandate
    print(f"\nMandate ID: {mandate.mandate_id}")
    print(f"Signed amount_minor: {mandate.payload['amount_minor']}")

    print("\n--- Verifying the untouched mandate ---")
    try:
        verify_mandate(mandate, intent.intent_id)
        print("VALID - signature and all bound fields match. Purchase would proceed.")
    except MandateError as exc:
        print(f"UNEXPECTED REJECTION: {exc}")
        return

    print("\n--- Tampering the signed payload (changing amount_minor to 100) ---")
    mandate.payload["amount_minor"] = 100
    mandate.save()

    print("--- Re-verifying the tampered mandate ---")
    try:
        verify_mandate(mandate, intent.intent_id)
        print("BUG: tampered mandate was accepted. This should never happen.")
    except MandateError as exc:
        print(f"REJECTED: {exc}")
        print("\nNo Razorpay call was made. The tampered transaction never reached the payment layer.")


if __name__ == "__main__":
    main()