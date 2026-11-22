"""Request validation, servings reduction, concurrency-safe approval."""
from django.test import TestCase
from django.utils import timezone

from core.exceptions import FoodBridgeError
from core.listings_service import create_listing
from core.models import ListingStatus, PickupRequest, RequestStatus
from core.requests_service import confirm_request, create_request
from core.testing import create_hotel, create_ngo


def _listing(hotel, total=10, safe_minutes=120):
    now = timezone.now()
    return create_listing(
        hotel=hotel.profile,
        total_servings=total,
        pickup_window_start=now + timezone.timedelta(minutes=5),
        pickup_window_end=now + timezone.timedelta(minutes=90),
        safe_until=now + timezone.timedelta(minutes=safe_minutes),
        items_data=[{"name": "Rice", "category": "veg", "quantity": 10, "unit": "servings"}],
        photo_files=[],
    )


class RequestValidationTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=50)

    def test_amount_cannot_exceed_servings_available(self):
        listing = _listing(self.hotel, total=5)
        with self.assertRaises(FoodBridgeError):
            create_request(listing, self.ngo.profile, 6)

    def test_amount_cannot_exceed_ngo_capacity(self):
        listing = _listing(self.hotel, total=100)
        with self.assertRaises(FoodBridgeError):
            create_request(listing, self.ngo.profile, 60)  # capacity is 50

    def test_cannot_request_same_listing_twice(self):
        listing = _listing(self.hotel, total=20)
        create_request(listing, self.ngo.profile, 5)
        with self.assertRaises(FoodBridgeError):
            create_request(listing, self.ngo.profile, 5)


class ServingsReductionTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=50)

    def test_approving_reduces_servings_available(self):
        listing = _listing(self.hotel, total=20)
        pickup = create_request(listing, self.ngo.profile, 8)
        confirm_request(pickup.pk, self.hotel)
        listing.refresh_from_db()
        self.assertEqual(listing.servings_available, 12)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, RequestStatus.CONFIRMED)
        self.assertEqual(pickup.handover.status, "active")
        self.assertEqual(pickup.handover.expires_at, listing.safe_until)

    def test_listing_becomes_fulfilled_when_fully_claimed(self):
        listing = _listing(self.hotel, total=5)
        pickup = create_request(listing, self.ngo.profile, 5)
        confirm_request(pickup.pk, self.hotel)
        listing.refresh_from_db()
        self.assertEqual(listing.servings_available, 0)
        self.assertEqual(listing.status, ListingStatus.FULFILLED)

    def test_cancel_after_approval_returns_servings(self):
        from core.requests_service import cancel_request

        listing = _listing(self.hotel, total=10)
        pickup = create_request(listing, self.ngo.profile, 4)
        confirm_request(pickup.pk, self.hotel)
        cancel_request(pickup.pk, self.ngo, "Change of plan")
        listing.refresh_from_db()
        self.assertEqual(listing.servings_available, 10)
        self.assertEqual(listing.status, ListingStatus.POSTED)
