import threading
import pytest
from apps.tools.mcp_dispatch import dispatch_tool_call
from apps.commerce.authorization import confirm_purchase_intent
from apps.commerce.models import Order, PurchaseIntent
from apps.commerce.razorpay_client import get_order_create_call_count


def _propose_and_confirm(task, raw_token, product_id):
    propose = dispatch_tool_call(
        tool_id="propose_purchase_intent", action="propose_purchase_intent",
        agent_token=raw_token, task_id=task.task_id, resource_type="", resource_id=None,
        parameters={"task_id": task.task_id, "product_id": product_id, "quantity": 1},
    )
    intent_id = propose["result"]["intent_id"]
    confirm_purchase_intent(intent_id)
    return intent_id


@pytest.mark.django_db
class TestQuantityValidation:
    def _propose(self, task, raw_token, product_id, quantity):
        return dispatch_tool_call(
            tool_id="propose_purchase_intent", action="propose_purchase_intent",
            agent_token=raw_token, task_id=task.task_id, resource_type="", resource_id=None,
            parameters={"task_id": task.task_id, "product_id": product_id, "quantity": quantity},
        )

    def test_string_quantity_rejected(self, security_demo_tools, mandate_test_product, agent_task_with_propose_policy):
        agent, task, raw_token = agent_task_with_propose_policy
        result = self._propose(task, raw_token, mandate_test_product.product_id, "abc")
        assert result["result"]["reason"] == "INVALID_QUANTITY"

    def test_negative_quantity_rejected(self, security_demo_tools, mandate_test_product, agent_task_with_propose_policy):
        agent, task, raw_token = agent_task_with_propose_policy
        result = self._propose(task, raw_token, mandate_test_product.product_id, -1)
        assert result["result"]["reason"] == "INVALID_QUANTITY"

    def test_zero_quantity_rejected(self, security_demo_tools, mandate_test_product, agent_task_with_propose_policy):
        agent, task, raw_token = agent_task_with_propose_policy
        result = self._propose(task, raw_token, mandate_test_product.product_id, 0)
        assert result["result"]["reason"] == "INVALID_QUANTITY"

    def test_bool_quantity_rejected(self, security_demo_tools, mandate_test_product, agent_task_with_propose_policy):
        agent, task, raw_token = agent_task_with_propose_policy
        result = self._propose(task, raw_token, mandate_test_product.product_id, True)
        assert result["result"]["reason"] == "INVALID_QUANTITY"


@pytest.mark.django_db
class TestHandlerExceptionSafety:
    def test_handler_exception_does_not_crash_and_does_not_leak(self, monkeypatch, security_demo_tools, agent_task_with_propose_policy):
        from apps.tools import handlers

        def _boom(arguments):
            raise RuntimeError("super secret internal detail that must never reach the caller")

        monkeypatch.setitem(handlers.TOOL_HANDLERS, "propose_purchase_intent", _boom)

        agent, task, raw_token = agent_task_with_propose_policy
        result = dispatch_tool_call(
            tool_id="propose_purchase_intent", action="propose_purchase_intent",
            agent_token=raw_token, task_id=task.task_id, resource_type="", resource_id=None,
            parameters={"task_id": task.task_id, "product_id": "whatever", "quantity": 1},
        )
        assert result["decision"] == "ALLOW"
        assert result["result"]["status"] == "error"
        assert result["result"]["reason"] == "TOOL_EXECUTION_ERROR"
        assert "super secret internal detail" not in str(result)


@pytest.mark.django_db
class TestFinalizePaymentIdempotency:
    def test_repeated_finalize_is_idempotent(self, security_demo_tools, mandate_test_product, agent_task_with_propose_policy, monkeypatch):
        agent, task, raw_token = agent_task_with_propose_policy
        intent_id = _propose_and_confirm(task, raw_token, mandate_test_product.product_id)

        create = dispatch_tool_call(
            tool_id="create_order", action="create_order", agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id, parameters={"intent_id": intent_id},
        )
        order_id = create["result"]["order_id"]

        from apps.commerce.razorpay_client import get_client
        monkeypatch.setattr(
            "apps.commerce.razorpay_client.get_client",
            lambda: type("FakeClient", (), {"utility": type("U", (), {"verify_payment_signature": staticmethod(lambda x: None)})()})(),
        )

        params = {
            "intent_id": intent_id,
            "razorpay_order_id": create["result"]["razorpay_order_id"],
            "razorpay_payment_id": "pay_fake123",
            "razorpay_signature": "sig_fake123",
        }
        first = dispatch_tool_call(
            tool_id="finalize_payment", action="finalize_payment", agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id, parameters=params,
        )
        second = dispatch_tool_call(
            tool_id="finalize_payment", action="finalize_payment", agent_token=raw_token, task_id=task.task_id,
            resource_type="purchase_intent", resource_id=intent_id, parameters=params,
        )

        assert first["result"]["status"] == "ok"
        assert second["result"]["status"] == "ok"
        assert second["result"].get("idempotent") is True
        assert Order.objects.filter(order_id=order_id).count() == 1


@pytest.mark.django_db(transaction=True)
class TestConcurrentCreateOrder:
    def test_two_concurrent_requests_yield_one_order_one_provider_call(
        self, security_demo_tools, mandate_test_product, agent_task_with_propose_policy
    ):
        agent, task, raw_token = agent_task_with_propose_policy
        intent_id = _propose_and_confirm(task, raw_token, mandate_test_product.product_id)

        before_count = get_order_create_call_count()
        barrier = threading.Barrier(2)
        results = [None, None]

        def _attempt(index):
            barrier.wait()
            results[index] = dispatch_tool_call(
                tool_id="create_order", action="create_order", agent_token=raw_token, task_id=task.task_id,
                resource_type="purchase_intent", resource_id=intent_id, parameters={"intent_id": intent_id},
            )

        t1 = threading.Thread(target=_attempt, args=(0,))
        t2 = threading.Thread(target=_attempt, args=(1,))
        t1.start(); t2.start()
        t1.join(); t2.join()

        after_count = get_order_create_call_count()

        assert Order.objects.filter(purchase_intent__intent_id=intent_id).count() == 1
        assert after_count - before_count == 1

        oks = [r for r in results if r["result"].get("status") == "ok"]
        denies = [r for r in results if r["result"].get("status") == "error" and r["result"].get("reason") == "ORDER_ALREADY_EXISTS"]
        assert len(oks) == 1
        assert len(denies) == 1