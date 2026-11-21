# Product Requirements Document (PRD)
**Product:** CollabEdit — Real-Time Collaborative Editor  
**Version:** 1.0  
**Author:** Engineering Team  
**Date:** 2026-11-22  
**Status:** APPROVED

---

## 1. Purpose

CollabEdit is a web-based collaborative document editor that allows multiple authenticated users to create, edit, and share rich-text documents simultaneously. Changes made by any user are reflected in real time for all collaborators. The authoritative document state is persisted durably in PostgreSQL.

This PRD defines what the product must do. It does not define how. Implementation decisions are captured in ADRs under `docs/02-architecture/adr/`.

---

## 2. Problem Statement

The existing prototype demonstrates the technical skeleton of a real-time editor but is not safe or reliable enough for use by more than one person:

- Any anonymous user who knows a room URL can read and overwrite any document.
- Concurrent edits from two users silently discard one user's work.
- Document content can be lost on server restart.
- No user identity exists — users cannot be identified, authenticated, or attributed.
- The UI shows fake placeholder users instead of real collaborators.

---

## 3. Goals

| Goal | Metric |
|---|---|
| Authenticated access only | 0 unauthenticated users can read or edit any document |
| Conflict-free concurrent editing | 0 edit conflicts or silent data loss under simultaneous editing by ≥ 2 users |
| Durable persistence | Document content survives server restart; PostgreSQL is authoritative |
| Fine-grained permission control | Owner, Editor, and Viewer roles enforced at both HTTP and WebSocket layers |
| Accurate presence | Online user list reflects actual connected users, not counters or placeholders |
| Operational reliability | Application passes health checks; failures are logged and observable |

---

## 4. Non-Goals (Out of Scope for Version 1.0)

- Mobile native applications.
- Offline editing (documents require server connectivity).
- End-to-end encryption of document content.
- Real-time video or audio communication.
- Payment, subscription, or billing.
- Document export (PDF, DOCX).
- Multi-language localisation beyond English.

---

## 5. User Personas

### 5.1 Document Owner (Primary)
A registered user who creates a document. Can edit content, change the title, share the document with specific users, change their permissions, and delete the document.

### 5.2 Editor
A registered user who has been granted edit access to a document by its owner. Can read and edit content. Cannot delete the document or change permissions.

### 5.3 Viewer
A registered user who has been granted view-only access. Can read content in real time but cannot type into the editor.

### 5.4 Unauthenticated Visitor
Can access the landing page and register or sign in. Cannot access, create, or view any document.

---

## 6. Feature Requirements

### 6.1 Authentication (P0)

| ID | Requirement |
|---|---|
| AUTH-01 | Users must be able to register with a username, email address, and password. |
| AUTH-02 | Users must be able to log in with username/email and password. |
| AUTH-03 | Users must be able to log out. |
| AUTH-04 | Passwords must meet Django's default validation rules (min length 8, not common, not purely numeric). |
| AUTH-05 | Sessions must be managed by Django's session framework with secure cookie flags in production. |
| AUTH-06 | Unauthenticated requests to any document endpoint must receive a redirect to the login page. |

### 6.2 Document Management (P0)

| ID | Requirement |
|---|---|
| DOC-01 | An authenticated user can create a new document. A UUID is assigned as the document's permanent identifier. |
| DOC-02 | The document creator is automatically assigned the Owner role. |
| DOC-03 | An authenticated user can view a list of documents they own or have been granted access to. |
| DOC-04 | An owner can rename a document title (max 255 characters). |
| DOC-05 | An owner can delete a document. Deletion is soft (marked deleted, not physically removed) for a configurable retention period. |
| DOC-06 | A user without any permission on a document receives a 403 response — not a 404 that reveals existence. |

### 6.3 Sharing and Permissions (P0)

| ID | Requirement |
|---|---|
| PERM-01 | An owner can share a document with another registered user by username or email, assigning either Editor or Viewer role. |
| PERM-02 | An owner can revoke or change the permission of any collaborator. |
| PERM-03 | An owner cannot revoke their own ownership (the document always has exactly one owner). |
| PERM-04 | Permission changes take effect immediately — an active WebSocket session must be re-validated on the next message. |
| PERM-05 | A user with Viewer permission can connect to the WebSocket but cannot send edit operations. |

### 6.4 Collaborative Editing (P0)

