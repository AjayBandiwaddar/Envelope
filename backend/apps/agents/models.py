"""
Agent registry.

Minimum conceptual schema per ARCHITECTURE.md Section 5.7:
    agent_id, name, description, status, created_at

Per docs/SPEC_REVIEW.md Section 3.1, each agent also holds a hashed
bearer token used to authenticate its own execution requests. The token
determines identity at authentication time (Day 3) rather than trusting
a client-supplied agent_id in the request body — this field exists now
so the model is complete, even though the authentication view that uses
it is Day 3 work.
"""

import hashlib
import secrets

from django.db import models


class AgentStatus(models.TextChoices):
    """
    Per POLICY_SPEC.md Section 25 reason codes INVALID_AGENT / AGENT_DISABLED,
    an agent must have at least an active/disabled distinction.
    """

    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"


class Agent(models.Model):
    """A registered AI agent that may request authorization decisions."""

    agent_id = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Stable, human-readable identifier, e.g. 'support-agent-01'.",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=AgentStatus.choices, default=AgentStatus.ACTIVE
    )

    # Hashed bearer token used to authenticate this agent's execution
    # requests (Day 3). The raw token is shown to the caller exactly once,
    # at creation time, and never stored or logged in plaintext -
    # ARCHITECTURE.md Section 21 "never log secrets".
    token_hash = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["agent_id"]

    def __str__(self) -> str:
        return self.agent_id

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """SHA-256 of the raw token. Never store or log the raw value itself."""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def issue_token(self) -> str:
        """
        Generate a new bearer token for this agent, store only its hash,
        and return the raw value. Callers must display/return this value
        to the requester immediately - it cannot be recovered later.
        """
        raw_token = secrets.token_urlsafe(32)
        self.token_hash = self.hash_token(raw_token)
        self.save(update_fields=["token_hash", "updated_at"])
        return raw_token

    def is_active(self) -> bool:
        return self.status == AgentStatus.ACTIVE
