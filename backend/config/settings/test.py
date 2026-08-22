"""
Test settings.

Uses a file-based SQLite database instead of PostgreSQL so the test
suite can run without requiring Docker/PostgreSQL to be available (e.g.
in CI runners or sandboxed environments without Docker). Application
code must not rely on PostgreSQL-specific features for domain logic; if
a future feature genuinely requires PostgreSQL-only behavior, that must
be called out explicitly rather than silently breaking this test config.

File-based (not ":memory:") deliberately: Django's in-memory SQLite
uses a single shared connection, which is not safe to access from a
worker thread (e.g. anyio.to_thread.run_sync, used by the async MCP
server tests in tests/security/test_adversarial_mcp.py to bridge sync
Django ORM calls into an async context) - it produces "database table
is locked" errors under concurrent thread access. A file-based SQLite
DB lets each thread open its own connection to the same underlying
file, which works correctly. This has no bearing on production
behavior, which always uses real PostgreSQL (config/settings/dev.py) -
this is purely a test-infrastructure choice.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",  # noqa: F405 - BASE_DIR comes from `from .base import *`
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",  # fast hashing for tests only
]