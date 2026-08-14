"""
Deterministic evaluation of a single parameter constraint against a
request's supplied parameter value.

Per POLICY_SPEC.md Section 16: "Constraints must be evaluated
deterministically... No model call is necessary." This module makes no
API calls of any kind and has no side effects.
"""

from __future__ import annotations

from .types import Constraint, ConstraintOperator


class ConstraintEvaluationError(Exception):
    """
    Raised when a constraint's stored shape itself is invalid (e.g. a
    non-numeric `value` on an LTE constraint). This is distinct from the
    constraint simply not being satisfied - an invalid constraint is a
    data problem, and the caller must translate it into
    POLICY_EVALUATION_ERROR / DENY rather than letting an unhandled
    exception propagate, per AGENTS.md's Fail-Closed Rule.
    """


def evaluate_constraint(constraint: Constraint, actual_value: object) -> bool:
    """
    Return True if `actual_value` satisfies `constraint`, False if it does
    not. Raises ConstraintEvaluationError if the constraint's own shape is
    malformed (e.g. attempting a numeric comparison against a non-numeric
    stored value) - this is a POLICY_EVALUATION_ERROR condition, not a
    plain "constraint failed" one, and callers must handle it explicitly.
    """
    op = constraint.operator
    expected = constraint.value

    if op == ConstraintOperator.LTE:
        _require_numeric(expected, "LTE constraint value")
        _require_numeric(actual_value, "LTE actual value")
        return actual_value <= expected

    if op == ConstraintOperator.GTE:
        _require_numeric(expected, "GTE constraint value")
        _require_numeric(actual_value, "GTE actual value")
        return actual_value >= expected

    if op == ConstraintOperator.EQ:
        return actual_value == expected

    if op == ConstraintOperator.IN:
        if not isinstance(expected, (list, tuple, set)):
            raise ConstraintEvaluationError(
                "IN constraint value must be a list of allowed values."
            )
        return actual_value in expected

    if op == ConstraintOperator.BOOL_EQ:
        if not isinstance(expected, bool):
            raise ConstraintEvaluationError(
                "BOOL_EQ constraint value must be a boolean."
            )
        return actual_value is expected

    raise ConstraintEvaluationError(f"Unsupported constraint operator: {op!r}")


def _require_numeric(value: object, what: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConstraintEvaluationError(f"{what} must be numeric, got {value!r}.")
