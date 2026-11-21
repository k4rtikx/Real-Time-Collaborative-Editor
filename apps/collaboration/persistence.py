"""
Async document persistence — flush Yjs state to PostgreSQL.

Design:
    - Called by DocumentConsumer on a debounced 30-second timer.
    - Called immediately when the last WebSocket connection to a document disconnects.
    - Uses select_for_update() to prevent concurrent flush races.
    - Retries up to 3 times on OperationalError with exponential backoff.
    - Updates the Redis cache TTL after a successful flush.
    - Never crashes the caller — logs errors and returns False on failure.
"""
from __future__ import annotations

import asyncio
import logging

from django.db import OperationalError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

YDOC_REDIS_KEY = "collabedit:ydoc:{doc_id}"
YDOC_TTL = 86400  # 24 hours
MAX_RETRIES = 3


async def flush_to_db(doc_id: int, encoded_state: bytes, redis_client=None) -> bool:
    """
    Write the Yjs encoded document state to PostgreSQL.

    Args:
        doc_id: The Document primary key.
        encoded_state: The Yjs encoded state as bytes.
        redis_client: Optional async Redis client for cache update.

    Returns:
        True if the flush succeeded, False if all retries were exhausted.
    """
    for attempt in range(MAX_RETRIES):
        try:
            await _do_flush(doc_id, encoded_state)

            # Update Redis cache TTL on success
            if redis_client is not None:
                try:
                    await redis_client.set(
                        YDOC_REDIS_KEY.format(doc_id=doc_id),
                        encoded_state,
                        ex=YDOC_TTL,
                    )
                except Exception as redis_err:
                    # Redis failure after successful DB write is not critical
                    logger.warning(
                        "flush_to_db: Redis cache update failed (non-critical)",
                        extra={"doc_id": doc_id, "error": str(redis_err)},
                    )

            logger.info(
                "flush_to_db: succeeded",
                extra={"doc_id": doc_id, "attempt": attempt + 1, "bytes": len(encoded_state)},
            )
            return True

        except OperationalError as e:
            backoff = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                "flush_to_db: OperationalError, will retry",
                extra={
                    "doc_id": doc_id,
                    "attempt": attempt + 1,
                    "max_retries": MAX_RETRIES,
                    "backoff_seconds": backoff,
                    "error": str(e),
                },
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(backoff)

        except Exception as e:
            logger.error(
                "flush_to_db: unexpected error",
                extra={"doc_id": doc_id, "attempt": attempt + 1, "error": str(e)},
                exc_info=True,
            )
            break  # Don't retry on unexpected errors

    logger.error(
        "flush_to_db: failed after all retries",
        extra={"doc_id": doc_id, "max_retries": MAX_RETRIES},
    )
    return False


async def _do_flush(doc_id: int, encoded_state: bytes) -> None:
    """Execute the actual database write inside a transaction."""
    from apps.documents.models import Document

    async with transaction.atomic():
        document = await Document.objects.select_for_update().aget(id=doc_id)
        document.yjs_state = encoded_state
        document.updated_at = timezone.now()
        await document.asave(update_fields=["yjs_state", "updated_at"])


async def load_from_db(doc_id: int) -> bytes | None:
    """
    Load the Yjs encoded state from PostgreSQL.

    Returns None if the document does not exist or has no saved state.
    """
    from apps.documents.models import Document

    try:
        document = await Document.objects.aget(id=doc_id, is_deleted=False)
        if document.yjs_state:
            return bytes(document.yjs_state)
        return None
    except Document.DoesNotExist:
        logger.warning("load_from_db: Document not found", extra={"doc_id": doc_id})
        return None
