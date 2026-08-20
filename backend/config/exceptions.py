"""
DRF exception handler producing the error envelope from API_SPEC.md
Section 5: {"error": {"code", "message", "details"}, "request_id"}.

Maps DRF's built-in exceptions to the API-layer error codes from
API_SPEC.md Section 25. These are a distinct namespace from the
authorization reason codes in POLICY_SPEC.md Section 25 - see
docs/SPEC_REVIEW.md Section 2.2.
"""

from rest_framework import exceptions
from rest_framework.views import exception_handler


def _error_code_for(exc) -> str:
    if isinstance(exc, exceptions.AuthenticationFailed):
        return "INVALID_CREDENTIALS"
    if isinstance(exc, exceptions.NotAuthenticated):
        return "AUTHENTICATION_REQUIRED"
    if isinstance(exc, exceptions.PermissionDenied):
        return "AUTHENTICATION_REQUIRED"
    if isinstance(exc, exceptions.NotFound):
        return "TASK_NOT_FOUND"  # overridden per-view where a more specific code applies
    if isinstance(exc, exceptions.ValidationError):
        return "VALIDATION_ERROR"
    if isinstance(exc, exceptions.Throttled):
        return "RATE_LIMIT_EXCEEDED"
    return "INTERNAL_ERROR"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None

    message = str(exc)
    details = response.data if isinstance(response.data, dict) else {"detail": response.data}

    response.data = {
        "error": {
            "code": _error_code_for(exc),
            "message": message,
            "details": details,
        },
        "request_id": request_id,
    }
    return response