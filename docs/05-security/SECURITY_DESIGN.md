# Security Design

## CollabEdit — Security Architecture

**Version:** 2.0  
**Last updated:** 2026-11-22  
**Classification:** Internal

---

## 1. Threat model summary

| Threat | Control |
|---|---|
| Unauthenticated access to documents | Session authentication on all document endpoints and WebSocket |
| Cross-user document access | Per-document permission model (`DocumentPermission`) |
| CSRF attacks on state-changing endpoints | `CsrfViewMiddleware` + POST-only logout |
| Cross-origin WebSocket hijacking | `AllowedHostsOriginValidator` |
| Credential brute-force | Redis Token Bucket rate limiting on login (10 req/60 s/IP) |
| Account enumeration via error messages | Uniform error messages on login failure |
| Session fixation | Django rotates session ID on login |
| Secret key exposure | Environment variables only; `.env` in `.gitignore` |
| XSS via document content | Quill.js sanitises HTML; Yjs state is binary |
| SQL injection | Django ORM with parameterised queries |
| Path traversal | No user-controlled file paths |
| Mass assignment | Explicit `update_fields=[]` on all saves |
| Excessive WebSocket payloads | 1 MB hard limit per message |
| WebSocket flood | Redis Token Bucket (60 tokens, 20/s refill) |
| Sensitive data in logs | `JsonFormatter` masks known sensitive key names |
| Insecure cookies | `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True` in production |
| Clickjacking | `XFrameOptionsMiddleware` (DENY) |
| HTTPS downgrade | `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000` in production |

---

## 2. Authentication

**Technology:** Django built-in session authentication  
**User model:** `accounts.User(AbstractUser)` — extends Django's user with no additional fields in V1  
**Session storage:** Database sessions (default)  
**Session cookie:**

| Setting | Development | Production |
|---|---|---|
| `SESSION_COOKIE_SECURE` | False | True |
| `SESSION_COOKIE_HTTPONLY` | True | True |
| `SESSION_COOKIE_SAMESITE` | `Lax` | `Lax` |

**Password policy:** Django's built-in validators:
- Minimum length: 8 characters
- Not too similar to username or email
- Not a common password
- Not entirely numeric

**Failed login:** Generic error message — does not indicate whether username or password was wrong.

---

## 3. Authorization

**Model:** Per-document, per-user role

| Role | Grant mechanism | Capabilities |
|---|---|---|
| `owner` | `Document.owner` FK | Full CRUD, share/revoke, restore revisions |
| `editor` | `DocumentPermission.role = 'editor'` | Read, write, create revisions |
| `viewer` | `DocumentPermission.role = 'viewer'` | Read only; cannot send WS updates |
| (none) | — | Cannot access document at all |

**Key invariant:** The document owner is NOT stored in `DocumentPermission`. Ownership is exclusively on `Document.owner`. This prevents an owner accidentally revoking their own owner status.

**Permission check chain:** Every view/consumer that accesses a document calls `get_user_role()` or `has_*_permission()` from `apps.documents.permissions`. No ad-hoc checks in views.

**WebSocket enforcement:**
- Anonymous connections: rejected with close code `4001` before `accept()`
- No-permission connections: rejected with `4003` before `accept()`
- Viewer sending `MSG_UPDATE`: connection closed with `4003`

---

## 4. CSRF protection

All state-changing HTTP endpoints use `CsrfViewMiddleware`:
- Form POSTs include `csrfmiddlewaretoken`
- AJAX POST (`/documents/<uuid>/title/`) requires `X-CSRFToken` header
- Logout is POST-only (prevents CSRF-based logout via `<img src="...">`)

---

## 5. Rate limiting

**Algorithm:** Redis Token Bucket (Lua script — atomic check-and-update)  
**Fail-open:** If Redis is unavailable, requests are allowed through (logged at WARNING)

| Endpoint | Capacity | Refill |
|---|---|---|
| `/accounts/login/` | 10 tokens | 10/60 s |
| `/accounts/register/` | 5 tokens | 5/60 s |
| `/documents/` | 60 tokens | 1/s (per authenticated user) |
| `/documents/create/` | 10 tokens | 10/60 s (per authenticated user) |
| WebSocket messages | 60 tokens | 20/s (per connection) |

---

## 6. Transport security

| Setting | Value |
|---|---|
| `SECURE_SSL_REDIRECT` | True (production) |
| `SECURE_HSTS_SECONDS` | 31536000 (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | True |
| `SECURE_HSTS_PRELOAD` | True |
| `SECURE_BROWSER_XSS_FILTER` | True |
| `SECURE_CONTENT_TYPE_NOSNIFF` | True |

TLS is terminated at the Render edge. The application receives plain HTTP internally (hence `SECURE_PROXY_SSL_HEADER` for correct scheme detection).

---

## 7. Secret management

| Secret | Storage | Rotation |
|---|---|---|
| `SECRET_KEY` | Render environment variable | Rotate by updating env var + redeploy |
| `DATABASE_URL` | Render environment variable | Rotate via Neon console + update env var |
| `REDIS_URL` | Render environment variable | Rotate via Render Redis console |

**Never:** Commit secrets to git. `.env` is in `.gitignore`. `.env.example` contains only placeholders.

---

## 8. Input validation

| Input | Validation |
|---|---|
| Username | Django's `AbstractUser` validators |
| Password | Django password validators (4 validators) |
| Document title | `max_length=255`; truncated in view before save |
| Share username | `User.objects.get(username=...)` — 404 if not found |
| Share role | Explicit allowlist (`editor`, `viewer`) in `share_document()` |
| WebSocket payload | 1 MB size limit before any parsing |
| JSON body (title update) | `json.loads()` in try/except; type validation |

---

## 9. Audit logging

The `audit.AuditEvent` model records:
- Document creation, deletion, restoration
- Permission grants, updates, revocations
- Actor (user ID), document ID, target user, IP address, timestamp

Audit events are immutable (no `update` or `delete` endpoints). They are written via `log_event()` which is fire-and-forget (exceptions are caught and logged but do not fail the main operation).

---

## 10. Known limitations (V1)

| Limitation | Impact | Mitigation plan |
|---|---|---|
| No email verification | User can register with any email | Add email verification in V2 |
| No MFA | Account compromise possible | Add TOTP in V2 |
| No document content encryption at rest | Data visible to DB admin | Out of scope for V1; consider at-rest encryption for V3 |
| Session-based auth (not JWT) | WebSocket auth depends on session cookie | Acceptable; JWT would add complexity without benefit for this stack |
| No IP allowlist | No geographic restriction | Out of scope |
