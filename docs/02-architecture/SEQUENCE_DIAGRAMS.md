# Sequence Diagrams
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## 1. User Registration

```
Browser          Django (accounts/views.py)      PostgreSQL
   |                       |                         |
   |-- GET /accounts/register/ -->|                  |
   |<-- 200 Registration form ----|                  |
   |                       |                         |
   |-- POST /accounts/register/ -->|                 |
   |     {username, email, password}|                |
   |                       |-- validate form ------->|
   |                       |-- INSERT auth_user ----->|
   |                       |<-- user created ---------|
   |                       |-- login(request, user)  |
   |                       |-- INSERT django_session ->|
   |<-- 302 /documents/ ---|                         |
```

---

## 2. WebSocket Authentication and Document Load

```
Browser         Uvicorn     AuthMiddleware    DocumentConsumer    Redis       PostgreSQL
   |                |             |                  |               |              |
   |-- WSS connect ->|            |                  |               |              |
   |                 |-- scope -> |                  |               |              |
   |                 |   (session cookie)             |               |              |
   |                 |            |-- resolve user -->|               |              |
   |                 |            |   (session DB lookup)             |              |
   |                 |            |<-- scope["user"] --|              |              |
   |                 |-- route ----------------------------------->   |              |
   |                 |                                | connect()     |              |
   |                 |                                |-- auth check: is_authenticated? 
   |                 |                                |-- permission check (DB) ------>|
   |                 |                                |<-- role: "editor" -------------|
   |                 |                                |-- accept() --|               |
   |                 |                                |-- GET ydoc:{doc_id} ->|      |
   |                 |                                |<-- HIT: Yjs state ----|      |
   |                 |                                |   OR                  |      |
   |                 |                                |<-- MISS --------------|      |
   |                 |                                |-- SELECT yjs_state ----------->|
   |                 |                                |<-- yjs_state bytes ------------|
   |                 |                                |-- SET ydoc:{doc_id} ->|      |
   |<-- sync message (Yjs state) -------------------|                  |              |
```

---

## 3. Concurrent Edit — Two Users (Yjs CRDT)

```
User A (Browser)      DocumentConsumer A      channels_redis      DocumentConsumer B      User B (Browser)
       |                      |                      |                      |                     |
       |-- WS: Yjs update A -->|                     |                      |                     |
       |                      |-- apply update to Y.Doc                     |                     |
       |                      |-- SET ydoc:{doc_id} (Redis) -->|            |                     |
       |                      |-- group_send(update_A) -------->|           |                     |
       |                      |                      |-- broadcast -------->|                     |
       |                      |                      |          |-- apply update_A to Y.Doc       |
       |                      |                      |          |-- WS: send update_A ----------->|
       |                      |                      |          |                     |-- apply to Quill
       |                      |                      |          |                     |
       |                      |                      |          |<-- WS: update_B ----|
       |                      |                      |<-- group_send(update_B) -------|
       |<-- broadcast update_B |<-- broadcast update_B          |                     |
       |-- apply to Quill     |-- apply update_B to Y.Doc       |                     |
       |                      |                                 |                     |
       |   [Both Y.Docs now converge to identical state via CRDT merge]               |
```

---

## 4. Persistence Flush Flow

```
DocumentConsumer                 asyncio event loop        PostgreSQL          Redis
       |                               |                        |                 |
       |-- receive update ------------>|                        |                 |
       |-- apply to Y.Doc             |                        |                 |
       |-- SET ydoc:{doc_id} (TTL 24h) ---------------------------------->|      |
       |-- _schedule_flush() -------->|                        |                 |
       |                              |-- cancel old timer    |                  |
       |                              |-- create_task(flush, delay=30s)          |
       |                              |                        |                 |
       |   ... (more edits, timer keeps resetting) ...         |                 |
       |                              |                        |                 |
       |                              |-- 30s elapsed          |                 |
       |                              |-- flush_to_db() ------>|                 |
       |                              |   SELECT ... FOR UPDATE|                 |
       |                              |   UPDATE yjs_state=... |                 |
       |                              |<-- OK -----------------|                 |
       |                              |-- SET ydoc TTL refresh ---------->|      |
```

---

## 5. User Disconnection and Presence Cleanup

```
Browser         DocumentConsumer        Redis (presence)      Other Consumers      Other Browsers
   |                   |                       |                     |                    |
   |-- close tab ------>|                      |                     |                    |
   |                   |-- disconnect()        |                     |                    |
   |                   |-- ZREM presence ----->|                     |                    |
   |                   |-- DEL presence_data ->|                     |                    |
   |                   |-- HDEL awareness ----->|                    |                    |
   |                   |-- group_send(presence_update) ------------->|                    |
   |                   |-- remaining = ZCARD presence               |                    |
   |                   |   if remaining == 0:  |                    |                    |
   |                   |     flush_to_db() (immediate)              |                    |
   |                   |     group_discard()   |                    |                    |
   |                   |-- group_discard()     |                    |                    |
   |                   |                       |                    |-- WS: awareness update ->|
   |                   |                       |                    |   (without disconnected user)
```

---

## 6. Rate Limit Exceeded (HTTP)

```
Browser        RateLimitMiddleware        Redis              View
   |                   |                    |                  |
   |-- POST /accounts/login/ -->|           |                  |
   |                   |-- GET rl:http:{ip} ->|               |
   |                   |<-- bucket state ----|               |
   |                   |-- tokens < cost?    |               |
   |                   |   YES (10th+ request)               |
   |<-- HTTP 429 ------|   {error: rate_limit_exceeded,       |
   |   Retry-After: 6  |    retry_after: 6}                  |
   |                   |                    |                  |
   |   ... 6 seconds later ...              |                  |
   |-- POST /accounts/login/ -->|           |                  |
   |                   |-- GET rl:http:{ip} ->|               |
   |                   |<-- bucket refilled  |               |
   |                   |-- tokens >= cost    |               |
   |                   |-- forward request ----------------------->|
   |<-- 200 or 400 ----|                    |                  |
```

---

## 7. Version Restore Flow

```
Owner (Browser)     documents/views.py    documents/services.py    PostgreSQL    DocumentConsumer (all)
       |                   |                      |                     |                |
       |-- POST /revisions/{id}/restore/ -->|     |                    |                |
       |                   |-- has_edit_permission? ->                  |                |
       |                   |<-- role: owner ------                      |                |
       |                   |-- restore_revision(doc, rev) ------------->|                |
       |                   |                      |-- SELECT rev.yjs_state              |
       |                   |                      |<-- yjs_state bytes                  |
       |                   |                      |-- BEGIN TRANSACTION                 |
       |                   |                      |-- INSERT DocumentRevision (pre-restore snapshot)
       |                   |                      |-- UPDATE Document SET yjs_state=rev.yjs_state
       |                   |                      |-- COMMIT                            |
       |                   |                      |-- SET ydoc:{doc_id} = rev.yjs_state (Redis)
       |                   |                      |-- channel_layer.group_send(restore_broadcast)
       |                   |                      |                                     |-- apply full state update
       |                   |                      |                                     |-- send to browsers
       |<-- 200 OK --------|                      |                     |                |
```
