"""Account service layer — business logic for user operations."""
import logging
from typing import Optional

from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


def create_user(username: str, email: str, password: str) -> User:
    """
    Create and return a new active user.

    Raises:
        ValueError: If username or email already exists.
    """
    if User.objects.filter(username=username).exists():
        raise ValueError(f"Username '{username}' is already taken.")
    if User.objects.filter(email=email.lower()).exists():
        raise ValueError(f"Email '{email}' is already registered.")

    user = User.objects.create_user(
        username=username,
        email=email.lower(),
        password=password,
    )
    logger.info("User created", extra={"username": username})
    return user


def get_user_by_username(username: str) -> Optional[User]:
    """Return a User by username, or None."""
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        return None


def get_user_by_email(email: str) -> Optional[User]:
    """Return a User by email (case-insensitive), or None."""
    try:
        return User.objects.get(email=email.lower())
    except User.DoesNotExist:
        return None
