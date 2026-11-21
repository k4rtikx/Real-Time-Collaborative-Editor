# Data Flow
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## 1. Document Content Data Flow

### 1.1 Write Path (Edit → Storage)

```
User types
  │
Quill.js generates Y.Text delta
  │
y-quill binding converts delta to Yjs update (binary)
  │
WebSocket sends binary frame to server
  │
DocumentConsumer.receive_bytes()
  │
├─ [Rate limit check] → reject if exceeded
├─ [Payload size check] → reject if > 1 MB
├─ [Permission check] → reject if Viewer
│
├─ y-py: Y.Doc.apply_update(update)         [Server CRDT state updated]
│
├─ Redis SET collabedit:ydoc:{doc_id} = Y.Doc.encode_state()   [Cache updated, TTL reset]
│
├─ channel_layer.group_send(update)         [Broadcast to other consumers]
│    └─ Other DocumentConsumers → WebSocket → Other browsers
│         └─ y-quill applies update to Quill.js
│
└─ _schedule_flush() resets debounce timer (30s)
     │
     [30 seconds later, or on last-disconnect]
     │
     persistence.flush_to_db()
       │
       ├─ SELECT ... FOR UPDATE documents WHERE id={doc_id}
       ├─ UPDATE Document SET yjs_state=..., updated_at=now()
       │   [Retry up to 3× on OperationalError]
       └─ Update Redis TTL
```

### 1.2 Read Path (Page Load → Editor Populated)

```
User navigates to /documents/{uuid}/
  │
documents/views.py: get_document_or_403()
  │
├─ Render index.html with {document_id, group_name}
│   (No document content in HTTP response — Yjs state loaded via WebSocket)
│
└─ Browser opens WebSocket: wss://{host}/ws/documents/{uuid}/
     │
     DocumentConsumer.connect()
       │
       ├─ Auth check (scope["user"])
       ├─ Permission check (DB query)
       ├─ accept()
       │
       ├─ presence.add_connection(doc_id, conn_id, user)
       │
       ├─ Redis GET collabedit:ydoc:{doc_id}
       │    ├─ HIT: decode Yjs state → Y.Doc.load(state)
       │    └─ MISS: PostgreSQL SELECT yjs_state WHERE id={doc_id}
       │              └─ Y.Doc.load(state)
       │              └─ Redis SET collabedit:ydoc:{doc_id} = state, EX 86400
       │
       └─ Send Sync Step 1 message to client
            └─ Client responds with Sync Step 2
                 └─ Client receives full current state
                      └─ y-quill populates Quill.js editor
```

---

## 2. Presence Data Flow

### 2.1 Connection

```
DocumentConsumer.connect() accepted
  │
presence.add_connection(doc_id, conn_id, user)
  │
├─ Redis ZADD collabedit:presence:{doc_id} {timestamp} {conn_id}
├─ Redis HSET collabedit:presence_data:{doc_id}:{conn_id}
│         {user_id: ..., username: ..., color: ..., connected_at: ...}
│         EXPIRE 30 seconds
│
└─ channel_layer.group_send(presence_joined, {user_id, username, conn_id})
     └─ All consumers in room broadcast awareness update to their browsers
          └─ Browser adds user to presence panel
```

### 2.2 Disconnection

```
DocumentConsumer.disconnect() (clean or unclean)
  │
presence.remove_connection(doc_id, conn_id)
  │
├─ Redis ZREM collabedit:presence:{doc_id} {conn_id}
├─ Redis DEL collabedit:presence_data:{doc_id}:{conn_id}
├─ Yjs awareness: remove conn_id from awareness state
│
└─ remaining_count = Redis ZCARD collabedit:presence:{doc_id}
     │
     ├─ if remaining_count == 0:
     │    └─ persistence.flush_to_db(doc_id)  [Immediate flush]
     │
     └─ channel_layer.group_send(presence_left, {conn_id})
          └─ All remaining consumers broadcast awareness update
               └─ Browsers remove user from presence panel
```

### 2.3 Stale Presence Cleanup

