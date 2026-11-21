# High-Level Design (HLD)
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## 1. System Overview

CollabEdit is a real-time collaborative rich-text editor delivered as a single Django application served over ASGI (Uvicorn). It uses Django Channels for WebSocket management, Yjs CRDT for conflict-free collaborative editing, Redis as the channel layer and state cache, and PostgreSQL as the authoritative data store.

---

## 2. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Internet (HTTPS / WSS)                          │
└───────────────────────────────────────────┬─────────────────────────────────┘
                                            │
┌───────────────────────────────────────────▼─────────────────────────────────┐
│                       Render — Single Docker Container                       │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         Uvicorn (ASGI)                                 │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                  Django ProtocolTypeRouter                      │  │  │
│  │  │                                                                 │  │  │
│  │  │  HTTP                            WebSocket                     │  │  │
│  │  │   │                               │                            │  │  │
│  │  │   ▼                               ▼                            │  │  │
│  │  │  Django App                AllowedHostsOriginValidator          │  │  │
│  │  │  ├── core/middleware        AuthMiddlewareStack                 │  │  │
│  │  │  ├── apps/accounts/        URLRouter                            │  │  │
│  │  │  ├── apps/documents/        └── DocumentConsumer                │  │  │
│  │  │  └── core/health_checks/        (AsyncWebsocketConsumer)        │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────┬─────────────────────────┬────────────────────────┘
                           │                         │
          ┌────────────────▼──┐          ┌───────────▼────────────┐
          │  Neon PostgreSQL  │          │  Render Redis           │
          │                   │          │                         │
          │  users            │          │  Channel layer          │
          │  documents        │          │  Yjs state (TTL 24h)   │
          │  doc_permissions  │          │  Presence hashes        │
          │  doc_revisions    │          │  Awareness data         │
          │  audit_events     │          │  Rate-limit buckets     │
          └───────────────────┘          └─────────────────────────┘
```

---

## 3. Component Summary

| Component | Technology | Responsibility |
|---|---|---|
| **HTTP Layer** | Django 5.2 views | Authentication, document CRUD, permission management, health check |
| **WebSocket Layer** | Django Channels + AsyncWebsocketConsumer | Real-time Yjs update relay, presence, persistence flush |
| **CRDT Engine** | Yjs (`y-py` server-side, `y-quill` + `yjs` client-side) | Conflict-free merge of concurrent edits |
| **Channel Layer** | `channels_redis` | Pub/sub for broadcasting Yjs updates and awareness across consumers |
| **Rate Limiter** | `core/rate_limiting.py` (Redis Token Bucket) | HTTP and WebSocket rate control |
| **Presence** | `apps/collaboration/presence.py` (Redis hash + TTL) | Connection-aware online user tracking |
| **Persistence** | `apps/collaboration/persistence.py` (async debounced) | Yjs state → PostgreSQL flush |
| **PostgreSQL** | Neon (psycopg async) | Authoritative document storage, user accounts, permissions |
| **Redis** | Render Redis | Channel layer, Yjs state cache, presence, rate-limit state |

---

## 4. Request Flows

### 4.1 HTTP Request Flow (Authenticated)

```
Browser ──HTTPS──► Uvicorn
                     │
                   Django ASGI (HTTP)
                     │
                   core/middleware.py  (request ID, security headers)
                     │
                   core/rate_limiting.py  (Token Bucket check)
                     │
                   SessionMiddleware + AuthenticationMiddleware
                     │
                   View (apps/accounts/ or apps/documents/)
                     │
                   Service layer (apps/documents/services.py)
                     │
                   Django ORM ──────────────────► PostgreSQL
                     │
                   HTTP Response ◄──────────────────────────
```

### 4.2 WebSocket Connection Flow

```
Browser ──WSS──► Uvicorn
                   │
                 AllowedHostsOriginValidator  (origin check)
                   │
                 AuthMiddlewareStack           (session → user)
                   │
                 URLRouter  →  DocumentConsumer.connect()
                                │
                              Permission check (apps/documents/permissions.py)
                                │
                              [Reject with 4001/4003] OR [accept()]
                                │
                              Join channel group  (room = doc UUID)
                                │
                              Load Yjs state from Redis or PostgreSQL
                                │
                              Send `sync` message to this client
