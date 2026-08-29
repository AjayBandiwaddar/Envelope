import pytest
from apps.commerce.views import _run_security_scenario
from apps.commerce.razorpay_client import get_order_create_call_count





@pytest.mark.django_db
class TestSecurityDemoScenarios:
    def test_skip_confirmation_is_denied(self, security_demo_tools, mandate_test_product):
        before = get_order_create_call_count()
        result = _run_security_scenario("skip_confirmation")
        after = get_order_create_call_count()

        assert result["decision"] == "DENY"
        assert result["reason_code"] == "POLICY_NOT_FOUND"
        assert result["razorpay_calls_made"] == 0
        assert after == before

    def test_unknown_parameter_is_denied(self, security_demo_tools, mandate_test_product):
        before = get_order_create_call_count()
        result = _run_security_scenario("unknown_parameter")
        after = get_order_create_call_count()

        assert result["decision"] == "DENY"
        assert result["reason_code"] == "UNKNOWN_PARAMETER"
        assert result["razorpay_calls_made"] == 0
        assert after == before

    def test_tampered_mandate_is_allow_but_blocked(self, security_demo_tools, mandate_test_product):
        before = get_order_create_call_count()
        result = _run_security_scenario("tampered_mandate")
        after = get_order_create_call_count()

        assert result["decision"] == "ALLOW"
        assert result["result"]["status"] == "error"
        assert result["result"]["reason"] == "MANDATE_VERIFICATION_FAILED"
        assert result["razorpay_calls_made"] == 0
        assert after == before