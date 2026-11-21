"""
Health check endpoint.

GET /health/
    Returns HTTP 200 if all services are operational.
    Returns HTTP 503 if any service is degraded.
    No authentication required.
    Not rate-limited.

Response body (JSON):
    {
        "status": "ok" | "degraded",
        "db": "ok" | "error",
        "redis": "ok" | "error"
    }
"""
from __future__ import annotations

import logging
import os

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """Probe PostgreSQL and Redis connectivity."""
    checks: dict[str, str] = {}

    # --- PostgreSQL ---
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["db"] = "ok"
    except Exception as e:
        logger.error("Health check: PostgreSQL failed", extra={"error": str(e)})
        checks["db"] = "error"

    # --- Redis ---
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
        client = redis.Redis.from_url(redis_url, socket_timeout=2.0)
        client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.error("Health check: Redis failed", extra={"error": str(e)})
        checks["redis"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    checks["status"] = "ok" if all_ok else "degraded"

    return JsonResponse(checks, status=200 if all_ok else 503)
