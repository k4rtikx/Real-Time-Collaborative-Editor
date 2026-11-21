"""
Presence manager tests.

Uses fakeredis for in-memory Redis simulation — no live Redis required.
"""
import time

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fake_aioredis
    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False


pytestmark = pytest.mark.skipif(not HAS_FAKEREDIS, reason="fakeredis not installed")


@pytest_asyncio.fixture
async def redis():
    """Return a fake async Redis client."""
    server = fake_aioredis.FakeServer()
    client = fake_aioredis.FakeRedis(server=server)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def presence(redis):
    from apps.collaboration.presence import PresenceManager
    return PresenceManager(redis)


def _make_user(user_id, username):
    return type("User", (), {"id": user_id, "username": username, "is_authenticated": True})()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_connection_returns_count(presence):
    """add_connection should return the total active connection count."""
    user = _make_user(1, "alice")
    count = await presence.add_connection(doc_id=1, conn_id="conn-1", user=user)
    assert count == 1

    count2 = await presence.add_connection(doc_id=1, conn_id="conn-2", user=user)
    assert count2 == 2


@pytest.mark.asyncio
async def test_remove_connection_returns_remaining(presence):
    """remove_connection should return remaining connection count."""
    user = _make_user(1, "alice")
    await presence.add_connection(doc_id=1, conn_id="conn-1", user=user)
    await presence.add_connection(doc_id=1, conn_id="conn-2", user=user)

    remaining = await presence.remove_connection(doc_id=1, conn_id="conn-1")
    assert remaining == 1

    remaining2 = await presence.remove_connection(doc_id=1, conn_id="conn-2")
    assert remaining2 == 0


@pytest.mark.asyncio
async def test_get_active_users_returns_users(presence):
    """get_active_users should return connected users."""
    alice = _make_user(1, "alice")
    bob = _make_user(2, "bob")

    await presence.add_connection(doc_id=1, conn_id="conn-a", user=alice)
    await presence.add_connection(doc_id=1, conn_id="conn-b", user=bob)

    users = await presence.get_active_users(doc_id=1)
    usernames = {u["username"] for u in users}
    assert "alice" in usernames
    assert "bob" in usernames


@pytest.mark.asyncio
async def test_get_active_users_deduplicates_same_user(presence):
    """Multiple tabs from the same user appear only once."""
    alice = _make_user(1, "alice")

    await presence.add_connection(doc_id=1, conn_id="conn-tab1", user=alice)
    await presence.add_connection(doc_id=1, conn_id="conn-tab2", user=alice)

    users = await presence.get_active_users(doc_id=1)
    # Alice should appear only once despite two connections
    assert len([u for u in users if u["username"] == "alice"]) == 1


@pytest.mark.asyncio
async def test_get_active_users_empty_after_disconnect(presence):
    """No users returned after all connections are removed."""
    user = _make_user(1, "alice")
    await presence.add_connection(doc_id=1, conn_id="conn-1", user=user)
    await presence.remove_connection(doc_id=1, conn_id="conn-1")

    users = await presence.get_active_users(doc_id=1)
    assert users == []


@pytest.mark.asyncio
async def test_separate_documents_do_not_interfere(presence):
    """Presence for different documents is isolated."""
    alice = _make_user(1, "alice")
    bob = _make_user(2, "bob")

    await presence.add_connection(doc_id=1, conn_id="conn-a", user=alice)
    await presence.add_connection(doc_id=2, conn_id="conn-b", user=bob)

    users_doc1 = await presence.get_active_users(doc_id=1)
    users_doc2 = await presence.get_active_users(doc_id=2)

    assert len(users_doc1) == 1
    assert users_doc1[0]["username"] == "alice"
    assert len(users_doc2) == 1
    assert users_doc2[0]["username"] == "bob"


@pytest.mark.asyncio
async def test_user_color_is_deterministic(presence):
    """Each user gets a consistent color based on their user_id."""
    user = _make_user(5, "charlie")
    await presence.add_connection(doc_id=1, conn_id="conn-1", user=user)

    users = await presence.get_active_users(doc_id=1)
    color1 = users[0]["color"]

    # Add again (simulate reconnect)
    await presence.remove_connection(doc_id=1, conn_id="conn-1")
    await presence.add_connection(doc_id=1, conn_id="conn-2", user=user)
    users2 = await presence.get_active_users(doc_id=1)
    color2 = users2[0]["color"]

    assert color1 == color2  # Same user → same color
