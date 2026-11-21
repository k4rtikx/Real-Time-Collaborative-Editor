# Acceptance Criteria
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## Format
Each criterion is linked to a User Story ID and uses the standard Given / When / Then format.

---

## AC-001 — User Registration (US-001)

**Given** I am on the registration page at `/accounts/register/`  
**When** I submit a valid username, email, and password (≥ 8 characters, not common)  
**Then** my account is created, I am logged in, and I am redirected to `/documents/`

**Given** I submit a username that already exists  
**When** the form is validated  
**Then** I see an error message "This username is already taken." and no account is created

**Given** I submit a password shorter than 8 characters  
**When** the form is validated  
**Then** I see a password validation error and no account is created

---

## AC-002 — User Login (US-002)

**Given** I am a registered user on the login page at `/accounts/login/`  
**When** I submit my correct username and password  
**Then** I am logged in and redirected to `/documents/`

**Given** I submit an incorrect password  
**When** the form is validated  
**Then** I see "Invalid username or password." and I remain on the login page. No specific field is highlighted (to avoid username enumeration).

---

## AC-003 — Logout (US-003)

**Given** I am logged in  
**When** I submit the logout form (`POST /accounts/logout/`)  
**Then** my session is destroyed, I am redirected to `/`, and subsequent requests to `/documents/` redirect me to `/accounts/login/`

---

## AC-004 — Redirect Unauthenticated Users (US-004)

**Given** I am not logged in  
**When** I navigate to `/documents/<uuid>/`  
**Then** I am redirected to `/accounts/login/?next=/documents/<uuid>/`

**Given** I complete login after the redirect  
**When** authentication succeeds  
**Then** I am forwarded to `/documents/<uuid>/` (the original destination)

---

## AC-005 — Create Document (US-005)

**Given** I am logged in  
**When** I click "New Document" (which calls `POST /documents/`)  
**Then** a new document with a UUID identifier is created in the database, I am its owner, and I am redirected to the editor at `/documents/<uuid>/`

---

## AC-006 — Document List (US-006)

**Given** I am logged in and I own or have access to 3 documents  
**When** I visit `/documents/`  
**Then** I see all 3 documents listed with their title, last-modified time, and my role

**Given** I have no documents  
**When** I visit `/documents/`  
**Then** I see an empty state with a prompt to create a new document

---

## AC-007 — 403 on Unauthorized Document Access (US-009)

**Given** I am logged in but have no permission on document `<uuid>`  
**When** I navigate to `/documents/<uuid>/`  
**Then** I receive HTTP 403 with a clear "You don't have access to this document." message  
**And** no document content or title is revealed

---

## AC-008 — Share Document (US-010)

**Given** I am the owner of a document  
**When** I submit `POST /documents/<uuid>/permissions/` with `{ "username": "alice", "role": "editor" }`  
**Then** alice has Editor access  
**And** alice can see the document in her document list  
**And** alice can connect to the WebSocket and send edit operations

**Given** I specify a username that does not exist  
**When** the request is processed  
**Then** I receive HTTP 404 with "User not found."

---

## AC-009 — Concurrent Editing Without Data Loss (US-015)

**Given** User A and User B are both connected to the same document as Editors  
**When** User A inserts "Hello" at position 0 and simultaneously User B inserts "World" at position 0  
**Then** after convergence (within 500 ms on a local network) both editors show the same merged content containing both "Hello" and "World"  
**And** neither user's insertion is silently discarded

---

## AC-010 — Viewer Cannot Edit (US-017)

**Given** I am connected to a document as a Viewer  
**When** I attempt to send a Yjs update message via the WebSocket  
**Then** the server closes my connection with code 4003  
**And** the rejected change is not applied to the document or broadcast to others

---

## AC-011 — Reconnection Recovers State (US-018)

**Given** I am connected to a document and have made several edits  
**When** my WebSocket connection drops and reconnects  
**Then** the server sends the current Yjs document state in a `sync` message  
**And** my editor displays the current content without requiring a page reload

---

## AC-012 — Presence List Shows Real Users (US-019, US-020)

**Given** Users A, B, and C are connected to the same document  
**When** I look at the presence panel  
**Then** I see A, B, and C by their actual usernames and avatar initials  
**And** no placeholder names ("Aditi", "Rohit") appear

**Given** User C closes their browser tab  
**When** up to 10 seconds have elapsed  
**Then** C no longer appears in the presence panel for A and B

---

## AC-013 — Persistence Survives Server Restart (US-023)

**Given** I have been editing a document and the last flush occurred 10 seconds ago  
**When** the server process is restarted  
**Then** when I reconnect, the document content is at most 30 seconds of edits behind the last-confirmed state  
**And** the content is loaded from PostgreSQL (not from Redis, which may be empty)

---

## AC-014 — Rate Limiting on Auth Endpoints (US-028)

**Given** I send 10 successful login requests within 60 seconds from the same IP  
**When** I send the 11th request  
**Then** I receive HTTP 429 with `Retry-After` header indicating when I can retry  
**And** the response body contains `{ "error": "rate_limit_exceeded", "retry_after": <seconds> }`

---

## AC-015 — WebSocket Message Rate Limiting (US-028)

**Given** I am connected as an Editor and I send 25 Yjs update messages within 1 second  
**When** the 21st message is received  
**Then** the server drops subsequent messages until the rate drops below 20/second  
**Or** closes the connection with code 4029 (rate limit exceeded)

---

## AC-016 — Health Check (US-029)

**Given** The application, database, and Redis are all operational  
**When** `GET /health/` is called  
**Then** HTTP 200 is returned with body `{ "status": "ok", "db": "ok", "redis": "ok" }`

**Given** The database connection fails  
**When** `GET /health/` is called  
**Then** HTTP 503 is returned with body `{ "status": "degraded", "db": "error", "redis": "ok" }`

---

## AC-017 — Secrets Not in Logs (US-027)

**Given** The application starts with a valid `DATABASE_URL`  
**When** I inspect the application logs  
**Then** the connection string, `SECRET_KEY`, passwords, and tokens do not appear in any log line

---

## AC-018 — Version History (US-024, US-026)

**Given** At least one automatic or manual snapshot has been saved  
**When** I visit `GET /documents/<uuid>/revisions/`  
**Then** I see a list of revisions with timestamps, revision number, and character count

**Given** I am an owner and there are 2+ revisions  
**When** I call `POST /documents/<uuid>/revisions/<id>/restore/`  
**Then** the document content is replaced with the content from that revision  
**And** a new revision is automatically created capturing the state before restore  
**And** all connected editors see the restored content via a Yjs update broadcast
