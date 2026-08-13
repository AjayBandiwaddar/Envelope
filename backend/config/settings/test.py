"""
Test settings.

Uses an in-memory SQLite database instead of PostgreSQL so the test suite
can run without requiring Docker/PostgreSQL to be available (e.g. in CI
runners or sandboxed environments without Docker). Application code must
not rely on PostgreSQL-specific features for Day 1/2 domain logic; if a
future feature genuinely requires PostgreSQL-only behavior, that must be
called out explicitly rather than silently breaking this test config.
"""

from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",  # fast hashing for tests only
]
