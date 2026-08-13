"""
Health and readiness endpoints.

Per API_SPEC.md §18-19:
  - GET /api/health/  -> liveness only, always {"status": "ok"} if the process
    is up and able to respond. Must not depend on external services.
  - GET /api/ready/   -> verifies required dependencies (database, Redis) and
    returns 503 if any required dependency is unavailable.

These are intentionally cross-cutting (not owned by any single domain app)
so they live alongside the project config rather than inside apps/*.
"""

import redis
from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_view(request):
    """Liveness check. Always returns 200 if the process can serve requests."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def ready_view(request):
    """Readiness check. Verifies database and Redis connectivity."""
    dependencies = {}
    all_ok = True

    # Database check
    try:
        conn = connections["default"]
        conn.cursor()
        dependencies["database"] = "ok"
    except OperationalError:
        dependencies["database"] = "unavailable"
        all_ok = False

    # Redis check
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        client.ping()
        dependencies["redis"] = "ok"
    except redis.exceptions.RedisError:
        dependencies["redis"] = "unavailable"
        all_ok = False
    except Exception:
        # Fail closed: any unexpected error while checking a dependency
        # means we cannot confirm readiness.
        dependencies["redis"] = "unavailable"
        all_ok = False

    status_code = 200 if all_ok else 503
    return Response(
        {
            "status": "ready" if all_ok else "not_ready",
            "dependencies": dependencies,
        },
        status=status_code,
    )
