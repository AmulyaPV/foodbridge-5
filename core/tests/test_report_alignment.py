"""Tests for everything the project report promises that the first build lacked:
individual recipients, quantity / deadline / location filters, storage notes, the report's
status words, reporting and removing listings, and history by outcome."""
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Verification
from core.exceptions import FoodBridgeError
from core.handover_service import derive_code
from core.listings_service import cancel_listing, create_listing
from core.models import FoodListing, ListingReport, ListingStatus, Notification, PickupRequest, ReportStatus, RequestStatus
from core.moderation_service import dismiss_report, remove_reported_listing, report_listing
from core.requests_service import cancel_request, confirm_handover, confirm_request, create_request
from core.testing import create_admin, create_hotel, create_individual, create_ngo


def _local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def _listing(hotel, total=20, safe_minutes=180, window_minutes=90, **extra):
    now = timezone.now()
    return create_listing(
        hotel=hotel.profile,
        total_servings=total,
        pickup_window_start=now + timezone.timedelta(minutes=5),
        pickup_window_end=now + timezone.timedelta(minutes=window_minutes),
        safe_until=now + timezone.timedelta(minutes=safe_minutes),
        items_data=[{"name": "Rice", "category": "veg", "quantity": total, "unit": "servings"}],
        photo_files=[],
        **extra,
    )


def _open_to_everyone(listing):
    """End the 10-minute first look so every recipient can see the listing."""
    FoodListing.objects.filter(pk=listing.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=30))
    listing.refresh_from_db()


def _client(user):
    client = Client()
    client.force_login(user)
    return client


class IndividualRecipientTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.person = create_individual(approved=True, lat=12.9720, lng=77.5950)
        self.listing = _listing(self.hotel)

    def test_individual_can_register_and_waits_for_verification(self):
        client = Client()
        response = client.post(
            reverse("accounts:register_individual"),
            {
                "email": "meena@example.com", "password1": "Str0ng-Passw0rd!", "password2": "Str0ng-Passw0rd!",
                "name": "Meena Devi", "phone": "9012345678", "address": "5 Lake Road", "household_size": "4",
                "latitude": "", "longitude": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:status"))
        from accounts.models import User

        user = User.objects.get(email="meena@example.com")
        self.assertTrue(user.is_individual and user.is_recipient)
        self.assertEqual(user.verification_status, Verification.PENDING)
        self.assertEqual(user.profile.household_size, 4)

    def test_individual_does_not_get_the_ngo_first_look(self):
        self.assertTrue(self.listing.first_look_active)
        self.assertFalse(self.listing.visible_to(self.person.profile))
        page = _client(self.person).get(reverse("core:ngo_dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.context["listings"]), 0)
        _open_to_everyone(self.listing)
        page = _client(self.person).get(reverse("core:ngo_dashboard"))
        self.assertEqual(len(page.context["listings"]), 1)

    def test_individual_is_capped_at_ten_servings(self):
        _open_to_everyone(self.listing)
        with self.assertRaises(FoodBridgeError):
            create_request(self.listing, self.person.profile, 11)
        pickup = create_request(self.listing, self.person.profile, 10)
        self.assertEqual(pickup.individual, self.person.profile)
        self.assertIsNone(pickup.ngo)
        self.assertEqual(pickup.recipient_kind, "Individual")

    def test_full_journey_for_an_individual(self):
        _open_to_everyone(self.listing)
        pickup = create_request(self.listing, self.person.profile, 4)
        confirm_request(pickup.pk, self.hotel)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.CONFIRMED)
        page = _client(self.person).get(reverse("core:my_requests")).content.decode()
        code = derive_code(pickup.pk, pickup.handover.salt)
        self.assertIn(code, page)
        self.assertNotIn(code, _client(self.hotel).get(reverse("core:hotel_requests")).content.decode())
        confirm_handover(pickup.pk, code, self.hotel)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.COLLECTED)
        self.assertTrue(Notification.objects.filter(user=self.person, kind="collected").exists())

    def test_individual_cannot_open_hotel_or_admin_pages(self):
        client = _client(self.person)
        self.assertEqual(client.get(reverse("core:hotel_dashboard")).status_code, 403)
        self.assertEqual(client.get(reverse("console:dashboard")).status_code, 403)
        self.assertEqual(client.get(reverse("core:needs_board")).status_code, 403)

    def test_unverified_individual_is_sent_to_status_page(self):
        pending = create_individual(approved=False)
        response = _client(pending).get(reverse("core:ngo_dashboard"))
        self.assertRedirects(response, reverse("accounts:status"))


class ReportVocabularyTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)

    def test_status_words_follow_the_report(self):
        listing = _listing(self.hotel, total=10)
        self.assertEqual(listing.display_status[0], "available")
        pickup = create_request(listing, self.ngo.profile, 4)
        listing = FoodListing.objects.get(pk=listing.pk)
        self.assertEqual(listing.display_status[0], "requested")
        confirm_request(pickup.pk, self.hotel)
        listing = FoodListing.objects.get(pk=listing.pk)
        self.assertEqual(listing.display_status[0], "confirmed")
        code = derive_code(pickup.pk, pickup.handover.salt)
        confirm_handover(pickup.pk, code, self.hotel)
        full = _listing(self.hotel, total=5)
        p2 = create_request(full, self.ngo.profile, 5)
        confirm_request(p2.pk, self.hotel)
        confirm_handover(p2.pk, derive_code(p2.pk, p2.handover.salt), self.hotel)
        self.assertEqual(FoodListing.objects.get(pk=full.pk).display_status[0], "collected")

    def test_expired_status(self):
        listing = _listing(self.hotel)
        FoodListing.objects.filter(pk=listing.pk).update(safe_until=timezone.now() - timezone.timedelta(minutes=1))
        self.assertEqual(FoodListing.objects.get(pk=listing.pk).display_status[0], "expired")

    def test_request_status_is_called_confirmed_not_approved(self):
        self.assertEqual(RequestStatus.CONFIRMED.value, "confirmed")
        self.assertNotIn("approved", RequestStatus.values)

    def test_listing_has_food_name_pickup_location_and_storage_notes(self):
        listing = _listing(
            self.hotel, title="Veg biryani", pickup_location="Back gate, 12 MG Road", storage_notes="Kept hot above 60 C"
        )
        self.assertEqual(listing.display_title, "Veg biryani")
        self.assertEqual(listing.location_text, "Back gate, 12 MG Road")
        plain = _listing(self.hotel)
        self.assertEqual(plain.location_text, self.hotel.profile.address)  # falls back to the hotel address
        self.assertEqual(plain.contact_number, self.hotel.profile.phone)
        self.assertEqual(plain.display_title, "Rice")  # falls back to the item names
        page = _client(self.hotel).get(reverse("core:listing_detail", args=[listing.pk])).content.decode()
        self.assertIn("Kept hot above 60 C", page)
        self.assertIn("Back gate, 12 MG Road", page)

    def test_hotel_can_edit_storage_notes_and_location(self):
        listing = _listing(self.hotel)
        now = timezone.now()
        response = _client(self.hotel).post(
            reverse("core:listing_edit", args=[listing.pk]),
            {
                "title": "Dal and rice", "pickup_location": "Kitchen door", "contact_phone": "9876543210",
                "storage_notes": "Chilled below 5 C", "pickup_window_start": _local(now + timezone.timedelta(minutes=10)),
                "pickup_window_end": _local(now + timezone.timedelta(hours=2)), "safe_until": _local(now + timezone.timedelta(hours=3)),
            },
        )
        self.assertEqual(response.status_code, 302)
        listing.refresh_from_db()
        self.assertEqual((listing.title, listing.storage_notes, listing.pickup_location), ("Dal and rice", "Chilled below 5 C", "Kitchen door"))

    def test_edit_rejects_a_deadline_before_pickup_opens(self):
        listing = _listing(self.hotel)
        now = timezone.now()
        response = _client(self.hotel).post(
            reverse("core:listing_edit", args=[listing.pk]),
            {
                "title": "", "pickup_location": "", "contact_phone": "", "storage_notes": "",
                "pickup_window_start": _local(now + timezone.timedelta(hours=2)),
                "pickup_window_end": _local(now + timezone.timedelta(hours=1)),
                "safe_until": _local(now + timezone.timedelta(hours=3)),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("pickup_window_end", response.context["form"].errors)


class BrowseFilterTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True, name="Mayura Hotel")
        self.other = create_hotel(approved=True, name="Sagar Restaurant")
        self.ngo = create_ngo(approved=True)
        self.small = _listing(self.hotel, total=6, window_minutes=45, title="Idli")
        self.big = _listing(self.other, total=80, window_minutes=400, title="Biryani", safe_minutes=500)
        for listing in (self.small, self.big):
            _open_to_everyone(listing)
        self.client = _client(self.ngo)

    def _titles(self, query=""):
        page = self.client.get(reverse("core:ngo_dashboard") + query)
        return {l.display_title for l in page.context["listings"]}

    def test_quantity_filter(self):
        self.assertEqual(self._titles("?min_servings=50"), {"Biryani"})
        self.assertEqual(self._titles("?min_servings=1"), {"Idli", "Biryani"})

    def test_pickup_deadline_filter(self):
        self.assertEqual(self._titles("?pickup_within=1"), {"Idli"})
        self.assertEqual(self._titles("?pickup_within=8"), {"Idli", "Biryani"})

    def test_location_or_name_search(self):
        self.assertEqual(self._titles("?q=sagar"), {"Biryani"})
        self.assertEqual(self._titles("?q=mg road"), {"Idli", "Biryani"})  # hotel address in test data

    def test_sorting_and_bad_input_do_not_crash(self):
        self.assertEqual(self.client.get(reverse("core:ngo_dashboard") + "?sort=servings&min_servings=abc&max_distance=x").status_code, 200)


class ReportAndRemoveTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        self.listing = _listing(self.hotel, total=10)

    def test_report_then_admin_removes_listing(self):
        pickup = create_request(self.listing, self.ngo.profile, 3)
        confirm_request(pickup.pk, self.hotel)
        report = report_listing(self.listing, self.ngo, "unsafe", "Smelled off")
        self.assertEqual(report.status, ReportStatus.OPEN)
        self.assertTrue(Notification.objects.filter(user=self.admin, kind="report").exists())

        remove_reported_listing(report, self.admin, "Failed a safety check")
        self.listing.refresh_from_db()
        report.refresh_from_db()
        pickup.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.REMOVED)
        self.assertEqual(report.status, ReportStatus.ACTIONED)
        self.assertEqual(pickup.status, RequestStatus.CANCELLED)
        self.assertFalse(self.listing.is_live)
        self.assertTrue(Notification.objects.filter(user=self.hotel, kind="listing_removed").exists())
        self.assertTrue(Notification.objects.filter(user=self.ngo, kind="listing_removed").exists())
        self.assertEqual(self.listing.display_status[0], "removed")

    def test_dismiss_keeps_listing_live(self):
        report = report_listing(self.listing, self.ngo, "other", "")
        dismiss_report(report, self.admin, "Looks fine")
        self.listing.refresh_from_db()
        self.assertTrue(self.listing.is_live)
        with self.assertRaises(FoodBridgeError):
            dismiss_report(report, self.admin)

    def test_report_rules(self):
        with self.assertRaises(FoodBridgeError):
            report_listing(self.listing, self.hotel, "other")  # own listing
        report_listing(self.listing, self.ngo, "other")
        with self.assertRaises(FoodBridgeError):
            report_listing(self.listing, self.ngo, "unsafe")  # duplicate open report

    def test_admin_console_remove_flow_through_the_urls(self):
        report_listing(self.listing, self.ngo, "misleading", "Wrong quantity")
        admin = _client(self.admin)
        for name in ("console:listings", "console:moderation", "console:reports", "console:dashboard", "console:user_list"):
            self.assertEqual(admin.get(reverse(name)).status_code, 200, name)
        report = ListingReport.objects.get()
        self.assertEqual(admin.get(reverse("console:moderation_decide", args=[report.pk])).status_code, 200)
        # a reason is required to remove
        response = admin.post(reverse("console:moderation_decide", args=[report.pk]), {"decision": "remove", "note": ""})
        self.assertEqual(response.status_code, 200)
        response = admin.post(reverse("console:moderation_decide", args=[report.pk]), {"decision": "remove", "note": "Wrong quantity"})
        self.assertRedirects(response, reverse("console:moderation"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.REMOVED)

    def test_admin_can_remove_without_a_report(self):
        admin = _client(self.admin)
        self.assertEqual(admin.get(reverse("console:listing_remove", args=[self.listing.pk])).status_code, 200)
        admin.post(reverse("console:listing_remove", args=[self.listing.pk]), {"reason": "Duplicate post"})
        self.listing.refresh_from_db()
        self.assertEqual((self.listing.status, self.listing.removal_reason), (ListingStatus.REMOVED, "Duplicate post"))

    def test_non_admins_cannot_moderate(self):
        for user in (self.hotel, self.ngo):
            client = _client(user)
            self.assertEqual(client.get(reverse("console:moderation")).status_code, 403)
            self.assertEqual(client.post(reverse("console:listing_remove", args=[self.listing.pk]), {"reason": "x"}).status_code, 403)
        self.listing.refresh_from_db()
        self.assertTrue(self.listing.is_live)

    def test_report_form_via_urls(self):
        client = _client(self.ngo)
        self.assertEqual(client.get(reverse("core:listing_report", args=[self.listing.pk])).status_code, 200)
        response = client.post(reverse("core:listing_report", args=[self.listing.pk]), {"reason": "unsafe", "details": "Looks old"})
        self.assertRedirects(response, reverse("core:listing_detail", args=[self.listing.pk]))
        self.assertEqual(ListingReport.objects.count(), 1)

    def test_hotel_closing_a_listing_tells_requesters(self):
        pickup = create_request(self.listing, self.ngo.profile, 3)
        cancel_listing(self.listing, self.hotel, "Ran out of time")
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.CANCELLED)
        self.assertTrue(Notification.objects.filter(user=self.ngo, kind="listing_removed").exists())

    def test_cancelling_a_request_notifies_the_other_side(self):
        pickup = create_request(self.listing, self.ngo.profile, 3)
        cancel_request(pickup.pk, self.ngo, "Van broke down")
        self.assertTrue(Notification.objects.filter(user=self.hotel, kind="cancelled").exists())


class HistoryAndReportsTests(TestCase):
    def setUp(self):
        self.admin = create_admin()
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)

    def test_history_groups_completed_cancelled_expired(self):
        done = _listing(self.hotel, total=5)
        p = create_request(done, self.ngo.profile, 5)
        confirm_request(p.pk, self.hotel)
        confirm_handover(p.pk, derive_code(p.pk, p.handover.salt), self.hotel)
        cancelled = _listing(self.hotel)
        cancel_listing(cancelled, self.hotel, "Changed plan")
        expired = _listing(self.hotel)
        FoodListing.objects.filter(pk=expired.pk).update(status=ListingStatus.EXPIRED)

        client = _client(self.hotel)
        counts = client.get(reverse("core:hotel_history")).context["counts"]
        self.assertEqual((counts["completed"], counts["cancelled"], counts["expired"]), (1, 1, 1))
        rows = client.get(reverse("core:hotel_history") + "?show=completed").context["rows"]
        self.assertEqual(len(rows), 1)

    def test_admin_summary_numbers_come_from_the_data(self):
        from console import reports

        listing = _listing(self.hotel, total=8)
        p = create_request(listing, self.ngo.profile, 8)
        confirm_request(p.pk, self.hotel)
        confirm_handover(p.pk, derive_code(p.pk, p.handover.salt), self.hotel)
        summary = reports.summary()
        self.assertEqual(summary["listings_created"], 1)
        self.assertEqual(summary["donations_collected"], 1)
        self.assertEqual(summary["servings_redistributed"], 8)
        self.assertEqual(reports.monthly_summary()[0]["servings"], 8)
        self.assertEqual(reports.top_recipients()[0]["kind"], "NGO")
        response = _client(self.admin).get(reverse("console:reports_csv"))
        self.assertIn(self.ngo.profile.name, response.content.decode())
