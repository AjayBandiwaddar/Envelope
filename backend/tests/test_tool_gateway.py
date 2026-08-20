"""
Tests for apps.tools.gateway - the execution boundary.

Per AGENTS.md's Core Security Principle, this is the single most
important property in the whole system to test explicitly: an
authorized tool executes and leaves a record; anything else must not
execute and must leave no record.
"""

import pytest

from apps.authorization import service
from apps.authorization.engine import AuthorizationDecision, Decision, ReasonCode
from apps.tools.gateway import ToolExecutionDenied, execute_tool
from apps.tools.models import ToolExecution


@pytest.mark.django_db
class TestToolGateway:
    def test_allow_decision_executes_and_records(
        self, agent_with_token, active_task, refund_policy, refund_tool
    ):
        agent, _ = agent_with_token
        decision = service.authorize(
            agent_id=agent.agent_id,
            user_id="user-001",
            task_id=active_task.task_id,
            tool_id="refund_order",
            action="refund_order",
            resource_type="order",
            resource_id="8291",
            parameters={"amount": 3000, "currency": "INR"},
            request_id="req-test-allow",
        )
        assert decision.decision == Decision.ALLOW

        assert ToolExecution.objects.count() == 0
        result = execute_tool(
            "refund_order", "refund_order", {"order_id": "8291", "amount": 3000, "currency": "INR"},
            decision, request_id="req-test-allow",
        )
        assert result["status"] == "refunded"
        assert ToolExecution.objects.count() == 1

    def test_deny_decision_never_executes(
        self, agent_with_token, active_task, refund_policy, refund_tool
    ):
        agent, _ = agent_with_token
        decision = service.authorize(
            agent_id=agent.agent_id,
            user_id="user-001",
            task_id=active_task.task_id,
            tool_id="refund_order",
            action="refund_order",
            resource_type="order",
            resource_id="8291",
            parameters={"amount": 99999, "currency": "INR"},
            request_id="req-test-deny",
        )
        assert decision.decision == Decision.DENY

        with pytest.raises(ToolExecutionDenied):
            execute_tool(
                "refund_order", "refund_order", {"order_id": "8291", "amount": 99999},
                decision, request_id="req-test-deny",
            )
        assert ToolExecution.objects.count() == 0

    def test_fabricated_allow_decision_for_unregistered_tool_is_rejected(self):
        """
        Defense in depth: even if a caller somehow constructed an ALLOW
        decision object directly (bypassing the engine entirely), the
        gateway independently re-checks that the tool is registered and
        active before executing anything.
        """
        fake_decision = AuthorizationDecision(
            decision=Decision.ALLOW, reason_code=ReasonCode.AUTHORIZED, reason="", policy_id=None
        )
        with pytest.raises(ToolExecutionDenied):
            execute_tool("tool-that-does-not-exist", "some_action", {}, fake_decision)

    @pytest.mark.django_db
    def test_disabled_tool_rejected_even_with_allow_decision(self, refund_tool):
        from apps.tools.models import ToolStatus

        refund_tool.status = ToolStatus.DISABLED
        refund_tool.save()

        fake_decision = AuthorizationDecision(
            decision=Decision.ALLOW, reason_code=ReasonCode.AUTHORIZED, reason="", policy_id=None
        )
        with pytest.raises(ToolExecutionDenied):
            execute_tool("refund_order", "refund_order", {}, fake_decision)
        assert ToolExecution.objects.count() == 0