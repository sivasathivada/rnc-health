#!/usr/bin/env bash
set -o errexit

echo "Cleaning up processes..."
pkill -f "celery -A rnchealth" || true

# Start Celery components FIRST in the background
echo "Starting Celery Backend Layer..."
celery -A rnchealth worker --pool=solo --loglevel=info &
celery -A rnchealth beat --loglevel=info &

# Give Celery 2 seconds to establish its Redis link
sleep 2

# Start Daphne LAST in the foreground (No & at the end)
echo "Launching Daphne ASGI Application..."
daphne -b 0.0.0.0 -p $PORT rnchealth.asgi:application