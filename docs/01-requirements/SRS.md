# Software Requirements Specification (SRS)
**Project:** CollabEdit — Real-Time Collaborative Editor  
**Version:** 1.0  
**Date:** 2026-11-22  
**Status:** APPROVED

---

## 1. Introduction

### 1.1 Purpose
This SRS defines the functional and non-functional requirements for the production-grade transformation of the CollabEdit real-time collaborative document editor.

### 1.2 Scope
The system allows authenticated users to create, edit, share, and version rich-text documents collaboratively. It operates over WebSockets using a CRDT-based synchronisation protocol (Yjs). PostgreSQL is the authoritative data store. Redis serves as the channel layer, presence store, Yjs state cache, and rate-limit state store.

### 1.3 Definitions

| Term | Definition |
|---|---|
| CRDT | Conflict-free Replicated Data Type. A data structure that merges concurrent edits without conflicts. |
| Yjs | An open-source CRDT framework used for collaborative text editing. |
| `y-py` | The Python server-side Yjs library used in the Django Channels consumer. |
| `y-quill` | The JavaScript Quill.js binding for Yjs. |
| Channel layer | The Django Channels pub/sub backend (implemented via `channels_redis`). |
| Room | A WebSocket group identified by a document UUID. All WebSocket connections for the same document belong to the same room. |
| Token Bucket | A rate-limiting algorithm that allows bursts up to a bucket capacity, then limits to a steady-state refill rate. |
| Owner | The user who created a document. Has full control. |
| Editor | A user granted write permission by the owner. |
| Viewer | A user granted read-only permission by the owner. |

---

## 2. Overall Description

### 2.1 System Context

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                        Internet                                  │
 │                                                                  │
 │  ┌──────────┐  HTTPS/WSS  ┌────────────────────────────────┐   │
 │  │ Browser  │◄───────────►│  Render (Single Container)      │   │
 │  └──────────┘             │  Uvicorn → Django ASGI           │   │
 │                           │  Django Channels                 │   │
 │                           └────────┬───────────┬────────────┘   │
 │                                    │           │                 │
 │                           ┌────────▼──┐  ┌────▼────────┐       │
 │                           │  Neon DB  │  │  Render      │       │
 │                           │ PostgreSQL│  │  Redis       │       │
 │                           └───────────┘  └─────────────┘       │
 └─────────────────────────────────────────────────────────────────┘
```

### 2.2 Assumptions
- Users have a modern browser supporting WebSockets and ES2020.
- Network latency between the application server and Redis is < 5 ms.
- Network latency between the application server and PostgreSQL is < 20 ms.
- The application is deployed as a single container (no horizontal scaling in V1).

### 2.3 Constraints
- Must preserve all existing PostgreSQL migrations; migration 0001 and 0002 must remain.
- Python 3.12, Django 5.2+, Django Channels 4.3+.
- No Celery, no separate worker process in V1.

---

## 3. Functional Requirements

### 3.1 User Account Management

**FR-ACC-01:** The system shall provide a registration endpoint (`POST /accounts/register/`) that accepts `username`, `email`, and `password`. On success, the user is logged in and redirected to the document list.

**FR-ACC-02:** The system shall provide a login endpoint (`POST /accounts/login/`) using Django's `AuthenticationForm`. Failed login attempts are logged (without the attempted password).

**FR-ACC-03:** The system shall provide a logout endpoint (`POST /accounts/logout/`) that invalidates the session.

**FR-ACC-04:** The system shall reject unauthenticated HTTP requests to all document and collaboration endpoints with HTTP 302 redirect to `/accounts/login/?next=<original-url>`.

**FR-ACC-05:** The system shall reject unauthenticated WebSocket connection attempts by closing the connection with code 4001 (Unauthorized) before calling `accept()`.

### 3.2 Document Management

**FR-DOC-01:** `POST /documents/` creates a new document. The request body contains an optional `title` (defaults to "Untitled document"). Returns the document UUID and redirect URL.

**FR-DOC-02:** `GET /documents/` returns a list of documents the authenticated user owns or has been granted access to, ordered by `updated_at` descending.

**FR-DOC-03:** `GET /documents/<uuid>/` renders the editor for a document the user has permission to access.

**FR-DOC-04:** `PATCH /documents/<uuid>/` updates the document `title`. Owner only.

**FR-DOC-05:** `DELETE /documents/<uuid>/` soft-deletes the document (sets `is_deleted=True`, `deleted_at=now()`). Owner only.

**FR-DOC-06:** Requests to `/documents/<uuid>/` for a document that does not exist return HTTP 404. Requests to a document the user has no permission on return HTTP 403.

### 3.3 Permission Management

**FR-PERM-01:** `POST /documents/<uuid>/permissions/` grants a user a role. Body: `{ "username": "...", "role": "editor"|"viewer" }`. Owner only.

**FR-PERM-02:** `PATCH /documents/<uuid>/permissions/<user_id>/` changes a user's role. Owner only.

**FR-PERM-03:** `DELETE /documents/<uuid>/permissions/<user_id>/` revokes a user's access. Owner only.

**FR-PERM-04:** An owner cannot remove their own permission entry.

### 3.4 Real-Time Collaboration (WebSocket)

**FR-WS-01:** WebSocket endpoint: `wss://<host>/ws/documents/<uuid>/`

**FR-WS-02:** On connect, the server authenticates the user (via Django session), checks document permission, and sends the current Yjs document state as a `sync` message.

**FR-WS-03:** The server accepts Yjs binary `update` messages from Editors, applies them to the server-side Yjs document, and broadcasts the update to all other connected clients in the same room.

