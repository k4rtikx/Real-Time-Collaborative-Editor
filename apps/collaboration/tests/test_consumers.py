"""
WebSocket consumer tests.

Uses Django Channels' WebsocketCommunicator for in-process WebSocket testing.
No actual network connection is made.

The consumer creates a Redis client on connect(). We patch _get_redis() to
return a fakeredis async client so no live Redis is required.
"""
from __future__ import annotations

import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    return User.objects.create_user(username="ws_alice", password="testpass123!")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="ws_bob", password="testpass123!")


@pytest.fixture
def document(db, user):
    """Create a document owned by `user`."""
    from apps.documents.services import create_document
    return create_document(owner=user, title="WS Test Document")


@pytest.fixture
def viewer_user(db, user, document):
    """Return a user with viewer access to `document`."""
    viewer = User.objects.create_user(username="ws_viewer", password="testpass123!")
    from apps.documents.services import share_document
    share_document(user, document, viewer, "viewer")
    return viewer


@pytest.fixture
def editor_user(db, user, document):
    """Return a user with editor access to `document`."""
    editor = User.objects.create_user(username="ws_editor", password="testpass123!")
    from apps.documents.services import share_document
    share_document(user, document, editor, "editor")
    return editor


# ---------------------------------------------------------------------------
# Helper: build a WebsocketCommunicator with optional authenticated user
# ---------------------------------------------------------------------------

def _make_communicator(user=None, doc_uuid="test-uuid-1234"):
    """
    Build a WebsocketCommunicator with optional authenticated user scope.
    Uses InMemoryChannelLayer (set by conftest.py / testing settings).
    """
    from doc_editor.asgi import application
    scope_user = user or type("AnonymousUser", (), {"is_authenticated": False})()
    communicator = WebsocketCommunicator(
        application,
        f"/ws/documents/{doc_uuid}/",
    )
    # Inject user directly into scope (bypasses session auth for unit tests)
    communicator.scope["user"] = scope_user
    return communicator


def _fake_redis():
    """Return a fakeredis async client, or None if fakeredis is not installed."""
    try:
        import fakeredis.aioredis as fake_aioredis
        server = fake_aioredis.FakeServer()
        return fake_aioredis.FakeRedis(server=server)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_anonymous_connect_rejected_4001():
    """Unauthenticated WebSocket connection must be rejected with code 4001."""
    communicator = _make_communicator(user=None, doc_uuid="any-uuid")
    connected, code = await communicator.connect()
    assert not connected or code == 4001
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_no_permission_connect_rejected_4003(other_user, document):
    """User with no permission must be rejected with code 4003."""
    communicator = _make_communicator(user=other_user, doc_uuid=document.uuid)
    connected, code = await communicator.connect()
    assert not connected or code == 4003
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_nonexistent_document_rejected_4004(user):
    """Non-existent document UUID must be rejected with code 4004."""
    communicator = _make_communicator(user=user, doc_uuid="00000000-0000-0000-0000-000000000000")
    connected, code = await communicator.connect()
    assert not connected or code == 4004
    await communicator.disconnect()


