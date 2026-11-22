# FoodBridge — 20-Question Viva Q&A

**1. Why a custom `User` model with a `role` field instead of three separate
Django auth models?**
A single login table keeps authentication, password reset, and admin tooling
uniform across all three user types, while `role` (TextChoices: hotel / ngo /
admin) decides what the person can do. `HotelProfile` and `NGOProfile` are
then one-to-one extensions holding only the fields that role needs. This
avoids duplicating Django's auth machinery three times and lets a single
`@role_required` decorator gate every view.

**2. How does the verification gate actually stop an unverified hotel from
posting?**
`accounts/decorators.py` defines `role_required(*roles, verified=True)`,
composed with `hotel_required`/`ngo_required`/`admin_required`. Every
hotel/NGO view is wrapped in one of these; if `user.is_verified` is `False`
(and the role isn't admin, which is auto-verified), the decorator redirects
to `/status/` instead of running the view. This is enforced server-side on
every request, not just hidden in the UI.

**3. Walk through what happens, step by step, when an NGO requests servings.**
`core/requests_service.create_request()` first calls
`listing.mark_expired_if_needed()` (self-healing check), then validates in
order: listing still POSTED, not past safe_until, amount ≤
`servings_available`, amount ≤ NGO's `daily_capacity`, no existing active
request from this NGO on this listing (enforced twice — in code and by a
partial unique DB constraint), and finally `safe_until_check()` — the
Safe-Until Clock. Only if every check passes does it create the
`PickupRequest` row and notify the hotel.

**4. How do you prevent two NGOs from both being confirmed for more servings
than exist (the over-claiming race condition)?**
`confirm_request()` is wrapped in `@transaction.atomic` and opens both the
`PickupRequest` and `FoodListing` rows with `select_for_update()`. That takes
a row lock in the database: a second, concurrent confirmation attempt on the same
listing blocks until the first transaction commits, then re-reads the now
up-to-date `servings_available` and is correctly rejected if there isn't
enough left. SQLite is configured with `transaction_mode: IMMEDIATE` so it
takes its write lock at the start of the transaction rather than lazily,
which matters for this exact scenario on SQLite specifically.

**5. Explain the pickup (handover) code lifecycle in detail.**
When a hotel confirms a request, `issue_code()` (in `core/handover_service.py`)
creates a `HandoverCode` row holding a random 128-bit salt from `secrets` and an
expiry equal to the listing's safe-until time. The 6 digits are *derived* from
(SECRET_KEY, pickup id, salt) with HMAC-SHA256, so they are never stored — a
database dump or the admin panel can't leak them. Only the confirmed recipient sees the
code (on My requests). At handover the hotel types it on the confirm page; the
check is a constant-time `hmac.compare_digest` on bytes. A correct code marks
the pickup collected and the code used (single use). A wrong code adds to
`failed_attempts`; the fifth locks the pickup, alerts every admin, and only an
admin can unlock it — which also issues a brand-new code. Every try is written
to `HandoverAttempt` (who, when, IP, outcome — never the typed digits).

**5a. Why derive the code instead of just storing a random number?**
Storing it would put a secret in plain text in the database, backups and the
admin screen. Deriving it from a random salt keeps it random per pickup but means
the database alone isn't enough to learn a code. Trade-off (be upfront about it):
anyone who has both the database *and* the SECRET_KEY could recompute codes, and
changing SECRET_KEY invalidates codes in flight.

**5b. A code can be regenerated — doesn't that let someone guess forever?**
No. Regenerating swaps the salt (old code dies at once) but the wrong-guess
counter is deliberately *not* reset, and it is capped at 2 regenerations. Total
guesses per pickup stay at 5. Only an admin unlock resets the counter.

**5c. Why does the code expire?**
It expires at the listing's safe-until time. Past that moment the food shouldn't
be handed over at all, so a still-working code would be a safety bug.

**6. Why `secrets.compare_digest` instead of a plain string comparison?**
A plain `==` comparison on strings in CPython short-circuits at the first
mismatched character, so the time it takes can (in principle) leak how many
leading characters were correct — a timing side-channel. `compare_digest`
always takes the same amount of time regardless of where the strings diverge,
which is the standard defense recommended for exactly this kind of secret
comparison.

**7. How does the Safe-Until Clock estimate travel time without a Google Maps
key?**
`core/geo.py`'s `estimate_travel_minutes()` tries the Google Distance Matrix
API first if `GOOGLE_MAPS_API_KEY` is set and the call succeeds; otherwise
(or if the call fails for any reason — network, quota, bad key) it falls back
to `haversine_km()`, a standard great-circle distance formula, divided by an
assumed average city speed (22 km/h) with a 5-minute prep buffer added. This
is explicitly an estimate and is presented as such in the UI, never implied
to be exact.

**8. What exactly does Smart Match rank NGOs on, and why those factors?**
`core/matching._score()` combines three signals: distance (closer is
better, via `1/(1+distance_km)`), capacity fit (`min(capacity,
total_servings)/max(...)`, so an NGO whose daily capacity closely matches the
listing size scores higher than one wildly over- or under-sized for it), and
reliability (collected vs. missed pickups, defaulting to a neutral 0.8 for
NGOs with no history). These are weighted 50/20/30. The top 5 get a
10-minute exclusive "first look" (`ListingMatch` rows + notification) before
the listing becomes visible to every verified NGO — this is meant to reduce
the scramble/duplicate-claim problem that a pure first-come system has.

**9. How is "first look" visibility actually enforced, not just a UI hint?**
`FoodListing.visible_to(ngo_profile)` is called server-side in both the
dashboard query (`core/views.ngo_dashboard`) and the detail view
(`listing_detail`). During the first 10 minutes after posting
(`first_look_active`), it only returns `True` if a `ListingMatch` row exists
for that NGO; an NGO that wasn't matched gets redirected away from the detail
page even if they guess the URL directly.

**10. What happens to reserved servings if a confirmed request is later
cancelled?**
`cancel_request()` checks whether the request had already been confirmed
(`was_approved` / status in CONFIRMED/ON_THE_WAY). If so, it adds the amount
back onto `listing.servings_available` inside the same atomic transaction,
and flips the listing's status back from FULFILLED to POSTED if it had been
fully claimed. `was_approved` itself is never unset, so the NGO's
reliability score (which only counts requests that were *ever* approved)
still correctly records this as a miss.

**11. How is an NGO's reliability score calculated, and why start new NGOs at
0.8 instead of 0 or 1?**
`core/reliability.py`: collected ÷ (collected + missed) among requests that
were ever confirmed. A brand-new NGO with zero history gets a neutral 0.8
rather than 0 (which would unfairly bury every new NGO at the bottom of
Smart Match forever) or 1 (which would let a new, unproven NGO outrank a
long-track-record NGO with one or two early misses).

**12. Why does a listing auto-expire "on read" as well as via a management
command?**
`FoodListing.mark_expired_if_needed()` is called whenever a listing is
touched (loaded in the hotel dashboard, viewed on the NGO side, or acted on
in `create_request`), so the system never shows or acts on stale data even if
the periodic `expire_listings` command hasn't run recently. The management
command is still useful for keeping the admin dashboard and open requests
tidy even when nobody happens to be browsing a particular listing.

**13. Where is file upload validated, and what's checked?**
`core/validators.py` — `validate_photo_file` / `validate_certificate_file`
check the file extension against an allow-list (jpg/jpeg/png/webp for
photos; those plus pdf for NGO certificates) and enforce `MAX_UPLOAD_MB`
(default 5MB, configurable via `.env`). For a certificate claiming to be a
PDF, it also peeks at the first 5 bytes for the `%PDF-` magic number, so a
renamed non-PDF file is rejected rather than silently stored. These run as
Django model-field validators, so they fire on every save path, not just one
form.

**14. Why is the NGO's request an "amount of servings" rather than a choice
of specific food items?**
This mirrors how surplus-food donation realistically works operationally —
a hotel doesn't want to field per-item negotiation under time pressure, and
servings are the unit that determines whether the hotel's capacity and the
NGO's capacity actually match. `PickupRequestForm` only exposes `amount`;
there's no UI or endpoint to request specific `FoodItem` rows at all.

**15. How would you swap SQLite for MySQL or PostgreSQL?**
Set `DB_ENGINE=mysql` (or `postgresql`) in `.env` along with
`DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT`; `foodbridge/settings.py`
branches on `DB_ENGINE` to build the right `DATABASES` dict. The matching
driver (`mysqlclient` or `psycopg[binary]`) is commented out in
`requirements.txt` ready to be installed. No other code changes are needed —
all three backends support everything the models use (indexes, a partial
`UniqueConstraint`, `select_for_update`).

**16. What stops the site from being unusable if `GOOGLE_MAPS_API_KEY` is
missing?**
Every Maps-dependent piece checks `MAPS_ENABLED` (a context processor value
derived from the settings key) and degrades gracefully: registration shows a
friendly note instead of the pin-picker map and still works from the typed
address alone; the NGO browse page shows a note instead of the side map but
the list, distances, and filters all still work; and `estimate_travel_minutes`
silently falls back to the haversine estimate. Nothing throws an error or
shows a broken embed.

**17. How does FoodBridge keep the whole site working fully offline, as
required?**
Bootstrap and its JS bundle are vendored locally under
`static/vendor/bootstrap/` via the optional `fetch_vendor` management command
(a one-time, one-internet-use step); `base.html` checks whether that local
copy exists and only falls back to a CDN `<link>`/`<script>` if it doesn't.
No other third-party JS libraries are used — all interactivity (the live
Safe-Until countdown, the maps pin picker) is vanilla JS.

**18. What's the purpose of `ActivityLog`, and what's an example entry?**
It's a flat, append-only audit trail of key actions — registrations,
listing posts/cancels, request confirmations/rejections/cancellations, pickup
collections, lockouts, and verification decisions — each tied to an actor
and optionally a target object. It's surfaced on the Admin dashboard
("Recent activity") and the dedicated Activity Log page, so an evaluator (or
a real admin) can see exactly what happened and when without digging through
raw database rows.

**19. Why is the CO2 figure on the Impact Certificate "just an estimate,"
and how is that made clear to the user?**
There's no universally agreed, verified per-serving CO2 figure for avoided
food waste — it depends heavily on food type, what would otherwise have
happened to it (landfill vs. incineration vs. compost), and local
infrastructure. Rather than present a misleadingly precise number, the
certificate shows the exact formula used (`total_servings × 2.5 kg CO2e`)
directly in the text, labelled as an estimate, so nobody could mistake it for
an audited figure.

**20. What would you point to as the biggest known limitation of this build,
and how would you address it with more time?**
The haversine/average-speed travel estimate (used whenever no Maps key is
configured, or whenever the Distance Matrix call fails) doesn't account for
real traffic, road networks, or one-way systems — it can under- or
over-estimate a genuinely short or long trip. With more time, a cached
Distance Matrix call per NGO-hotel pair (refreshed periodically rather than
per-request) would give a more accurate Safe-Until Clock without the per-page
latency or quota cost of calling it on every single page load.


## Questions about the report-alignment changes

**Q. The report's ER diagram has an Individual Recipient. Does the project?**
Yes. `IndividualProfile` is a fourth profile type next to hotel, NGO and admin. An individual registers, is verified by an admin like everyone else, may ask for at most 10 servings at a time, and never gets the NGO-only 10-minute first look. `PickupRequest` has two nullable foreign keys, `ngo` and `individual`, and a database check constraint guarantees exactly one of them is set.

**Q. How does an admin handle inappropriate listings?**
Any verified user can report a listing (`ListingReport`). Admins see an open-reports queue at `/manage/moderation/`, and can either dismiss the report or remove the listing. Removing sets the listing to `removed`, cancels every open request on it, and notifies the hotel (with the reason) and every affected recipient. Admins can also remove any listing directly from `/manage/listings/`.

**Q. Where do the report's status words (available, requested, confirmed, collected, expired) come from?**
`FoodListing.display_status` derives them from the listing and its requests, so there is one vocabulary on every page. The request status itself is stored as `confirmed` (not `approved`).

**Q. Which filters does an NGO have?**
Location or hotel name (text), distance, category, minimum servings, "pickup closes within N hours", and minimum safe time left, plus three sort orders.
