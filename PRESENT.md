# FoodBridge: running and presenting

## Start
| System | Command |
|---|---|
| macOS / Linux | `./start.sh` |
| Windows | `start.bat` |

Opens at **http://127.0.0.1:8000/**. Needs Python 3.11+, and internet only the first time (to install Django and Pillow).
The database (`db.sqlite3`) is ready and contains **only the admin account**: no hotels, NGOs or listings.

## Admin login
* Email: `admin@foodbridge.com`
* Password: `Admin@12345` (change it: Django admin at `/django-admin/`, or run `python manage.py changepassword admin@foodbridge.com`)
* Admin console: http://127.0.0.1:8000/manage/

## Presenting with real data
1. In a normal window register a **hotel** (`/register/hotel/`), in a private window an **NGO**, in another an **individual**.
2. Log in as admin, open *Verification* and verify each account.
3. Hotel posts surplus food, NGO or individual requests it, hotel confirms, recipient shows the one-time code, hotel enters it. Then try *Report listing* and, as admin, *Remove listing*.
4. Admin *Reports* shows listings created, donations collected and servings redistributed.

## Where things are
Backend: `accounts/`, `core/`, `console/` · Database: `db.sqlite3` (diagram: `docs/er-diagram.png`) · Report text to paste: `docs/REPORT-UPDATE.md` · Viva Q&A: `docs/viva-qa.md` · Tests: `python manage.py test` (85 pass)
