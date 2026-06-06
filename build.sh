#!/usr/bin/env bash
# exit on error if any single command fails
set -o errexit

# 1. Install all Python packages listed in requirements.txt
pip install -r requirements.txt

# 2. Gather all Django admin and app static assets (CSS, JS, Images) into one folder
python manage.py collectstatic --no-input

# 3. Apply your database migrations to your live Supabase PostgreSQL database
python manage.py migrate