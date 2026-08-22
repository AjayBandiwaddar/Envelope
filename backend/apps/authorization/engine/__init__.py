"""
Pure-Python policy engine package.

No Django, HTTP, or LLM-client imports are permitted anywhere in this
package - see THREAT_MODEL.md Section 3.6 and ARCHITECTURE.md Section 5.4.
The service layer that bridges this package to Django models and DRF
views lives in apps/authorization/service.py (Day 3), outside this
package.
"""

from .evaluator import evaluate
from .reason_codes import DEFAULT_REASON_TEXT, ReasonCode
from .types import (
    AgentSnapshot,
    AuthorizationDecision,
    AuthorizationRequestContext,
    Constraint,
    ConstraintOperator,
    Decision,
    PolicySnapshot,
    ProposedAction,
    ResourceScope,
    ResourceScopeMode,
    TaskSnapshot,
    ToolSnapshot,
)

__all__ = [
    "evaluate",
    "DEFAULT_REASON_TEXT",
    "ReasonCode",
    "AgentSnapshot",
    "AuthorizationDecision",
    "AuthorizationRequestContext",
    "Constraint",
    "ConstraintOperator",
    "Decision",
    "PolicySnapshot",
    "ProposedAction",
    "ResourceScope",
    "ResourceScopeMode",
    "TaskSnapshot",
    "ToolSnapshot",
]