# ADR-001 — Collaboration Engine
**Date:** 2026-11-22  
**Status:** ACCEPTED  
**Deciders:** Engineering Team

---

## Context

The existing implementation broadcasts the entire Quill.js HTML string on every keystroke. When two users type simultaneously, the server receives two full HTML snapshots and broadcasts both. Each client's editor applies the most recently received snapshot with `dangerouslyPasteHTML`, overwriting its local state. The result is **last-write-wins**: one user's concurrent edit is silently discarded.

This is not an edge case — it is guaranteed to happen on every keystroke from two or more simultaneous users.

A production collaborative editor requires a synchronisation mechanism that:

1. Merges concurrent edits from multiple users without loss.
2. Guarantees eventual consistency — all clients converge to the same document state.
3. Handles network interruption and reconnection.
4. Synchronises cursor and selection positions (awareness).
5. Does not require a custom distributed systems algorithm.

---

## Problem

What synchronisation approach should be used to replace full-HTML broadcast with conflict-free concurrent editing?

---

## Options Considered

### Option A — Operational Transformation (OT)

OT defines edit operations (insert, delete, retain) and a transformation function that adjusts an operation's position when it conflicts with a concurrent operation.

**Pros:**
- Well-understood theory; used by Google Docs.
- ShareDB provides a mature OT library for JavaScript.

**Cons:**
- Correct OT implementation for rich text (not just plain text) is notoriously difficult. The transformation function must handle all combinations of overlapping operations on formatted text.
- ShareDB requires a persistent server-side operational history and a JSON OT type (`rich-text`).
- No maintained Python server-side OT library with Quill.js support exists; would require implementing the OT server in Node.js or porting the logic to Python.
- Requires total ordering of operations — adds coordination complexity on the server.

### Option B — Custom CRDT

Implement a bespoke CRDT (e.g., LSEQ or RGA for sequences) tailored to the application.

**Pros:**
- Full control.

**Cons:**
- CRDTs for rich formatted text are research-level problems. Even well-funded teams take years to get this right.
- Zero test coverage for edge cases in concurrent operations until real users find bugs.
- Maintenance burden falls entirely on this team.

### Option C — Yjs CRDT (Selected)

Yjs is a production-grade CRDT framework. It provides:
- `Y.Text` — a CRDT-based rich text type compatible with Quill.js via the `y-quill` binding.
- Binary update messages — not full-document snapshots; only deltas are transmitted.
- Awareness protocol — cursor and selection positions synced without touching document state.
- `y-py` — a Python binding to the Yjs CRDT engine (compiled from Rust via PyO3), usable server-side in Django Channels consumers.
- Offline-first design — edits made while disconnected are merged on reconnect.
- Large production user base: Hocuspocus, Liveblocks, Tiptap Cloud all use Yjs.

**Pros:**
- No custom algorithm required.
- Quill.js binding (`y-quill`) is maintained by the Yjs project.
- Server-side library (`y-py`) runs in Python — no Node.js process needed.
- Binary encoding is far more efficient than full HTML strings.
- Awareness protocol handles cursor sync without application code.

**Cons:**
- `y-py` is a newer library; must pin to a known-good version and monitor for updates.
- The Yjs encoding format is binary — raw bytes over WebSocket (not JSON text frames).
- The `y-quill` binding requires Quill 1.x (not Quill 2.x). **This requires a Quill version change** from the current 2.0.2 CDN import to 1.3.7.
- Learning curve for Yjs message types (`sync`, `awareness`, `update`).

---

## Decision

**Use Yjs (Option C).**

Specifically:
- **Server-side:** `y-py` for Python CRDT operations in `DocumentConsumer`.
- **Client-side:** `yjs` + `y-quill` (Quill 1.x binding) + `y-websocket` provider protocol.
- **Transport:** Binary WebSocket frames (not text frames with JSON).
- **Quill version:** Downgrade from 2.0.2 to 1.3.7 to satisfy `y-quill` compatibility.

The WebSocket message protocol follows the y-websocket protocol:
- Message type `0` (`Sync Step 1`) — client sends its state vector; server responds with missing updates.
- Message type `1` (`Sync Step 2`) — server sends updates client is missing.
- Message type `2` (`Update`) — client sends a Yjs update (a mutation).
- Message type `3` (`Awareness`) — cursor, selection, user metadata.

---

## Consequences

**Positive:**
- Concurrent edits from any number of users are merged correctly without data loss.
- The server never discards an edit.
- Reconnecting clients receive exactly the updates they missed, not the full document.
- Cursor positions are synchronized via awareness without additional code.
- Message size is proportional to the edit delta, not the document size — large documents are handled efficiently.

**Negative:**
- Quill must be downgraded from 2.0.2 to 1.3.7. The existing CSS customisation in `index.html` must be audited against Quill 1.x.
- The `dangerouslyPasteHTML` approach in the frontend is replaced entirely; this is a full rewrite of the editor JavaScript.
- `y-py` must be monitored for security updates and API stability.

**Trade-offs:**
- We accept the Quill version downgrade because the alternative (OT) requires a custom server-side implementation that would take significantly longer to build and test correctly.
- We accept the `y-py` dependency because it is compiled from the same Yjs Rust core used in production by other Yjs server implementations, reducing the risk of CRDT correctness bugs.
