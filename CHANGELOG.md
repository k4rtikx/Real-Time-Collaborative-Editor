# Changelog

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning: [Semantic Versioning](https://semver.org/).

---

## [2.0.0] — 2026-11-22 — Production Engineering Transformation

### Added

**Collaboration engine**
- Yjs CRDT-based collaboration via `y-py` / `pycrdt` server-side and `y-quill` client-side
- Binary y-websocket protocol (MSG_SYNC1, MSG_SYNC2, MSG_UPDATE, MSG_AWARENESS)
- Proper Yjs state persistence to PostgreSQL (`yjs_state` BYTEA column)
- Redis Yjs state cache with 24-hour TTL (fast path on reconnect)
- Debounced async flush (every 30 s, or immediately on last client disconnect)
- Auto-snapshot every 100 updates; manual snapshot support

**Authentication and authorization**
- Full user registration, login, logout
- `accounts.User(AbstractUser)` — custom user model
- Per-document permission model: Owner / Editor / Viewer roles
- Document sharing and revocation (owner only)
- WebSocket authentication via `AuthMiddlewareStack`
- WebSocket authorisation checked before `accept()`
- Viewer enforcement on WebSocket (MSG_UPDATE from viewer → close 4003)

**Persistence and reliability**
- PostgreSQL as the authoritative document store
- 3-retry async flush with exponential backoff
- `DocumentRevision` — immutable point-in-time snapshots
- Revision restore with pre-restore snapshot
- Soft-delete (`is_deleted`, `deleted_at`)

**Rate limiting**
- Redis Token Bucket (Lua script, atomic) for HTTP endpoints
- Separate WebSocket Token Bucket per connection
- Configurable per-endpoint capacity and refill rates
- Fail-open on Redis unavailability

**Presence**
- Redis sorted-set presence tracking with per-connection TTL
- Multi-connection per user support
- Accurate disconnect cleanup
- Server-push JSON text frames for presence panel UI

**Security**
- `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` required as environment variables
- `DEBUG=False` in production
- `ALLOWED_HOSTS` enforced
- `AllowedHostsOriginValidator` on WebSocket
- HSTS, secure cookies, XSS filter, content type nosniff in production settings
- Request ID middleware for log correlation
- Sensitive key masking in JSON log formatter
- Payload size limit (1 MB) on WebSocket messages

**Infrastructure**
- Split settings: `base.py`, `development.py`, `production.py`
- Startup guard: missing env vars → `sys.exit(1)` with clear error
- WhiteNoise for static file serving
- Non-root Docker user (`collabedit:1001`)
- Docker `HEALTHCHECK` on port 8000
- Redis `maxmemory 256mb allkeys-lru` in Docker Compose
- GitHub Actions CI pipeline (lint + test + coverage)

**New database tables**
- `accounts_user` — custom user model
- `documents_documentpermission` — per-document role grants
- `documents_documentrevision` — revision snapshots
- `audit_auditevent` — immutable audit log

**New document fields** (migration 0003)
- `documents_document.title` — human-readable title
- `documents_document.owner` — FK to `accounts_user`
- `documents_document.yjs_state` — CRDT binary state
- `documents_document.is_deleted`, `deleted_at`, `created_at` — soft delete and timestamps

**Documentation** (Phase 1 & 2 complete)
- `PRD.md`, `SRS.md`, `USER_STORIES.md`, `ACCEPTANCE_CRITERIA.md`
- `HLD.md`, `LLD.md`, `SYSTEM_ARCHITECTURE.md`, `COMPONENT_DIAGRAMS.md`
- `DATABASE_DESIGN.md`, `DATA_FLOW.md`, `SEQUENCE_DIAGRAMS.md`
- ADR-001 through ADR-006
- `REST_API.md`, `WEBSOCKET_PROTOCOL.md`
- `TEST_PLAN.md`, `SECURITY_DESIGN.md`
- `DEPLOYMENT_GUIDE.md`, `RUNBOOK.md`
- Updated `README.md`

**Templates**
- `base.html` — shared dark-theme layout
- `accounts/register.html`, `accounts/login.html`
- `documents/list.html` — document grid with owned/shared sections
- `documents/editor.html` — Yjs + Quill editor with presence sidebar
- `documents/revisions.html`, `documents/403.html`

### Changed

- `documents/views.py` — legacy views rewritten to be safe and redirect to new editor
- `documents/consumers.py` — dead file (legacy consumer replaced by `apps/collaboration/consumers.py`)
- `doc_editor/asgi.py` — updated to use `AllowedHostsOriginValidator` + `AuthMiddlewareStack`
- `doc_editor/urls.py` — updated to include new namespaced app URLs
- `manage.py` — `DJANGO_SETTINGS_MODULE` → `doc_editor.settings.development`
- `requirements.txt` — added `whitenoise`, `pycrdt`
- `Dockerfile` — non-root user, `HEALTHCHECK`, `collectstatic`
- `docker-compose.yml` — Redis memory limits, healthcheck
- `.gitignore` — `.env` and `db.sqlite3` excluded

### Fixed

- Module-level Redis connection in `documents/views.py` crashing on import when `REDIS_URL` unset
- Background thread persistence (`save_to_db_background`) — removed (async debounced flush)
- Unsafe broadcast of full HTML content — replaced with Yjs CRDT deltas
- Missing CSRF protection on state-changing endpoints
- No authentication on WebSocket connections
- No authorisation on document access

---

## [1.0.0] — 2026-06-18 — Initial prototype

### Added
- Django project scaffolding
- `documents.Group` and `documents.Document` models
- WebSocket consumer broadcasting full HTML content
- Quill.js 2.0.2 editor
- Redis channel layer
- PostgreSQL persistence via background thread
- Docker and Docker Compose
- Deployment on Render
