"""
Testing settings.

Extends development settings with:
  - In-memory SQLite (or test PostgreSQL via DATABASE_URL env var)
  - In-memory channel layer (no Redis required)
  - Disabled rate limiting
  - Faster password hasher (MD5) for speed
  - No logging noise
"""
from .development import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Faster password hashing (tests only — NEVER use in production)
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# In-memory channel layer — no Redis required for consumer tests
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# ---------------------------------------------------------------------------
# Disable rate limiting — no Redis calls during HTTP tests
# ---------------------------------------------------------------------------
RATE_LIMIT_ENABLED = False

# ---------------------------------------------------------------------------
# Silence logging during tests
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"]},
}
