"""
Pure data structures for the authorization engine.

These are the "Authorization context" and "Authorization decision" domain
structures required by CODEX_EXECUTION_PLAN.md Day 2. They are plain
dataclasses with zero Django/HTTP/LLM dependencies, per
ARCHITECTURE.md Section 5.4 ("no dependency on Django ORM") and
AGENTS.md's Core Security Principle - the engine that consumes these
types must be testable and reasoned about independently of the web
framework and independently of any model client.

The service layer (Day 3) is responsible for converting Django ORM rows
into these snapshots before calling the engine, and for converting the
engine's AuthorizationDecision back into a persisted AuditEvent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .reason_codes import ReasonCode


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class ResourceScopeMode(str, Enum):
    EXACT = "EXACT"
    ANY = "ANY"
    NONE = "NONE"


class ConstraintOperator(str, Enum):
    """Per POLICY_SPEC.md Section 15 "Supported Constraint Types"."""

    LTE = "LTE"  # maximum numeric value
    GTE = "GTE"  # minimum numeric value
    EQ = "EQ"  # exact string / exact resource
    IN = "IN"  # allowed values
    BOOL_EQ = "BOOL_EQ"  # boolean requirement


@dataclass(frozen=True)
class AgentSnapshot:
    agent_id: str
    status: str  # "ACTIVE" | "DISABLED"

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    agent_id: str
    user_id: str
    status: str  # PENDING | ACTIVE | COMPLETED | EXPIRED | REVOKED
    expires_at: datetime

    def is_expired(self, at: datetime) -> bool:
        return at >= self.expires_at


@dataclass(frozen=True)
class ToolSnapshot:
    tool_id: str
    status: str  # "ACTIVE" | "DISABLED"

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"


@dataclass(frozen=True)
class ResourceScope:
    resource_type: str
    mode: ResourceScopeMode
    ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Constraint:
    operator: ConstraintOperator
    value: object  # int/float for LTE/GTE, str for EQ, list for IN, bool for BOOL_EQ


@dataclass(frozen=True)
class PolicySnapshot:
    policy_id: str
    status: str  # ACTIVE | DISABLED | REVOKED
    effect: Decision  # reuse ALLOW/DENY as the policy's own effect
    agent_id: str
    task_id: str
    tool_id: str
    user_id: str | None
    allowed_actions: tuple[str, ...]
    resource_scope: ResourceScope
    constraints: dict[str, Constraint] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"


@dataclass(frozen=True)
class ProposedAction:
    """What the agent is asking to do - the untrusted, client-supplied part."""

    tool_id: str
    action: str
    resource_type: str
    resource_id: str | None
    parameters: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthorizationRequestContext:
    """
    The already-authenticated identity context a request carries.
    `agent_id` here is derived from the caller's verified credential
    (Day 3), never trusted verbatim from a request body field - see
    docs/SPEC_REVIEW.md Section 3.1.
    """

    agent_id: str
    user_id: str | None
    task_id: str


@dataclass(frozen=True)
class AuthorizationDecision:
    decision: Decision
    reason_code: ReasonCode
    reason: str
    policy_id: str | None = None
