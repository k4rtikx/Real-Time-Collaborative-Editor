"""
Migration 0003 — Document V2.

Adds production fields to the existing documents_document table:
  - title         VARCHAR(255) default "Untitled document"
  - owner         FK → accounts_user (nullable for existing rows)
  - yjs_state     BYTEA — Yjs CRDT encoded state
  - is_deleted    BOOLEAN soft-delete flag
  - deleted_at    TIMESTAMP (nullable)
  - created_at    TIMESTAMP (auto, nullable for existing rows)

Also creates indexes defined on the Document.Meta class.

Depends on:
  ("documents", "0002_document")  — Document table must exist
  ("accounts",  "0001_initial")   — accounts_user table must exist
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_document"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="title",
            field=models.CharField(default="Untitled document", max_length=255),
        ),
        migrations.AddField(
            model_name="document",
            name="owner",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="yjs_state",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="document",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="document",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                null=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["owner"], name="doc_owner_idx"),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["is_deleted", "-updated_at"], name="doc_active_idx"),
        ),
    ]