# ---------------------------------------------------------------------------
# Permission enforcement on connect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_owner_can_connect(user, document):
    """Document owner must be accepted."""
    from unittest.mock import patch, AsyncMock
    fake_redis = _fake_redis()
    if fake_redis is None:
        pytest.skip("fakeredis not installed")

    with patch("apps.collaboration.consumers._get_redis", return_value=fake_redis), \
         patch("core.rate_limiting.get_redis_client"):
        communicator = _make_communicator(user=user, doc_uuid=document.uuid)
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_editor_can_connect(editor_user, document):
    """Editor must be accepted."""
    from unittest.mock import patch
    fake_redis = _fake_redis()
    if fake_redis is None:
        pytest.skip("fakeredis not installed")

    with patch("apps.collaboration.consumers._get_redis", return_value=fake_redis), \
         patch("core.rate_limiting.get_redis_client"):
        communicator = _make_communicator(user=editor_user, doc_uuid=document.uuid)
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_viewer_can_connect(viewer_user, document):
    """Viewer must be accepted (read-only)."""
    from unittest.mock import patch
    fake_redis = _fake_redis()
    if fake_redis is None:
        pytest.skip("fakeredis not installed")

    with patch("apps.collaboration.consumers._get_redis", return_value=fake_redis), \
         patch("core.rate_limiting.get_redis_client"):
        communicator = _make_communicator(user=viewer_user, doc_uuid=document.uuid)
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_payload_too_large_closes_4008(user, document):
    """Payload exceeding 1 MB must trigger close code 4008."""
    from unittest.mock import patch, MagicMock
    fake_redis = _fake_redis()
    if fake_redis is None:
        pytest.skip("fakeredis not installed")

    mock_limiter = MagicMock()
    mock_limiter.is_allowed.return_value = (True, 0.0)

    with patch("apps.collaboration.consumers._get_redis", return_value=fake_redis), \
         patch("core.rate_limiting.get_redis_client"), \
         patch("apps.collaboration.consumers.TokenBucket", return_value=mock_limiter):
        communicator = _make_communicator(user=user, doc_uuid=document.uuid)
        connected, _ = await communicator.connect()
        assert connected

        # Consume the initial Sync Step 2 message
        await communicator.receive_from()

        # Send oversized payload (1 MB + 1 byte)
        oversized = bytes(1_048_577)
        await communicator.send_to(bytes_data=oversized)

        response = await communicator.receive_output()
        assert response["type"] == "websocket.close"
        assert response.get("code") == 4008
        await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_viewer_cannot_send_update_closes_4003(viewer_user, document):
    """Viewer sending MSG_UPDATE (0x02) must result in close 4003."""
    from unittest.mock import patch, MagicMock
    fake_redis = _fake_redis()
    if fake_redis is None:
        pytest.skip("fakeredis not installed")

    mock_limiter = MagicMock()
    mock_limiter.is_allowed.return_value = (True, 0.0)

    with patch("apps.collaboration.consumers._get_redis", return_value=fake_redis), \
         patch("core.rate_limiting.get_redis_client"), \
         patch("apps.collaboration.consumers.TokenBucket", return_value=mock_limiter):
        communicator = _make_communicator(user=viewer_user, doc_uuid=document.uuid)
        connected, _ = await communicator.connect()
        assert connected

        # Consume the initial Sync Step 2 message
        await communicator.receive_from()

        # Send a MSG_UPDATE as viewer (type byte 0x02)
        update_msg = bytes([0x02, 0x01, 0x02, 0x03])
        await communicator.send_to(bytes_data=update_msg)

        response = await communicator.receive_output()
        assert response["type"] == "websocket.close"
        assert response.get("code") == 4003
        await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_step1_receives_response(user, document):
    """MSG_SYNC_STEP1 (0x00) must trigger a MSG_SYNC_STEP2 (0x01) response."""
    from unittest.mock import patch, MagicMock
    fake_redis = _fake_redis()
    if fake_redis is None:
        pytest.skip("fakeredis not installed")

    mock_limiter = MagicMock()
    mock_limiter.is_allowed.return_value = (True, 0.0)

    with patch("apps.collaboration.consumers._get_redis", return_value=fake_redis), \
         patch("core.rate_limiting.get_redis_client"), \
         patch("apps.collaboration.consumers.TokenBucket", return_value=mock_limiter):
        communicator = _make_communicator(user=user, doc_uuid=document.uuid)
        connected, _ = await communicator.connect()
        assert connected

        # First message from server: Sync Step 2 (initial state)
        initial = await communicator.receive_from()
        assert isinstance(initial, bytes)
        assert initial[0] == 0x01  # MSG_SYNC_STEP2

        # Send Sync Step 1 (empty state vector)
        await communicator.send_to(bytes_data=bytes([0x00]))

        # Expect Sync Step 2 response
        response = await communicator.receive_from()
        assert isinstance(response, bytes)
        assert response[0] == 0x01  # MSG_SYNC_STEP2

        await communicator.disconnect()
