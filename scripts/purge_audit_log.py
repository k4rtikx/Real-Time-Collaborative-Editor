#!/usr/bin/env python
"""
Management helper: purge audit log entries older than N days (default 90).

Usage (from project root, venv activated):
    python scripts/purge_audit_log.py
    python scripts/purge_audit_log.py --days 30
    python scripts/purge_audit_log.py --dry-run

This script should be run on a schedule (e.g., weekly cron / Render cron job).
"""
import argparse
import os
import sys
import django
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doc_editor.settings.production")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

django.setup()

from django.utils import timezone
from apps.audit.models import AuditEvent


def main():
    parser = argparse.ArgumentParser(description="Purge old audit log entries.")
    parser.add_argument("--days", type=int, default=90, help="Retention period in days (default: 90)")
    parser.add_argument("--dry-run", action="store_true", help="Print count without deleting")
    args = parser.parse_args()

    cutoff = timezone.now() - timedelta(days=args.days)
    qs = AuditEvent.objects.filter(created_at__lt=cutoff)
    count = qs.count()

    if args.dry_run:
        print(f"DRY RUN: Would delete {count} audit events older than {args.days} days (before {cutoff.date()}).")
    else:
        deleted, _ = qs.delete()
        print(f"Deleted {deleted} audit events older than {args.days} days (before {cutoff.date()}).")


if __name__ == "__main__":
    main()
