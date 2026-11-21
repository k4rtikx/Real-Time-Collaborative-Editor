"""
Base settings shared by all environments.
Do not use this file directly — import from development.py or production.py.
"""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ["SECRET_KEY"]  # validated in __init__.py; never None here
DEBUG = False  # overridden in development.py

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "channels",
    # Project apps
    "apps.accounts",
    "apps.documents",
    "apps.collaboration",
    "apps.audit",
]
# NOTE: "documents" legacy app is intentionally NOT in INSTALLED_APPS.
# apps.documents takes over with label="documents", which makes Django treat
# it as the owner of the existing documents_* tables. The legacy documents/
# package is kept on disk so its migration files (0001, 0002) remain
# discoverable — Django loads migrations by app label, so apps.documents
# with label="documents" picks them up directly.

AUTH_USER_MODEL = "accounts.User"

ASGI_APPLICATION = "doc_editor.asgi.application"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RequestIdMiddleware",
    "core.middleware.TokenBucketRateLimitMiddleware",
]

# ---------------------------------------------------------------------------
# URLs and Templates
# ---------------------------------------------------------------------------
ROOT_URLCONF = "doc_editor.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "frontend" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "doc_editor.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ["DATABASE_URL"]
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
    )
}

# ---------------------------------------------------------------------------
# Redis / Channel Layer
# ---------------------------------------------------------------------------
REDIS_URL = os.environ["REDIS_URL"]

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 1500,
            "expiry": 60,
        },
    },
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/documents/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------------------------
# Default PK
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Migration modules
# ---------------------------------------------------------------------------
# "apps.documents" has label="documents" and owns the existing documents_*
# tables. The legacy migrations (0001, 0002) live in documents/migrations/.
# We redirect Django to find all "documents" app migrations there so we don't
# have to copy them and can continue adding new ones in the same location.
MIGRATION_MODULES = {
    "documents": "documents.migrations",
}

# ---------------------------------------------------------------------------
# Rate limiting config (consumed by core/middleware.py)
# ---------------------------------------------------------------------------
RATE_LIMIT_ENABLED = True
RATE_LIMITS = {
    "/accounts/login/": {"capacity": 10, "refill_rate": 10 / 60},
    "/accounts/register/": {"capacity": 5, "refill_rate": 5 / 60},
    "/documents/": {"capacity": 60, "refill_rate": 1.0, "per_user": True},
    "/documents/create/": {"capacity": 10, "refill_rate": 10 / 60, "per_user": True},
}
