#!/bin/sh
set -e

python manage.py migrate --noinput

python manage.py shell <<'PYTHON'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
PYTHON

exec "$@"
