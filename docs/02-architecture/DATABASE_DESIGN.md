# Database Design
**Project:** CollabEdit  
**Version:** 1.0  
**Date:** 2026-11-22

---

## 1. Design Principles

1. PostgreSQL is the **only authoritative** store for document content.
2. Redis holds ephemeral data only (Yjs cache, presence, rate-limit state).
3. Existing migrations (0001, 0002) are preserved; new tables are added in new migrations.
4. All tables use `BigAutoField` PKs (consistent with `DEFAULT_AUTO_FIELD`).
5. Soft delete is used for documents to allow recovery.
6. All foreign keys have explicit `on_delete` behaviour.
7. Timestamps use `DateTimeField(auto_now_add=True)` or `auto_now=True`.

---

## 2. Schema Overview

```
auth_user (Django built-in)
    │
    ├─── documents_document (owner FK)
    │        │
    │        ├─── documents_documentpermission
    │        ├─── documents_documentrevision
    │        └─── audit_auditevent
    │
    └─── documents_documentpermission (user FK)
```

---

## 3. Table Definitions

### 3.1 `auth_user` (Django built-in — not modified)

| Column | Type | Notes |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `username` | `varchar(150)` | Unique |
| `email` | `varchar(254)` | |
| `password` | `varchar(128)` | Hashed |
| `is_active` | `boolean` | |
| `date_joined` | `timestamptz` | |

No changes to this table. No custom `AbstractUser` model is needed for V1 (we inherit `AbstractUser` for forward compatibility but add no new fields initially).

---

### 3.2 `documents_document` (extended from migration 0002)

> Migration 0003 adds the new columns. The existing `group`, `content`, and `updated_at` columns are **preserved** to avoid breaking existing data.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | |
| `group_id` | `BigInteger` | FK → `documents_group.id`, `CASCADE` | Existing — preserved |
| `content` | `TextField` | blank=True | Existing — preserved for migration compatibility |
| `updated_at` | `DateTimeField` | `auto_now=True` | Existing — preserved |
| `title` | `varchar(255)` | default="Untitled document" | **NEW** |
| `owner_id` | `BigInteger` | FK → `auth_user.id`, `PROTECT` | **NEW** — PROTECT prevents accidental user deletion losing docs |
| `yjs_state` | `BinaryField` | null=True, blank=True | **NEW** — Yjs encoded document state (replaces HTML `content`) |
| `is_deleted` | `boolean` | default=False | **NEW** |
| `deleted_at` | `DateTimeField` | null=True | **NEW** |
| `created_at` | `DateTimeField` | `auto_now_add=True` | **NEW** |

**Indexes:**
- `(owner_id)` — B-tree index for owner's document list query
- `(is_deleted, updated_at DESC)` — partial index for document list with soft-delete filter
- `(group_id)` — already implicit from FK

---

### 3.3 `documents_group` (existing — preserved)

| Column | Type | Constraints |
|---|---|---|
| `id` | `BigAutoField` | PK |
| `name` | `varchar(255)` | Unique |

> This table stores the UUID room identifier. It is preserved as-is for migration continuity. In the new design, `Document.group.name` = document UUID.

---

### 3.4 `documents_documentpermission` (NEW — migration 0004)

Stores per-user, per-document permission grants. The document owner does **not** have an entry here (ownership is on `Document.owner`).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | |
| `document_id` | `BigInteger` | FK → `documents_document.id`, `CASCADE` | |
| `user_id` | `BigInteger` | FK → `auth_user.id`, `CASCADE` | |
| `role` | `varchar(10)` | `choices=['editor','viewer']` | |
| `granted_at` | `DateTimeField` | `auto_now_add=True` | |
| `granted_by_id` | `BigInteger` | FK → `auth_user.id`, `SET_NULL`, null=True | Audit: who shared it |

**Constraints:**
- `UNIQUE (document_id, user_id)` — a user has at most one role per document

**Indexes:**
- `(user_id, document_id)` — for `GET /documents/` list of documents I can access

---

### 3.5 `documents_documentrevision` (NEW — migration 0004)

Immutable snapshots of document state at a point in time.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | |
| `document_id` | `BigInteger` | FK → `documents_document.id`, `CASCADE` | |
| `revision_number` | `PositiveIntegerField` | | Auto-incremented per document |
| `yjs_state` | `BinaryField` | | Full Yjs encoded state at this point |
| `content_html` | `TextField` | blank=True | HTML snapshot for human-readable preview |
| `created_at` | `DateTimeField` | `auto_now_add=True` | |
| `created_by_id` | `BigInteger` | FK → `auth_user.id`, `SET_NULL`, null=True | Who triggered the snapshot |
| `trigger` | `varchar(20)` | `choices=['manual','auto','restore']` | |

**Indexes:**
- `(document_id, revision_number DESC)` — for revision list query
- `(document_id, created_at DESC)` — for time-based queries

---

### 3.6 `audit_auditevent` (NEW — migration 0005)

