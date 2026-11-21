"""
Root conftest.py — pytest fixtures shared across the entire test suite.

Responsibilities:
  - Override CHANNEL_LAYERS to use InMemoryChannelLayer (no Redis required for unit tests)
  - Override RATE_LIMIT_ENABLED = False (no Redis calls in HTTP tests)
  - Provide shared Django fixtures for User and Document creation
  - Provide async-compatible fixtures for WebSocket consumer tests
"""
from __future__ import annotations

import django
import pytest
from django.conf import settings


# ---------------------------------------------------------------------------
# Settings overrides applied before the test session starts
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """
    Override Django settings for the test session.
    Called early — before Django apps are loaded.
    """
    # Use InMemoryChannelLayer so WebSocket consumer tests don't need Redis.
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
    # Disable HTTP rate limiting — no Redis connection needed for unit tests.
    settings.RATE_LIMIT_ENABLED = False


# ---------------------------------------------------------------------------
# Shared sync fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    """Return a standard authenticated user."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="TestPass123!",
    )


@pytest.fixture
def other_user(db):
    """Return a second user (no document permissions by default)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username="otheruser",
        email="otheruser@example.com",
        password="TestPass123!",
    )


@pytest.fixture
def document(db, user):
    """Return a document owned by `user`."""
    from apps.documents.services import create_document
    return create_document(owner=user, title="Test Document")


@pytest.fixture
def editor_permission(db, document, other_user):
    """Grant other_user editor access to document. Returns the DocumentPermission."""
    from apps.documents.services import share_document
    return share_document(user=document.owner, document=document, target_user=other_user, role="editor")


@pytest.fixture
def viewer_permission(db, document, other_user):
    """Grant other_user viewer access to document. Returns the DocumentPermission."""
    from apps.documents.services import share_document
    return share_document(user=document.owner, document=document, target_user=other_user, role="viewer")


@pytest.fixture
def authenticated_client(client, user):
    """Return a Django test Client logged in as `user`."""
    client.force_login(user)
    return client
