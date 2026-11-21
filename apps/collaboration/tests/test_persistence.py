"""
Persistence layer tests.

Tests flush_to_db and load_from_db with mocked database and Redis.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# flush_to_db tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_flush_to_db_success(db):
    """flush_to_db should write yjs_state to DB and return True."""
    from apps.documents.services import create_document
    from apps.collaboration.persistence import flush_to_db
    from django.contrib.auth import get_user_model

    User = get_user_model()
    owner = await User.objects.acreate_user(username="persist_alice", password="pass123!")
    doc = await _create_doc_async(owner, "Test Doc")

    result = await flush_to_db(doc.id, b"\x01\x02\x03", redis_client=None)
    assert result is True

    # Verify DB updated
    from apps.documents.models import Document
    refreshed = await Document.objects.aget(id=doc.id)
    assert bytes(refreshed.yjs_state) == b"\x01\x02\x03"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_flush_to_db_nonexistent_doc_returns_false():
    """flush_to_db on a non-existent doc_id should return False (not raise)."""
    from apps.collaboration.persistence import flush_to_db
    result = await flush_to_db(doc_id=999999, encoded_state=b"\x01", redis_client=None)
    assert result is False


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_flush_to_db_updates_redis_cache(db):
    """flush_to_db should update the Redis cache on success."""
    from apps.documents.services import create_document
    from apps.collaboration.persistence import flush_to_db
    from django.contrib.auth import get_user_model

    User = get_user_model()
    owner = await User.objects.acreate_user(username="persist_bob", password="pass123!")
    doc = await _create_doc_async(owner, "Cache Test")

    mock_redis = AsyncMock()
    result = await flush_to_db(doc.id, b"\xDE\xAD\xBE\xEF", redis_client=mock_redis)

    assert result is True
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][1] == b"\xDE\xAD\xBE\xEF"


# ---------------------------------------------------------------------------
# load_from_db tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_load_from_db_returns_state(db):
    """load_from_db should return the stored yjs_state bytes."""
    from apps.collaboration.persistence import flush_to_db, load_from_db
    from django.contrib.auth import get_user_model

    User = get_user_model()
    owner = await User.objects.acreate_user(username="persist_carol", password="pass123!")
    doc = await _create_doc_async(owner, "Load Test")

    await flush_to_db(doc.id, b"\xAB\xCD\xEF", redis_client=None)

    state = await load_from_db(doc.id)
    assert state == b"\xAB\xCD\xEF"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_load_from_db_returns_none_for_no_state(db):
    """load_from_db should return None if yjs_state is not set."""
    from apps.collaboration.persistence import load_from_db
    from django.contrib.auth import get_user_model

    User = get_user_model()
    owner = await User.objects.acreate_user(username="persist_dave", password="pass123!")
    doc = await _create_doc_async(owner, "Empty Doc")
    # yjs_state is null by default

    state = await load_from_db(doc.id)
    assert state is None


@pytest.mark.asyncio
async def test_load_from_db_returns_none_for_missing_doc():
    """load_from_db should return None for non-existent doc_id."""
    from apps.collaboration.persistence import load_from_db
    state = await load_from_db(doc_id=999999)
    assert state is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_doc_async(owner, title):
    """Create a document using sync service called via sync_to_async."""
    from asgiref.sync import sync_to_async
    from apps.documents.services import create_document
    return await sync_to_async(create_document)(owner=owner, title=title)
