# Component Diagrams

## CollabEdit — Component Interaction Diagrams

**Version:** 2.0  
**Last updated:** 2026-11-22

---

## 1. Top-level component diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              CollabEdit System                             │
│                                                                            │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                           Browser Client                           │   │
│  │                                                                    │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │   │
│  │  │  Quill.js    │◄─┤  y-quill     │◄─┤        Y.Doc             │ │   │
│  │  │  (editor UI) │  │  (binding)   │  │ (CRDT document state)    │ │   │
│  │  └──────────────┘  └──────────────┘  └────────────┬─────────────┘ │   │
│  │                                                    │               │   │
│  │                                              ┌─────▼──────────┐   │   │
│  │                                              │ WebSocket       │   │   │
│  │                                              │ (binary proto)  │   │   │
│  │                                              └─────┬──────────┘   │   │
│  └────────────────────────────────────────────────────│──────────────┘   │
│                                                        │ WSS / HTTPS      │
│  ┌─────────────────────────────────────────────────────▼────────────────┐ │
│  │                      Django / Channels (ASGI)                        │ │
│  │                                                                      │ │
│  │  ┌─────────────────────┐    ┌─────────────────────────────────────┐ │ │
│  │  │   apps/accounts     │    │        apps/collaboration            │ │ │
│  │  │                     │    │                                     │ │ │
│  │  │  User model         │    │  DocumentConsumer                   │ │ │
│  │  │  Registration view  │    │  ├── auth check                     │ │ │
│  │  │  Login view         │    │  ├── permission check               │ │ │
│  │  │  Logout view        │    │  ├── Yjs protocol handling          │ │ │
│  │  └─────────────────────┘    │  ├── Token Bucket (WS)             │ │ │
│  │                             │  ├── PresenceManager               │ │ │
│  │  ┌─────────────────────┐    │  └── persistence (flush)           │ │ │
│  │  │   apps/documents    │    └─────────────────────────────────────┘ │ │
│  │  │                     │                                             │ │
│  │  │  Document model     │    ┌─────────────────────────────────────┐ │ │
│  │  │  Permission model   │    │              core/                  │ │ │
│  │  │  Revision model     │    │                                     │ │ │
│  │  │  Views (CRUD)       │    │  RequestIdMiddleware                │ │ │
│  │  │  Services           │    │  TokenBucketRateLimitMiddleware      │ │ │
│  │  │  Selectors          │    │  TokenBucket (Lua + Redis)          │ │ │
│  │  │  Permissions        │    │  health_check view                  │ │ │
│  │  └─────────────────────┘    │  JsonFormatter (logging)            │ │ │
│  │                             └─────────────────────────────────────┘ │ │
│  │  ┌─────────────────────┐                                             │ │
│  │  │    apps/audit       │                                             │ │
│  │  │  AuditEvent model   │                                             │ │
│  │  │  log_event service  │                                             │ │
│  │  └─────────────────────┘                                             │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                │                    │                     │
│         ┌──────────────────────▼──────┐  ┌──────────▼─────────────────┐  │
│         │       Neon PostgreSQL       │  │      Render Redis          │  │
│         │                            │  │                            │  │
│         │  accounts_user             │  │  Channel layer pub/sub     │  │
│         │  documents_group           │  │  Token Bucket state        │  │
│         │  documents_document        │  │  Yjs state cache (24 h)    │  │
│         │  documents_permission      │  │  Presence sorted set       │  │
│         │  documents_revision        │  │                            │  │
│         │  audit_auditevent          │  │                            │  │
│         └────────────────────────────┘  └────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. `apps/documents` internal structure

```
apps/documents/
│
├── models.py
│   ├── Group              ← Legacy room-identifier (name == UUID)
│   ├── Document           ← Authoritative document record + yjs_state
│   ├── DocumentPermission ← Per-user role grant (editor | viewer)
│   └── DocumentRevision   ← Immutable point-in-time Yjs state snapshot
│
├── permissions.py         ← get_user_role() / has_*_permission()
│                             Single source of truth for access control
│
├── selectors.py           ← Pure read-only DB queries (no business logic)
│   ├── get_document_by_uuid()
│   ├── get_document_for_user()
│   ├── list_user_documents()
│   └── get_revisions_for_document()
│
├── services.py            ← Business logic + audit log
│   ├── create_document()
│   ├── share_document()
│   ├── revoke_permission()
│   ├── soft_delete_document()
│   ├── create_revision()
│   └── restore_revision()
│
├── views.py               ← HTTP request handlers (thin; delegates to services)
│   ├── document_list()
│   ├── document_create()
│   ├── document_detail()
│   ├── title_update()
│   ├── permission_create() / permission_delete()
│   ├── revision_list() / revision_create() / revision_restore()
│   └── document_delete()
│
└── urls.py                ← URL routing (app_name="documents")
```

