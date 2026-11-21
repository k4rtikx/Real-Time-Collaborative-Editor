# System Architecture

## CollabEdit — Production-Grade Real-Time Collaborative Editor

**Version:** 2.0  
**Last updated:** 2026-11-22  
**Status:** Approved

---

## 1. Architecture overview

CollabEdit follows a **layered monolithic architecture** deployed as a single ASGI process. The design prioritises operational simplicity and correctness over premature distribution. All collaboration logic runs in-process; Redis is used for channel layer pub/sub and rate-limit state only.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Browser                              │
│   Quill.js 1.3.7 + Yjs + y-quill + WebSocket (binary protocol)     │
└──────────────────────┬──────────────────────┬───────────────────────┘
                       │ HTTPS                │ WSS (binary)
                       ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Uvicorn ASGI Server                            │
│              (single worker; scale via Render instances)            │
├─────────────────────────────────────────────────────────────────────┤
│                         Django 5 / Channels 4                       │
│                                                                     │
│  ┌────────────────────┐    ┌────────────────────────────────────┐   │
│  │   HTTP Stack       │    │   WebSocket Stack                  │   │
│  │                    │    │                                    │   │
│  │  SecurityMW        │    │  AllowedHostsOriginValidator       │   │
│  │  WhiteNoiseMW      │    │  AuthMiddlewareStack               │   │
│  │  SessionMW         │    │  URLRouter                         │   │
│  │  CsrfMW            │    │  DocumentConsumer                  │   │
│  │  AuthMW            │    │  (AsyncWebsocketConsumer)          │   │
│  │  RequestIdMW       │    │                                    │   │
│  │  TokenBucketMW     │    │                                    │   │
│  │                    │    │                                    │   │
│  │  apps/accounts     │    │  apps/collaboration                │   │
│  │  apps/documents    │    │    ├── consumers.py                │   │
│  │  core/health       │    │    ├── presence.py                 │   │
│  └────────────────────┘    │    └── persistence.py              │   │
│                            └────────────────────────────────────┘   │
└──────────┬────────────────────────────┬───────────────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────┐         ┌──────────────────────────┐
│  Neon PostgreSQL │         │  Render Redis            │
│                  │         │                          │
│  accounts_user   │         │  Channel layer (pub/sub) │
│  documents_group │         │  Token bucket state      │
│  documents_doc.. │         │  Yjs state cache (TTL)   │
│  ..._permission  │         │  Presence (sorted set)   │
│  ..._revision    │         │                          │
│  audit_auditevent│         │                          │
└──────────────────┘         └──────────────────────────┘
```

---

## 2. Component breakdown

### 2.1 Frontend (browser)

| Component | Technology | Role |
|---|---|---|
| Rich-text editor | Quill.js 1.3.7 | Document editing surface |
| CRDT document | Yjs `Y.Doc` | Conflict-free document state |
| Quill binding | y-quill 0.1.6 | Bridges Yjs mutations ↔ Quill delta ops |
| WebSocket client | Browser WebSocket API | Binary y-websocket protocol transport |
| Awareness | Yjs awareness protocol (msg type 3) | Cursor/selection synchronisation |
| Presence panel | Custom JS | Live user list (driven by server JSON push) |

### 2.2 Backend HTTP layer (`apps/accounts`, `apps/documents`, `core/`)

| Component | Responsibility |
|---|---|
| `accounts` | Registration, login, logout; `User(AbstractUser)` model |
| `documents` | Document CRUD, permission management, revision history |
| `core/middleware` | Request ID tagging; HTTP Token Bucket rate limiting |
| `core/health_checks` | `/health/` liveness probe (PostgreSQL + Redis) |
| `core/rate_limiting` | Shared Lua-script Token Bucket implementation |

### 2.3 WebSocket layer (`apps/collaboration/`)

| Component | Responsibility |
|---|---|
| `consumers.py` | `DocumentConsumer` — authenticates, authorises, manages per-connection lifecycle |
| `presence.py` | `PresenceManager` — Redis sorted-set-based online user tracking with TTL |
| `persistence.py` | `flush_to_db` / `load_from_db` — durable Yjs state → PostgreSQL |
| `routing.py` | Maps `/ws/documents/<uuid>/` → `DocumentConsumer` |

### 2.4 Infrastructure layer

| Component | Technology | Role |
|---|---|---|
| Channel layer | `channels_redis` | Redis-backed pub/sub for broadcasting between consumer instances |
| Static files | WhiteNoise | Serves compressed/cached static files directly from Uvicorn |
| Audit log | `apps/audit` | Immutable audit event append log |
| Container | Docker | Reproducible runtime environment |
| CI | GitHub Actions | Lint + test on every push/PR |

---

## 3. Data flow — HTTP request lifecycle

```
Browser → Uvicorn → SecurityMW → WhiteNoiseMW → SessionMW
       → CsrfMW → AuthMW → RequestIdMW → TokenBucketMW
       → Django URL router → View function
       → Service layer (business logic)
       → Selector / Model (database I/O)
       → HTTP response → Browser
