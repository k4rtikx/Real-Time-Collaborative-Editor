"""Custom User model using AbstractUser for forward compatibility."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model.

    Inherits all fields from AbstractUser (username, email, password, etc.).
    Using AbstractUser instead of the built-in User allows adding profile
    fields in future migrations without replacing the auth model.

    No extra fields are added in V1.
    """

    class Meta:
        db_table = "accounts_user"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.username
