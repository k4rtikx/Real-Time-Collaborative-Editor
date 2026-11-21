"""
Fix migration state: 
- accounts.User uses db_table="accounts_user", so we need to CREATE the table
  (it doesn't reuse auth_user — it's a fresh separate table).
- Mark accounts.0001_initial as applied, then run remaining migrations.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doc_editor.settings.development")
django.setup()

from django.db import connection

# 1. Show existing tables
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cursor.fetchall()]
    print("Existing tables:")
    for t in tables:
        print(f"  {t}")

# 2. Check if accounts_user exists
accounts_user_exists = "accounts_user" in tables
print(f"\naccounts_user table exists: {accounts_user_exists}")

# 3. Check current migration state
with connection.cursor() as cursor:
    cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name;")
    applied = cursor.fetchall()
    print("\nApplied migrations:")
    for app, name in applied:
        print(f"  [{app}] {name}")
