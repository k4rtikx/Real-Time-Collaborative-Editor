"""
Initial migration for the audit app.
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, max_length=50)),
                ("document_id", models.BigIntegerField(db_index=True, null=True)),
                ("metadata", models.JSONField(default=dict)),
                ("ip_address", models.GenericIPAddressField(null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events_as_actor", to=settings.AUTH_USER_MODEL)),
                ("target_user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events_as_target", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "audit_auditevent",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["actor", "-created_at"], name="audit_actor_time_idx"),
                    models.Index(fields=["event_type", "-created_at"], name="audit_type_time_idx"),
                ],
            },
        ),
    ]
