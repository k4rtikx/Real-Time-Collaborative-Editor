# CollabEdit — Real-Time Collaborative Document Editor

> A production-grade collaborative document editing system built with **Django**, **Django Channels**, **Yjs (CRDT)**, **Redis**, and **PostgreSQL**.

[![CI](https://github.com/<your-org>/real-time-collaborative-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-org>/real-time-collaborative-editor/actions)

---

## Features

- **Real-time collaboration** — Multiple users edit the same document simultaneously using **Yjs CRDT** (Conflict-free Replicated Data Types) — no edit loss, no conflicts
- **Role-based access control** — Owner / Editor / Viewer roles per document
- **Document sharing** — Share documents with other users by username
- **Revision history** — Automatic and manual point-in-time snapshots with restore
- **Presence** — Live list of who is currently editing
- **Redis Token Bucket rate limiting** — HTTP and WebSocket flood protection
- **Secure by default** — CSRF, session auth, HTTPS enforcement, secure cookies
- **Production-ready** — Docker, CI/CD (GitHub Actions), Render + Neon deployment

---

## Technology stack

| Component | Technology |
|---|---|
| Backend framework | Python 3.13, Django 5.2 |
| Real-time layer | Django Channels 4, ASGI, Uvicorn |
| Collaboration engine | Yjs CRDT (pycrdt server-side, y-quill client-side) |
| Rich text editor | Quill.js 1.3.7 |
| Primary database | PostgreSQL (Neon serverless) |
| Cache / pub-sub | Redis (Render managed) |
| Static files | WhiteNoise |
| Containerisation | Docker, Docker Compose |
| CI/CD | GitHub Actions |
| Hosting | Render |

---

## Quick start (local development)

### Prerequisites
- Python 3.13+
- Redis running locally (`redis-server`)
- PostgreSQL database (or use Neon)

```bash
# Clone
git clone <repo-url>
cd real-time-collaborative-editor

# Virtual environment
python -m venv venv
source venv/bin/activate       # Linux/macOS
.\venv\Scripts\Activate        # Windows

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL, REDIS_URL

# Database setup
python manage.py migrate
python manage.py createsuperuser

# Run (ASGI — required for WebSocket support)
uvicorn doc_editor.asgi:application --reload
```

Open `http://localhost:8000` → register → create a document → share the URL with another browser.

---

## Docker Compose

```bash
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

App available at `http://localhost:8000`.

---

## Running tests

```bash
python -m pytest apps/ tests/ --tb=short --cov=apps --cov=core --cov-report=term-missing
```

---

## Project structure

```
real-time-collaborative-editor/
│
├── apps/
│   ├── accounts/          # User auth (registration, login, logout)
│   ├── documents/         # Document CRUD, permissions, revisions
│   ├── collaboration/     # WebSocket consumer, presence, persistence
│   └── audit/             # Immutable audit event log
│
├── core/                  # Shared middleware, rate limiting, health checks
├── frontend/              # Templates and static assets
├── documents/             # Legacy app (preserved for migration continuity)
├── doc_editor/            # Django project config (settings, URLs, ASGI)
├── tests/                 # Cross-app integration and security tests
│
├── docs/
│   ├── 01-requirements/   # PRD, SRS, User Stories, Acceptance Criteria
│   ├── 02-architecture/   # HLD, LLD, System Architecture, ADRs
│   ├── 03-api/            # REST API, WebSocket Protocol
│   ├── 04-testing/        # Test Plan
│   ├── 05-security/       # Security Design
│   ├── 06-deployment/     # Deployment Guide
│   └── 07-operations/     # Runbook
│
├── .github/workflows/ci.yml   # GitHub Actions CI pipeline
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── manage.py
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key — 50+ random chars |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `DJANGO_SETTINGS_MODULE` | No | Defaults to `doc_editor.settings.development` |
| `ALLOWED_HOSTS` | Production | Comma-separated allowed hostnames |
| `DEBUG` | No | `True` in development; `False` in production |

---

## WebSocket protocol

Clients communicate via a binary y-websocket protocol over `wss://<host>/ws/documents/<uuid>/`.

| Message type | Byte | Description |
|---|---|---|
| `MSG_SYNC_STEP1` | `0x00` | Client sends state vector |
| `MSG_SYNC_STEP2` | `0x01` | Server sends full/delta state |
| `MSG_UPDATE` | `0x02` | Yjs document delta |
| `MSG_AWARENESS` | `0x03` | Cursor/selection metadata |

See [`docs/03-api/WEBSOCKET_PROTOCOL.md`](docs/03-api/WEBSOCKET_PROTOCOL.md) for full details.

---

## Deployment (Render)

See [`docs/06-deployment/DEPLOYMENT_GUIDE.md`](docs/06-deployment/DEPLOYMENT_GUIDE.md) for the complete step-by-step guide.

**Short version:**
1. Create Render Web Service connected to this repo
2. Set all environment variables (`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `DJANGO_SETTINGS_MODULE=doc_editor.settings.production`, `ALLOWED_HOSTS`)
3. Set pre-deploy command: `python manage.py migrate --noinput`
4. Set health check path: `/health/`
5. Push to `main` → automatic deploy

---

## Documentation

| Document | Location |
|---|---|
| Product Requirements | `docs/01-requirements/PRD.md` |
| Software Requirements Spec | `docs/01-requirements/SRS.md` |
| High-Level Design | `docs/02-architecture/HLD.md` |
| Low-Level Design | `docs/02-architecture/LLD.md` |
| System Architecture | `docs/02-architecture/SYSTEM_ARCHITECTURE.md` |
| Database Design | `docs/02-architecture/DATABASE_DESIGN.md` |
| Sequence Diagrams | `docs/02-architecture/SEQUENCE_DIAGRAMS.md` |
| REST API | `docs/03-api/REST_API.md` |
| WebSocket Protocol | `docs/03-api/WEBSOCKET_PROTOCOL.md` |
| Test Plan | `docs/04-testing/TEST_PLAN.md` |
| Security Design | `docs/05-security/SECURITY_DESIGN.md` |
| Deployment Guide | `docs/06-deployment/DEPLOYMENT_GUIDE.md` |
| Operations Runbook | `docs/07-operations/RUNBOOK.md` |

---

## License

MIT
