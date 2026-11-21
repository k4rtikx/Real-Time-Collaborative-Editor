# ADR-005 — Authentication and Authorization
**Date:** 2026-11-22  
**Status:** ACCEPTED  
**Deciders:** Engineering Team

---

## Context

The existing application has zero authentication or authorization. Any user who knows a room UUID can read and modify any document. The `login.html` template exists but has no view, URL, or backend integration.

A production collaborative editor must:
1. Know who each user is (authentication).
2. Control what each user can do to each document (authorization).
3. Enforce these controls at both the HTTP and WebSocket layers.

---

## Problem

What authentication and authorization framework should be used, and how should it be integrated at both the HTTP and WebSocket layers?

---

## Options Considered

### Option A — Django built-in auth (`django.contrib.auth`) — Selected

Django's built-in authentication system provides:
- `User` model with password hashing (PBKDF2 by default).
- Session-based authentication via cookies.
- `@login_required` decorator and `LoginRequiredMixin`.
- Password validation (already configured in `settings.py`).
- Admin integration.
- `django.contrib.auth.views` for login, logout, and password management.
- `AuthMiddlewareStack` from Django Channels for WebSocket session-to-user resolution.

**Pros:**
- Already in `INSTALLED_APPS`; zero new dependencies.
- WebSocket authentication via `AuthMiddlewareStack` is officially supported by Django Channels.
- Well-tested, well-documented.
- Password validators already configured.

**Cons:**
- Session-based auth requires cookies — works for browsers, not for API clients. Acceptable for V1 (no API clients).
- Does not provide OAuth/SSO out of the box. Deferred to post-V1.

### Option B — `django-allauth`

Adds social login (Google, GitHub, etc.) on top of Django auth.

**Rejected:** Adds significant complexity and dependencies. OAuth providers require application registration and secrets management. The existing `index.html` references `user.socialaccount_set` (suggesting allauth was considered), but the backend never implemented it. Deferred to post-V1 when SSO is a confirmed requirement.

### Option C — Token-based auth (DRF + JWT)

Replace session auth with JWT tokens for a stateless API.

**Rejected:** Overkill for V1. The application is a server-rendered web app, not a pure API. Session cookies are simpler, more secure (HttpOnly, SameSite), and already supported by Django Channels.

---

## Decision

**Use Django built-in authentication (Option A)** with `AbstractUser` subclass for forward compatibility.

### Authentication Design

**HTTP:**
- All document and collaboration views require authentication via `@login_required` or `LoginRequiredMixin`.
- Unauthenticated requests redirect to `/accounts/login/?next=<original-url>`.
- Login and registration forms use Django's built-in `AuthenticationForm` and a custom `RegistrationForm`.

**WebSocket:**
- `asgi.py` wraps the WebSocket URL router in `AuthMiddlewareStack`:
  ```python
  from channels.auth import AuthMiddlewareStack
  from channels.security.websocket import AllowedHostsOriginValidator
  
  application = ProtocolTypeRouter({
      "http": django_asgi_app,
      "websocket": AllowedHostsOriginValidator(
          AuthMiddlewareStack(
              URLRouter(websocket_urlpatterns)
          )
      ),
  })
  ```
- `AuthMiddlewareStack` reads the Django session cookie and resolves `scope["user"]`.
- `DocumentConsumer.connect()` checks `self.scope["user"].is_authenticated` **before** calling `self.accept()`. If not authenticated, the connection is closed with code 4001.

### Authorization Design

Three permission levels per document:

| Role | Can read | Can send edits | Can manage permissions | Can delete document |
|---|---|---|---|---|
| Owner | ✅ | ✅ | ✅ | ✅ |
| Editor | ✅ | ✅ | ❌ | ❌ |
| Viewer | ✅ | ❌ | ❌ | ❌ |
| No access | ❌ | ❌ | ❌ | ❌ |

**Permission resolution:**
```python
# apps/documents/permissions.py

def get_user_role(user, document) -> str | None:
    """Returns 'owner', 'editor', 'viewer', or None."""
    if document.owner_id == user.id:
        return 'owner'
    perm = DocumentPermission.objects.filter(
        document=document, user=user
    ).values_list('role', flat=True).first()
    return perm  # 'editor', 'viewer', or None

def has_edit_permission(user, document) -> bool:
    return get_user_role(user, document) in ('owner', 'editor')

def has_view_permission(user, document) -> bool:
    return get_user_role(user, document) is not None
```

**WebSocket authorization:**
- `connect()`: Load document, call `has_view_permission()`. If `False` → close 4003. If `True` → `accept()`, record role in `self.role`.
- `receive_bytes()`: If `self.role` is `'viewer'` and message is an edit update → close 4003.
- Permission changes take effect on the next message after the grant/revoke because the role is re-checked on each edit operation for Viewer-to-Editor promotion. For revocation, the change is propagated via a channel group message that triggers disconnection.

**HTTP authorization:**
- Views use `get_object_or_404` for existence, then `has_view_permission()` / `has_edit_permission()` returning 403 on failure.
- 403 (not 404) is returned on unauthorized access to prevent document existence disclosure.

### Password Security

Django's default password validators are configured:
- `UserAttributeSimilarityValidator`
- `MinimumLengthValidator` (8 characters)
- `CommonPasswordValidator`
- `NumericPasswordValidator`

Passwords are stored using PBKDF2-SHA256 (Django default). No custom hashing required.

### Session Security (Production)

```python
# settings/production.py
SESSION_COOKIE_SECURE = True      # HTTPS only
SESSION_COOKIE_HTTPONLY = True    # No JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_AGE = 86400 * 14  # 2-week session lifetime
```

---

## Consequences

**Positive:**
- Zero new dependencies.
- WebSocket authentication is handled by Django Channels' official middleware.
- `AbstractUser` subclass allows adding profile fields (avatar, display name) in a future migration without replacing the auth model.
- Session cookies are HttpOnly and SameSite — protected against XSS and CSRF by default.

**Negative:**
- Session-based auth does not work for programmatic API clients (curl, mobile apps) without cookie management. Acceptable for V1.
- If the user's session expires while they are editing, their next WebSocket message will be rejected. The frontend must handle reconnection after re-login gracefully.

**Trade-offs:**
- We defer OAuth/SSO (allauth) to post-V1 because the `AbstractUser` subclass makes it easy to add social accounts later via `django-allauth`'s adapter pattern without changing the User model.