**FR-WS-04:** The server accepts Yjs `awareness` messages (cursor/selection/presence) and broadcasts them to all other connected clients.

**FR-WS-05:** Viewer connections receive all broadcasts but the server rejects `update` messages from them (closes with code 4003 — Forbidden).

**FR-WS-06:** When a client disconnects, the server removes their awareness state and updates the presence information for all remaining clients.

**FR-WS-07:** The server flushes the Yjs document state to PostgreSQL when the last client disconnects from a room, or every 30 seconds while the room is active.

### 3.5 Version History

**FR-VER-01:** `GET /documents/<uuid>/revisions/` returns a list of saved revisions. Owner and Editor access.

**FR-VER-02:** `POST /documents/<uuid>/revisions/` creates a manual snapshot. Owner and Editor access.

**FR-VER-03:** `POST /documents/<uuid>/revisions/<revision_id>/restore/` restores the document to a previous revision. Owner only.

### 3.6 Rate Limiting

**FR-RATE-01:** Auth endpoints apply Token Bucket: capacity=10, refill_rate=10/minute, keyed by IP address.

**FR-RATE-02:** Document API endpoints apply Token Bucket: capacity=60, refill_rate=60/minute, keyed by `user_id`.

**FR-RATE-03:** WebSocket messages apply throttling: max 20 messages/second per connection, enforced server-side.

**FR-RATE-04:** Payloads larger than 1 MB are rejected; connection is closed with code 4008.

### 3.7 Health Check

**FR-HEALTH-01:** `GET /health/` returns HTTP 200 and JSON: `{ "status": "ok", "db": "ok"|"error", "redis": "ok"|"error" }`. No authentication required.

---

## 4. Non-Functional Requirements

### 4.1 Performance

| NFR-ID | Requirement |
|---|---|
| NFR-PERF-01 | WebSocket message roundtrip (edit → server → other client) ≤ 200 ms on a local network. |
| NFR-PERF-02 | HTTP document list (`GET /documents/`) responds in ≤ 300 ms for up to 100 documents. |
| NFR-PERF-03 | The system must handle at least 50 concurrent WebSocket connections per document without message loss. |
| NFR-PERF-04 | PostgreSQL flush must complete within 2 seconds for a document of up to 10,000 words. |

### 4.2 Reliability

| NFR-ID | Requirement |
|---|---|
| NFR-REL-01 | Document content must survive a server restart with no data loss beyond the last 30-second flush window. |
| NFR-REL-02 | Persistence failures must not crash the WebSocket consumer; the error must be logged and retried. |
| NFR-REL-03 | A Redis outage must not cause the application to become unavailable; pending operations are queued and retried. |

### 4.3 Security

| NFR-ID | Requirement |
|---|---|
| NFR-SEC-01 | All WebSocket connections must be authenticated. Zero unauthenticated connections accepted. |
| NFR-SEC-02 | HTTPS must be enforced in production (`SECURE_SSL_REDIRECT = True`). |
| NFR-SEC-03 | HSTS must be enabled with a minimum duration of 1 year. |
| NFR-SEC-04 | No secret or credential must appear in any log line. |
| NFR-SEC-05 | The Django admin must require two-factor authentication in production. (Post-V1 — noted for roadmap.) |

### 4.4 Maintainability

| NFR-ID | Requirement |
|---|---|
| NFR-MAIN-01 | Business logic must reside in service modules, not in views or consumers. |
| NFR-MAIN-02 | Each module must have a single responsibility. |
| NFR-MAIN-03 | Test coverage for `apps/` and `core/` must be ≥ 80%. |
| NFR-MAIN-04 | All public functions and classes must have docstrings. |

### 4.5 Observability

| NFR-ID | Requirement |
|---|---|
| NFR-OBS-01 | Structured JSON logging in production. |
| NFR-OBS-02 | Each log record includes: `timestamp`, `level`, `logger`, `message`, `request_id` (where applicable). |
| NFR-OBS-03 | Errors that result in HTTP 500 or WebSocket close are logged at ERROR level with full traceback. |

---

## 5. Interface Requirements

### 5.1 User Interface
- Rich-text editor powered by Quill.js with Yjs binding (`y-quill`).
- Collaborator presence panel showing real authenticated usernames and avatar initials.
- Real-time cursor positions from other users rendered via Yjs awareness.
- Save status indicator: "Saving…", "Saved", "Offline".
- Document title editable inline, persisted to the server.

### 5.2 External Interfaces
- **PostgreSQL (Neon):** Django ORM via `psycopg` (async driver in consumers).
- **Redis (Render):** `channels_redis` for channel layer; `redis-py` for direct key operations.
- **Yjs (server-side):** `y-py` Python library.

---

## 6. Data Requirements

### 6.1 Data Retention
- Documents: Retained indefinitely unless owner deletes; soft-deleted documents purged after 30 days.
- Document revisions: Retained for the lifetime of the document.
- Audit events: Retained for 90 days.
- Redis keys: TTL set per key type (see ADR-004).

### 6.2 Data Integrity
- PostgreSQL is the authoritative store. Redis is a cache and fast-path only.
- All database writes that modify `Document.content` or create `DocumentRevision` use `select_for_update()` or are protected by application-level ordering.

---

## 7. Transition Requirements

- Existing database migrations (0001, 0002) must not be altered.
- New models are added in new migrations.
- The existing `Group` → `Document` data relationship is preserved; new models are added alongside.
- The landing page URL (`/`) and editor URL (`/<uuid>/`) continue to work after refactoring.
