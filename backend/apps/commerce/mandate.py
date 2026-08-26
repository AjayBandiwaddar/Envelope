"""
Cryptographic purchase mandates - a simplified, single-keypair analogue
of AP2's signed Cart Mandate pattern. Not a claim of AP2 conformance:
AP2 chains three mandates as W3C Verifiable Credentials signed by the
user's own wallet; this signs one payload, server-side, at the moment
confirm_purchase_intent runs. What it borrows faithfully from AP2 is the
core idea - authorization evidence should be a portable, independently
verifiable, tamper-evident artifact bound to the exact transaction
facts, not just a database row trusted because it's in our database.

Replay note: the payload includes a nonce for structural fidelity to
the AP2 mandate pattern. This code does NOT implement nonce-based replay
detection (no ledger of consumed nonces). Duplicate use is prevented at
the application level instead: PurchaseIntent -> Order is a strict
one-to-one, so a second create_order against an already-ordered intent
fails structurally (ORDER_ALREADY_EXISTS) regardless of this layer. Be
precise about that distinction if asked - it's a deliberate choice, not
an oversight.
"""

from __future__ import annotations
import base64
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MANDATE_TTL_MINUTES = 30


class MandateError(Exception):
    """Base class for every mandate verification failure. Callers must
    treat every subclass as DENY - never inspect it to decide to proceed anyway."""


class MandateSignatureInvalid(MandateError):
    pass


class MandateExpired(MandateError):
    pass


class MandateIntentMismatch(MandateError):
    pass


class MandateFieldMismatch(MandateError):
    pass


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Sorted-key, whitespace-free JSON - the same payload always produces
    the same bytes to sign or verify, regardless of how it was built in Python."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_private_key() -> Ed25519PrivateKey:
    if not settings.MANDATE_PRIVATE_KEY:
        raise RuntimeError("MANDATE_PRIVATE_KEY is not configured - run `python manage.py generate_mandate_keys`.")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(settings.MANDATE_PRIVATE_KEY))


def _load_public_key() -> Ed25519PublicKey:
    if not settings.MANDATE_PUBLIC_KEY:
        raise RuntimeError("MANDATE_PUBLIC_KEY is not configured.")
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(settings.MANDATE_PUBLIC_KEY))


def build_and_sign_mandate(intent) -> tuple[dict, str]:
    """Called only from confirm_purchase_intent, at the same moment the
    Policy rows are written - both represent the same human-confirmed event."""
    now = timezone.now()
    payload = {
        "mandate_id": f"mandate-{uuid.uuid4().hex[:12]}",
        "version": "1",
        "issuer": "razorpaybuildathon-firewall",
        "agent_id": intent.task.agent.agent_id,
        "task_id": intent.task.task_id,
        "user_id": intent.user_id,
        "intent_id": intent.intent_id,
        "product_id": intent.product.product_id,
        "quantity": intent.quantity,
        "amount_minor": intent.canonical_amount_minor,
        "currency": intent.currency,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=MANDATE_TTL_MINUTES)).isoformat(),
        "nonce": secrets.token_hex(16),
    }
    signature = _load_private_key().sign(_canonical_bytes(payload))
    return payload, base64.b64encode(signature).decode()


def verify_mandate(mandate, intent_id: str) -> dict:
    """
    Full chain, in order, stopping at the first failure:
      1. signature valid against the stored payload
      2. not expired
      3. payload.intent_id matches the intent actually being acted on
      4. every signed fact matches current authoritative DB state
    Raises a MandateError subclass on any failure - never returns a
    partial or "probably fine" result.
    """
    public_key = _load_public_key()
    try:
        public_key.verify(base64.b64decode(mandate.signature), _canonical_bytes(mandate.payload))
    except InvalidSignature:
        raise MandateSignatureInvalid("Mandate signature does not match its payload.")

    expires_at_raw = mandate.payload.get("expires_at")
    if not expires_at_raw or timezone.now() > datetime.fromisoformat(expires_at_raw):
        raise MandateExpired("Mandate has expired.")

    if mandate.payload.get("intent_id") != intent_id:
        raise MandateIntentMismatch("Mandate does not correspond to the requested purchase intent.")

    intent = mandate.intent
    expected = {
        "agent_id": intent.task.agent.agent_id,
        "task_id": intent.task.task_id,
        "user_id": intent.user_id,
        "product_id": intent.product.product_id,
        "quantity": intent.quantity,
        "amount_minor": intent.canonical_amount_minor,
        "currency": intent.currency,
    }
    for field, expected_value in expected.items():
        if mandate.payload.get(field) != expected_value:
            raise MandateFieldMismatch(f"Mandate field '{field}' does not match current authoritative state.")

    return mandate.payload