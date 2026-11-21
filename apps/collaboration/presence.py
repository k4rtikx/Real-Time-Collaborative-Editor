"""
Redis-backed connection-aware presence manager.

Data structures:
    collabedit:presence:{doc_id}
        Sorted set: {conn_id -> connected_at timestamp}
        Used for efficient stale-connection cleanup via ZRANGEBYSCORE.

    collabedit:presence_data:{doc_id}:{conn_id}
        Hash: {user_id, username, color, connected_at}
        TTL: 30 seconds (refreshed on heartbeat; cleanup fallback for crashes)

Design notes:
    - Multiple browser tabs from the same user each get their own conn_id.
    - get_active_users() deduplicates by user_id before returning.
    - Stale entries (crashed connections) are cleaned by TTL and cleanup_stale().
"""
from __future__ import annotations

import logging
import time
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Color palette for cursor display — deterministic per user_id
_COLORS = ["#f472b6", "#22d3ee", "#c084fc", "#fb923c", "#34d399", "#60a5fa", "#fbbf24"]

PRESENCE_KEY = "collabedit:presence:{doc_id}"
PRESENCE_DATA_KEY = "collabedit:presence_data:{doc_id}:{conn_id}"
PRESENCE_TTL = 30  # seconds


def _user_color(user_id: int) -> str:
    return _COLORS[user_id % len(_COLORS)]


class PresenceManager:
    """
    Manages presence state for collaborative document sessions.

    Args:
        redis_client: An async redis-py client instance.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    async def add_connection(self, doc_id: int, conn_id: str, user) -> int:
        """
        Register a new WebSocket connection.

        Returns:
            Total number of active connections for this document.
        """
        now = time.time()
        presence_key = PRESENCE_KEY.format(doc_id=doc_id)
        data_key = PRESENCE_DATA_KEY.format(doc_id=doc_id, conn_id=conn_id)

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zadd(presence_key, {conn_id: now})
            pipe.hset(
                data_key,
                mapping={
                    "user_id": str(user.id),
                    "username": user.username,
                    "color": _user_color(user.id),
                    "connected_at": str(now),
                },
            )
            pipe.expire(data_key, PRESENCE_TTL)
            await pipe.execute()

        count = await self._redis.zcard(presence_key)
        logger.debug(
            "Presence: connection added",
            extra={"doc_id": doc_id, "conn_id": conn_id, "user": user.username, "count": count},
        )
        return count

    async def remove_connection(self, doc_id: int, conn_id: str) -> int:
        """
        Remove a connection from presence tracking.

        Returns:
            Remaining number of active connections for this document.
        """
        presence_key = PRESENCE_KEY.format(doc_id=doc_id)
        data_key = PRESENCE_DATA_KEY.format(doc_id=doc_id, conn_id=conn_id)

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zrem(presence_key, conn_id)
            pipe.delete(data_key)
            await pipe.execute()

        count = await self._redis.zcard(presence_key)
        logger.debug(
            "Presence: connection removed",
            extra={"doc_id": doc_id, "conn_id": conn_id, "remaining": count},
        )
        return count

    async def get_active_users(self, doc_id: int) -> list[dict[str, Any]]:
        """
        Return deduplicated list of users currently connected to a document.

        Multiple tabs from the same user appear only once.
        """
        presence_key = PRESENCE_KEY.format(doc_id=doc_id)
        conn_ids = await self._redis.zrange(presence_key, 0, -1)

        users: list[dict] = []
        for conn_id_bytes in conn_ids:
            conn_id = conn_id_bytes.decode() if isinstance(conn_id_bytes, bytes) else conn_id_bytes
            data_key = PRESENCE_DATA_KEY.format(doc_id=doc_id, conn_id=conn_id)
            data = await self._redis.hgetall(data_key)
            if data:
                decoded = {
                    k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                    for k, v in data.items()
                }
                decoded["conn_id"] = conn_id
                users.append(decoded)

        # Deduplicate by user_id (keep first occurrence = oldest connection)
        seen_users: set[str] = set()
        unique: list[dict] = []
        for u in users:
            uid = u.get("user_id", "")
            if uid not in seen_users:
                seen_users.add(uid)
                unique.append(u)

        return unique

    async def cleanup_stale(self, doc_id: int) -> int:
        """
        Remove connections whose presence_data TTL has expired (crashed connections).

        Returns:
            Number of stale connections removed.
        """
        presence_key = PRESENCE_KEY.format(doc_id=doc_id)
        cutoff = time.time() - PRESENCE_TTL
        stale_conn_ids = await self._redis.zrangebyscore(presence_key, 0, cutoff)

        if not stale_conn_ids:
            return 0

        async with self._redis.pipeline() as pipe:
            for conn_id_bytes in stale_conn_ids:
                conn_id = conn_id_bytes.decode() if isinstance(conn_id_bytes, bytes) else conn_id_bytes
                pipe.zrem(presence_key, conn_id)
                pipe.delete(PRESENCE_DATA_KEY.format(doc_id=doc_id, conn_id=conn_id))
            await pipe.execute()

        logger.info(
            "Presence: stale connections cleaned",
            extra={"doc_id": doc_id, "removed": len(stale_conn_ids)},
        )
        return len(stale_conn_ids)

    async def refresh_connection(self, doc_id: int, conn_id: str) -> None:
        """Refresh the TTL of a connection's presence data (heartbeat)."""
        data_key = PRESENCE_DATA_KEY.format(doc_id=doc_id, conn_id=conn_id)
        now = time.time()
        presence_key = PRESENCE_KEY.format(doc_id=doc_id)
        async with self._redis.pipeline() as pipe:
            pipe.zadd(presence_key, {conn_id: now}, xx=True)  # update score only if exists
            pipe.expire(data_key, PRESENCE_TTL)
            await pipe.execute()
