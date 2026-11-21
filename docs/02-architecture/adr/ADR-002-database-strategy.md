# ADR-002 — Database Strategy
**Date:** 2026-11-22  
**Status:** ACCEPTED  
**Deciders:** Engineering Team

---

## Context

The existing application uses two PostgreSQL tables (`Group`, `Document`) and a Redis key (`doc:{room}`) for document content. The Redis key holds the authoritative in-memory HTML string, with a background thread periodically writing to PostgreSQL. If Redis is wiped (restart, eviction), the system falls back to PostgreSQL — but PostgreSQL may be many edits behind due to the unreliable background thread.

Decisions needed:
1. What is the authoritative store for document content?
2. How should the new Yjs binary state be stored?
3. How should existing migrations be handled?
4. What connection configuration is appropriate?

---

## Problem

Define a clear, correct data storage strategy for all application data that ensures PostgreSQL is always the authoritative source of truth.

---

## Options Considered

### Option A — Keep Redis as primary, PostgreSQL as backup (current approach)

Redis holds the latest content; PostgreSQL is eventually consistent via background threads.

**Rejected because:**
- Redis is not a durable database. Data is lost on restart unless persistence is explicitly configured (and Render's managed Redis may not guarantee durability).
- Background thread persistence has ordering and crash-safety problems documented in Phase 0.
- "Eventually consistent" means edits can be permanently lost.

### Option B — Eliminate Redis for document content (PostgreSQL only)

Store Yjs state only in PostgreSQL. No Redis cache for content.

**Rejected because:**
- Loading the Yjs document state from PostgreSQL on every WebSocket connection adds 20–50 ms of latency per connection.
- When the server has multiple active connections to the same document, each consumer would need to independently load from PostgreSQL and then coordinate — adding significant complexity.
- Redis channel layer already requires Redis; eliminating Redis for content doesn't remove the dependency.

### Option C — PostgreSQL authoritative + Redis as fast-path cache (Selected)

- PostgreSQL is the **authoritative** store for all document data.
- Redis holds a TTL-bounded cache of the Yjs encoded state for fast-path loading when connecting to an active document.
- Redis is populated from PostgreSQL on first connection; PostgreSQL is written on flush.
- Redis loss → PostgreSQL fallback, with no data loss beyond the unflushed window (≤ 30 seconds).

---

## Decision

**Use Option C: PostgreSQL authoritative with Redis as fast-path cache.**

Specifically:

1. **`Document.yjs_state` (BinaryField in PostgreSQL)** — the Yjs encoded state, written on each flush. This is the recovery source of truth.

2. **`ydoc:{doc_id}` (Redis BinaryString, TTL 24h)** — the Yjs encoded state cached in Redis for fast loading when a user connects to an active document. Written on every flush and invalidated (TTL) after 24 hours of inactivity.

3. **Document load on WebSocket connect:**
   ```
   Redis GET ydoc:{doc_id}
     ├─ HIT  → decode Yjs state, send sync to client
     └─ MISS → SELECT yjs_state FROM documents WHERE id=... 
                → load into Yjs doc
                → Redis SET ydoc:{doc_id} = encoded state, TTL 24h
                → send sync to client
   ```

4. **Existing columns preserved:** `Document.content` (HTML text) is kept for migration continuity. It is no longer written by the new code but is not dropped — dropping it is deferred to a future cleanup migration.

5. **Connection configuration:**
   - `CONN_MAX_AGE = 60` (seconds) — reuse connections for synchronous Django views.
   - Async consumers use `psycopg` async driver via Django's async ORM (`sync_to_async` not needed).

---

## Consequences

**Positive:**
- Document content is never permanently lost to a Redis restart.
- The flush window (≤ 30 seconds) is the maximum data loss window, and it is bounded and documented.
- Redis MISS is handled transparently; the application degrades gracefully under Redis failure.
- Existing migrations are preserved; no data is lost.

**Negative:**
- The first connection to a document after a Redis miss incurs a PostgreSQL read (< 20 ms on Neon).
- Two copies of the Yjs state exist (Redis and PostgreSQL); they can briefly diverge (by up to one flush window).

**Trade-offs:**
- We accept the brief Redis/PostgreSQL divergence because the divergence is bounded, documented, and results in at most 30 seconds of data loss in the worst case (Redis wiped, server crashes simultaneously). This is acceptable for a collaborative text editor; it is not acceptable for financial transactions.