Append-only audit log for security-relevant actions.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | |
| `event_type` | `varchar(50)` | | e.g., `document.created`, `permission.granted`, `document.deleted` |
| `actor_id` | `BigInteger` | FK → `auth_user.id`, `SET_NULL`, null=True | The user who performed the action |
| `document_id` | `BigInteger` | FK → `documents_document.id`, `SET_NULL`, null=True | Related document if applicable |
| `target_user_id` | `BigInteger` | FK → `auth_user.id`, `SET_NULL`, null=True | The user affected (e.g., in permission grant) |
| `metadata` | `JSONField` | default=dict | Additional structured data |
| `ip_address` | `GenericIPAddressField` | null=True | |
| `created_at` | `DateTimeField` | `auto_now_add=True` | |

**Indexes:**
- `(actor_id, created_at DESC)`
- `(document_id, created_at DESC)`
- `(event_type, created_at DESC)`

**Retention:** 90 days. A management command `python manage.py purge_audit_events --older-than-days=90` runs in a scheduled job.

---

## 4. Entity-Relationship Diagram

```
┌──────────────┐       ┌──────────────────────────┐
│  auth_user   │       │   documents_document      │
│──────────────│       │──────────────────────────│
│ id (PK)      │◄──────│ owner_id (FK)             │
│ username     │       │ id (PK)                   │
│ email        │       │ group_id (FK)             │
│ password     │       │ title                     │
└──────────────┘       │ yjs_state                 │
        │              │ content (legacy)           │
        │              │ is_deleted                 │
        │              │ created_at                 │
        │              │ updated_at                 │
        │              └──────────┬────────────────┘
        │                         │
        │              ┌──────────▼──────────────────┐
        │              │ documents_documentpermission  │
        │              │─────────────────────────────│
        │◄─────────────│ user_id (FK)                 │
        │◄─────────────│ granted_by_id (FK)           │
        │              │ document_id (FK)             │
        │              │ role                         │
        │              │ granted_at                   │
        │              └─────────────────────────────┘
        │
        │              ┌──────────────────────────────┐
        │              │ documents_documentrevision    │
        │              │──────────────────────────────│
        │◄─────────────│ created_by_id (FK)           │
        │              │ document_id (FK)             │
        │              │ revision_number              │
        │              │ yjs_state                    │
        │              │ content_html                 │
        │              │ trigger                      │
        │              │ created_at                   │
        │              └──────────────────────────────┘
        │
        │              ┌──────────────────────────────┐
        │              │ audit_auditevent              │
        │              │──────────────────────────────│
        │◄─────────────│ actor_id (FK)                │
        │◄─────────────│ target_user_id (FK)          │
        │              │ document_id (FK)             │
        │              │ event_type                   │
        │              │ metadata (JSON)              │
        │              │ ip_address                   │
        │              │ created_at                   │
        │              └──────────────────────────────┘
```

---

## 5. Key Queries and Index Justification

| Query | Columns used | Index |
|---|---|---|
| Documents owned by user | `owner_id`, `is_deleted`, `updated_at` | `(owner_id)`, `(is_deleted, updated_at DESC)` |
| Documents accessible by user | `user_id` on `documentpermission`, JOIN `document` | `(user_id, document_id)` |
| Revisions for a document | `document_id`, `revision_number` | `(document_id, revision_number DESC)` |
| Audit events by actor | `actor_id`, `created_at` | `(actor_id, created_at DESC)` |

---

## 6. Data Migration Strategy

| Migration | Action |
|---|---|
| `0001_initial` | Existing — creates `Group` table |
| `0002_document` | Existing — creates `Document` table |
| `0003_document_v2` | **New** — adds `title`, `owner_id`, `yjs_state`, `is_deleted`, `deleted_at`, `created_at` to `Document` |
| `0004_permissions_revisions` | **New** — creates `DocumentPermission`, `DocumentRevision` |
| `0005_audit` | **New** — creates `AuditEvent` |
| `0006_accounts_user` | **New** — creates custom `User` model (if `AbstractUser` subclass is used) |

> Migration 0003 backfills `owner_id` as nullable initially, then a data migration assigns ownership of existing documents, then `owner_id` is made non-nullable.

---

## 7. Deletion Behaviour Summary

| Table | on_delete | Reason |
|---|---|---|
| `Document.owner` → `auth_user` | `PROTECT` | Prevent accidental user deletion that would orphan documents |
| `Document.group` → `Group` | `CASCADE` (existing) | Room deletion cascades to document |
| `DocumentPermission.document` → `Document` | `CASCADE` | Permission entries removed when document deleted |
| `DocumentPermission.user` → `auth_user` | `CASCADE` | Revoke access when user account deleted |
| `DocumentRevision.document` → `Document` | `CASCADE` | Revisions deleted with document |
| `AuditEvent.actor` → `auth_user` | `SET_NULL` | Preserve audit trail even if user deleted |
| `AuditEvent.document` → `Document` | `SET_NULL` | Preserve audit trail even if document deleted |
