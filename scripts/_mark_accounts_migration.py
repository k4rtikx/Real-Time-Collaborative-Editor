from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("INSERT INTO django_migrations (app, name, applied) SELECT 'accounts', '0001_initial', NOW() WHERE NOT EXISTS (SELECT 1 FROM django_migrations WHERE app='accounts' AND name='0001_initial');")
    cursor.execute("SELECT app, name FROM django_migrations WHERE app='accounts';")
    print(cursor.fetchall())
