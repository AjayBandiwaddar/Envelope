"""
Audit event log.

Per ARCHITECTURE.md Section 21 ("Observability"), an audit record must
capture: request ID, timestamp, agent ID, user ID (when available),
task ID, action, resource, tool, policy ID, decision, denial reason,
and latency. Never log secrets (Section 21) or sensitive authentication
material.

Deliberately uses plain string fields for agent_id/task_id/policy_id/
tool_id rather than ForeignKeys. An audit log's job is to outlive and
remain independent of the mutable state it describes - THREAT_MODEL.md
Section 6.3 notes that the POC does not defend against a compromised
administrator tampering with the audit log, but it should at least not
*structurally* couple audit permanence to unrelated referential-integrity
decisions (e.g. an agent or task being deleted should never cascade-
delete the audit trail that recorded what that agent did).

The actual write-path (creating these records as part of the
authorization flow) is Day 3 work, per CODEX_EXECUTION_PLAN.md's split
between Day 2 (models + engine) and Day 3 (API + audit event creation).
This model only defines the shape.
"""

from django.db import models


class Decision(models.TextChoices):
    ALLOW = "ALLOW", "Allow"
    DENY = "DENY", "Deny"


class AuditEvent(models.Model):
    """An immutable-in-spirit record of one authorization decision."""

    request_id = models.CharField(max_length=64, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    agent_id = models.CharField(max_length=100, blank=True, default="")
    user_id = models.CharField(max_length=100, blank=True, default="")
    task_id = models.CharField(max_length=100, blank=True, default="")
    tool_id = models.CharField(max_length=100, blank=True, default="")
    action = models.CharField(max_length=100, blank=True, default="")

    resource_type = models.CharField(max_length=100, blank=True, default="")
    resource_id = models.CharField(max_length=100, blank=True, default="")

    # Snapshot of the request's parameters, for audit/explainability.
    # Never store secrets/tokens here - only tool-call parameters
    # (amounts, currencies, IDs), which is all this field is populated
    # with by the service layer that will write these records (Day 3).
    parameters = models.JSONField(default=dict, blank=True)

    policy_id = models.CharField(max_length=100, blank=True, default="")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    reason_code = models.CharField(max_length=64)
    reason = models.TextField(blank=True, default="")

    latency_ms = models.FloatField(
        null=True,
        blank=True,
        help_text="Time spent evaluating this authorization decision, in milliseconds.",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["agent_id", "timestamp"]),
            models.Index(fields=["task_id", "timestamp"]),
            models.Index(fields=["decision", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.decision} {self.action} ({self.reason_code})"
