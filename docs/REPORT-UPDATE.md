# Updating the project report so it matches the project

The project now implements every statement in the synopsis (see the table at the end).
It also goes **beyond** the synopsis in several places. Your examiner should not find a
feature in the software that the report never mentions, so paste the replacement text
below into the report. Page numbers refer to the PDF you shared.

Two new figures are in this folder, ready to insert:
`er-diagram.png` (page 10) and `architecture-diagram.png` (page 11). Editable sources: `.dot` and `.svg`.

---

## Page 2, Abstract: one sentence to add at the end of paragraph 3

> Beyond listing and requesting, the system includes a Safe-Until Clock that shows how long food stays safe and blocks requests that cannot arrive in time, a Smart Match step that gives the nearest, most reliable NGOs a short first look, a one-time pickup code that proves a handover, reliability scores, an impact certificate for donors, an NGO needs board, and an administrator activity log.

## Pages 6–7, Scope: replace the paragraph beginning "The project may initially operate..."

> The project may initially operate within a selected city or locality to keep pickup coordination practical. The following features, listed in an earlier plan as possible extensions, are now implemented: **verified NGO profiles** (admin verification of every hotel, NGO and individual before use), **distance filtering with optional Google Maps** (map pins, distance in kilometres and an estimated travel time; the system works without a Maps key using typed addresses), **summary reports and analytics** (listings created, donations collected, servings redistributed, by month and by top donors and recipients, with CSV export) and **collection confirmation using a one-time six-digit handover code** (a code rather than a QR code). In addition the system includes a Safe-Until Clock, Smart Match, a reliability score, an Impact Certificate, a Needs Board and an administrator activity log (described under Modules). Email, SMS and WhatsApp alerts, multilingual screens, a mobile application, QR-based confirmation and integration with external donation networks remain future work and are **not** implemented.

## Page 8–9, Modules: add these items

**1. Hotel / Food Donor Module** (add after the last bullet)
* Post an item list with a food name, category, quantity, cooking time and allergen note for each item, plus storage and handling notes, a pickup address (defaulting to the hotel's address) and a contact number.
* Confirm or decline requests (a confirmed request reserves the servings and creates a one-time pickup code), then enter the code the recipient shows to mark the donation as collected.
* Repost a previous listing in one step, view donation history by outcome (completed, cancelled, expired) and print an Impact Certificate.
* Report a listing that looks wrong.

**2. NGO / Recipient Module** (replace its heading and add)
* *NGO / Individual Recipient Module.* Individuals who need food (not part of an NGO) can register, are verified by the administrator, and can request up to 10 servings at a time.
* Filter available food by location or hotel name, distance, category, minimum servings, how soon the pickup closes and minimum safe time left; sort by nearest, soonest to expire or most servings.
* See a travel-time check before requesting; requests that cannot arrive before the safe-until time are blocked.
* Mark "on my way" with an estimated time, show the pickup code at collection, view active requests and full history.
* NGOs (not individuals) also receive Smart Match first-look alerts and can post needs on the Needs Board.

**3. Administrator Module** (replace the second bullet)
* Review and verify hotel, NGO and individual accounts; suspend or reactivate accounts.
* Review **reports on listings** from users, and **remove** a listing (or dismiss the report). Removing a listing cancels open requests and tells the hotel and the recipients why. Admins can also remove any listing directly from an all-listings page.
* Unlock pickups that were locked after five wrong code entries, and view the activity log.

**4. Notification and Tracking Module** (add)
* Each request moves through the states requested, confirmed, on the way, collected (or declined, cancelled, expired). A listing is shown to users as available, requested, confirmed, collected or expired. A donation record is kept for each request.

## Page 10, ER diagram: replace Fig. 1 with `er-diagram.png`

What changed and why it is correct now:
* **INDIVIDUAL_RECIPIENT** is a real entity (one per user with that role).
* **FOOD_LISTING** has food name, storage notes, pickup location and contact phone as the report says; the food items are a separate **FOOD_ITEM** entity (one listing, many items) so each dish has its own quantity, category and allergens.
* **DONATION_REQUEST** is submitted by *either* an NGO *or* an individual (exactly one; enforced by a database constraint).
* New entities: **HANDOVER_CODE**, **LISTING_REPORT**, **NOTIFICATION**.
* The request status is **confirmed** (the report's word), and the pickup address defaults to the hotel's address unless the hotel enters another.
* The figure caption has a typo ("FoddBridge"); it should read "FoodBridge".

## Page 11, Architecture: replace Fig. 2 with `architecture-diagram.png`

It adds the role-based access layer, the secure handover, Smart Match and reliability, the admin console (verification, reports on listings, activity log) and the notification / needs-board / certificate components.

## Page 12, Working of the system: add after "Typical Donation Workflow"

1. Hotel publishes a surplus-food listing; Smart Match gives the closest, most reliable NGOs a ten-minute first look.
2. A recipient requests servings; the Safe-Until Clock blocks the request if the trip would take longer than the food stays safe.
3. The hotel confirms or declines. Confirming reserves the servings and creates a one-time pickup code visible only to the recipient.
4. The recipient marks "on my way", travels, and shows the code; the hotel enters it, and the donation is marked collected (five wrong entries lock the pickup until an administrator unlocks it).
5. Listings that pass their safe-until time are marked expired automatically; history and reports update from recorded data.

## Page 13, References: nothing to change.

(Optionally cite Django's CheckConstraint documentation if you describe the "exactly one recipient" rule.)

---

## Traceability: every report statement and where it lives in the code

| Report statement | Where it is implemented |
|---|---|
| Hotels, NGOs and *people who need food* | `accounts.IndividualProfile`, `/register/individual/` |
| Listing: category, servings, preparation time, location, deadline, **storage info**, availability | `FoodListing.title / pickup_location / contact_phone / storage_notes`, `FoodItem.cooking_time_note` |
| Status: available, requested, **confirmed**, collected, expired | `FoodListing.display_status`; request value `confirmed` |
| Filter by **location, category, quantity, deadline** | `core.views.ngo_dashboard` (`q`, `category`, `min_servings`, `pickup_within`, plus distance and safe time) |
| Admin verifies accounts | `console` verification queue (hotels, NGOs, individuals) |
| Admin **manages reported or inappropriate content**, supports suspension | `ListingReport`, `/manage/moderation/`, `/manage/listings/`, `core.moderation_service` |
| In-website notifications | `core.notify`, Alerts page |
| History of completed, cancelled and expired donations | `/hotel/history/` (tabs), `/ngo/requests/?view=history` |
| Reports: listings created, donations collected, servings redistributed | `console.reports.summary()`, `/manage/reports/` |
| Hotel edits or closes listings; expired ones leave search | `listing_edit`, `listing_cancel`, `FoodListing.is_live` |
| Reduce duplicate claims when a request is accepted | `requests_service.confirm_request` (row lock) |
