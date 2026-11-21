# Error Codes Reference

## CollabEdit — HTTP and WebSocket Error Codes

---

## HTTP error responses

### 400 Bad Request

Returned when the request body is malformed or contains invalid data.

| Endpoint | Cause | Response body |
|---|---|---|
| `POST /documents/<uuid>/title/` | Invalid JSON | `{"error": "Invalid JSON."}` |
| `POST /documents/<uuid>/title/` | Blank title | `{"error": "Title must not be blank."}` |

---

### 403 Forbidden

Returned when the user is authenticated but does not have permission.

| Endpoint | Cause |
|---|---|
| `GET /documents/<uuid>/` | No permission (view rendered as 403) |
| `POST /documents/<uuid>/title/` | User is a viewer |
| `POST /documents/<uuid>/delete/` | User is not the owner |
| `POST /documents/<uuid>/share/` | User is not the owner |
| `POST /documents/<uuid>/share/<username>/revoke/` | User is not the owner |
| `POST /documents/<uuid>/revisions/<n>/restore/` | User is not the owner |

---

### 404 Not Found

Returned when a resource does not exist or has been soft-deleted.

| Endpoint | Cause |
|---|---|
| Any document endpoint | Document UUID not found |
| Any document endpoint | Document `is_deleted=True` |
| `POST /documents/<uuid>/share/<username>/revoke/` | Username not found |
| `POST /documents/<uuid>/revisions/<n>/restore/` | Revision number not found |

---

### 405 Method Not Allowed

Returned when the wrong HTTP method is used.

| Endpoint | Cause |
|---|---|
| `GET /accounts/logout/` | Logout requires POST |
| `GET /documents/create/` | Create requires POST |
| `GET /documents/<uuid>/delete/` | Delete requires POST |

---

### 429 Too Many Requests

Returned when the rate limit is exceeded.

**Response body:**
```json
{
  "error": "rate_limit_exceeded",
  "retry_after": 42,
  "message": "Too many requests. Please wait before trying again."
}
```

**Response headers:** `Retry-After: <seconds>`

| Endpoint | Limit |
|---|---|
| `POST /accounts/login/` | 10 requests per 60 s per IP |
| `POST /accounts/register/` | 5 requests per 60 s per IP |
| `/documents/` (GET) | 60 requests per 60 s per user |
| `/documents/create/` (POST) | 10 requests per 60 s per user |

---

### 500 Internal Server Error

Unexpected server-side error. Check server logs (`level:ERROR`) for details.

---

### 503 Service Unavailable

Returned by `/health/` when PostgreSQL or Redis is unreachable.

```json
{
  "status": "degraded",
  "checks": {
    "database": "error: connection refused",
    "redis": "ok"
  }
}
```

---

## WebSocket close codes

### Standard codes

| Code | Meaning |
|---|---|
| `1000` | Normal closure |
| `1001` | Going away (server shutting down) |
| `1011` | Server error |

### Application-specific codes (4000–4999)

| Code | Name | Trigger |
|---|---|---|
| `4001` | Unauthenticated | WebSocket connection with no valid Django session |
| `4003` | Unauthorized | No permission on the document; or viewer sent MSG_UPDATE |
| `4004` | Not found | Document UUID does not exist or `is_deleted=True` |
| `4008` | Payload too large | Message body exceeds 1,048,576 bytes (1 MB) |
| `4029` | Rate limited | WebSocket Token Bucket exhausted (60 tokens, 20/s refill) |

---

## Django form validation errors

These are returned as rendered HTML (not JSON) on registration and login forms.

| Field | Error | Cause |
|---|---|---|
| `username` | "A user with that username already exists." | Duplicate username |
| `email` | "An account with this email address already exists." | Duplicate email |
| `password1` | "This password is too short. It must contain at least 8 characters." | Password too short |
| `password2` | "The two password fields didn't match." | Password mismatch |
| `__all__` | "Invalid username or password." | Login failure |
| `__all__` | "This account is inactive." | Account disabled |

---

## Share / permission errors (flash messages)

These appear as flash messages on redirect after `POST /documents/<uuid>/share/`:

| Message | Cause |
|---|---|
| "User '<username>' not found." | Username does not exist |
| "Only the document owner can share it." | Caller is not the owner |
| "Cannot share a document with its own owner." | Tried to share with self |
| "Invalid role: '<role>'. Must be 'editor' or 'viewer'." | Invalid role value |
