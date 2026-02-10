#!/bin/sh
set -e

python manage.py migrate --noinput

python manage.py shell <<'PYTHON'
from django.contrib.auth import get_user_model
from django.core.management import call_command
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
from rides.models import Ride
if not Ride.objects.exists():
    call_command('loaddata', 'seed_rides', verbosity=0)
PYTHON

exec "$@"
