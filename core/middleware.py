"""
Core middleware.

RequestIdMiddleware:
    Attaches a unique request ID to every HTTP request and response.
    Used for correlating log entries.

TokenBucketRateLimitMiddleware:
    Applies Redis Token Bucket rate limiting to configured HTTP endpoints.
    Returns HTTP 429 with Retry-After header on limit exceeded.
    Fails open (allows the request) if Redis is unavailable.

SecurityHeadersMiddleware:
    Adds security headers not covered by Django's built-in middleware.
"""
from __future__ import annotations

import logging
import os
import uuid

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Attach a UUID request ID to every request and response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = str(uuid.uuid4())
        request.request_id = request_id
        response = self.get_response(request)
        response["X-Request-Id"] = request_id
        return response


class TokenBucketRateLimitMiddleware:
    """
    Redis Token Bucket rate limiting middleware.

    Reads RATE_LIMITS from settings. Each entry maps a path prefix to
    a bucket configuration dict with keys:
        capacity    (float) — max tokens (burst limit)
        refill_rate (float) — tokens per second
        per_user    (bool)  — key on user_id instead of IP (default: False)

    Skips rate limiting if:
        - RATE_LIMIT_ENABLED is False (development mode)
        - The path is not in RATE_LIMITS
        - Redis is unavailable (fail-open)
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._limiters: dict = {}
        self._enabled = getattr(settings, "RATE_LIMIT_ENABLED", True)

    def _get_limiter(self, path: str):
        """Return the rate limiter config for the given path, or None."""
        rate_limits = getattr(settings, "RATE_LIMITS", {})
        for prefix, config in rate_limits.items():
            if path.startswith(prefix):
                return config
        return None

    def __call__(self, request):
        if not self._enabled:
            return self.get_response(request)

        # Skip static, ws, admin, and health paths
        skip_prefixes = ("/static/", "/ws/", "/admin/", "/health/")
        if any(request.path.startswith(p) for p in skip_prefixes):
            return self.get_response(request)

        config = self._get_limiter(request.path)
        if config is None:
            return self.get_response(request)

        # Determine identifier
        per_user = config.get("per_user", False)
        if per_user and request.user.is_authenticated:
            identifier = f"user:{request.user.id}"
        else:
            identifier = f"ip:{_get_client_ip(request)}"

        try:
            from core.rate_limiting import TokenBucket, get_redis_client
            limiter = TokenBucket(
                get_redis_client(),
                capacity=config["capacity"],
                refill_rate=config["refill_rate"],
                key_prefix=f"http:{request.path.replace('/', '_')}",
            )
            allowed, retry_after = limiter.is_allowed(identifier)
            if not allowed:
                return JsonResponse(
                    {
                        "error": "rate_limit_exceeded",
                        "retry_after": round(retry_after),
                        "message": "Too many requests. Please wait before trying again.",
                    },
                    status=429,
                    headers={"Retry-After": str(round(retry_after))},
                )
        except Exception as e:
            logger.warning(
                "Rate limit check failed — allowing request (fail-open)",
                extra={"path": request.path, "error": str(e)},
            )

        return self.get_response(request)


def _get_client_ip(request) -> str:
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
