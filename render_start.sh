
#!/usr/bin/env bash
# exit on error
set -o errexit

echo "==> Starting Celery Beat Scheduler..."
celery -A rnchealth beat --loglevel=info &

echo "==> Starting Celery Worker (Concurrency = 1)..."
celery -A rnchealth worker --loglevel=info --concurrency=1 &

echo "==> Starting ASGI Server (Daphne)..."
daphne -b 0.0.0.0 -p $PORT rnchealth.asgi:application