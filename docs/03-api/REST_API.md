# REST API Reference

## CollabEdit REST API

**Base URL:** `https://<host>`  
**Authentication:** Django session cookie (set on login)  
**Content-Type:** `application/x-www-form-urlencoded` for form posts; `application/json` for AJAX endpoints  
**CSRF:** All state-changing requests require the `X-CSRFToken` header or `csrfmiddlewaretoken` body field

---

## Authentication endpoints (`/accounts/`)

### `POST /accounts/register/`
Register a new user account.

**Request body (form)**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `username` | string | yes | ≤150 chars; letters, digits, `@`, `.`, `+`, `-`, `_` |
| `email` | string | no | Valid email; unique if provided |
| `password1` | string | yes | Django password validators apply |
| `password2` | string | yes | Must match `password1` |
| `csrfmiddlewaretoken` | string | yes | CSRF token |

**Success:** Redirect `302` → `/documents/`  
**Failure:** `200` with form rendered with field errors

---

### `POST /accounts/login/`
Authenticate an existing user.

**Request body (form)**

| Field | Type | Required |
|---|---|---|
| `username` | string | yes |
| `password` | string | yes |
| `csrfmiddlewaretoken` | string | yes |

**Success:** Redirect `302` → `?next=` or `/documents/`  
**Failure:** `200` with form rendered with error  
**Rate limit:** 10 req / 60 s per IP

---

### `POST /accounts/logout/`
Log out the current user.

**Headers:** `X-CSRFToken: <token>`  
**Success:** Redirect `302` → `/`

---

## Document endpoints (`/documents/`)

> All document endpoints require authentication. Unauthenticated requests redirect to `/accounts/login/?next=<url>`.

### `GET /documents/`
List all documents owned by or shared with the current user.

**Response:** HTML — document list page  
**Rate limit:** 60 req / 60 s per authenticated user

---

### `POST /documents/create/`
Create a new document.

**Request body (form)**

| Field | Type | Required | Default |
|---|---|---|---|
| `title` | string | no | `"Untitled document"` |
| `csrfmiddlewaretoken` | string | yes | — |

**Success:** Redirect `302` → `/documents/<uuid>/`  
**Rate limit:** 10 req / 60 s per authenticated user

---

### `GET /documents/<uuid>/`
Render the collaborative editor for a document.

**Path params:** `uuid` — document UUID (matches `Group.name`)  
**Response:** HTML — editor page with embedded Yjs client  
**Permission required:** viewer, editor, or owner  
**Errors:**
- `404` — document not found or deleted
- `403` — no permission

---

### `POST /documents/<uuid>/title/`
Update the document title (AJAX).

**Headers:** `Content-Type: application/json`, `X-CSRFToken: <token>`  
**Permission required:** editor or owner

**Request body (JSON)**
```json
{ "title": "My new title" }
```

**Response (200)**
```json
{ "status": "ok", "title": "My new title" }
```

**Errors:**
- `400` — invalid JSON or blank title
- `403` — insufficient permission
- `404` — document not found

---

### `POST /documents/<uuid>/delete/`
Soft-delete a document.

**Permission required:** owner  
**Success:** Redirect `302` → `/documents/`

---

### `POST /documents/<uuid>/share/`
Grant a user access to a document.

**Permission required:** owner  
**Request body (form)**

| Field | Type | Required | Values |
|---|---|---|---|
| `username` | string | yes | Existing username |
| `role` | string | yes | `editor` \| `viewer` |
| `csrfmiddlewaretoken` | string | yes | — |

**Success:** Redirect `302` → `/documents/<uuid>/` with success flash  
**Errors:** Redirect with error flash (user not found, invalid role, sharing with self)

---

### `POST /documents/<uuid>/share/<username>/revoke/`
Revoke a user's access to a document.

**Permission required:** owner  
**Success:** Redirect `302` → `/documents/<uuid>/` with success flash

---

### `GET /documents/<uuid>/revisions/`
List revision history for a document.

**Permission required:** viewer, editor, or owner  
**Response:** HTML — revision list page

---

### `POST /documents/<uuid>/revisions/create/`
Manually create a point-in-time revision snapshot.

**Permission required:** editor or owner  
**Success:** Redirect `302` → `/documents/<uuid>/revisions/` with flash

---

### `POST /documents/<uuid>/revisions/<number>/restore/`
Restore the document to a previous revision.

**Permission required:** owner  
**Behaviour:** Creates a pre-restore snapshot first, then overwrites `yjs_state` and `content`  
**Success:** Redirect `302` → `/documents/<uuid>/` with flash

---

## Infrastructure endpoints

### `GET /health/`
Liveness probe — checks PostgreSQL and Redis connectivity.

**Authentication:** None required  
**Response (200)**
```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

**Response (503)** — one or more checks failed
```json
{
  "status": "degraded",
  "checks": {
    "database": "ok",
    "redis": "error: Connection refused"
  }
}
```

---

## HTTP status codes

| Code | Meaning |
|---|---|
| `200` | OK |
| `302` | Redirect |
| `400` | Bad request (invalid input) |
| `403` | Forbidden (insufficient permission) |
| `404` | Not found |
| `405` | Method not allowed |
| `429` | Too many requests (rate limited) |
| `500` | Internal server error |
| `503` | Service unavailable |

### 429 response body
```json
{
  "error": "rate_limit_exceeded",
  "retry_after": 42,
  "message": "Too many requests. Please wait before trying again."
}
```
**Headers:** `Retry-After: <seconds>`
