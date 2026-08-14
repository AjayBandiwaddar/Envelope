"""
Machine-readable authorization reason codes.

Verbatim from POLICY_SPEC.md Section 25 "Reason Codes" - the minimum set.
Per docs/SPEC_REVIEW.md Section 2.2, this is the canonical reason-code
namespace for authorization *decisions* (used in AuthorizationDecision,
audit events, and the POST /api/authorize/ response body). It is a
separate namespace from API_SPEC.md Section 25's HTTP/API-layer
`error.code` values (VALIDATION_ERROR, AUTHENTICATION_REQUIRED, etc.),
which cover request-level failures that never reach policy evaluation
at all.

This module has zero dependencies outside the Python standard library,
by design - see THREAT_MODEL.md Section 3.6 and ARCHITECTURE.md
Section 5.4 ("no dependency on Django ORM"). It must stay that way.
"""

from enum import Enum


class ReasonCode(str, Enum):
    AUTHORIZED = "AUTHORIZED"

    INVALID_AGENT = "INVALID_AGENT"
    AGENT_DISABLED = "AGENT_DISABLED"

    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_NOT_ACTIVE = "TASK_NOT_ACTIVE"
    TASK_EXPIRED = "TASK_EXPIRED"
    TASK_REVOKED = "TASK_REVOKED"

    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    POLICY_DISABLED = "POLICY_DISABLED"
    POLICY_REVOKED = "POLICY_REVOKED"

    USER_SCOPE_MISMATCH = "USER_SCOPE_MISMATCH"

    ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"

    TOOL_NOT_REGISTERED = "TOOL_NOT_REGISTERED"
    TOOL_DISABLED = "TOOL_DISABLED"

    RESOURCE_TYPE_NOT_ALLOWED = "RESOURCE_TYPE_NOT_ALLOWED"
    RESOURCE_ID_NOT_ALLOWED = "RESOURCE_ID_NOT_ALLOWED"

    REQUIRED_PARAMETER_MISSING = "REQUIRED_PARAMETER_MISSING"
    PARAMETER_SCHEMA_INVALID = "PARAMETER_SCHEMA_INVALID"
    PARAMETER_LIMIT_EXCEEDED = "PARAMETER_LIMIT_EXCEEDED"
    PARAMETER_VALUE_NOT_ALLOWED = "PARAMETER_VALUE_NOT_ALLOWED"

    EXPLICIT_DENY = "EXPLICIT_DENY"

    POLICY_EVALUATION_ERROR = "POLICY_EVALUATION_ERROR"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Human-readable default explanations, used when the caller of the engine
# doesn't supply a more specific message. Kept separate from the codes
# themselves - POLICY_SPEC.md Section 25: "Reason codes should remain
# stable even if human-readable explanations change."
DEFAULT_REASON_TEXT: dict[ReasonCode, str] = {
    ReasonCode.AUTHORIZED: "Request satisfies task authorization.",
    ReasonCode.INVALID_AGENT: "The requesting agent is unknown.",
    ReasonCode.AGENT_DISABLED: "The requesting agent is disabled.",
    ReasonCode.TASK_NOT_FOUND: "The referenced task could not be found.",
    ReasonCode.TASK_NOT_ACTIVE: "The referenced task is not currently active.",
    ReasonCode.TASK_EXPIRED: "The referenced task has expired.",
    ReasonCode.TASK_REVOKED: "The referenced task has been revoked.",
    ReasonCode.POLICY_NOT_FOUND: "No policy grants this action for this task.",
    ReasonCode.POLICY_DISABLED: "The matching policy is currently disabled.",
    ReasonCode.POLICY_REVOKED: "The matching policy has been revoked.",
    ReasonCode.USER_SCOPE_MISMATCH: "The request's user does not match the authorized scope.",
    ReasonCode.ACTION_NOT_ALLOWED: "This action is not authorized for this task.",
    ReasonCode.TOOL_NOT_REGISTERED: "The referenced tool is not registered.",
    ReasonCode.TOOL_DISABLED: "The referenced tool is currently disabled.",
    ReasonCode.RESOURCE_TYPE_NOT_ALLOWED: "This resource type is not authorized.",
    ReasonCode.RESOURCE_ID_NOT_ALLOWED: "This specific resource is not authorized.",
    ReasonCode.REQUIRED_PARAMETER_MISSING: "A required parameter is missing from the request.",
    ReasonCode.PARAMETER_SCHEMA_INVALID: "One or more parameters do not match the expected schema.",
    ReasonCode.PARAMETER_LIMIT_EXCEEDED: "A parameter value exceeds the authorized limit.",
    ReasonCode.PARAMETER_VALUE_NOT_ALLOWED: "A parameter value is not in the authorized set.",
    ReasonCode.EXPLICIT_DENY: "An explicit deny policy matches this request.",
    ReasonCode.POLICY_EVALUATION_ERROR: "An error occurred while evaluating policy; failing closed.",
    ReasonCode.RATE_LIMIT_EXCEEDED: "The request rate limit has been exceeded.",
}
