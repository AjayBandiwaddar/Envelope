from __future__ import annotations
import time
from django.db import OperationalError, transaction
from django.db.models import F
from django.utils import timezone
from apps.commerce.authorization import confirm_purchase_intent
from apps.commerce.models import (
    PurchaseIntent, PurchaseIntentStatus, SpendingEnvelope, EnvelopeStatus,
    EnvelopeDebit, EnvelopeDebitStatus,
)

_SQLITE_LOCK_RETRY_ATTEMPTS = 5
_SQLITE_LOCK_RETRY_DELAY_SECONDS = 0.05


def _is_sqlite_lock_error(exc: OperationalError) -> bool:
    message = str(exc)
    return "database is locked" in message or "database table is locked" in message


def try_auto_confirm_via_envelope(intent_id: str) -> tuple[bool, str]:
    """
    Returns (confirmed, reason). reason is one of:
      "confirmed"             - auto-confirmed successfully
      "no_envelope"           - no active envelope covers this agent+merchant+currency
      "insufficient_balance"  - an envelope exists but doesn't cover this amount
      "not_pending"           - intent wasn't PENDING (already handled)
    Retries a bounded number of times on SQLite's "database is locked"
    error - a development-database artifact, not a correctness gap.
    """
    last_error = None
    for _ in range(_SQLITE_LOCK_RETRY_ATTEMPTS):
        try:
            return _attempt_auto_confirm(intent_id)
        except OperationalError as exc:
            if not _is_sqlite_lock_error(exc):
                raise
            last_error = exc
            time.sleep(_SQLITE_LOCK_RETRY_DELAY_SECONDS)
    raise last_error


def _attempt_auto_confirm(intent_id: str) -> tuple[bool, str]:
    intent = PurchaseIntent.objects.select_related(
        "task", "task__agent", "product", "product__merchant"
    ).get(intent_id=intent_id)

    if intent.status != PurchaseIntentStatus.PENDING:
        return False, "not_pending"

    agent = intent.task.agent
    merchant = intent.product.merchant
    amount = intent.canonical_amount_minor

    candidate = SpendingEnvelope.objects.filter(
        agent=agent, merchant=merchant, currency=intent.currency,
        status=EnvelopeStatus.ACTIVE, expires_at__gt=timezone.now(),
    ).order_by("id").first()

    if candidate is None:
        return False, "no_envelope"

    with transaction.atomic():
        updated = SpendingEnvelope.objects.filter(
            id=candidate.id, status=EnvelopeStatus.ACTIVE,
            expires_at__gt=timezone.now(), remaining_amount_minor__gte=amount,
        ).update(remaining_amount_minor=F("remaining_amount_minor") - amount)

        if updated == 0:
            return False, "insufficient_balance"

        EnvelopeDebit.objects.create(
            envelope_id=candidate.id, intent=intent,
            amount_minor=amount, status=EnvelopeDebitStatus.HELD,
        )
        confirm_purchase_intent(intent.intent_id)

    return True, "confirmed"


def capture_envelope_hold(intent_id: str) -> None:
    """
    Called on finalize_payment success. Marks the hold permanent - no
    balance change, since the amount was already removed from the
    envelope at auto-confirm time. A no-op (raises) if there is no
    HELD debit for this intent, e.g. this purchase was never
    envelope-backed in the first place, or was already captured/
    released - callers must only call this after confirming a debit
    exists and is still HELD.
    """
    updated = EnvelopeDebit.objects.filter(
        intent__intent_id=intent_id, status=EnvelopeDebitStatus.HELD,
    ).update(status=EnvelopeDebitStatus.CAPTURED)
    if updated == 0:
        raise ValueError(
            f"No HELD EnvelopeDebit found for intent {intent_id} - "
            "either this purchase was not envelope-backed, or its "
            "hold was already captured or released."
        )


def release_envelope_hold(intent_id: str) -> bool:
    """
    Called when a purchase fails or is explicitly abandoned after
    auto-confirmation. Atomically credits the held amount back to the
    envelope and marks the debit RELEASED. Idempotent by design: the
    WHERE clause only matches a debit still in HELD status, so calling
    this twice (or racing it against a concurrent capture) can never
    double-credit the envelope - the second call simply matches zero
    rows and returns False.

    Returns True if a hold was actually released, False if there was
    nothing to release (no debit, or already captured/released).
    """
    try:
        debit = EnvelopeDebit.objects.select_related("envelope").get(
            intent__intent_id=intent_id, status=EnvelopeDebitStatus.HELD,
        )
    except EnvelopeDebit.DoesNotExist:
        return False

    with transaction.atomic():
        released = EnvelopeDebit.objects.filter(
            id=debit.id, status=EnvelopeDebitStatus.HELD,
        ).update(status=EnvelopeDebitStatus.RELEASED)

        if released == 0:
            return False  # lost a race to a concurrent capture/release

        SpendingEnvelope.objects.filter(id=debit.envelope_id).update(
            remaining_amount_minor=F("remaining_amount_minor") + debit.amount_minor
        )

    return True