"""
Policy - the record that actually grants (or explicitly denies) authority.

Per POLICY_SPEC.md Section 3:
"Policy owns allowed tools, actions, resources, parameter constraints, and
explicit allow/deny rules. Task owns agent/user binding, lifecycle,
expiration, and revocation. Do not duplicate action/resource/parameter
authority on the task model."

Field layout follows POLICY_SPEC.md Section 3 and the example policy in
Section 26 as closely as Django's relational model allows. Per Section 5
("For Week 1, prefer specific-agent policies... do not implement
agent-group inheritance unless required"), agent_scope is a required FK
to a single Agent rather than a group/list.
"""

from django.db import models


class PolicyStatus(models.TextChoices):
    """Per POLICY_SPEC.md Section 4."""

    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"
    REVOKED = "REVOKED", "Revoked"


class PolicyEffect(models.TextChoices):
    """Per POLICY_SPEC.md Section 3: valid policy effects are ALLOW and DENY."""

    ALLOW = "ALLOW", "Allow"
    DENY = "DENY", "Deny"


class ResourceScopeMode(models.TextChoices):
    """Per POLICY_SPEC.md Section 13."""

    EXACT = "EXACT", "Exact"
    ANY = "ANY", "Any"
    NONE = "NONE", "None"


class Policy(models.Model):
    """
    A single authorization rule scoped to a task, tool, and set of actions,
    with optional resource and parameter constraints.
    """

    policy_id = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=20, choices=PolicyStatus.choices, default=PolicyStatus.ACTIVE
    )
    effect = models.CharField(max_length=10, choices=PolicyEffect.choices)

    # --- Scope ---
    agent_scope = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="policies",
        help_text="The specific agent this policy applies to (POLICY_SPEC.md Section 5).",
    )
    user_scope = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Optional. If set, this policy only applies when the "
            "authenticated user matches (POLICY_SPEC.md Section 6)."
        ),
    )
    task_scope = models.ForeignKey(
        "tasks.Task",
        on_delete=models.CASCADE,
        related_name="policies",
        help_text="The task this policy grants (or denies) authority within.",
    )
    tool_scope = models.ForeignKey(
        "tools.Tool",
        on_delete=models.CASCADE,
        related_name="policies",
        help_text="The single registered tool this policy applies to.",
    )

    allowed_actions = models.JSONField(
        default=list,
        help_text="List of action name strings this policy applies to, e.g. ['refund_order'].",
    )

    # --- Resource scope (POLICY_SPEC.md Section 11-13) ---
    resource_type = models.CharField(max_length=100, blank=True, default="")
    resource_mode = models.CharField(
        max_length=10,
        choices=ResourceScopeMode.choices,
        default=ResourceScopeMode.NONE,
    )
    resource_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Used only when resource_mode is EXACT.",
    )

    # --- Parameter constraints (POLICY_SPEC.md Section 14-18) ---
    # Shape: {"amount": {"operator": "LTE", "value": 5000}, "currency": {"operator": "EQ", "value": "INR"}}
    # Supported operators (POLICY_SPEC.md Section 15): LTE, GTE, EQ, IN, BOOL_EQ.
    # Deliberately not an arbitrary expression language, per POLICY_SPEC.md
    # Section 15: "Avoid arbitrary expression languages in Week 1."
    constraints = models.JSONField(default=dict, blank=True)

    priority = models.IntegerField(
        default=0,
        help_text=(
            "Documented in POLICY_SPEC.md Section 3 but not required for "
            "correctness in Week 1: explicit DENY always overrides ALLOW "
            "regardless of priority (Section 21), so this field is stored "
            "for future use / operator readability rather than consumed "
            "by the evaluation algorithm."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "policy_id"]
        indexes = [
            models.Index(fields=["task_scope", "status"]),
        ]
        verbose_name_plural = "policies"

    def __str__(self) -> str:
        return f"{self.policy_id} ({self.effect})"

    def is_active(self) -> bool:
        return self.status == PolicyStatus.ACTIVE
