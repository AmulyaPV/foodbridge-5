# FoodBridge — how this project works (plain-language guide)

## What the website does

Hotels often cook more food than they sell. FoodBridge lets a **hotel** post that
surplus, lets a **verified NGO** request some of it, and tracks the pickup until the
food is handed over. An **admin** checks that hotels, NGOs and individuals are genuine. People who need food but are not part of an NGO can also register as **individuals** and request a few servings.

## The four roles

| Role | Can do |
|------|--------|
| Hotel | Post a listing (items, servings, photos, pickup window, safe-until time) · confirm or decline requests · report a listing · confirm handover with the code · see history and an Impact Certificate |
| NGO | Browse and filter food · request servings · say "I'm on my way" · show the pickup code · post a need on the Needs Board |
| Individual | Browse and filter food · request up to 10 servings at a time · show the pickup code |
| Admin | Verify/reject/suspend hotels, NGOs and individuals · review reports on listings and remove listings · unlock locked pickups · view reports and the activity log |

New accounts must be verified by the admin before they can do anything.

## One pickup, step by step

1. Hotel **posts a listing**. The system ranks verified NGOs (distance, capacity fit, reliability) and gives the top 5 a 10-minute "first look" (*Smart Match*).
2. NGO **requests** some servings. The *Safe-Until Clock* checks the NGO can realistically arrive before the food stops being safe; if not, the request is blocked.
3. Hotel **confirms**. Servings are reserved (locked in a database transaction so two confirmations can't claim the same food) and the **Secure Handover Code** is created.
4. NGO sees the code, taps **on my way** (with an ETA).
5. At the counter the NGO shows the code; the hotel **types it in**. Correct → *Collected*. Five wrong tries → locked until an admin unlocks it.
6. The NGO's reliability score and the hotel's Impact Certificate update from real data.

## How the code is organised (Django)

Django splits a site into *apps*. Each app has: `models.py` (database tables), `views.py` (what happens on each page), `urls.py` (which address goes to which view), and HTML in `templates/`.

```text
foodbridge/   settings + root urls (the "front door")
accounts/     users, login, registration, hotel/NGO profiles, verification
core/         the main product: listings, requests, handover code, matching, needs, notifications
console/      the admin's own dashboard (verification queue, reports, locked pickups)
templates/    every HTML page
static/       CSS and JavaScript
docs/         diagrams and design notes (start with this file)
```

Inside `core/` the logic is deliberately kept out of the views:

| File | What it holds |
|------|---------------|
| `models.py` | Tables: listings, items, photos, requests, handover code + attempts, needs, notifications, activity log |
| `listings_service.py` | Creating, reposting, cancelling and (admin) removing listings |
| `moderation_service.py` | Reporting a listing; dismissing or acting on a report |
| `requests_service.py` | Request lifecycle: create, confirm, reject, cancel, on the way |
| `handover_service.py` | **The handover code rules** |
| `matching.py`, `reliability.py`, `geo.py` | Smart Match ranking, reliability score, distance/travel time |
| `views.py` | Thin: read the request, call a service, show a page |
| `tests/` | 85 automated tests |

Rule of thumb: **model = data, service = rules, view = glue, template = look.**

## Request → response, concretely (hotel types the code)

1. Browser posts the form to `/hotel/requests/<id>/handover/` (`core/urls.py`).
2. `views.confirm_handover` checks the user is a verified hotel that owns the pickup.
3. It calls `handover_service.confirm_handover(...)`, which checks status, expiry and the code inside one database transaction.
4. Success → pickup saved as collected, activity logged, NGO notified. Failure → counter and attempt log saved, then an error message is shown.

## Running and testing

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # your admin login
python manage.py runserver            # http://127.0.0.1:8000/
python manage.py test                 # should print: Ran 85 tests ... OK
```

Try it yourself with three browser windows (or one normal + two private windows): register a hotel, register an NGO, log in as admin at `/manage/` and verify both, then walk through a pickup.

## Where to read next

* `docs/handover-code.md` — the code feature in depth (goals, data model, flow)
* `docs/er-diagram.md` and `docs/flow-diagram.md` — database and flow diagrams
* `docs/viva-qa.md` — likely examiner questions with answers
* `docs/REPORT-UPDATE.md` — exact text to paste into the report so it matches the software
