import pytest
from apps.commerce.mandate import verify_mandate, MandateError, MandateSignatureInvalid


@pytest.mark.django_db
class TestPurchaseMandate:
    def test_valid_mandate_verifies(self, confirmed_purchase_intent):
        mandate = confirmed_purchase_intent.mandate
        result = verify_mandate(mandate, confirmed_purchase_intent.intent_id)
        assert result["intent_id"] == confirmed_purchase_intent.intent_id

    def test_tampered_amount_is_rejected(self, confirmed_purchase_intent):
        mandate = confirmed_purchase_intent.mandate
        mandate.payload["amount_minor"] = 100
        mandate.save()
        with pytest.raises(MandateSignatureInvalid):
            verify_mandate(mandate, confirmed_purchase_intent.intent_id)

    def test_wrong_intent_id_is_rejected(self, confirmed_purchase_intent):
        mandate = confirmed_purchase_intent.mandate
        with pytest.raises(MandateError):
            verify_mandate(mandate, "some-other-intent-id")