# FoodBridge

FoodBridge connects hotels and restaurants that have surplus food with verified
NGOs and individuals who can collect it — so good food reaches people instead of the bin.

Roles: **Hotel / restaurant**, **NGO**, **Individual recipient**, **Admin**.

**Quick start:** run `./start.sh` (Windows: `start.bat`) and read [PRESENT.md](PRESENT.md). The database ships empty except for one admin account (`admin@foodbridge.com` / `Admin@FoodBridge26`).

## What the project report promises (all implemented)

- Listings carry a food name, category and quantity per item, storage and handling
  notes, a pickup address, a contact number, a collection deadline and a status
  shown as *available, requested, confirmed, collected or expired*.
- NGOs and individuals filter by **location, category, quantity and pickup
  deadline** (plus distance and safe time left).
- Admins verify accounts, review **reported listings**, **remove** listings and
  suspend accounts; reports show listings created, donations collected and
  servings redistributed.
- History of completed, cancelled and expired donations for hotels and recipients.

`docs/REPORT-UPDATE.md` has the exact text to paste into the report for the
features that go *beyond* it (Safe-Until Clock, Smart Match, reliability score,
Impact Certificate, Needs Board, activity log, handover code, Google Maps).

## Signature features

1. **Safe-Until Clock** — every listing shows a live countdown to when the food
   stops being safe. Estimated travel time (Google Distance Matrix if a key is
   set, otherwise a haversine-distance estimate) is compared against the time
   left; a request that can't realistically arrive in time is blocked.
2. **Smart Match** — when a listing is posted, verified NGOs are ranked by
   distance, capacity fit and reliability. The top 5 get a 10-minute "first
   look" before the listing opens to everyone, cutting down duplicate claims.
3. **Live pickup tracker with a Secure Handover Code** — Posted → Requested →
   Confirmed → On the way → Collected, visible to both sides. On confirmation the recipient
   (and only the recipient) gets a 6-digit code to show at handover. The code is derived
   from a random 128-bit salt, so the digits are never stored in the database; it
   works once, expires when the food stops being safe, locks after 5 wrong tries
   (admins are alerted), can be replaced twice if lost, and every attempt is
   logged. Full design: [docs/handover-code.md](docs/handover-code.md).
4. **NGO Needs Board** — NGOs post what they need ("dinner for 60 tonight");
   hotels see it and can prioritise accordingly.
5. **Trust & Impact** — an NGO reliability score (collected vs. missed
   pickups), verified badges, and a printable per-hotel Impact Certificate
   with real totals and a clearly labelled, formula-shown CO2 estimate.

## Tech stack

- Python 3.11+, Django 5.x, SQLite by default (ready to switch to MySQL/PostgreSQL)
- Django templates + Bootstrap 5 + vanilla JS — works fully offline once
  Bootstrap is fetched locally (see below)
- Pillow for photo uploads
- Google Maps JavaScript API + Places, read from `GOOGLE_MAPS_API_KEY` — the
  site works completely with typed addresses if this is left empty
- Custom user model with a `role` field; CSRF protection and server-side
  validation throughout

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # edit if you want a Maps key, etc.

python manage.py migrate           # safe on an existing database: it keeps your data
python manage.py createsuperuser   # only if you delete db.sqlite3 and want a new Admin
python manage.py runserver
```

Open http://127.0.0.1:8000/ — the database starts completely empty. Register
a hotel and an NGO, log in as the admin account you just created at
`/manage/`, and verify them from the verification queue. 

### Working offline (optional but recommended)

Bootstrap and both fonts (Bricolage Grotesque, Hanken Grotesk) are already
bundled in `static/`, so the whole site works with **no internet at all**.
If you delete `static/vendor/`, pages fall back to a CDN, and
`python manage.py fetch_vendor` re-downloads Bootstrap.

### Getting a Google Maps API key (optional)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/), create
   a project (or use an existing one).
2. Enable **Maps JavaScript API**, **Places API**, and **Distance Matrix API**.
3. Create an API key under *APIs & Services → Credentials*, and restrict it to
   those three APIs (and your domain, for production).
4. Put it in `.env` as `GOOGLE_MAPS_API_KEY=...`.

Without a key: registration still works via a typed address, the NGO browse
page shows a note instead of a map, and the Safe-Until Clock falls back to a
haversine-distance travel estimate — nothing breaks.

### Switching the database

Edit `.env`:

```
DB_ENGINE=mysql        # or postgresql
DB_NAME=foodbridge
DB_USER=...
DB_PASSWORD=...
DB_HOST=127.0.0.1
DB_PORT=3306
```

Then uncomment the matching driver in `requirements.txt` (`mysqlclient` or
`psycopg[binary]`), `pip install -r requirements.txt` again, and re-run
`migrate`.

## Running the tests

```bash
python manage.py check
python manage.py test
```

85 tests cover: registration + verification gating, individual recipients,
request validation (servings/capacity/duplicate), servings reduction on confirmation,
the report's filters, status words and storage notes, reporting and removing listings,
history by outcome, summary reports, the handover code
(secrecy, single use, expiry, regeneration, 5-attempt lockout, admin unlock, attempt log), Safe-Until Clock blocking,
Smart Match ranking, per-role permissions, photo upload validation, and a full
end-to-end journey (register -> admin verifies -> post listing -> request ->
confirm -> on the way -> handover code -> certificate/reports) that renders every page.

## Expiring listings in the background

Listings also expire automatically the moment anyone views them past their
`safe_until` time, but for a tidy admin dashboard you can run this
periodically (e.g. via cron or a scheduled task) to mark stale listings and
their open requests as expired even when nobody is browsing:

```bash
python manage.py expire_listings
```

## Project layout

```
foodbridge/        settings, root urls
accounts/          custom User, Hotel/NGO/Individual profiles, auth, registration
core/               listings, requests, pickup codes, matching, needs board,
                     notifications, activity log, geo/travel estimates
console/            admin dashboard, verification, listing reports and removal, reports, activity log
templates/          all HTML, organised to mirror the apps above
static/             CSS, JS, bundled Bootstrap and fonts
docs/               project guide, handover-code design, ER diagram, feature comparison, viva Q&A
```

## Known limitations

- Distance/travel-time without a Google Maps key is a straight-line
  (haversine) estimate with an average city-speed assumption — not live
  traffic.
- The CO2 figure on the Impact Certificate is explicitly labelled an estimate
  with its formula shown; it is not a verified lifecycle figure.
- No email delivery is wired up beyond Django's console backend by default
  (notifications are in-app only; switch `EMAIL_BACKEND` in `.env` for real
  email).
- Google Maps features need your own API key and internet; everything else works
  without them.
