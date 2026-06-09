
#!/usr/bin/env bash
# exit on error
set -o errexit

echo "==> Cleaning up any lingering background Celery processes..."
# Forcefully kill any running celery processes owned by the render user
pkill -f "celery -A rnchealth" || true

echo "Running Migrations..."
python manage.py migrate

echo "Starting Daphne Web Server..."
# Run Daphne in the background (&)
daphne -b 0.0.0.0 -p $PORT rnchealth.asgi:application &

# 🌟 THE CRITICAL FIX: Wait for the network socket and environment to settle
echo "Waiting for network layers to stabilize..."
sleep 5

echo "Starting Celery Worker & Beat..."
# Run Celery Worker using the solo pool to prevent Python concurrency network blockages
celery -A rnchealth worker --pool=solo --loglevel=info &
celery -A rnchealth beat --loglevel=info