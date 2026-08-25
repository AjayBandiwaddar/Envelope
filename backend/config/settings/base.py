"""
Base Django settings for the Agent Action Firewall backend.

Shared by all environments (dev/test/prod). Environment-specific
overrides live in dev.py and test.py.

Security-sensitive configuration is read from environment variables,
per ARCHITECTURE.md §22 and AGENTS.md "Data Handling" / "Coding Rules".
Never hard-code production secrets here.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

# Read a .env file if present (local development convenience only).
# Production deployments should supply real environment variables directly.
env_file = BASE_DIR.parent / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-secret-key-do-not-use-in-production",
)

DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
]

# Domain apps. Per docs/SPEC_REVIEW.md §2.1, a dedicated `tasks` app is
# included even though AGENTS.md's own app list omitted it, because
# ARCHITECTURE.md §6-7 and CODEX_EXECUTION_PLAN.md Day 1 §5 both require it.
LOCAL_APPS = [
    "apps.agents",
    "apps.tasks",
    "apps.policies",
    "apps.authorization",
    "apps.tools",
    "apps.audit",
    "apps.commerce",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.RequestIDMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database (PostgreSQL is the system of record — ARCHITECTURE.md §5.11)
# ---------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://agentfw:agentfw_dev_password@localhost:5432/agent_action_firewall",
    )
}

# ---------------------------------------------------------------------------
# Redis (supporting infrastructure only — ARCHITECTURE.md §5.10)
# ---------------------------------------------------------------------------

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.agents.authentication.AdminTokenAuthentication",
        "apps.agents.authentication.AgentBearerTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # API_SPEC.md §28: bound request body size to limit trivial DoS vectors.
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
}

# Shared secret for administrative endpoints (docs/SPEC_REVIEW.md Section
# 3.1). Generate a real random value for anything beyond local dev - see
# .env.example.
ADMIN_API_TOKEN = env("ADMIN_API_TOKEN", default="dev-admin-token-change-me")
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
DEMO_AGENT_TOKEN = env("DEMO_AGENT_TOKEN", default="")
DEMO_TASK_ID = env("DEMO_TASK_ID", default="demo-buyer-task")

# Default task lifetime when a caller doesn't specify expires_at
# (API_SPEC.md Section 8.1's create-task example doesn't show an
# expires_at field in the request; this fills that gap - documented
# assumption, see apps/tasks/serializers.py).
DEFAULT_TASK_DURATION_MINUTES = env.int("DEFAULT_TASK_DURATION_MINUTES", default=30)

# Per-agent rate limiting (apps/authorization/rate_limit.py). Generous
# defaults so normal demo/benchmark traffic isn't affected; tighten for
# any real deployment.
RATE_LIMIT_MAX_REQUESTS = env.int("RATE_LIMIT_MAX_REQUESTS", default=100)
RATE_LIMIT_WINDOW_SECONDS = env.int("RATE_LIMIT_WINDOW_SECONDS", default=60)

DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=1 * 1024 * 1024)  # 1 MB, API_SPEC.md §28

# ---------------------------------------------------------------------------
# CORS (API_SPEC.md §27 — explicit local origin only, never "*")
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"]
)

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging: never log secrets or sensitive payloads (ARCHITECTURE.md §21)
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
}