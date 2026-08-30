import threading
import pytest
from apps.tools.handlers import DEFAULT_TOOLS
from django.utils import timezone
from datetime import timedelta
from apps.agents.models import Agent, AgentStatus
from apps.tasks.models import Task, TaskStatus
from apps.commerce.models import Product, PurchaseIntent, PurchaseIntentStatus
from apps.commerce.envelope import try_auto_confirm_via_envelope, SpendingEnvelope, EnvelopeStatus


def _make_agent_task(agent_id, task_id):
    agent = Agent.objects.create(agent_id=agent_id, name=agent_id, status=AgentStatus.ACTIVE)
    task = Task.objects.create(
        task_id=task_id, agent=agent, user_id="envelope-test-user",
        status=TaskStatus.ACTIVE, expires_at=timezone.now() + timedelta(minutes=30),
    )
    return agent, task


def _make_intent(intent_id, task, agent, product, amount_minor):
    return PurchaseIntent.objects.create(
        intent_id=intent_id, task=task, agent_id=agent.agent_id, user_id=task.user_id,
        product=product, quantity=1, canonical_amount_minor=amount_minor,
        currency=product.currency, status=PurchaseIntentStatus.PENDING,
    )


@pytest.mark.django_db
class TestEnvelopeMerchantScoping:
    def test_envelope_does_not_cover_different_merchant(self, reference_merchant, second_merchant):
        agent, task = _make_agent_task("envelope-agent-1", "envelope-task-1")
        product_on_second_merchant = Product.objects.create(
            product_id="second-merchant-product", name="Other Merchant Product",
            price_minor=100000, currency="INR", merchant=second_merchant,
        )
        envelope = SpendingEnvelope.objects.create(
            envelope_id="env-1", agent=agent, merchant=reference_merchant,
            max_amount_minor=500000, remaining_amount_minor=500000, currency="INR",
            status=EnvelopeStatus.ACTIVE, expires_at=timezone.now() + timedelta(days=1),
        )
        intent = _make_intent("intent-cross-merchant", task, agent, product_on_second_merchant, 100000)
        confirmed, _ = try_auto_confirm_via_envelope(intent.intent_id)
        assert confirmed is False
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == 500000  # untouched
        intent.refresh_from_db()
        assert intent.status == PurchaseIntentStatus.PENDING  # unchanged, falls back to manual gate

    def test_envelope_covers_matching_merchant(self, reference_merchant, create_order_tool, finalize_payment_tool):
        agent, task = _make_agent_task("envelope-agent-2", "envelope-task-2")
        product = Product.objects.create(
            product_id="matching-merchant-product", name="Matching Product",
            price_minor=120000, currency="INR", merchant=reference_merchant,
        )
        envelope = SpendingEnvelope.objects.create(
            envelope_id="env-2", agent=agent, merchant=reference_merchant,
            max_amount_minor=500000, remaining_amount_minor=500000, currency="INR",
            status=EnvelopeStatus.ACTIVE, expires_at=timezone.now() + timedelta(days=1),
        )
        intent = _make_intent("intent-matching-merchant", task, agent, product, 120000)
        confirmed, _ = try_auto_confirm_via_envelope(intent.intent_id)
        assert confirmed is True
        envelope.refresh_from_db()
        assert envelope.remaining_amount_minor == 380000
        intent.refresh_from_db()
        assert intent.status == PurchaseIntentStatus.AUTHORIZED
        assert hasattr(intent, "mandate")  # confirm_purchase_intent ran for real


@pytest.mark.django_db(transaction=True)
class TestEnvelopeConcurrentDecrement:
    def test_two_concurrent_purchases_never_overdraw_envelope(self, reference_merchant, create_order_tool, finalize_payment_tool):
        """
        Envelope has exactly enough remaining balance (Rs.1,500) to cover
        ONE of two simultaneous Rs.1,000 purchase attempts, not both.
        Mirrors TestConcurrentCreateOrder's barrier pattern: this must
        fail against a naive read-then-write implementation and pass
        only against an atomic conditional UPDATE (F() expression,
        WHERE remaining >= amount, in one SQL statement).
        """
        agent, task = _make_agent_task("envelope-agent-3", "envelope-task-3")
        product = Product.objects.create(
            product_id="concurrency-product", name="Concurrency Product",
            price_minor=100000, currency="INR", merchant=reference_merchant,
        )
        envelope = SpendingEnvelope.objects.create(
            envelope_id="env-3", agent=agent, merchant=reference_merchant,
            max_amount_minor=150000, remaining_amount_minor=150000, currency="INR",
            status=EnvelopeStatus.ACTIVE, expires_at=timezone.now() + timedelta(days=1),
        )
        intent_a = _make_intent("intent-concurrent-a", task, agent, product, 100000)
        intent_b = _make_intent("intent-concurrent-b", task, agent, product, 100000)

        barrier = threading.Barrier(2)
        results = [None, None]

        def _attempt(index, intent_id):
            barrier.wait()
            try:
                results[index] = try_auto_confirm_via_envelope(intent_id)[0]
            except Exception as exc:
                results[index] = exc

        t1 = threading.Thread(target=_attempt, args=(0, intent_a.intent_id))
        t2 = threading.Thread(target=_attempt, args=(1, intent_b.intent_id))
        t1.start(); t2.start()
        t1.join(); t2.join()

        envelope.refresh_from_db()
        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, f"unexpected exception(s) in concurrent attempt: {errors}"
        assert envelope.remaining_amount_minor == 50000  # exactly one decrement applied
        assert envelope.remaining_amount_minor >= 0       # never negative, under no interleaving
        successes = [r for r in results if r is True]
        failures = [r for r in results if r is False]
        assert len(successes) == 1
        assert len(failures) == 1

from apps.tools.handlers import DEFAULT_TOOLS


class TestEnvelopeIsNotAgentExposed:
    """
    The single most important invariant for this feature: an envelope
    grants delegated authority, so creating/extending/revoking one must
    be structurally unreachable by the agent - not just undocumented,
    unreachable. This mirrors how confirm_purchase_intent itself is
    never an MCP tool.
    """
    def test_no_envelope_tool_registered_in_default_tools(self):
        tool_ids = {tool["tool_id"] for tool in DEFAULT_TOOLS}
        envelope_related = {t for t in tool_ids if "envelope" in t.lower()}
        assert envelope_related == set(), (
            f"An envelope-related MCP tool exists: {envelope_related}. "
            "Envelope creation/mutation must never be agent-callable."
        )

    def test_no_envelope_handler_registered(self):
        from apps.tools.handlers import TOOL_HANDLERS
        envelope_handlers = {name for name in TOOL_HANDLERS if "envelope" in name.lower()}
        assert envelope_handlers == set()

    @pytest.mark.django_db
    def test_dispatch_tool_call_rejects_unknown_envelope_tool(self, agent_task_with_propose_policy):
        """
        Belt-and-suspenders: even if someone registers a Tool row named
        e.g. 'create_envelope' without adding a matching Policy, the
        firewall's own POLICY_NOT_FOUND path must deny it - the same
        protection that already covers every other unauthorized tool.
        """
        from apps.tools.mcp_dispatch import dispatch_tool_call
        agent, task, raw_token = agent_task_with_propose_policy
        result = dispatch_tool_call(
            tool_id="create_envelope", action="create_envelope",
            agent_token=raw_token, task_id=task.task_id,
            resource_type="", resource_id=None, parameters={},
        )
        assert result["decision"] != "ALLOW"