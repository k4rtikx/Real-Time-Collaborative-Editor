"""
Redis Token Bucket rate limiter.

The check-and-update operation is atomic via a Lua script,
preventing race conditions under concurrent access.

Usage:
    limiter = TokenBucket(redis_client, capacity=10, refill_rate=10/60, key_prefix="http_login")
    allowed, retry_after = limiter.is_allowed("192.168.1.1")

Fail-open: If Redis is unavailable, is_allowed() returns (True, 0.0) and
logs a warning. This prevents a Redis outage from making the application
appear down to legitimate users.
"""
from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lua script — atomic token bucket check and update
# ---------------------------------------------------------------------------
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)
local refilled = math.min(capacity, tokens + elapsed * refill_rate)

if refilled >= cost then
    redis.call('HMSET', key, 'tokens', refilled - cost, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return {1, 0}
else
    local wait_tokens = cost - refilled
    local retry_ms = math.ceil(wait_tokens / refill_rate * 1000)
    redis.call('HMSET', key, 'tokens', refilled, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return {0, retry_ms}
end
"""


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    """Return a module-level cached synchronous Redis client."""
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
    return redis.Redis.from_url(redis_url, decode_responses=False, socket_timeout=1.0)


class TokenBucket:
    """
    Redis-backed Token Bucket rate limiter.

    Args:
        redis_client: A synchronous redis.Redis instance.
        capacity: Maximum number of tokens (burst limit).
        refill_rate: Tokens added per second (steady-state rate).
        key_prefix: Prefix used to build the Redis key.
                    Full key: collabedit:rl:{key_prefix}:{identifier}
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        capacity: float,
        refill_rate: float,
        key_prefix: str,
    ):
        self._redis = redis_client
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._key_prefix = key_prefix
        self._script = redis_client.register_script(_TOKEN_BUCKET_LUA)

    def is_allowed(self, identifier: str, cost: float = 1.0) -> tuple[bool, float]:
        """
        Check whether the request is within the rate limit.

        Args:
            identifier: A unique string identifying the client (IP or user ID).
            cost: Token cost of this request (default 1).

        Returns:
            (allowed, retry_after_seconds)
            - allowed: True if the request is within the limit.
            - retry_after_seconds: 0 if allowed; seconds to wait if denied.
        """
        key = f"collabedit:rl:{self._key_prefix}:{identifier}"
        try:
            result = self._script(
                keys=[key],
                args=[self._capacity, self._refill_rate, time.time(), cost],
            )
            allowed = bool(result[0])
            retry_after = float(result[1]) / 1000.0  # milliseconds → seconds
            return allowed, retry_after
        except redis.ConnectionError as e:
            logger.warning(
                "TokenBucket: Redis unavailable — allowing request (fail-open)",
                extra={"key_prefix": self._key_prefix, "identifier": identifier, "error": str(e)},
            )
            return True, 0.0
        except Exception as e:
            logger.error(
                "TokenBucket: unexpected error — allowing request (fail-open)",
                extra={"key_prefix": self._key_prefix, "identifier": identifier, "error": str(e)},
                exc_info=True,
            )
            return True, 0.0
