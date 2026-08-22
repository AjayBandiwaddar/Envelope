"""
Per-agent rate limiting for the authorization path, backed by Redis.

Design decision worth being explicit about: if Redis itself is
unreachable, the rate-limit *check* fails OPEN (does not block the
request), not closed. This is a narrow, deliberate exception to
AGENTS.md's general Fail-Closed Rule, made for a specific reason:
ARCHITECTURE.md Section 5.10 explicitly requires Redis to remain
"supporting infrastructure only" and never become load-bearing for
core correctness. If a Redis outage turned every legitimate agent
request into a DENY, Redis would have become a single point of failure
for the entire authorization path - exactly what that section forbids.

This does NOT weaken the authorization DECISION itself. Policy
evaluation (apps.authorization.service.authorize) still fails closed
completely independently, for entirely separate reasons (missing
agent/task/policy data, malformed constraints, audit-write failure).
Only the rate-limit *counter* fails open when its own backing store is
down - an agent within its normal request pattern is unaffected either
way, and an agent trying to abuse the system during a Redis outage
still has to pass the full, always-fail-closed policy engine.
"""

from __future__ import annotations

import redis
from django.conf import settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
    return _client


def is_rate_limited(agent_id: str) -> bool:
    """
    Returns True if `agent_id` has exceeded settings.RATE_LIMIT_MAX_REQUESTS
    within the current settings.RATE_LIMIT_WINDOW_SECONDS window.
    """
    try:
        client = _get_client()
        key = f"ratelimit:agent:{agent_id}"
        count = client.incr(key)
        if count == 1:
            client.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
        return count > settings.RATE_LIMIT_MAX_REQUESTS
    except redis.exceptions.RedisError:
        return False


def reset_rate_limit(agent_id: str) -> None:
    """Test/admin helper - clears the counter for one agent."""
    try:
        _get_client().delete(f"ratelimit:agent:{agent_id}")
    except redis.exceptions.RedisError:
        pass