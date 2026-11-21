"""
One-time migration state repair script.
Run from project root: manage.py shell < scripts/_fix_migration_state.py
"""
from django.db import connection

# 1. Show existing tables
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cursor.fetchall()]

print("Existing tables:", tables)
print("accounts_user exists:", "accounts_user" in tables)

# 2. Show applied migrations
with connection.cursor() as cursor:
    cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name;")
    rows = cursor.fetchall()

print("\nApplied migrations:")
for app, name in rows:
    print(f"  [{app}] {name}")

# 3. If accounts_user does NOT exist, we need to CREATE it then mark applied
if "accounts_user" not in tables:
    print("\naccounts_user table MISSING — will create via raw SQL then mark migration applied")
    with connection.cursor() as cursor:
        # Create accounts_user (mirrors what accounts.0001_initial would do)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts_user (
                id bigserial PRIMARY KEY,
                password varchar(128) NOT NULL,
                last_login timestamptz NULL,
                is_superuser boolean NOT NULL DEFAULT false,
                username varchar(150) NOT NULL UNIQUE,
                first_name varchar(150) NOT NULL DEFAULT '',
                last_name varchar(150) NOT NULL DEFAULT '',
                email varchar(254) NOT NULL DEFAULT '',
                is_staff boolean NOT NULL DEFAULT false,
                is_active boolean NOT NULL DEFAULT true,
                date_joined timestamptz NOT NULL DEFAULT now()
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts_user_groups (
                id bigserial PRIMARY KEY,
                user_id bigint NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
                group_id integer NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE,
                UNIQUE(user_id, group_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts_user_user_permissions (
                id bigserial PRIMARY KEY,
                user_id bigint NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
                permission_id integer NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
                UNIQUE(user_id, permission_id)
            );
        """)
        print("Created accounts_user table and relations")

    # Mark accounts.0001_initial as applied
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO django_migrations (app, name, applied)
            SELECT 'accounts', '0001_initial', NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM django_migrations WHERE app='accounts' AND name='0001_initial'
            );
        """)
    print("Marked accounts.0001_initial as applied in django_migrations")
else:
    print("\naccounts_user exists — just marking migration as applied")
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO django_migrations (app, name, applied)
            SELECT 'accounts', '0001_initial', NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM django_migrations WHERE app='accounts' AND name='0001_initial'
            );
        """)
    print("Done")

print("\nRepair complete. Now run: python manage.py migrate")
