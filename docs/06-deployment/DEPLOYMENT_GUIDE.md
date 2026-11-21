# Deployment Guide

## CollabEdit — Production Deployment on Render + Neon PostgreSQL

**Version:** 2.0  
**Last updated:** 2026-11-22  
**Target platform:** Render (Web Service, managed Redis), Neon PostgreSQL (serverless)

---

## 1. Prerequisites

| Tool / Account | Required for |
|---|---|
| [Render](https://render.com) account | Hosting the application and Redis |
| [Neon](https://neon.tech) account | Serverless PostgreSQL |
| GitHub repository | Source for Render's CI/CD |
| Docker (local) | Local development and verification |

---

## 2. Environment variables

Set these in Render's **Environment** tab (never commit to source control):

| Variable | Example value | Notes |
|---|---|---|
| `SECRET_KEY` | `50-char random string` | Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DATABASE_URL` | `postgresql://user:pass@host/db?sslmode=require` | Neon connection string (pooled endpoint) |
| `REDIS_URL` | `redis://:password@host:6379` | Render Redis internal URL |
| `DJANGO_SETTINGS_MODULE` | `doc_editor.settings.production` | Use production settings |
| `ALLOWED_HOSTS` | `yourdomain.onrender.com` | Comma-separated list |
| `DEBUG` | `False` | Must be False in production |

---

## 3. Render setup — step by step

### 3.1 Create a Render Redis instance
1. Go to Render dashboard → **New** → **Redis**
2. Plan: **Free** (suitable for demo) or **Starter** (production)
3. Name: `collabedit-redis`
4. After creation, copy the **Internal Redis URL**

### 3.2 Create a Neon PostgreSQL database
1. Go to [neon.tech](https://neon.tech) → New project
2. Region: nearest to your Render region
3. Copy the **Connection string** (pooled, `?sslmode=require`)

### 3.3 Create the Render Web Service
1. Render dashboard → **New** → **Web Service**
2. Connect your GitHub repository
3. **Build command:** `docker build -t collabedit .`
4. **Start command:** leave blank (uses `CMD` from Dockerfile)
5. **Environment:** Docker
6. Set all environment variables from §2
7. Add a **pre-deploy command:**
   ```
   python manage.py migrate --noinput
   ```
8. **Health check path:** `/health/`

### 3.4 Deploy
Push to your main branch → Render automatically:
1. Builds the Docker image
2. Runs pre-deploy command (`migrate`)
3. Starts the new instance
4. Routes traffic (zero-downtime swap)

---

## 4. Dockerfile

The production Dockerfile is at the project root. Key points:
- Multi-stage build (future optimization)
- Non-root user `collabedit` (uid 1001)
- `HEALTHCHECK` on port 8000
- Runs `collectstatic` during build (WhiteNoise serves static files)
- Uvicorn with `--workers 1` (scale via Render replicas)

---

## 5. Docker Compose (local development)

```bash
# Start all services
docker compose up --build

# Run migrations
docker compose exec web python manage.py migrate

# Create a superuser
docker compose exec web python manage.py createsuperuser

# Run tests
docker compose exec web python -m pytest apps/ tests/ --tb=short

# Stop
docker compose down
```

The `docker-compose.yml` includes:
- `web` service (the Django app)
- `redis` service (Redis 7, `maxmemory 256mb allkeys-lru`)
- PostgreSQL is **not** in Docker Compose — use the Neon DATABASE_URL with sslmode=require

---

## 6. Local development without Docker

```powershell
# 1. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Set environment variables (copy and edit)
copy .env.example .env
# Edit .env: set SECRET_KEY, DATABASE_URL, REDIS_URL

# 4. Run migrations
python manage.py migrate

# 5. Create a superuser
python manage.py createsuperuser

# 6. Collect static files
python manage.py collectstatic --noinput

# 7. Start the development server
python manage.py runserver
# OR with Uvicorn (ASGI):
uvicorn doc_editor.asgi:application --reload
```

---

## 7. Running tests

```powershell
# Run all tests with coverage
python -m pytest apps/ tests/ --tb=short --cov=apps --cov=core --cov-report=term-missing

# Run only fast unit tests
python -m pytest apps/ tests/ -m "not slow" --tb=short

# Run a specific test file
python -m pytest apps/accounts/tests/test_views.py -v
```

---

## 8. Migrations

**Always run migrations before starting a new release:**
```bash
python manage.py migrate --noinput
```

**Check for missing migrations before deploying:**
```bash
python manage.py migrate --check
```

**Migration history:**

| App | Migration | Description |
|---|---|---|
| `documents` | `0001_initial` | `Group` table |
| `documents` | `0002_document` | `Document` table |
| `documents` | `0003_document_v2` | Added `title`, `owner`, `yjs_state`, soft-delete |
| `documents` | `0004_permissions_revisions` | `DocumentPermission`, `DocumentRevision` |
| `accounts` | `0001_initial` | `accounts_user` table |
| `audit` | `0001_initial` | `audit_auditevent` table |

---

## 9. Scaling

| Dimension | How to scale |
|---|---|
| Web workers | Increase Render replicas (channel layer is Redis-backed, so multi-worker works) |
| Database | Neon auto-scales; use connection pooling (already in `DATABASE_URL`) |
| Redis | Upgrade Render Redis plan |
| WebSocket connections | Each Uvicorn worker handles many concurrent WebSocket connections via asyncio |

---

## 10. Rollback

If a deployment fails:
1. Render keeps the previous Docker image available
2. Click **Rollback** in the Render dashboard
3. If the new migration is incompatible, run the reverse migration manually from a one-off Render job

---

## 11. Secret rotation

1. Generate a new `SECRET_KEY`
2. Set it in Render environment (all running instances pick it up on next request)
3. Users will be logged out (session signature changes) — expected behavior
4. Database credentials: update `DATABASE_URL` and redeploy

---

## 12. Health monitoring

| Endpoint | Purpose |
|---|---|
| `/health/` | Liveness probe — checks PostgreSQL + Redis |

Render's health check is configured to call `/health/` every 30 seconds. If it returns non-2xx three times, Render marks the deployment as failed.