---

## 3. `apps/collaboration` internal structure

```
apps/collaboration/
│
├── routing.py        ← ws/documents/<uuid>/ → DocumentConsumer
│
├── consumers.py      ← DocumentConsumer (AsyncWebsocketConsumer)
│   │
│   ├── connect()
│   │   ├── [AUTH]  reject anon → 4001
│   │   ├── [DB]    load Document
│   │   ├── [PERM]  check role  → 4003 if none
│   │   ├── accept()
│   │   ├── channel_layer.group_add()
│   │   ├── PresenceManager.add_connection()
│   │   ├── load Yjs state (Redis → PG fallback)
│   │   ├── send Sync Step 2
│   │   └── init WebSocket Token Bucket
│   │
│   ├── receive_bytes()
│   │   ├── size guard (1 MB)
│   │   ├── Token Bucket check
│   │   ├── MSG_SYNC1   → _handle_sync_step1()
│   │   ├── MSG_UPDATE  → _handle_update()
│   │   └── MSG_AWARENESS → _handle_awareness()
│   │
│   ├── disconnect()
│   │   ├── cancel debounced flush task
│   │   ├── PresenceManager.remove_connection()
│   │   ├── if last conn → immediate flush to PG
│   │   └── channel_layer.group_discard()
│   │
│   └── channel layer handlers
│       ├── yjs_update()     ← forward binary update to this WS
│       ├── yjs_awareness()  ← forward awareness to this WS
│       └── presence_update() ← forward presence JSON to this WS
│
├── presence.py       ← PresenceManager
│   ├── Redis sorted set: collabedit:presence:{doc_id}
│   │   score = expiry timestamp; member = conn_id
│   ├── Redis hash: collabedit:presence:meta:{doc_id}:{conn_id}
│   │   fields: user_id, username, connected_at
│   ├── add_connection(doc_id, conn_id, user) → None
│   ├── remove_connection(doc_id, conn_id) → remaining_count
│   └── get_active_users(doc_id) → list[dict]
│
└── persistence.py    ← Async flush helpers
    ├── flush_to_db(doc_id, yjs_state, redis_client)
    │   ├── 3 retry attempts with exponential backoff
    │   ├── UPDATE documents_document SET yjs_state=... WHERE id=...
    │   └── Invalidate Redis cache on success
    └── load_from_db(doc_id) → bytes | None
        └── SELECT yjs_state FROM documents_document WHERE id=...
```

---

## 4. Redis key space

| Key pattern | Type | TTL | Purpose |
|---|---|---|---|
| `collabedit:rl:http:*:{identifier}` | Hash | 60 s | HTTP Token Bucket state |
| `collabedit:rl:ws:{conn_id}` | Hash | 60 s | WebSocket Token Bucket state |
| `collabedit:ydoc:{doc_id}` | String (bytes) | 24 h | Yjs encoded state cache |
| `collabedit:presence:{doc_id}` | Sorted set | TTL via member scores | Active connection registry |
| `collabedit:presence:meta:{doc_id}:{conn_id}` | Hash | 10 min | Per-connection user metadata |
| `asgi:*` | Various | Per channels_redis | Django Channels pub/sub |

---

## 5. Database entity-relationship

```
accounts_user
  id PK
  username UNIQUE
  email
  password
  is_active, is_staff, ...

documents_group
  id PK
  name VARCHAR(255) UNIQUE   ← UUID string

documents_document
  id PK
  group_id FK → documents_group
  title VARCHAR(255)
  owner_id FK → accounts_user (PROTECT, nullable)
  content TEXT               ← legacy; not written by new code
  yjs_state BYTEA            ← authoritative CRDT state
  is_deleted BOOL
  deleted_at TIMESTAMP
  created_at TIMESTAMP
  updated_at TIMESTAMP

documents_documentpermission
  id PK
  document_id FK → documents_document (CASCADE)
  user_id FK → accounts_user (CASCADE)
  role VARCHAR(10)           ← 'editor' | 'viewer'
  granted_at TIMESTAMP
  granted_by_id FK → accounts_user (SET NULL)
  UNIQUE(document_id, user_id)

documents_documentrevision
  id PK
  document_id FK → documents_document (CASCADE)
  revision_number INT
  yjs_state BYTEA
  content_html TEXT
  trigger VARCHAR(20)        ← 'manual' | 'auto' | 'restore'
  created_at TIMESTAMP
  created_by_id FK → accounts_user (SET NULL)
  UNIQUE(document_id, revision_number)

audit_auditevent
  id PK
  event_type VARCHAR(64)
  actor_id FK → accounts_user (SET NULL)
  document_id FK → documents_document (SET NULL)
  target_user_id FK → accounts_user (SET NULL)
  metadata JSONB
  ip_address VARCHAR(45)
  created_at TIMESTAMP
```