```

**Rate limiting decision point:** `TokenBucketRateLimitMiddleware` checks the Redis Token Bucket before the view runs. If the bucket is empty, 429 is returned with a `Retry-After` header.

---

## 4. Data flow — WebSocket collaboration lifecycle

```
Browser ──(WSS)──► Uvicorn ──► AllowedHostsOriginValidator
                                │  rejects cross-origin
                                ▼
                           AuthMiddlewareStack
                                │  resolves session → user
                                ▼
                           DocumentConsumer.connect()
                                │  1. authenticate (4001 if anon)
                                │  2. load document
                                │  3. check permission (4003 if none)
                                │  4. accept()
                                │  5. join channel group
                                │  6. register presence
                                │  7. send Sync Step 2 (full Yjs state)
                                │  8. init WebSocket Token Bucket
                                ▼
                           receive() loop
                                │  MSG_SYNC1  → respond with full state
                                │  MSG_UPDATE → broadcast + schedule flush
                                │  MSG_AWARENESS → broadcast
                                ▼
                           disconnect()
                                │  cancel flush timer
                                │  remove presence
                                │  if last conn → immediate flush to PG
                                │  leave channel group
```

---

## 5. Deployment topology (Render)

```
┌────────────────────────────────────────────────────────┐
│  Render Web Service (Docker)                           │
│                                                        │
│  CMD: uvicorn doc_editor.asgi:application              │
│       --host 0.0.0.0 --port $PORT                      │
│                                                        │
│  Auto-scales via Render replicas                       │
│  DJANGO_SETTINGS_MODULE=doc_editor.settings.production │
└──────────────┬───────────────────────┬─────────────────┘
               │                       │
               ▼                       ▼
   Neon PostgreSQL (serverless)   Render Redis (managed)
   Connection pooling via         maxmemory 256 MB
   DATABASE_URL with sslmode      allkeys-lru eviction
```

**Migration strategy:** `python manage.py migrate` runs as a Render pre-deploy command before the new instance takes traffic.

---

## 6. Security perimeter

| Boundary | Control |
|---|---|
| HTTP origins | `ALLOWED_HOSTS` env var; `SecurityMiddleware` |
| WebSocket origins | `AllowedHostsOriginValidator` |
| Session authentication | Django session + `AuthMiddlewareStack` |
| CSRF | `CsrfViewMiddleware` on all state-changing HTTP endpoints |
| Logout | POST-only (`require_http_methods(["POST"])`) |
| Rate limiting | Redis Token Bucket (HTTP + WebSocket) |
| Secrets | Environment variables only; never committed |
| HTTPS/WSS | Enforced by Render TLS termination; HSTS in production settings |
| Payload size | 1 MB WebSocket message limit (`MAX_PAYLOAD_BYTES`) |
| Sensitive logs | `JsonFormatter` masks known sensitive key patterns |

---

## 7. Scalability notes

The current architecture runs correctly on a single Uvicorn worker. To scale horizontally:

1. **Channel layer:** Already Redis-backed (`channels_redis`) — multiple workers automatically pub/sub through the shared Redis instance.
2. **Yjs in-memory state (`_ydocs`):** Process-local. In a multi-worker deployment, each worker loads document state from Redis (fast path) or PostgreSQL (slow path) on first WebSocket connection. Workers do not share in-memory state.
3. **Presence:** Redis sorted set — naturally shared across workers.
4. **Rate limiting:** Redis-backed Token Bucket — naturally shared across workers.
5. **Sessions:** Django database sessions — shared via PostgreSQL.

No architectural changes are required to scale to multiple workers. The debounced flush timer is per-process; in a multi-worker deployment each process may flush independently, which is safe because `flush_to_db` uses `update_fields=["yjs_state", "updated_at"]` and PostgreSQL row-level locking via `select_for_update` on revisions.
