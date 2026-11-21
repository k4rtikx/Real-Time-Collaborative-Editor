# Test Plan

## CollabEdit — Testing Strategy

**Version:** 2.0  
**Last updated:** 2026-11-22  
**Coverage target:** ≥80% on `apps/` and `core/`

---

## 1. Testing layers

| Layer | Location | Runs in CI | Description |
|---|---|---|---|
| Unit | `apps/*/tests/` | Yes | Individual functions, services, permission helpers |
| Integration (HTTP) | `apps/*/tests/` | Yes | Full request/response cycle via Django test client |
| Integration (WS) | `apps/collaboration/tests/` | Yes | WebSocket consumer via `channels.testing` |
| Concurrency | `tests/concurrency/` | Optional | Multiple simultaneous editors |
| Security | `tests/security/` | Yes | Auth bypass, CSRF, permission escalation attempts |
| Performance | `tests/performance/` | No (manual) | Load testing with Locust |

---

## 2. Test configuration

**Framework:** pytest + pytest-django + pytest-asyncio  
**Coverage:** pytest-cov  
**Configuration:** `pytest.ini` at project root

```ini
[pytest]
DJANGO_SETTINGS_MODULE = doc_editor.settings.development
asyncio_mode = auto
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

**Run all tests:**
```bash
python -m pytest apps/ tests/ --tb=short --cov=apps --cov=core --cov-report=term-missing
```

---

## 3. Unit tests — accounts (`apps/accounts/tests/test_views.py`)

| Test | Description |
|---|---|
| `test_register_success` | Valid registration creates user and redirects |
| `test_register_duplicate_username` | Duplicate username returns form error |
| `test_register_duplicate_email` | Duplicate email returns form error |
| `test_register_password_mismatch` | Password mismatch returns form error |
| `test_login_success` | Valid credentials redirect to `/documents/` |
| `test_login_invalid_credentials` | Wrong password returns error |
| `test_login_redirects_authenticated` | Already-logged-in users are redirected |
| `test_logout_post_only` | GET to logout returns 405 |
| `test_logout_success` | POST logout clears session |
| `test_unauthenticated_redirects_to_login` | Protected views redirect anon users |

---

## 4. Unit tests — documents (`apps/documents/tests/test_documents.py`)

| Test | Description |
|---|---|
| `test_create_document` | Service creates Document + Group |
| `test_share_document_editor` | Owner can share as editor |
| `test_share_document_viewer` | Owner can share as viewer |
| `test_share_non_owner_raises` | Non-owner cannot share |
| `test_share_with_self_raises` | Cannot share with owner |
| `test_revoke_permission` | Owner can revoke |
| `test_soft_delete` | Soft-delete sets `is_deleted=True` |
| `test_create_revision` | Creates revision with correct number |
| `test_restore_revision` | Restores state + creates pre-restore snapshot |
| `test_get_user_role_owner` | Returns `'owner'` for document owner |
| `test_get_user_role_editor` | Returns `'editor'` for editor |
| `test_get_user_role_viewer` | Returns `'viewer'` for viewer |
| `test_get_user_role_no_access` | Returns `None` for unshared user |
| `test_document_list_view` | Lists owned and shared documents |
| `test_document_detail_requires_auth` | Unauthenticated → redirect |
| `test_document_detail_forbidden` | No permission → 403 |
| `test_document_detail_not_found` | Unknown UUID → 404 |
| `test_title_update_valid` | JSON title update succeeds |
| `test_title_update_blank` | Blank title returns 400 |
| `test_title_update_viewer_forbidden` | Viewer cannot update title |

---

## 5. Integration tests — WebSocket consumer (`apps/collaboration/tests/`)

| Test | Description |
|---|---|
| `test_anonymous_connect_rejected_4001` | Anon WS → close 4001 |
| `test_no_permission_connect_rejected_4003` | No-permission WS → close 4003 |
| `test_document_not_found_rejected_4004` | Bad UUID WS → close 4004 |
| `test_viewer_can_connect` | Viewer WS accepts |
| `test_viewer_cannot_send_update` | Viewer MSG_UPDATE → close 4003 |
| `test_editor_can_send_update` | Editor MSG_UPDATE → broadcast |
| `test_owner_can_send_update` | Owner MSG_UPDATE → broadcast |
| `test_payload_too_large_rejected_4008` | > 1 MB payload → close 4008 |
| `test_sync_step1_response` | Server responds to MSG_SYNC_STEP1 |
| `test_awareness_broadcast` | MSG_AWARENESS broadcast to room |
| `test_presence_on_connect` | Presence update sent on connect |
| `test_presence_on_disconnect` | Presence update sent on disconnect |

---

## 6. Security tests (`tests/security/`)

| Test | Description |
|---|---|
| `test_csrf_required_on_create` | Missing CSRF token → 403 |
| `test_cannot_access_other_users_document` | No-permission user → 403 |
| `test_cannot_modify_document_as_viewer` | Viewer cannot POST to title endpoint |
| `test_logout_get_not_allowed` | GET logout → 405 |
| `test_rate_limit_login` | 11+ login attempts → 429 |
| `test_websocket_cross_origin_rejected` | Cross-origin WS → rejected |

---

## 7. Rate limiting tests (`tests/test_rate_limiting.py`)

| Test | Description |
|---|---|
| `test_token_bucket_allows_within_capacity` | Requests within capacity are allowed |
| `test_token_bucket_denies_over_capacity` | Excess requests are denied |
| `test_token_bucket_refills_over_time` | Bucket refills at correct rate |
| `test_token_bucket_fail_open_on_redis_error` | Redis failure → allow (fail-open) |

---

## 8. Health check tests (`tests/test_health.py`)

| Test | Description |
|---|---|
| `test_health_ok` | Returns `{"status": "ok"}` when both services up |
| `test_health_db_down` | Returns `{"status": "degraded"}` when DB unreachable |

---

## 9. CI pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs:

1. **Install dependencies** — `pip install -r requirements.txt -r requirements-dev.txt`
2. **Lint** — `black --check .` + `isort --check .` + `flake8 .`
3. **Test** — `pytest apps/ tests/ --cov=apps --cov=core --cov-fail-under=80`
4. **Services** — PostgreSQL 16 and Redis 7 as GitHub Actions services

Triggered on: push to any branch + pull requests to `main`.

---

## 10. Manual test scenarios

These should be verified manually before each production release:

| Scenario | Expected |
|---|---|
| Register → login → create document | Works end-to-end |
| Share document with another user (editor) | Editor can type |
| Share document with another user (viewer) | Viewer cannot type |
| Revoke permission | Former editor loses access |
| Two browsers editing simultaneously | Both see each other's changes |
| One browser goes offline, edits, reconnects | Offline edits merged correctly |
| Owner restores a revision | Document reverts to old state |
| Legacy URL `/<uuid>/` | Redirects to new editor if owner set |
