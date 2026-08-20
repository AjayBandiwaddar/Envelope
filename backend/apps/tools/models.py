"""
Tool registry.

Minimum conceptual schema per ARCHITECTURE.md Section 5.6:
    tool_id, name, service, description, input_schema, risk_level, status, handler

`handler` is intentionally NOT a database field: a Python callable can't
be stored in PostgreSQL. The mapping from tool_id to its actual mock
implementation lives in code (apps/tools/handlers.py, added when the
Tool Gateway is built on Day 3), keeping this model limited to the data
that genuinely needs to persist - per AGENTS.md "Do not create
unnecessary fields."
"""

from django.db import models


class ToolStatus(models.TextChoices):
    """Per POLICY_SPEC.md Section 10: unknown or DISABLED tools -> DENY."""

    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"


class RiskLevel(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class Tool(models.Model):
    """A registered tool an agent may be authorized to invoke."""

    tool_id = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    service = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional metadata/grouping field, e.g. 'orders'.",
    )
    description = models.TextField(blank=True, default="")

    # A JSON-schema-like description of accepted parameters, used by the
    # authorization engine to validate/reject unknown parameters before
    # execution - POLICY_SPEC.md Section 18 "Prefer rejecting unknown
    # parameters." Kept intentionally simple (list of expected parameter
    # names with types) rather than full JSON Schema, per AGENTS.md
    # "Avoid arbitrary expression languages in Week 1."
    input_schema = models.JSONField(default=dict, blank=True)

    risk_level = models.CharField(
        max_length=20, choices=RiskLevel.choices, default=RiskLevel.LOW
    )
    status = models.CharField(
        max_length=20, choices=ToolStatus.choices, default=ToolStatus.ACTIVE
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tool_id"]

    def __str__(self) -> str:
        return self.tool_id

    def is_active(self) -> bool:
        return self.status == ToolStatus.ACTIVE


class ToolExecution(models.Model):
    """
    A persistent record that a tool actually executed (or was rejected).
    Exists so tests - and a human running curl/psql - can prove whether
    execution happened, per CODEX_EXECUTION_PLAN.md Day 3: 'Create
    execution counters/state for mock tools so tests can prove whether
    execution happened.' A DB row survives across requests and processes,
    which an in-memory counter would not.
    """

    tool_id = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    request_id = models.CharField(max_length=64, blank=True, default="")
    arguments = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-executed_at"]

    def __str__(self) -> str:
        return f"{self.tool_id} @ {self.executed_at}"