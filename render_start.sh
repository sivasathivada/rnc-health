
#!/usr/bin/env bash
# exit on error
set -o errexit

echo "==> Cleaning up any lingering background Celery processes..."
# Forcefully kill any running celery processes owned by the render user
pkill -f "celery -A rnchealth" || true

echo "==> Starting Celery Worker (Concurrency restricted to 1)..."
# 1. Spins up worker in background and immediately moves to next line
celery -A rnchealth worker --loglevel=info --concurrency=1 &

echo "==> Starting Celery Beat Scheduler..."
# 2. Spins up scheduler in background and immediately moves to next line
celery -A rnchealth beat --loglevel=info &

echo "==> Booting Daphne ASGI Web Server..."
# 3. Spins up Daphne in foreground, locking the process open to host your site
daphne -b 0.0.0.0 -p $PORT rnchealth.asgi:application