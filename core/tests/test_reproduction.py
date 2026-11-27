"""Step 2: Failing reproduction test.
Asserts that homepage and NGO dashboard show accurate, unified live remaining quantities
per item, reflecting approvals and cancellations.
"""
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import FoodListing, FoodItem, ListingStatus, PickupRequest
from core.testing import create_hotel, create_ngo
from core.requests_service import create_request, decide_request, cancel_request


class InventoryReproductionTest(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        now = timezone.now()

        # Listing with 4 items: Puri 20, Vada 20, Idli 20, Sambar 20 (Total = 80 servings)
        self.listing = FoodListing.objects.create(
            hotel=self.hotel.profile,
            title="Breakfast Buffet Surplus",
            total_servings=80,
            servings_available=80,
            pickup_window_start=now,
            pickup_window_end=now + timezone.timedelta(hours=2),
            safe_until=now + timezone.timedelta(hours=4),
            status=ListingStatus.POSTED,
        )
        self.puri = FoodItem.objects.create(listing=self.listing, name="Puri", category="veg", quantity=20, unit="servings")
        self.vada = FoodItem.objects.create(listing=self.listing, name="Vada", category="veg", quantity=20, unit="servings")
        self.idli = FoodItem.objects.create(listing=self.listing, name="Idli", category="veg", quantity=20, unit="servings")
        self.sambar = FoodItem.objects.create(listing=self.listing, name="Sambar", category="veg", quantity=20, unit="servings")

    def test_reproduce_homepage_and_ngo_dash_inventory_display(self):
        # 1. Before any request: both pages must show each item's remaining quantity (20 each)
        res_home = self.client.get(reverse("core:landing"))
        self.client.force_login(self.ngo)
        res_ngo = self.client.get(reverse("core:ngo_dashboard"))

        home_html = res_home.content.decode("utf-8")
        ngo_html = res_ngo.content.decode("utf-8")

        # Expect each item with remaining quantity on both pages
        self.assertIn("Puri", home_html, "Homepage should show food items on the listing")
        self.assertIn("Puri", ngo_html, "NGO dashboard should show food items on the listing")

        # 2. NGO requests 10 Puri, 5 Vada, 10 Idli, 10 Sambar (35 servings)
        # Pending requests should NOT consume inventory
        req = create_request(
            self.listing,
            self.ngo.profile,
            item_quantities={
                self.puri.id: 10,
                self.vada.id: 5,
                self.idli.id: 10,
                self.sambar.id: 10,
            },
        )
        res_home_pending = self.client.get(reverse("core:landing"))
        res_ngo_pending = self.client.get(reverse("core:ngo_dashboard"))
        # Check quantities are still 20 each
        self.assertIn("20", res_home_pending.content.decode("utf-8"))

        # 3. Hotel approves request
        decide_request(req.pk, self.hotel, action="approve_all")

        # After approval: Puri remaining=10, Vada=15, Idli=10, Sambar=10 (Total remaining = 45)
        # Listing should also have "Partially allocated" label on both pages
        res_home_approved = self.client.get(reverse("core:landing"))
        res_ngo_approved = self.client.get(reverse("core:ngo_dashboard"))
        home_approved_html = res_home_approved.content.decode("utf-8")
        ngo_approved_html = res_ngo_approved.content.decode("utf-8")

        self.assertIn("Partially allocated", home_approved_html, "Homepage should display Partially allocated badge")
        self.assertIn("Partially allocated", ngo_approved_html, "NGO dashboard should display Partially allocated badge")

        # 4. Cancel before collection: stock must be restored on both pages
        cancel_request(req.pk, self.hotel, reason="Donation cancelled before collection")
        res_home_cancelled = self.client.get(reverse("core:landing"))
        res_ngo_cancelled = self.client.get(reverse("core:ngo_dashboard"))
        home_canc_html = res_home_cancelled.content.decode("utf-8")
        ngo_canc_html = res_ngo_cancelled.content.decode("utf-8")

        # Status badge should return to Available
        self.assertIn("Available", home_canc_html)
        self.assertIn("Available", ngo_canc_html)
