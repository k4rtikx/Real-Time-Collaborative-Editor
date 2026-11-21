# Operations Runbook

## CollabEdit — Production Operations

**Version:** 2.0  
**Audience:** On-call engineer  
**Last updated:** 2026-11-22

---

## 1. Health check

```bash
curl https://<host>/health/
```

Expected response:
```json
{ "status": "ok", "checks": { "database": "ok", "redis": "ok" } }
```

If `status` is `"degraded"`, check which service is failing.

---

## 2. Common incidents

### 2.1 Application returns 500 errors

**Check:**
1. Render service logs (dashboard → Logs tab)
2. Look for Python tracebacks
3. Verify environment variables are all set (`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`)

**Fix:**
- If import error → check `INSTALLED_APPS`, `MIGRATION_MODULES`, settings file selection
- If DB connection → verify `DATABASE_URL` and Neon status at [neon.tech/status](https://neon.tech/status)
- If Redis connection → verify `REDIS_URL` and Render Redis status

---

### 2.2 WebSocket connections fail (clients disconnect immediately)

**Symptoms:** Browser console shows `WebSocket connection to ... failed`

**Check:**
1. Browser DevTools → Network → WS frames
2. Close code in the connection:
   - `4001` → user is not authenticated (session expired)
   - `4003` → permission denied
   - `4004` → document UUID invalid or document deleted
   - `4008` → payload too large
   - `4029` → rate limited

**Fix:**
- `4001`: User needs to log in again
- `4003`: Check document permissions in Django admin
- `4029`: Rate limit is per-connection; it auto-recovers after backoff

---

### 2.3 Edits not being saved

**Symptoms:** Users see edits disappear after reconnect

**Root cause candidates:**
1. Redis Yjs state cache TTL expired + DB flush never completed
2. `flush_to_db` failed 3 times (check logs for `persistence: DB flush failed after 3 attempts`)
3. Document `yjs_state` column is `NULL` (migration 0003 not applied)

**Fix:**
1. Check Render logs for `persistence:` log entries
2. Run `python manage.py shell -c "from apps.documents.models import Document; print(Document.objects.filter(yjs_state__isnull=True).count())"` — if > 0, migration is incomplete
3. Run `python manage.py migrate --noinput` via Render Shell

---

### 2.4 Database migration errors

**Symptoms:** Render pre-deploy command fails; new deployment doesn't start

**Fix:**
1. SSH into Render Shell (Render dashboard → Shell)
2. Run: `python manage.py showmigrations`
3. Run: `python manage.py migrate --noinput --verbosity 2`
4. If conflict: `python manage.py migrate documents 0002 --noinput` to roll back to a known state, then re-run

---

### 2.5 Redis memory full (OOM)

**Symptoms:** `REDIS_OOM_SCORE_ADJ` errors in logs; connections failing

**Prevention:** Redis is configured with `maxmemory 256mb allkeys-lru` — it auto-evicts LRU keys  
**Fix:**
1. If Yjs caches are evicted, next WebSocket connect will reload from PostgreSQL (graceful degradation)
2. If channel layer keys are evicted, in-flight WebSocket messages may be dropped (reconnect resyncs)
3. If rate-limit buckets are evicted, affected clients get a brief free pass (fail-open)
4. Upgrade Render Redis plan if OOM is frequent

---

### 2.6 High response latency

**Symptoms:** Page loads slow; `/health/` shows `"ok"` but P95 > 2 s

**Check:**
1. Neon PostgreSQL query times (Neon console → Monitoring)
2. Check if `TokenBucketRateLimitMiddleware` is making slow Redis calls (should be < 5 ms)
3. Check for missing indexes: `python manage.py check --database default`

**Fix:**
- Neon: check for missing connections or cold-start (use pooled connection string)
- Redis: check Render Redis connection count

---

## 3. Admin operations

### Create a superuser
```bash
# Via Render Shell
python manage.py createsuperuser
```

### Access Django admin
`https://<host>/admin/` — requires superuser account

### View document content in admin
`/admin/documents/document/` — lists all documents with owner, title, and updated_at

### Manually trigger a document revision
```python
# python manage.py shell
from apps.documents.models import Document
from apps.documents.services import create_revision

doc = Document.objects.get(id=<id>)
create_revision(doc, created_by=None, trigger="manual")
```

---

## 4. Useful management commands

```bash
# Check for configuration errors
python manage.py check

# Check for missing migrations
python manage.py migrate --check

# Show migration state
python manage.py showmigrations

# Collect static files
python manage.py collectstatic --noinput

# Django shell
python manage.py shell

# Start dev server
python manage.py runserver

# Start ASGI dev server (WebSocket support)
uvicorn doc_editor.asgi:application --reload
```

---

## 5. Log format

All logs are JSON (in production). Key fields:

| Field | Description |
|---|---|
| `timestamp` | ISO 8601 UTC timestamp |
| `level` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logger` | Logger name (e.g. `apps.collaboration.consumers`) |
| `message` | Human-readable event description |
| `request_id` | UUID for correlating HTTP request logs |
| `user_id` | Authenticated user ID (where available) |
| `doc_uuid` | Document UUID (collaboration events) |
| `conn_id` | WebSocket connection ID |

**Search patterns (Render log search):**
```
# All errors
level:ERROR

# Collaboration events for a document
doc_uuid:<uuid>

# Rate limit hits
rate_limit_exceeded

# Persistence failures
persistence: DB flush failed
```

---

## 6. Backup and recovery

**PostgreSQL:** Neon provides automatic daily backups. Use the Neon console to restore.  
**Redis:** No persistent data that isn't also in PostgreSQL. Redis is a cache layer only.  
**Document state:** `Document.yjs_state` in PostgreSQL is the authoritative source.  
**Revisions:** `DocumentRevision` stores point-in-time snapshots. Use `restore_revision()` to recover.

---

## 7. On-call checklist

When paged for a production issue:

1. ✅ Check `/health/` — is it returning 200?
2. ✅ Check Render dashboard — is the service running?
3. ✅ Check Render logs — look for ERROR or CRITICAL entries
4. ✅ Check Neon status — is PostgreSQL reachable?
5. ✅ Check Render Redis status — is Redis reachable?
6. ✅ Check GitHub Actions — did a bad deploy go out?
7. ✅ If unclear, roll back using Render's rollback button
