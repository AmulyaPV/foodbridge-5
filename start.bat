@echo off
REM Run FoodBridge (Windows): start.bat  ->  http://127.0.0.1:8000/
cd /d "%~dp0"
if not exist venv ( echo Creating virtual environment... & python -m venv venv )
call venv\Scripts\activate
pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
python manage.py migrate -v0
echo.
echo FoodBridge is running at http://127.0.0.1:8000/   (Ctrl+C to stop)
python manage.py runserver 127.0.0.1:8000
