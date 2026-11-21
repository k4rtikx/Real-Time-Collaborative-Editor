# ADR-004 — Redis Architecture
**Date:** 2026-11-22  
**Status:** ACCEPTED  
**Deciders:** Engineering Team

---

## Context

Redis is already used for two purposes in the existing application:
1. Django Channels channel layer (`channels_redis`).
2. Document content cache (`doc:{room_name}`).

The existing Redis usage has no defined key naming convention, no TTL policy, and the content cache key has no expiry (grows forever).

The new design adds Yjs state caching, presence management, awareness state, and rate-limit token buckets — all backed by Redis.

---

## Problem

Define clear Redis responsibilities, key naming conventions, TTL policies, failure behaviour, and memory management so that Redis remains a fast, ephemeral cache layer and is never confused with a durable store.

---

## Decision

### 1. Redis Responsibilities

| Responsibility | Type | Notes |
|---|---|---|
| Django Channels channel layer | Managed by `channels_redis` | Do not interact with these keys directly |
| Yjs document state cache | String (binary) | Fast-path for WebSocket connect |
| Yjs awareness state | Hash | Per-document cursor/selection/presence metadata |
| Presence tracking | Sorted Set + Hash | Connection-aware, TTL-enforced |
| Rate-limit token buckets | Hash | Per-IP (HTTP) and per-connection (WebSocket) |

**Redis must NOT be used for:**
- Authoritative document content (PostgreSQL only).
- User session storage (Django session backend handles this; default is database).
- Long-lived application state.

---

### 2. Key Naming Conventions

All application-managed keys (excluding `channels_redis` internal keys) use the prefix `collabedit:`.

| Key pattern | Type | TTL | Purpose |
|---|---|---|---|
| `collabedit:ydoc:{doc_id}` | String (bytes) | 24 hours | Yjs encoded document state cache |
| `collabedit:awareness:{doc_id}` | Hash `{conn_id: JSON}` | 10 seconds (per field via sorted set clock) | Cursor/selection/user metadata per connection |
| `collabedit:presence:{doc_id}` | Sorted Set `{conn_id: timestamp}` | Member expires via `ZREMRANGEBYSCORE` | Active connections per document |
| `collabedit:presence_data:{doc_id}:{conn_id}` | Hash `{user_id, username, color}` | 30 seconds | Per-connection user metadata |
| `collabedit:rl:http:{ip}` | Hash `{tokens, last_refill}` | 60 seconds | HTTP rate limit bucket |
| `collabedit:rl:ws:{conn_id}` | Hash `{tokens, last_refill}` | 60 seconds | WebSocket rate limit bucket |

**Convention rationale:**
- Prefix `collabedit:` isolates application keys from `channels_redis` keys (which use `asgi:*`).
- `{doc_id}` uses the integer PostgreSQL primary key (not the UUID) for compactness.
- Sorted sets for presence allow efficient `ZREMRANGEBYSCORE` cleanup without scanning.

---

### 3. TTL Policies

| Key | TTL | Reason |
|---|---|---|
| `collabedit:ydoc:{doc_id}` | 24 hours from last write | Documents inactive for 24h reload from PostgreSQL; prevents unbounded memory growth |
| `collabedit:awareness:{doc_id}` | Refreshed on each awareness update; field removed on disconnect | Awareness is ephemeral; stale entries cleaned up aggressively |
| `collabedit:presence:{doc_id}:*` | 30 seconds; refreshed on heartbeat | Prevents stuck presence from crashed connections |
| `collabedit:rl:*` | 60 seconds | Rate limit window; allows natural expiry of idle client state |

**Global Redis policy:**
- `maxmemory-policy: allkeys-lru` — if Redis approaches its memory limit, least-recently-used keys are evicted. This is safe because all Redis data is a cache and can be repopulated from PostgreSQL.
- `maxmemory` should be set to 75% of the available Redis instance memory in production.

---

### 4. Atomic Operations

Operations that must be atomic use Lua scripts or Redis pipelines to prevent race conditions.

**Token Bucket refill and consume (rate limiting):**
```lua
-- Atomic: check and decrement token bucket
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = now - last_refill
local refilled = math.min(capacity, tokens + elapsed * refill_rate)

if refilled >= cost then
    redis.call('HMSET', key, 'tokens', refilled - cost, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 1  -- allowed
else
    redis.call('HMSET', key, 'tokens', refilled, 'last_refill', now)
    redis.call('EXPIRE', key, 60)
    return 0  -- denied
end
```

**Presence connect/disconnect** uses `ZADD`/`ZREM` on the sorted set and `HSET`/`HDEL` on the data hash in a pipeline. These operations are not atomic relative to each other but are idempotent — a stale entry is cleaned by TTL.

---

### 5. Failure Behaviour

| Redis failure scenario | Application behaviour |
|---|---|
| Redis completely unreachable on startup | Application starts; `ydoc` cache miss falls through to PostgreSQL; rate limiting disabled (fail-open); `/health/` returns `"redis": "error"` |
| Redis connection lost mid-operation | `channels_redis` retries automatically; direct `redis-py` calls catch `ConnectionError` and log at WARNING; operation continues where possible |
| Redis evicts `ydoc:{doc_id}` due to memory pressure | Next connect loads from PostgreSQL (normal miss handling) |
| Rate limit key evicted | Token bucket resets to full capacity — allows a brief burst from that client |

The application must never crash because Redis is unavailable. Rate limiting and presence tracking degrade gracefully; document editing continues.

---

### 6. Memory Considerations

Assuming:
- 100 active documents
- Average Yjs encoded state: 50 KB per document
- 500 concurrent connections, 2 rate-limit keys each

Estimated Redis usage:
- `ydoc` keys: 100 × 50 KB = 5 MB
- `awareness` + `presence`: 500 × ~200 bytes = 100 KB
- `rl` keys: 1,000 × ~50 bytes = 50 KB
- `channels_redis` overhead: ~10 MB

**Total estimated: ~15–20 MB** — well within any Render Redis instance size.

---

## Consequences

**Positive:**
- Clear separation between authoritative (PostgreSQL) and ephemeral (Redis) data.
- Key naming makes Redis contents inspectable and debuggable via `redis-cli`.
- TTLs prevent unbounded memory growth; `allkeys-lru` is a safety net.
- Atomic Lua script ensures correct Token Bucket behaviour under concurrent access.
- Redis failure degrades gracefully rather than crashing the application.

**Negative:**
- Presence tracking requires two Redis structures (sorted set + hash); slightly more complex than a simple counter.
- The old `doc:{room_name}` cache key (no namespace, no TTL) must be migrated: existing keys should be deleted or allowed to expire naturally.

**Trade-offs:**
- We use `allkeys-lru` rather than `volatile-lru` because we set TTLs on all our keys — using `allkeys-lru` is safer if a key somehow loses its TTL.
