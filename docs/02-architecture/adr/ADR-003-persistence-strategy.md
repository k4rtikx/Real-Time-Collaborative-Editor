# ADR-003 — Persistence Strategy
**Date:** 2026-11-22  
**Status:** ACCEPTED  
**Deciders:** Engineering Team

---

## Context

The existing persistence mechanism spawns a `threading.Thread` per WebSocket message to call `document.save()` in the background. Problems identified in Phase 0:

- **Race condition:** Multiple concurrent threads write to the same row; last thread to execute wins, potentially writing older content on top of newer.
- **Data loss on shutdown:** Threads are `daemon=True`; they are killed silently when the process exits.
- **No retry:** `except Exception: print(...)` discards failures.
- **Connection exhaustion:** Each thread opens a new Django ORM database connection.
- **Performance:** One thread per message; burst typing spawns hundreds of threads per minute.

---

## Problem

Define a reliable, ordered, crash-safe persistence mechanism that:
1. Preserves the most recent document state.
2. Does not lose data on process exit.
3. Retries on transient failure.
4. Does not exhaust database connections.
5. Does not add a separate process or task queue dependency.

---

## Options Considered

### Option A — Celery Task Queue

Each WebSocket message enqueues a Celery task. A separate Celery worker process executes tasks from a Redis queue. Tasks are idempotent; the latest version of a document always wins using `updated_at` timestamp comparison.

**Pros:**
- Celery is mature and production-proven.
- Task queue provides natural ordering and retry.
- Separates persistence from the WebSocket consumer lifecycle.

**Cons:**
- Adds a Celery worker process to the deployment (extra container, extra complexity on Render).
- Adds `celery`, `kombu`, and `amqp` as dependencies.
- Over-engineered for V1 — the same behaviour can be achieved within the async consumer.

**Rejected for V1.** Noted for consideration if the application scales beyond a single container.

### Option B — `asyncio.Task` with debounce inside the consumer (Selected)

Each `DocumentConsumer` instance maintains an asyncio-managed debounce timer. On receiving a Yjs update:
1. The Yjs state is applied and cached in Redis immediately (synchronous fast path).
2. The debounce timer is reset to 30 seconds.
3. When the timer fires (or the last client disconnects), `flush_to_db()` is called as an async coroutine using Django's async ORM.

**Pros:**
- No new processes or dependencies.
- Asyncio coroutine runs in the same event loop — no thread creation.
- Django 4.1+ supports async ORM queries natively.
- Consumer lifecycle (connect/disconnect) guarantees flush on last-disconnect.
- Debounce limits database writes to at most once per 30 seconds per document, regardless of message frequency.

**Cons:**
- If the ASGI process is killed with `SIGKILL` (not `SIGTERM`), the debounce timer is not flushed. This is an inherent limitation of in-process timers.
- Must handle the case where multiple consumer instances exist for the same document (multi-worker or multi-tab). The flush must be idempotent and ordered.

### Option C — Periodic asyncio task at the application level

A single background asyncio task runs every 30 seconds and flushes all active documents.

**Cons:**
- More complex coordination; requires a shared registry of active documents.
- Harder to reason about the lifecycle of the flush relative to WebSocket connections.
- Not materially better than Option B for V1 single-worker deployment.

---

## Decision

**Use Option B: asyncio debounced flush within `DocumentConsumer`.**

Implementation details:

```python
class DocumentConsumer(AsyncWebsocketConsumer):
    _flush_task: asyncio.Task | None = None
    FLUSH_INTERVAL = 30  # seconds

    async def _schedule_flush(self):
        if self._flush_task:
            self._flush_task.cancel()
        self._flush_task = asyncio.create_task(self._flush_after_delay())

    async def _flush_after_delay(self):
        await asyncio.sleep(self.FLUSH_INTERVAL)
        await persistence.flush_to_db(self.doc_id)

    async def disconnect(self, close_code):
        # Cancel timer; flush immediately if last connection
        if self._flush_task:
            self._flush_task.cancel()
        remaining = await presence.remove_connection(self.doc_id, self.conn_id)
        if remaining == 0:
            await persistence.flush_to_db(self.doc_id)
```

`persistence.flush_to_db()`:
1. Load current Yjs encoded state from the consumer's in-memory Yjs doc.
2. Use `select_for_update()` to prevent concurrent flush races.
3. Write `Document.yjs_state` and `Document.updated_at`.
4. Retry up to 3 times on `OperationalError` with backoff: 1s, 2s, 4s.
5. Log failure at ERROR level if all retries exhausted.
6. Update Redis cache TTL.

---

## Consequences

**Positive:**
- No daemon threads. No thread pool.
- Maximum one database write per 30 seconds per document under any typing rate.
- Flush-on-last-disconnect ensures content is saved when all users leave.
- Retry logic handles transient PostgreSQL connectivity issues.
- No new dependency.

**Negative:**
- In the worst case (SIGKILL + no flush), up to 30 seconds of edits since the last successful flush are not in PostgreSQL. They remain in Redis (TTL 24h) and will be loaded on the next connection — so data is not permanently lost as long as Redis survives. If both ASGI process and Redis are lost simultaneously, data loss is bounded to the unflushed window.

**Trade-offs:**
- We accept the SIGKILL risk because Render sends SIGTERM before SIGKILL (allowing graceful shutdown), and SIGTERM handling can trigger a synchronous final flush before exit.
