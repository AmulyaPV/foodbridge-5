"""End-to-end walkthrough through the real URLs: registration -> admin verification ->
listing -> request -> approval -> on-the-way -> handover code -> certificate/reports.

Every page a user can reach is rendered at least once, so template or URL-name mistakes
show up here instead of in front of an evaluator.
"""
import re

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, Verification
from core.models import FoodListing, PickupRequest, RequestStatus
from core.testing import PASSWORD, create_admin


def _local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


class FullFlowTests(TestCase):
    def ok(self, response, expected=200):
        self.assertEqual(response.status_code, expected, getattr(response, "url", ""))
        return response

    def test_public_pages_render(self):
        client = Client()
        for name in ["core:landing", "accounts:login", "accounts:register_hotel", "accounts:register_ngo"]:
            self.ok(client.get(reverse(name)))
        # Protected pages send anonymous users to login
        for name in ["core:hotel_dashboard", "core:ngo_dashboard", "console:dashboard", "core:notifications"]:
            response = client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)

    def test_error_pages_render(self):
        client = Client(raise_request_exception=False)
        self.ok(client.get("/this-page-does-not-exist/"), 404)

    def test_complete_donation_journey(self):
        admin = create_admin()

        # ---- Registration (hotel + NGO)
        hotel_client, ngo_client, admin_client = Client(), Client(), Client()
        response = hotel_client.post(
            reverse("accounts:register_hotel"),
            {
                "email": "grandhotel@example.com", "password1": PASSWORD, "password2": PASSWORD,
                "name": "Grand Hotel", "contact_person": "Asha Rao", "phone": "9876543210",
                "address": "12 MG Road, Bengaluru", "latitude": "12.9716", "longitude": "77.5946",
                "fssai_number": "11223344556677",
            },
        )
        self.assertRedirects(response, reverse("accounts:status"))
        response = ngo_client.post(
            reverse("accounts:register_ngo"),
            {
                "email": "helpers@example.org", "password1": PASSWORD, "password2": PASSWORD,
                "name": "Helpers Trust", "contact_person": "Ravi Kumar", "phone": "9123456780",
                "address": "4 Church Street, Bengaluru", "latitude": "12.9352", "longitude": "77.6245",
                "registration_number": "NGO/00001/2020", "daily_capacity": "100", "service_area": "Central Bengaluru",
            },
        )
        self.assertRedirects(response, reverse("accounts:status"))
        self.ok(hotel_client.get(reverse("accounts:status")))

        # Unverified accounts cannot reach dashboards
        self.assertRedirects(hotel_client.get(reverse("core:hotel_dashboard")), reverse("accounts:status"))

        # ---- Admin verifies both
        self.assertTrue(admin_client.login(username=admin.username, password=PASSWORD))
        self.ok(admin_client.get(reverse("console:dashboard")))
        self.ok(admin_client.get(reverse("console:verification_queue")))
        for email in ["grandhotel@example.com", "helpers@example.org"]:
            user = User.objects.get(email=email)
            self.ok(admin_client.get(reverse("console:verification_decide", args=[user.pk])))
            self.assertRedirects(
                admin_client.post(reverse("console:verification_decide", args=[user.pk]), {"decision": "approve"}),
                reverse("console:verification_queue"),
            )
            user.refresh_from_db()
            self.assertEqual(user.verification_status, Verification.APPROVED)
        for name in ["console:user_list", "console:reports", "console:reports_csv", "console:activity_log", "console:locked_pickups"]:
            self.ok(admin_client.get(reverse(name)))

        # ---- Hotel posts a listing
        self.assertRedirects(hotel_client.get(reverse("accounts:home")), reverse("core:hotel_dashboard"), fetch_redirect_response=False)
        self.ok(hotel_client.get(reverse("core:hotel_dashboard")))
        self.ok(hotel_client.get(reverse("core:listing_create")))
        now = timezone.now()
        response = hotel_client.post(
            reverse("core:listing_create"),
            {
                "total_servings": "40",
                "pickup_window_start": _local(now + timezone.timedelta(minutes=5)),
                "pickup_window_end": _local(now + timezone.timedelta(hours=2)),
                "safe_until": _local(now + timezone.timedelta(hours=4)),
                "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000",
                "items-0-name": "Veg biryani", "items-0-category": "veg", "items-0-quantity": "40",
                "items-0-unit": "servings", "items-0-cooking_time_note": "Cooked 6 PM", "items-0-allergens_note": "",
            },
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        listing = FoodListing.objects.get()
        self.ok(hotel_client.get(reverse("core:listing_detail", args=[listing.pk])))
        self.ok(hotel_client.get(reverse("core:listing_edit", args=[listing.pk])))
        self.ok(hotel_client.get(reverse("core:listing_repost", args=[listing.pk])))
        self.ok(hotel_client.get(reverse("core:listing_cancel", args=[listing.pk])))

        # ---- NGO browses, posts a need, requests food
        self.ok(ngo_client.get(reverse("core:ngo_dashboard")))
        self.ok(ngo_client.get(reverse("core:ngo_dashboard") + "?category=veg&max_distance=50&min_safe_minutes=30"))
        self.ok(ngo_client.get(reverse("core:needs_board")))
        response = ngo_client.post(
            reverse("core:needs_board"),
            {"servings_needed": "60", "needed_by": _local(now + timezone.timedelta(hours=6)), "notes": "Dinner for 60"},
        )
        self.assertRedirects(response, reverse("core:needs_board"))
        self.ok(hotel_client.get(reverse("core:needs_board")))

        # Smart Match may give the first look to this NGO or open to all; the NGO is the only candidate here.
        listing.refresh_from_db()
        detail = self.ok(ngo_client.get(reverse("core:listing_detail", args=[listing.pk]), follow=True))
        ngo_client.post(reverse("core:request_create", args=[listing.pk]), {"amount": "25"})
        pickup = PickupRequest.objects.get()
        self.assertEqual(pickup.status, RequestStatus.REQUESTED)
        self.ok(ngo_client.get(reverse("core:my_requests")))

        # ---- Hotel approves; NGO sees the code (hotel must not)
        self.ok(hotel_client.get(reverse("core:hotel_requests")))
        hotel_client.post(reverse("core:request_confirm", args=[pickup.pk]))
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.CONFIRMED)
        listing.refresh_from_db()
        self.assertEqual(listing.servings_available, 15)
        from core.handover_service import derive_code

        code = derive_code(pickup.pk, pickup.handover.salt)
        ngo_page = self.ok(ngo_client.get(reverse("core:my_requests"))).content.decode()
        self.assertIn(code, ngo_page)
        hotel_page = self.ok(hotel_client.get(reverse("core:hotel_requests"))).content.decode()
        self.assertNotIn(code, hotel_page)
        self.assertNotIn(code, self.ok(hotel_client.get(reverse("core:confirm_handover", args=[pickup.pk]))).content.decode())

        # ---- On the way, wrong code, then correct code
        ngo_client.post(reverse("core:mark_on_the_way", args=[pickup.pk]), {"eta_minutes": "15"})
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.ON_THE_WAY)
        self.ok(hotel_client.get(reverse("core:confirm_handover", args=[pickup.pk])))
        hotel_client.post(reverse("core:confirm_handover", args=[pickup.pk]), {"code": "000000"})
        pickup.refresh_from_db()
        self.assertEqual(pickup.handover.failed_attempts, 1)
        hotel_client.post(reverse("core:confirm_handover", args=[pickup.pk]), {"code": code})
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.COLLECTED)

        # ---- After-the-fact pages
        for name in ["core:hotel_history", "core:impact_certificate", "core:notifications"]:
            self.ok(hotel_client.get(reverse(name)))
        self.ok(ngo_client.get(reverse("core:notifications")))
        self.ok(admin_client.get(reverse("console:reports")))
        csv_body = self.ok(admin_client.get(reverse("console:reports_csv"))).content.decode()
        self.assertIn("Grand Hotel", csv_body)

    def test_pickup_lockout_via_views_notifies_admin_and_admin_can_unlock(self):
        from core.models import MAX_PICKUP_ATTEMPTS
        from core.testing import create_hotel, create_ngo
        from core.listings_service import create_listing
        from core.requests_service import confirm_request, create_request

        admin = create_admin("boss@example.com")
        hotel, ngo = create_hotel(), create_ngo()
        now = timezone.now()
        listing = create_listing(
            hotel=hotel.profile, total_servings=10,
            pickup_window_start=now + timezone.timedelta(minutes=5),
            pickup_window_end=now + timezone.timedelta(hours=1),
            safe_until=now + timezone.timedelta(hours=3),
            items_data=[{"name": "Dal", "category": "veg", "quantity": 10, "unit": "servings"}], photo_files=[],
        )
        pickup = create_request(listing, ngo.profile, 4)
        confirm_request(pickup.pk, hotel)
        pickup.refresh_from_db()

        client = Client()
        client.login(username=hotel.username, password=PASSWORD)
        from core.handover_service import derive_code

        old_salt = pickup.handover.salt
        real = derive_code(pickup.pk, old_salt)
        wrong = "999999" if real != "999999" else "888888"
        for _ in range(MAX_PICKUP_ATTEMPTS):
            client.post(reverse("core:confirm_handover", args=[pickup.pk]), {"code": wrong})
        pickup.refresh_from_db()
        self.assertEqual(pickup.handover.status, "locked")
        self.assertTrue(admin.notifications.filter(kind="lockout").exists())

        admin_client = Client()
        admin_client.login(username=admin.username, password=PASSWORD)
        page = self.ok(admin_client.get(reverse("console:locked_pickups"))).content.decode()
        self.assertIn(f"#{pickup.pk}", page)
        admin_client.post(reverse("console:unlock_pickup", args=[pickup.pk]))
        pickup.refresh_from_db()
        self.assertEqual(pickup.handover.status, "active")
        self.assertEqual(pickup.handover.failed_attempts, 0)
        self.assertNotEqual(pickup.handover.salt, old_salt)  # unlocking issues a brand-new code
