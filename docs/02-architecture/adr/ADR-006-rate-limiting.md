# ADR-006 — Rate Limiting
**Date:** 2026-11-22  
**Status:** ACCEPTED  
**Deciders:** Engineering Team

---

## Context

The existing application has no rate limiting of any kind. A single client can:
- Send unlimited HTTP requests to login/register (enabling brute-force attacks).
- Send unlimited WebSocket messages (enabling DoS via message flood).
- Send arbitrarily large WebSocket payloads (enabling DoS via memory exhaustion).

---

## Problem

What rate-limiting algorithm and implementation should be used for HTTP endpoints and WebSocket connections?

---

## Algorithm Decision: Token Bucket (Confirmed)

> The user has explicitly confirmed: **Token Bucket algorithm**.

### Why Token Bucket for this application

| Property | Token Bucket | Fixed Window | Sliding Window Log |
|---|---|---|---|
| Allows bursts | ✅ Yes | ❌ No (hard cutoff) | ✅ Yes |
| Smooth steady-state | ✅ Yes | ❌ No (resets abruptly) | ✅ Yes |
| Memory efficient | ✅ O(1) per key | ✅ O(1) per key | ❌ O(events) per key |
| Redis atomic implementation | ✅ Lua script | ✅ INCR + EXPIRE | ❌ Complex |
| Suits typing patterns | ✅ Yes (bursty) | ❌ No | ✅ Yes |

**Token Bucket is the correct choice for a text editor** because:
- Users type in bursts (a word or sentence) followed by pauses.
- A Fixed Window would reject the burst as "too many messages" even though the average rate is well within limits.
- Token Bucket allows the burst (up to bucket capacity) and then enforces the steady-state rate.

---

## Implementation Design

### Core Algorithm

```
State per key: { tokens: float, last_refill: float (Unix timestamp) }

On each request:
1. elapsed = now - last_refill
2. tokens = min(capacity, tokens + elapsed × refill_rate)
3. if tokens >= cost:
       tokens -= cost
       store {tokens, now}
       return ALLOWED
   else:
       store {tokens, now}
       return DENIED
```

### Redis Implementation

The state is stored in a Redis hash. The check-and-update is atomic via Lua script (see ADR-004 for the script).

```python
# core/rate_limiting.py

class TokenBucket:
    """
    Redis-backed Token Bucket rate limiter.
    
    Args:
        capacity: Maximum number of tokens (burst limit).
        refill_rate: Tokens added per second (steady-state rate).
        key_prefix: Redis key prefix.
    """
    
    LUA_SCRIPT = """..."""  # see ADR-004
    
    def __init__(self, redis_client, capacity: float, refill_rate: float, key_prefix: str):
        self.redis = redis_client
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.key_prefix = key_prefix
        self._script = redis_client.register_script(self.LUA_SCRIPT)
    
    def is_allowed(self, identifier: str, cost: float = 1.0) -> tuple[bool, float]:
        """
        Returns (allowed: bool, retry_after_seconds: float).
        retry_after_seconds is 0 if allowed.
        """
        key = f"collabedit:rl:{self.key_prefix}:{identifier}"
        now = time.time()
        result = self._script(
            keys=[key],
            args=[self.capacity, self.refill_rate, now, cost]
        )
        allowed = bool(result)
        if not allowed:
            # Estimate when next token will be available
            retry_after = cost / self.refill_rate
            return False, retry_after
        return True, 0.0
```

### Rate Limit Configurations

| Endpoint | Identifier | Capacity | Refill Rate | Rationale |
|---|---|---|---|---|
| `POST /accounts/login/` | IP address | 10 tokens | 10/min (0.167/s) | Prevent brute-force; allows initial burst |
| `POST /accounts/register/` | IP address | 5 tokens | 5/min (0.083/s) | Stricter; registration is less frequent |
| `GET /documents/` (list) | user_id | 60 tokens | 60/min (1/s) | Normal browsing |
| `POST /documents/` (create) | user_id | 10 tokens | 10/min (0.167/s) | Prevent spam document creation |
| `GET /health/` | None | Unlimited | — | Health checks must not be rate-limited |
| WebSocket messages | conn_id | 60 tokens | 20/s | Allows 60-token burst, then 20 msg/s |

### HTTP Rate Limiting Integration

A Django middleware class applies rate limiting to configured endpoints.

```python
# core/middleware.py

class TokenBucketRateLimitMiddleware:
    """
    Applies Token Bucket rate limiting to HTTP requests.
    
    Exempt paths: /health/, /static/, /ws/
    Returns HTTP 429 with Retry-After header on limit exceeded.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.limiters = {
            '/accounts/login/': TokenBucket(redis_client, 10, 10/60, 'http_login'),
            '/accounts/register/': TokenBucket(redis_client, 5, 5/60, 'http_register'),
            ...
        }
    
    def __call__(self, request):
        limiter = self.limiters.get(request.path)
        if limiter:
            identifier = self._get_client_ip(request)
            allowed, retry_after = limiter.is_allowed(identifier)
            if not allowed:
                return JsonResponse(
                    {'error': 'rate_limit_exceeded', 'retry_after': round(retry_after)},
                    status=429,
                    headers={'Retry-After': str(round(retry_after))}
                )
        return self.get_response(request)
```

### WebSocket Rate Limiting Integration

Applied in `DocumentConsumer.receive_bytes()`:

```python
async def receive_bytes(self, data):
    # 1. Payload size check
    if len(data) > 1_048_576:  # 1 MB
        await self.close(code=4008)
        return
    
    # 2. Message rate check
    allowed, retry_after = await self.ws_limiter.is_allowed_async(self.channel_name)
    if not allowed:
        await self.close(code=4029)
        return
    
    # 3. Process message...
```

### Response Codes

| Code | Context | Meaning |
|---|---|---|
| HTTP 429 | HTTP requests | Rate limit exceeded; `Retry-After` header present |
| WS 4001 | WebSocket | Unauthenticated |
| WS 4003 | WebSocket | Unauthorized (Viewer sending edit, or no permission) |
| WS 4008 | WebSocket | Payload too large |
| WS 4029 | WebSocket | Rate limit exceeded |

### Failure Behaviour

If Redis is unreachable:
- Rate limiting **fails open** (allows the request).
- A WARNING log entry is emitted: `"Rate limit check failed: Redis unavailable — allowing request"`.
- This is intentional: a Redis outage must not make the application appear down to legitimate users.

---

## Consequences

**Positive:**
- Token Bucket accurately models typing patterns — allows bursts without false positives.
- Redis Lua script ensures atomic check-and-update with no race conditions.
- O(1) memory per client key with 60-second TTL.
- Fail-open behaviour prevents Redis outage from blocking legitimate users.
- Clear error codes distinguish rate-limiting from authentication/authorization errors.

**Negative:**
- Fail-open means a Redis outage temporarily disables rate limiting. An attacker who causes Redis to crash gains unconstrained access during the outage window.
- IP-based rate limiting is bypassed by distributed attacks from many IPs (not addressed in V1).

**Trade-offs:**
- We accept fail-open because the alternative (fail-closed, i.e., blocking all requests when Redis is down) makes the application unavailable during Redis maintenance or connectivity issues. Fail-open is the standard choice for rate limiting in distributed systems.
- We use IP-based limiting for auth endpoints rather than user-based because the attacker is not authenticated at the time of the attack.