If a connection crashes without calling `disconnect()`:
- `collabedit:presence_data:{doc_id}:{conn_id}` expires after 30 seconds (TTL).
- A periodic task (run every 10 seconds in the consumer via `asyncio.create_task`) calls `presence.cleanup_stale(doc_id)`:
  ```
  Redis ZRANGEBYSCORE collabedit:presence:{doc_id} 0 {now - 30}
  → ZREM each stale conn_id
  → DEL each stale presence_data key
  → Broadcast updated presence to remaining clients
  ```

---

## 3. Authentication Data Flow

```
Browser                    Django                       PostgreSQL
   │                          │                              │
   │-- POST /accounts/login/ ->│                             │
   │                          │-- AuthenticationForm.validate()
   │                          │-- authenticate(username, password)
   │                          │-- SELECT auth_user WHERE username=... -->│
   │                          │<-- user record (or None) --------------|
   │                          │-- check_password(password, stored_hash)
   │                          │-- login(request, user)
   │                          │-- INSERT django_session ------------------>│
   │<-- 302 /documents/ ------|   Set-Cookie: sessionid=... HttpOnly Secure
   │
   │-- GET /documents/ ------->│
   │   Cookie: sessionid=...  │-- SessionMiddleware: resolve session
   │                          │-- AuthenticationMiddleware: resolve user
   │                          │-- @login_required: pass
   │                          │-- View executes
   │<-- 200 Document list -----|
```

---

## 4. Rate Limit Data Flow

```
Browser                   Middleware                      Redis
   │                          │                              │
   │-- POST /accounts/login/ ->│                             │
   │                          │-- compute key: collabedit:rl:http_login:{ip}
   │                          │-- EVAL Lua script ----------->│
   │                          │   HMGET {tokens, last_refill} │
   │                          │   compute elapsed + refill    │
   │                          │   if tokens >= 1:            │
   │                          │     HMSET tokens=tokens-1    │
   │                          │     return 1 (allowed)        │
   │                          │   else:                       │
   │                          │     return 0 (denied)         │
   │                          │<-- 1 or 0 -------------------|
   │                          │                              │
   │   if 0 (denied):         │                              │
   │<-- 429 Retry-After: N ---|                              │
   │                          │                              │
   │   if 1 (allowed):        │                              │
   │                          │-- forward to view           │
   │<-- view response ---------|                              │
```

---

## 5. Audit Event Data Flow

Audit events are written synchronously in service functions (not in middleware, not in consumers).

```
Owner calls POST /documents/{uuid}/permissions/
  │
documents/services.py: grant_permission(owner, document, target_user, role)
  │
├─ DocumentPermission.objects.create(...)   [PostgreSQL write]
│
└─ audit_services.log_event(
       event_type='permission.granted',
       actor=owner,
       document=document,
       target_user=target_user,
       metadata={'role': role},
       ip_address=request.META['REMOTE_ADDR']
   )
     │
     └─ AuditEvent.objects.create(...)      [PostgreSQL write]
```

Audit events are never updated or deleted (append-only). Purge is via management command.

---

## 6. Version Snapshot Data Flow

### 6.1 Automatic Snapshot (every N CRDT updates)

```
DocumentConsumer.receive_bytes()
  │
self._update_count += 1
  │
if self._update_count % 100 == 0:
  │
  └─ create_revision(doc_id, trigger='auto', created_by=self.user)
       │
       ├─ state = Y.Doc.encode_state()
       ├─ html = Y.Doc.to_html()          [human-readable preview]
       └─ DocumentRevision.objects.create(
              document_id=doc_id,
              revision_number=next_revision_number(),
              yjs_state=state,
              content_html=html,
              trigger='auto',
              created_by=self.user
          )
```

### 6.2 Manual Snapshot (user request)

```
POST /documents/{uuid}/revisions/
  │
documents/views.py → services.create_revision(doc_id, trigger='manual', created_by=request.user)
  │
├─ Load current Yjs state from Redis (ydoc:{doc_id}) or PostgreSQL
└─ DocumentRevision.objects.create(...)
```
