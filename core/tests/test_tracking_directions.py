import json
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from accounts.models import User, Role, HotelProfile, NGOProfile, IndividualProfile, Verification
from core.models import FoodListing, FoodItem, PickupRequest, RequestStatus, PickupTrackingSession, TrackingSessionStatus
from core.tracking_service import start_tracking_session, update_tracking_location, stop_tracking_session


class TrackingAndDirectionsTests(TestCase):
    def setUp(self):
        # 1. Hotel user & profile
        self.hotel_user = User.objects.create_user(
            username="test_hotel", email="hotel@example.com", password="password", role=Role.HOTEL, verification_status=Verification.APPROVED
        )
        self.hotel_profile = HotelProfile.objects.create(
            user=self.hotel_user,
            name="The Grand Palace",
            fssai_number="12345678901234",
            phone="+919876543210",
            address="100 MG Road",
            latitude=12.9716,
            longitude=77.5946,
        )

        # 2. NGO user & profile
        self.ngo_user = User.objects.create_user(
            username="test_ngo", email="ngo@example.com", password="password", role=Role.NGO, verification_status=Verification.APPROVED
        )
        self.ngo_profile = NGOProfile.objects.create(
            user=self.ngo_user,
            name="City Food Bank",
            registration_number="REG10001",
            daily_capacity=1000,
            service_area="Bangalore",
            phone="+919876543211",
            address="200 Brigade Rd",
            latitude=12.9750,
            longitude=77.5980,
        )

        # 3. Individual user & profile
        self.ind_user = User.objects.create_user(
            username="test_ind", email="ind@example.com", password="password", role=Role.INDIVIDUAL, verification_status=Verification.APPROVED
        )
        self.ind_profile = IndividualProfile.objects.create(
            user=self.ind_user,
            name="John Doe",
            phone="+919876543212",
            address="300 Residency Rd",
            latitude=12.9760,
            longitude=77.5990,
        )

        # 4. Another unrelated hotel
        self.other_hotel_user = User.objects.create_user(
            username="other_hotel", email="other@example.com", password="password", role=Role.HOTEL, verification_status=Verification.APPROVED
        )
        self.other_hotel_profile = HotelProfile.objects.create(
            user=self.other_hotel_user,
            name="Other Hotel",
            fssai_number="99999999999999",
            phone="+919876543299",
            address="Other Place",
            latitude=12.9000,
            longitude=77.5000,
        )

        # 5. Food Listing
        now = timezone.now()
        self.listing = FoodListing.objects.create(
            hotel=self.hotel_profile,
            title="Surplus Meals",
            pickup_location="100 MG Road",
            contact_phone="+919876543210",
            total_servings=50,
            servings_available=50,
            pickup_window_start=now,
            pickup_window_end=now + timezone.timedelta(hours=2),
            safe_until=now + timezone.timedelta(hours=4),
        )

        # 6. Approved Pickup Request for NGO
        self.pickup_req = PickupRequest.objects.create(
            listing=self.listing,
            ngo=self.ngo_profile,
            amount=20,
            status=RequestStatus.CONFIRMED,
        )

    def test_hotel_location_manage_view(self):
        client = Client()
        client.force_login(self.hotel_user)
        # GET form
        resp = client.get("/hotel/location/")
        self.assertEqual(resp.status_code, 200)

        # POST update location
        resp = client.post("/hotel/location/", {
            "address": "500 Lavelle Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "latitude": "12.9700",
            "longitude": "77.5900",
        })
        self.assertRedirects(resp, "/hotel/listings/")
        self.hotel_profile.refresh_from_db()
        self.assertEqual(self.hotel_profile.address, "500 Lavelle Road")
        self.assertEqual(self.hotel_profile.latitude, 12.9700)
        self.assertEqual(self.hotel_profile.city, "Bengaluru")

    def test_request_directions_access_control(self):
        client = Client()
        # Anonymous -> redirected
        resp = client.get(f"/requests/{self.pickup_req.pk}/directions/")
        self.assertEqual(resp.status_code, 302)

        # Other hotel -> forbidden
        client.force_login(self.other_hotel_user)
        resp = client.get(f"/requests/{self.pickup_req.pk}/directions/")
        self.assertEqual(resp.status_code, 403)

        # NGO owner -> allowed
        client.force_login(self.ngo_user)
        resp = client.get(f"/requests/{self.pickup_req.pk}/directions/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "The Grand Palace")

    def test_live_gps_lifecycle_and_api_endpoints(self):
        client = Client()
        client.force_login(self.ngo_user)

        # Start tracking
        resp = client.post(f"/api/requests/{self.pickup_req.pk}/tracking/start/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))

        session = PickupTrackingSession.objects.get(pickup_request=self.pickup_req)
        self.assertTrue(session.is_active)

        # Push valid coordinates (500m away)
        resp = client.post(
            f"/api/requests/{self.pickup_req.pk}/tracking/location/",
            data=json.dumps({"latitude": 12.9720, "longitude": 77.5950, "accuracy": 15.0}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.current_latitude, 12.9720)
        self.assertIsNotNone(session.last_distance_meters)

        # Hotel checks status
        hotel_client = Client()
        hotel_client.force_login(self.hotel_user)
        resp = hotel_client.get(f"/api/requests/{self.pickup_req.pk}/tracking/status/")
        self.assertEqual(resp.status_code, 200)
        hotel_data = resp.json()
        self.assertTrue(hotel_data["active"])
        self.assertEqual(hotel_data["latitude"], 12.9720)

        # Unrelated hotel blocked from polling
        other_client = Client()
        other_client.force_login(self.other_hotel_user)
        resp = other_client.get(f"/api/requests/{self.pickup_req.pk}/tracking/status/")
        self.assertEqual(resp.status_code, 403)

        # Stop tracking
        resp = client.post(f"/api/requests/{self.pickup_req.pk}/tracking/stop/")
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, TrackingSessionStatus.STOPPED)

    def test_invalid_coordinates_rejected(self):
        client = Client()
        client.force_login(self.ngo_user)
        client.post(f"/api/requests/{self.pickup_req.pk}/tracking/start/")

        # Out of bounds lat
        resp = client.post(
            f"/api/requests/{self.pickup_req.pk}/tracking/location/",
            data=json.dumps({"latitude": 999.0, "longitude": 77.0}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

        # (0, 0) coordinates
        resp = client.post(
            f"/api/requests/{self.pickup_req.pk}/tracking/location/",
            data=json.dumps({"latitude": 0, "longitude": 0}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
