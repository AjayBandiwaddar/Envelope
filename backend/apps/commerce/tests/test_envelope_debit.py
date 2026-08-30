import pytest
from django.utils import timezone
from datetime import timedelta
from apps.commerce.models import (
    Product, PurchaseIntent, PurchaseIntentStatus, PurchaseMandate,
    SpendingEnvelope, EnvelopeStatus, EnvelopeDebit, EnvelopeDebitStatus,
    Order, OrderStatus,
)
from apps.commerce.envelope import try_auto_confirm_via_envelope, release_envelope_hold, capture_envelope_hold


@pytest.mark.django_db
class TestEnvelopeDebitLifecycle:
    def _setup(self, reference_merchant, create_order_tool, finalize_payment_tool, balance=500000, price=120000):
        from apps.agents.models import Agent, AgentStatus
        from apps.tasks.models import Task, TaskStatus
        agent = Agent.objects.create(agent_id="debit-agent", name="debit-agent", status=AgentStatus.ACTIVE)
        task = Task.objects.create(task_id="debit-task", agent=agent, user_id="u", status=TaskStatus.ACTIVE,
                                    expires_at=timezone.now() + timedelta(minutes=30))
        product = Product.objects.create(product_id="debit-product", name="Debit Product",
                                          price_minor=price, currency="INR", merchant=reference_merchant)
        envelope = SpendingEnvelope.objects.create(
            envelope_id="env-debit", agent=agent, merchant=reference_merchant,
            max_amount_minor=balance, remaining_amount_minor=balance, currency="INR",
            status=EnvelopeStatus.ACTIVE, expires_at=timezone.now() + timedelta(days=1),
        )
        intent = PurchaseIntent.objects.create(
            intent_id="debit-intent", task=task, agent_id=agent.agent_id, user_id=task.user_id,
            product=product, quantity=1, canonical_amount_minor=price, currency="INR",
            status=PurchaseIntentStatus.PENDING,
        )
        return envelope, intent

    def test_auto_confirm_creates_held_debit(self, reference_merchant, create_order_tool, finalize_payment_tool):
        envelope, intent = self._setup(reference_merchant, create_order_tool, finalize_payment_tool)
        confirmed, _ = try_auto_confirm_via_envelope(intent.intent_id)
        assert confirmed is True
        debit = EnvelopeDebit.objects.get(intent=intent)
        assert debit.status == EnvelopeDebitStatus.HELD
        assert debit.amount_minor == 120000
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == 380000

    def test_capture_marks_debit_captured_without_changing_balance(self, reference_merchant, create_order_tool, finalize_payment_tool):
        envelope, intent = self._setup(reference_merchant, create_order_tool, finalize_payment_tool)
        try_auto_confirm_via_envelope(intent.intent_id)
        envelope.refresh_from_db()
        balance_after_hold = envelope.remaining_amount_minor
        capture_envelope_hold(intent.intent_id)
        debit = EnvelopeDebit.objects.get(intent=intent)
        assert debit.status == EnvelopeDebitStatus.CAPTURED
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == balance_after_hold  # unchanged

    def test_release_credits_balance_back_exactly_once(self, reference_merchant, create_order_tool, finalize_payment_tool):
        envelope, intent = self._setup(reference_merchant, create_order_tool, finalize_payment_tool)
        try_auto_confirm_via_envelope(intent.intent_id)
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == 380000

        release_envelope_hold(intent.intent_id)
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == 500000  # fully restored
        debit = EnvelopeDebit.objects.get(intent=intent)
        assert debit.status == EnvelopeDebitStatus.RELEASED

        # Second release attempt must be a no-op, not a double-credit.
        release_envelope_hold(intent.intent_id)
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == 500000

    def test_capture_after_release_is_rejected(self, reference_merchant, create_order_tool, finalize_payment_tool):
        envelope, intent = self._setup(reference_merchant, create_order_tool, finalize_payment_tool)
        try_auto_confirm_via_envelope(intent.intent_id)
        release_envelope_hold(intent.intent_id)
        with pytest.raises(ValueError):
            capture_envelope_hold(intent.intent_id)

    def test_no_debit_created_when_manual_gate_used_instead(self, reference_merchant, create_order_tool, finalize_payment_tool):
        # No envelope exists at all for this agent - auto-confirm should
        # decline cleanly and create no EnvelopeDebit row whatsoever.
        from apps.agents.models import Agent, AgentStatus
        from apps.tasks.models import Task, TaskStatus
        agent = Agent.objects.create(agent_id="no-envelope-agent", name="x", status=AgentStatus.ACTIVE)
        task = Task.objects.create(task_id="no-envelope-task", agent=agent, user_id="u", status=TaskStatus.ACTIVE,
                                    expires_at=timezone.now() + timedelta(minutes=30))
        product = Product.objects.create(product_id="no-env-product", name="X", price_minor=1000,
                                          currency="INR", merchant=reference_merchant)
        intent = PurchaseIntent.objects.create(
            intent_id="no-env-intent", task=task, agent_id=agent.agent_id, user_id=task.user_id,
            product=product, quantity=1, canonical_amount_minor=1000, currency="INR",
            status=PurchaseIntentStatus.PENDING,
        )
        confirmed, _ = try_auto_confirm_via_envelope(intent.intent_id)
        assert confirmed is False
        assert EnvelopeDebit.objects.filter(intent=intent).count() == 0

    def test_capture_hooked_into_real_finalize_payment_success(self, reference_merchant, create_order_tool, finalize_payment_tool):
        from apps.tools.handlers import create_order as create_order_handler, finalize_payment as finalize_payment_handler
        from unittest.mock import patch
        envelope, intent = self._setup(reference_merchant, create_order_tool, finalize_payment_tool)
        confirmed, _ = try_auto_confirm_via_envelope(intent.intent_id)
        assert confirmed is True

        with patch("apps.commerce.razorpay_client.create_razorpay_order", return_value={"id": "order_fake123"}):
            order_result = create_order_handler({"intent_id": intent.intent_id})
        assert order_result["status"] == "ok"

        with patch("apps.commerce.razorpay_client.get_client") as mock_client:
            mock_client.return_value.utility.verify_payment_signature.return_value = None
            final_result = finalize_payment_handler({
                "intent_id": intent.intent_id,
                "razorpay_order_id": "order_fake123",
                "razorpay_payment_id": "pay_fake456",
                "razorpay_signature": "sig_fake",
            })
        assert final_result["status"] == "ok"
        debit = EnvelopeDebit.objects.get(intent=intent)
        assert debit.status == EnvelopeDebitStatus.CAPTURED