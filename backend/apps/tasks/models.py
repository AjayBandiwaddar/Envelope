"""
Task lifecycle and identity binding.

Per POLICY_SPEC.md Section 3 and ARCHITECTURE.md Section 5.8:
"A task binds an agent and user to a limited task context. It owns
lifecycle, expiration, and revocation state. It does not own allowed
tools, actions, resources, or parameter constraints; those belong to
policies scoped to the task."
"""

from django.db import models
from django.utils import timezone


class TaskStatus(models.TextChoices):
    """Per POLICY_SPEC.md Section 8 "Task Lifecycle"."""

    PENDING = "PENDING", "Pending"
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    EXPIRED = "EXPIRED", "Expired"
    REVOKED = "REVOKED", "Revoked"


class Task(models.Model):
    """
    A task-scoped authorization context: binds one agent and (optionally)
    one user to a time-limited, revocable scope. The actual authority
    (allowed tools/actions/resources/parameters) is defined by Policy
    records that reference this task, not by fields on this model.
    """

    task_id = models.SlugField(max_length=100, unique=True)
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="tasks",
        help_text="The agent this task's authority is bound to.",
    )
    # Stored as a plain string, not a FK to a Django User model. This POC
    # has no end-user account system (per AGENTS.md Non-Goals: no
    # enterprise SSO); user_id is an opaque identifier supplied by
    # whatever created the task, used only for user-scope matching.
    user_id = models.CharField(max_length=100, blank=True, default="")

    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING
    )

    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Server-side expiration time. Never trust an agent-supplied timestamp."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent", "status"]),
        ]

    def __str__(self) -> str:
        return self.task_id

    def is_expired(self, at=None) -> bool:
        """
        Time check independent of the stored `status` field, per
        POLICY_SPEC.md Section 19: "Use server-side time. Do not trust
        timestamps supplied by the agent." A task whose status has not
        yet been lazily transitioned to EXPIRED must still be treated as
        expired if the clock says so.
        """
        at = at or timezone.now()
        return at >= self.expires_at
