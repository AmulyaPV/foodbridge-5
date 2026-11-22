"""Smart Match ranking: closer, better-fit, more-reliable NGOs rank higher."""
from django.test import TestCase
from django.utils import timezone

from core.listings_service import create_listing
from core.matching import rank_ngos_for_listing
from core.models import ListingMatch
from core.testing import create_hotel, create_ngo


class SmartMatchTests(TestCase):
    def test_closer_ngo_ranks_above_farther_ngo(self):
        hotel = create_hotel(approved=True, lat=12.9716, lng=77.5946)
        near = create_ngo(approved=True, lat=12.9720, lng=77.5950, capacity=50)  # a few hundred metres
        far = create_ngo(approved=True, lat=13.5, lng=78.5, capacity=50)  # far away
        now = timezone.now()
        listing = create_listing(
            hotel=hotel.profile,
            total_servings=10,
            pickup_window_start=now + timezone.timedelta(minutes=5),
            pickup_window_end=now + timezone.timedelta(minutes=90),
            safe_until=now + timezone.timedelta(hours=3),
            items_data=[{"name": "Curry", "category": "veg", "quantity": 10, "unit": "servings"}],
            photo_files=[],
        )
        ranked = rank_ngos_for_listing(listing)
        ranked_ngo_ids = [ngo.pk for ngo, _score, _dist in ranked]
        self.assertLess(ranked_ngo_ids.index(near.profile.pk), ranked_ngo_ids.index(far.profile.pk))

    def test_first_look_matches_are_created_on_post(self):
        hotel = create_hotel(approved=True)
        create_ngo(approved=True)
        now = timezone.now()
        listing = create_listing(
            hotel=hotel.profile,
            total_servings=10,
            pickup_window_start=now + timezone.timedelta(minutes=5),
            pickup_window_end=now + timezone.timedelta(minutes=90),
            safe_until=now + timezone.timedelta(hours=3),
            items_data=[{"name": "Curry", "category": "veg", "quantity": 10, "unit": "servings"}],
            photo_files=[],
        )
        self.assertTrue(ListingMatch.objects.filter(listing=listing).exists())

    def test_unverified_ngo_is_never_matched(self):
        hotel = create_hotel(approved=True)
        unverified = create_ngo(approved=False)
        now = timezone.now()
        listing = create_listing(
            hotel=hotel.profile,
            total_servings=10,
            pickup_window_start=now + timezone.timedelta(minutes=5),
            pickup_window_end=now + timezone.timedelta(minutes=90),
            safe_until=now + timezone.timedelta(hours=3),
            items_data=[{"name": "Curry", "category": "veg", "quantity": 10, "unit": "servings"}],
            photo_files=[],
        )
        ranked_ids = [ngo.pk for ngo, _s, _d in rank_ngos_for_listing(listing)]
        self.assertNotIn(unverified.profile.pk, ranked_ids)