| ID | Requirement |
|---|---|
| COLLAB-01 | Multiple authenticated users with Editor permission can edit the same document concurrently without data loss. |
| COLLAB-02 | Changes from one user appear in all other connected users' editors within 500 ms on a local network under normal load. |
| COLLAB-03 | Conflicts between concurrent edits must be resolved automatically using a CRDT algorithm (Yjs). No user action is required. |
| COLLAB-04 | A user who reconnects after a disconnection receives the current document state without requiring a page reload. |
| COLLAB-05 | Cursor and text selection positions of each collaborator are visible to other connected users. |

### 6.5 Presence (P1)

| ID | Requirement |
|---|---|
| PRES-01 | The editor UI shows the actual names and avatar initials of all currently connected users. |
| PRES-02 | A user who disconnects (tab closed, network dropped) is removed from the presence list within 10 seconds. |
| PRES-03 | A user connected from multiple browser tabs is shown once in the presence list. |
| PRES-04 | Presence information does not survive a server restart as a stale state — cleanup occurs on startup. |

### 6.6 Persistence (P0)

| ID | Requirement |
|---|---|
| PERS-01 | Document content is durably stored in PostgreSQL. |
| PERS-02 | Content is flushed from the in-memory CRDT state to PostgreSQL at least every 30 seconds while the document is active, and immediately when the last user disconnects. |
| PERS-03 | A flush failure is retried up to 3 times with exponential backoff before logging an error. |
| PERS-04 | A newly connecting client receives the current CRDT state from Redis (fast path) or from PostgreSQL (recovery path). |
| PERS-05 | Redis must not be the only permanent store. Loss of Redis data must not cause document content loss. |

### 6.7 Version History (P1)

| ID | Requirement |
|---|---|
| VER-01 | A document snapshot is saved to the `DocumentRevision` table whenever an owner or editor explicitly requests it, or automatically every 100 CRDT updates. |
| VER-02 | An owner can view a list of saved revisions with timestamps and author information. |
| VER-03 | An owner can restore a previous revision. The restored content becomes the new current state. |

### 6.8 Rate Limiting (P0)

| ID | Requirement |
|---|---|
| RATE-01 | HTTP authentication endpoints (login, register) are limited using a Token Bucket: 10 requests per minute per IP. |
| RATE-02 | Document API endpoints are limited: 60 requests per minute per authenticated user. |
| RATE-03 | WebSocket message rate is throttled: maximum 20 messages per second per connection. |
| RATE-04 | WebSocket message payload is limited to 1 MB. |
| RATE-05 | A client exceeding rate limits receives a structured error response (HTTP 429 or WebSocket close code 4029). |

### 6.9 Security (P0)

| ID | Requirement |
|---|---|
| SEC-01 | `SECRET_KEY`, `DATABASE_URL`, and `REDIS_URL` must only be set via environment variables. |
| SEC-02 | No secrets or credentials must appear in logs. |
| SEC-03 | `ALLOWED_HOSTS` must be explicitly set to the deployment hostname. |
| SEC-04 | WebSocket connections must be validated against `ALLOWED_HOSTS` using `AllowedHostsOriginValidator`. |
| SEC-05 | All WebSocket connections must be authenticated before `accept()` is called. |
| SEC-06 | HTTPS and WSS must be enforced in production. |
| SEC-07 | Secure cookie flags (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) must be enabled in production. |

### 6.10 Operations (P1)

| ID | Requirement |
|---|---|
| OPS-01 | A `/health/` HTTP endpoint returns 200 with database and Redis connectivity status. |
| OPS-02 | All application log output uses structured JSON format in production. |
| OPS-03 | No `print()` statements are used anywhere in production code. |
| OPS-04 | A CI pipeline runs linting, type checks, and the full test suite on every push. |

---

## 7. Constraints

- PostgreSQL hosted on Neon; connection string provided via `DATABASE_URL`.
- Redis hosted on Render; connection string provided via `REDIS_URL`.
- Application deployed on Render as a single Docker container.
- Python 3.12, Django 5.x, Django Channels 4.x.
- No separate microservices or task queues in V1.

---

## 8. Success Criteria

| Criterion | Measurement |
|---|---|
| Zero edit loss under concurrent editing | Yjs CRDT convergence test: 2+ simultaneous editors, 0 lost operations |
| Authentication enforcement | No unauthenticated access to any document endpoint |
| Persistence durability | Server restart test: document content identical before and after |
| Rate limiting | 429 returned on 11th auth request within 60 seconds from same IP |
| Health check | `/health/` returns 200 within 2 seconds |
| Test coverage | ≥ 80% line coverage on `apps/` and `core/` |