```

### 4.3 WebSocket Edit Flow (Editor)

```
Browser (User A) sends Yjs binary update
  │
DocumentConsumer.receive_bytes()
  │
Rate limit check (20 msg/s per connection)
  │
Payload size check (≤ 1 MB)
  │
Permission check (Editor role required)
  │
y-py: apply update to server-side Yjs doc
  │
Redis: set ydoc:{doc_id} = encoded state (TTL 24h)
  │
channel_layer.group_send(room, update) ──► All other consumers in room
  │                                           └─► Browser (User B, C, ...)
  │
Debounce timer reset (30s flush window)
```

### 4.4 Persistence Flush Flow

```
Timer fires (30s) OR last client disconnects
  │
persistence.py: flush_to_db(doc_id)
  │
  ├─ Acquire advisory lock (PostgreSQL pg_try_advisory_lock)
  │
  ├─ Encode Yjs state to bytes
  │
  ├─ Document.objects.filter(id=doc_id).update(yjs_state=..., updated_at=now())
  │                                              [async ORM, no threads]
  │
  ├─ [On failure] Retry up to 3× with exponential backoff (1s, 2s, 4s)
  │
  └─ Release advisory lock
```

---

## 5. Security Boundary Summary

| Boundary | Control |
|---|---|
| Public internet → Application | HTTPS/WSS only; `SECURE_SSL_REDIRECT=True` |
| WebSocket origin | `AllowedHostsOriginValidator` |
| WebSocket authentication | `AuthMiddlewareStack` (session-based) |
| WebSocket authorization | Permission check in `connect()` before `accept()` |
| HTTP authentication | `@login_required` decorator / `LoginRequiredMixin` |
| HTTP authorization | `permissions.py` service, returns 403 on failure |
| Rate limiting | Redis Token Bucket per IP (HTTP) and per connection (WS) |
| Secrets | Environment variables only; never logged |

---

## 6. Data Store Responsibilities

### PostgreSQL — Authoritative
- User accounts (`auth_user`)
- Documents (`documents_document`) — includes Yjs binary state
- Document permissions (`documents_documentpermission`)
- Document revisions (`documents_documentrevision`)
- Audit events (`audit_auditevent`)

### Redis — Ephemeral / Performance
- `channels:*` — Django Channels channel layer (managed by `channels_redis`)
- `ydoc:{doc_id}` — Yjs encoded document state (TTL: 24 hours)
- `awareness:{doc_id}` — Yjs awareness state per document
- `presence:{doc_id}` — Hash of `{conn_id: {user_id, username, connected_at}}` (field TTL via sorted set)
- `rl:http:{ip}` — HTTP rate limit bucket state
- `rl:ws:{conn_id}` — WebSocket message rate limit bucket state

---

## 7. Deployment Architecture

```
Render Platform
  │
  ├── Web Service (Docker)
  │     image: collabedit:latest
  │     CMD: uvicorn doc_editor.asgi:application --host 0.0.0.0 --port 8000 --workers 1
  │     env: DATABASE_URL, REDIS_URL, SECRET_KEY, DEBUG=False, ALLOWED_HOSTS
  │
  ├── Redis (Render managed)
  │     REDIS_URL → web service env
  │
  └── PostgreSQL (Neon)
        DATABASE_URL → web service env
```

> **Note:** Single worker in V1. Horizontal scaling (multiple Uvicorn workers or replicas) requires that all workers share the same Redis channel layer, which `channels_redis` supports by design. No code changes are needed to scale out.

---

## 8. Technology Decision Summary

| Decision | Choice | ADR |
|---|---|---|
| Collaboration engine | Yjs CRDT (`y-py` + `y-quill`) | ADR-001 |
| Database strategy | PostgreSQL (Neon), Django ORM with async | ADR-002 |
| Persistence mechanism | Async debounced flush in consumer | ADR-003 |
| Redis architecture | Layered key namespaces, explicit TTLs | ADR-004 |
| Authentication & Authorization | Django built-in auth + `AbstractUser` | ADR-005 |
| Rate limiting | Redis Token Bucket | ADR-006 |
