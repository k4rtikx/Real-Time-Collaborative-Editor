"""
Settings package.
Selects the appropriate settings module based on DJANGO_SETTINGS_MODULE.
Validates required environment variables at startup.

load_dotenv() is called HERE (before the validation check) so that .env
values are available even if they were not set in the shell environment.
"""
import os
import sys
from pathlib import Path

# Load .env from the project root (two levels up: settings/ → doc_editor/ → root)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_FILE, override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars

_REQUIRED = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]
_missing = [v for v in _REQUIRED if not os.getenv(v)]
if _missing:
    print(
        f"STARTUP ERROR: Missing required environment variables: {', '.join(_missing)}\n"
        f"Set them in your .env file or deployment environment.\n"
        f"Looked for .env at: {_ENV_FILE}",
        file=sys.stderr,
    )
    sys.exit(1)
