#!/usr/bin/env python
"""
Management helper: create superuser non-interactively.

Usage (from project root, venv activated):
    python scripts/create_superuser.py

Environment variables:
    DJANGO_SUPERUSER_USERNAME  (default: admin)
    DJANGO_SUPERUSER_EMAIL     (default: admin@example.com)
    DJANGO_SUPERUSER_PASSWORD  (required)
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doc_editor.settings.development")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

if not password:
    print("Error: DJANGO_SUPERUSER_PASSWORD environment variable is required.", file=sys.stderr)
    sys.exit(1)

if User.objects.filter(username=username).exists():
    print(f"Superuser '{username}' already exists — skipping.")
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser '{username}' created successfully.")
