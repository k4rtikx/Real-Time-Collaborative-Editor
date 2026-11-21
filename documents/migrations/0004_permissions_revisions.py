"""
Migration 0004 — DocumentPermission and DocumentRevision tables.

Creates:
  documents_documentpermission   — per-user, per-document permission grant
  documents_documentrevision     — immutable point-in-time Yjs state snapshots

Depends on:
  ("documents", "0003_document_v2")  — Document V2 must exist
  ("accounts",  "0001_initial")      — accounts_user table must exist
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_document_v2"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # DocumentPermission
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="DocumentPermission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[("editor", "Editor"), ("viewer", "Viewer")],
                        max_length=10,
                    ),
                ),
                ("granted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permissions",
                        to="documents.document",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="granted_permissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_permissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "documents_documentpermission",
            },
        ),
        migrations.AlterUniqueTogether(
            name="documentpermission",
            unique_together={("document", "user")},
        ),
        migrations.AddIndex(
            model_name="documentpermission",
            index=models.Index(fields=["user", "document"], name="perm_user_doc_idx"),
        ),
        # ------------------------------------------------------------------
        # DocumentRevision
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="DocumentRevision",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("revision_number", models.PositiveIntegerField()),
                ("yjs_state", models.BinaryField()),
                ("content_html", models.TextField(blank=True)),
                (
                    "trigger",
                    models.CharField(
                        choices=[
                            ("manual", "Manual"),
                            ("auto", "Automatic"),
                            ("restore", "Pre-restore snapshot"),
                        ],
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="documents.document",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "documents_documentrevision",
                "ordering": ["-revision_number"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="documentrevision",
            unique_together={("document", "revision_number")},
        ),
        migrations.AddIndex(
            model_name="documentrevision",
            index=models.Index(
                fields=["document", "-revision_number"], name="rev_doc_num_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="documentrevision",
            index=models.Index(
                fields=["document", "-created_at"], name="rev_doc_time_idx"
            ),
        ),
    ]
