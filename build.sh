#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

echo "=== FoodBridge Render Build Step ==="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "=== Collecting Static Files ==="
python manage.py collectstatic --noinput

echo "=== Applying Database Migrations ==="
python manage.py migrate --noinput

echo "=== Render Build Complete ==="
