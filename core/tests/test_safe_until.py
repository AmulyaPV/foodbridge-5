"""Safe-Until Clock: blocking requests that can't realistically arrive in time."""
from django.test import TestCase
from django.utils import timezone

from core.exceptions import FoodBridgeError
from core.listings_service import create_listing
from core.requests_service import create_request
from core.testing import create_hotel, create_ngo


class SafeUntilClockTests(TestCase):
    def test_request_blocked_when_food_expires_before_arrival(self):
        # NGO is far away (large lat/lng gap), food is safe for only 2 minutes.
        hotel = create_hotel(approved=True, lat=12.9716, lng=77.5946)
        ngo = create_ngo(approved=True, lat=28.7041, lng=77.1025, capacity=50)  # Delhi vs Bengaluru
        now = timezone.now()
        listing = create_listing(
            hotel=hotel.profile,
            total_servings=10,
            pickup_window_start=now + timezone.timedelta(minutes=1),
            pickup_window_end=now + timezone.timedelta(minutes=5),
            safe_until=now + timezone.timedelta(minutes=2),
            items_data=[{"name": "Soup", "category": "veg", "quantity": 10, "unit": "servings"}],
            photo_files=[],
        )
        with self.assertRaises(FoodBridgeError):
            create_request(listing, ngo.profile, 1)

    def test_request_allowed_when_plenty_of_time(self):
        hotel = create_hotel(approved=True, lat=12.9716, lng=77.5946)
        ngo = create_ngo(approved=True, lat=12.9352, lng=77.6245, capacity=50)  # nearby
        now = timezone.now()
        listing = create_listing(
            hotel=hotel.profile,
            total_servings=10,
            pickup_window_start=now + timezone.timedelta(minutes=5),
            pickup_window_end=now + timezone.timedelta(minutes=90),
            safe_until=now + timezone.timedelta(hours=5),
            items_data=[{"name": "Soup", "category": "veg", "quantity": 10, "unit": "servings"}],
            photo_files=[],
        )
        pickup = create_request(listing, ngo.profile, 1)
        self.assertIsNotNone(pickup.pk)
