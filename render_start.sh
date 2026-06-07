
#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Spins up worker in background and immediately moves to next line
celery -A rnchealth worker --loglevel=info --concurrency=1 &

# 2. Spins up scheduler in background and immediately moves to next line
celery -A rnchealth beat --loglevel=info &

# 3. Spins up Daphne in foreground, locking the process open to host your site
daphne -b 0.0.0.0 -p $PORT rnchealth.asgi:application