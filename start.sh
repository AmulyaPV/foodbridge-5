#!/usr/bin/env bash
# Run FoodBridge (macOS / Linux): ./start.sh  ->  http://127.0.0.1:8000/
set -e
cd "$(dirname "$0")"
PY=python3; command -v python3 >/dev/null || PY=python
if [ ! -d venv ]; then echo "Creating virtual environment..."; $PY -m venv venv; fi
. venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
python manage.py migrate -v0
echo
echo "FoodBridge is running at http://127.0.0.1:8000/   (Ctrl+C to stop)"
python manage.py runserver 127.0.0.1:8000
