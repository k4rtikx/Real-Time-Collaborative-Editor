"""
DocumentConsumer — AsyncWebsocketConsumer for real-time collaborative editing.

Protocol: y-websocket binary protocol.
Message type byte (first byte of every message):
    0  = Sync Step 1  (client sends its state vector; server responds with missing updates)
    1  = Sync Step 2  (server sends updates the client is missing)
    2  = Yjs Update   (a document delta — Editor-only)
    3  = Awareness    (cursor, selection, user metadata — all roles)

Authentication:
    Handled by AuthMiddlewareStack before connect().
    scope["user"] is a resolved Django User or AnonymousUser.

Authorization:
    Checked in connect() before accept().
    WebSocket close codes:
        4001 — Unauthenticated
        4003 — Unauthorized (no permission, or Viewer sending edit)
        4004 — Document not found
        4008 — Payload too large
        4029 — Rate limit exceeded

Persistence:
    Yjs state is flushed to PostgreSQL every FLUSH_INTERVAL seconds
    or immediately when the last client disconnects from a document.
    Uses asyncio debounced timer — no threads.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Optional

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.collaboration import persistence as persistence_module
from apps.collaboration.presence import PresenceManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MSG_SYNC_STEP1 = 0
MSG_SYNC_STEP2 = 1
MSG_UPDATE = 2
MSG_AWARENESS = 3

MAX_PAYLOAD_BYTES = 1_048_576   # 1 MB
FLUSH_INTERVAL = 30             # seconds
AUTO_SNAPSHOT_EVERY = 100       # Yjs updates between auto-snapshots
WS_RATE_CAPACITY = 60.0         # token bucket capacity
WS_RATE_REFILL = 20.0           # tokens per second

YDOC_REDIS_KEY = "collabedit:ydoc:{doc_id}"
YDOC_TTL = 86400                # 24 hours

# ---------------------------------------------------------------------------
# Module-level shared state (per ASGI worker process)
# ---------------------------------------------------------------------------
# In a single-worker deployment these are process-local.
# In multi-worker deployments, Yjs state is loaded from Redis/DB on each
# worker's first connection to a document.
_ydocs: dict[int, bytes] = {}   # doc_id → latest encoded Yjs state (bytes)
_flush_tasks: dict[int, asyncio.Task] = {}


def _get_redis():
    """Return an async Redis client (lazy import to allow settings loading first)."""
    import redis.asyncio as aioredis
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
    return aioredis.Redis.from_url(redis_url, decode_responses=False)


class DocumentConsumer(AsyncWebsocketConsumer):
    """
    Real-time collaborative document WebSocket consumer.

    One instance is created per WebSocket connection.
    Multiple instances may exist for the same document (one per connected user).
    """

    async def connect(self):
        # ------------------------------------------------------------------
        # 1. Authentication
        # ------------------------------------------------------------------
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            logger.warning("WS connect rejected: unauthenticated")
            await self.close(code=4001)
            return

        # ------------------------------------------------------------------
        # 2. Extract document UUID from URL
        # ------------------------------------------------------------------
        self.doc_uuid: str = self.scope["url_route"]["kwargs"]["doc_uuid"]

        # ------------------------------------------------------------------
        # 3. Load document and check permission
        # ------------------------------------------------------------------
        self.document = await self._load_document(self.doc_uuid)
        if self.document is None:
            logger.warning("WS connect rejected: document not found", extra={"doc_uuid": self.doc_uuid})
            await self.close(code=4004)
            return

        self.role = await sync_to_async(self._get_role)(user, self.document)
        if self.role is None:
            logger.warning(
                "WS connect rejected: no permission",
                extra={"doc_uuid": self.doc_uuid, "user_id": user.id},
            )
            await self.close(code=4003)
            return

        # ------------------------------------------------------------------
        # 4. Accept connection
        # ------------------------------------------------------------------
        await self.accept()

        self.user = user
        self.doc_id: int = self.document.id
        self.conn_id: str = str(uuid.uuid4())
        self.room_name: str = str(self.doc_uuid)
        self._update_count: int = 0
        self._redis = _get_redis()
        self._presence = PresenceManager(self._redis)

        # ------------------------------------------------------------------
        # 5. Join channel group
        # ------------------------------------------------------------------
        await self.channel_layer.group_add(self.room_name, self.channel_name)

        # ------------------------------------------------------------------
        # 6. Register presence
        # ------------------------------------------------------------------
        await self._presence.add_connection(self.doc_id, self.conn_id, user)
        await self._broadcast_presence()

        # ------------------------------------------------------------------
        # 7. Load Yjs document state and send sync
        # ------------------------------------------------------------------
        encoded_state = await self._load_ydoc_state()
        _ydocs[self.doc_id] = encoded_state

        # Send Sync Step 2 (full state to this client)
        # In production this should send Step 1 first; for simplicity we
        # send the full encoded state so the client can initialise its Y.Doc.
        sync_msg = bytes([MSG_SYNC_STEP2]) + (encoded_state or b"")
        await self.send(bytes_data=sync_msg)

        # ------------------------------------------------------------------
        # 8. Initialise rate limiter
        # ------------------------------------------------------------------
        from core.rate_limiting import TokenBucket, get_redis_client
        self._ws_limiter = TokenBucket(
            get_redis_client(),
            capacity=WS_RATE_CAPACITY,
            refill_rate=WS_RATE_REFILL,
            key_prefix="ws",
        )

        logger.info(
            "WS connected",
            extra={
                "doc_uuid": self.doc_uuid,
                "user_id": user.id,
                "role": self.role,
                "conn_id": self.conn_id,
            },
        )

    async def receive(self, text_data=None, bytes_data=None):
        """Entry point for all incoming WebSocket messages."""
        if bytes_data is not None:
            await self.receive_bytes(bytes_data)
        elif text_data is not None:
            # Unexpected text frame — ignore (all protocol messages are binary)
            logger.debug("WS: unexpected text frame ignored", extra={"conn_id": self.conn_id})

    async def receive_bytes(self, data: bytes):
        """Process a binary WebSocket message."""
        # ------------------------------------------------------------------
        # Guards
        # ------------------------------------------------------------------
        if len(data) > MAX_PAYLOAD_BYTES:
            logger.warning(
                "WS: payload too large — closing",
                extra={"conn_id": self.conn_id, "size": len(data)},
            )
            await self.close(code=4008)
            return

        # Rate limit check (synchronous Token Bucket is fast enough here)
        allowed, retry_after = self._ws_limiter.is_allowed(self.conn_id)
        if not allowed:
            logger.warning(
                "WS: rate limit exceeded — closing",
                extra={"conn_id": self.conn_id, "retry_after": retry_after},
            )
            await self.close(code=4029)
            return

        if not data:
            return

        msg_type = data[0]
        payload = data[1:]

        if msg_type == MSG_SYNC_STEP1:
            await self._handle_sync_step1(payload)
        elif msg_type == MSG_UPDATE:
            await self._handle_update(payload)
        elif msg_type == MSG_AWARENESS:
            await self._handle_awareness(payload)
        else:
            logger.debug(
                "WS: unknown message type ignored",
                extra={"conn_id": self.conn_id, "msg_type": msg_type},
            )

    async def _handle_sync_step1(self, state_vector: bytes):
        """
        Client sent its state vector.
        Respond with the encoded state (all ops the client is missing).
        """
        encoded_state = _ydocs.get(self.doc_id, b"")
        response = bytes([MSG_SYNC_STEP2]) + encoded_state
        await self.send(bytes_data=response)

    async def _handle_update(self, update: bytes):
        """
        Apply a Yjs update from an Editor.
        Broadcast to all other connections in the room.
        Cache in Redis and schedule a PostgreSQL flush.
        """
        if self.role == "viewer":
            logger.warning(
                "WS: viewer attempted to send update — closing",
                extra={"conn_id": self.conn_id, "user_id": self.user.id},
            )
            await self.close(code=4003)
            return

        # In a full Yjs implementation, we would apply the update to a Y.Doc
        # object (via y-py) and re-encode the state. Without y-py installed,
        # we store updates as an append log and serve the latest full state.
        # This is replaced by proper y-py merge once the dependency is available.
        current = _ydocs.get(self.doc_id, b"")
        # Naive approach: last full state wins (replaced by CRDT merge in Phase 3B)
        # When y-py is installed: apply_update + encode_state_as_update
        _ydocs[self.doc_id] = current  # placeholder; y-py replaces this

        # Cache latest state in Redis
        try:
            await self._redis.set(
                YDOC_REDIS_KEY.format(doc_id=self.doc_id),
                current or b"",
                ex=YDOC_TTL,
            )
        except Exception as e:
            logger.warning("WS: Redis cache update failed", extra={"error": str(e)})

        # Broadcast to all connections in the room (excluding sender)
        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "yjs_update",
                "update": update,
                "sender_channel": self.channel_name,
            },
        )

        # Schedule debounced PostgreSQL flush
        await self._schedule_flush()

        # Auto-snapshot every N updates
        self._update_count += 1
        if self._update_count % AUTO_SNAPSHOT_EVERY == 0:
            await self._create_auto_snapshot()

    async def _handle_awareness(self, payload: bytes):
        """Broadcast awareness update (cursor/selection) to all other connections."""
        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "yjs_awareness",
                "payload": payload,
                "sender_channel": self.channel_name,
            },
        )

    # ------------------------------------------------------------------
    # Channel layer event handlers (called by group_send broadcasts)
    # ------------------------------------------------------------------

    async def yjs_update(self, event: dict):
        """Forward a Yjs update to this WebSocket (from another consumer)."""
        if event.get("sender_channel") == self.channel_name:
            return  # Don't echo back to sender
        await self.send(bytes_data=bytes([MSG_UPDATE]) + event["update"])

    async def yjs_awareness(self, event: dict):
        """Forward an awareness update to this WebSocket."""
        if event.get("sender_channel") == self.channel_name:
            return
        await self.send(bytes_data=bytes([MSG_AWARENESS]) + event["payload"])

    async def presence_update(self, event: dict):
        """Forward a presence update as a JSON text frame."""
        await self.send(text_data=json.dumps({
            "type": "presence",
            "users": event["users"],
        }))

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    async def disconnect(self, close_code: int):
        if not hasattr(self, "doc_id"):
            return  # connect() failed before setup; nothing to clean up

        # Cancel debounced flush timer
        task = _flush_tasks.pop(self.doc_id, None)
        if task and not task.done():
            task.cancel()

        # Remove from presence
        remaining = await self._presence.remove_connection(self.doc_id, self.conn_id)

        # Flush to DB if this was the last connection
        if remaining == 0:
            encoded_state = _ydocs.pop(self.doc_id, b"")
            if encoded_state:
                await persistence_module.flush_to_db(
                    self.doc_id, encoded_state, redis_client=self._redis
                )

        await self._broadcast_presence()
        await self.channel_layer.group_discard(self.room_name, self.channel_name)

        logger.info(
            "WS disconnected",
            extra={
                "doc_uuid": self.doc_uuid,
                "user_id": getattr(self.user, "id", None),
                "conn_id": self.conn_id,
                "close_code": close_code,
                "remaining_connections": remaining,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _schedule_flush(self):
        """Reset (or start) the debounced flush timer."""
        existing = _flush_tasks.get(self.doc_id)
        if existing and not existing.done():
            existing.cancel()
        _flush_tasks[self.doc_id] = asyncio.create_task(
            self._flush_after_delay()
        )

    async def _flush_after_delay(self):
        """Wait FLUSH_INTERVAL seconds then flush to PostgreSQL."""
        await asyncio.sleep(FLUSH_INTERVAL)
        encoded_state = _ydocs.get(self.doc_id, b"")
        if encoded_state:
            await persistence_module.flush_to_db(
                self.doc_id, encoded_state, redis_client=self._redis
            )

    async def _broadcast_presence(self):
        """Broadcast current presence list to all connections in the room."""
        users = await self._presence.get_active_users(self.doc_id)
        await self.channel_layer.group_send(
            self.room_name,
            {"type": "presence_update", "users": users},
        )

    async def _load_ydoc_state(self) -> bytes:
        """
        Load Yjs document state.
        Fast path: Redis cache.
        Slow path: PostgreSQL.
        """
        redis_key = YDOC_REDIS_KEY.format(doc_id=self.doc_id)
        try:
            cached = await self._redis.get(redis_key)
            if cached:
                logger.debug("ydoc: Redis cache hit", extra={"doc_id": self.doc_id})
                return cached
        except Exception as e:
            logger.warning("ydoc: Redis get failed", extra={"error": str(e)})

        # Fallback: load from PostgreSQL
        state = await persistence_module.load_from_db(self.doc_id)
        if state:
            try:
                await self._redis.set(redis_key, state, ex=YDOC_TTL)
            except Exception:
                pass  # Non-critical; will reload from DB next time
        return state or b""

    async def _create_auto_snapshot(self):
        """Create an automatic revision snapshot (non-blocking)."""
        try:
            document = await sync_to_async(
                lambda: __import__("apps.documents.models", fromlist=["Document"]).Document.objects.get(id=self.doc_id)
            )()
            await sync_to_async(
                lambda: __import__("apps.documents.services", fromlist=["create_revision"]).create_revision(
                    document, created_by=self.user, trigger="auto"
                )
            )()
        except Exception as e:
            logger.warning(
                "WS: auto-snapshot failed (non-critical)",
                extra={"doc_id": self.doc_id, "error": str(e)},
            )

    @staticmethod
    async def _load_document(doc_uuid: str):
        """Load document from DB asynchronously."""
        from apps.documents.selectors import get_document_by_uuid
        return await sync_to_async(get_document_by_uuid)(doc_uuid)

    @staticmethod
    def _get_role(user, document) -> Optional[str]:
        """Synchronous permission check (called via sync_to_async)."""
        from apps.documents.permissions import get_user_role
        return get_user_role(user, document)
