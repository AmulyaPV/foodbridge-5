"""Registration, login, and verification gating."""
from django.test import TestCase
from django.urls import reverse

from accounts.models import HotelProfile, Role, User, Verification
from core.testing import PASSWORD, create_admin, create_hotel, create_ngo


class RegistrationTests(TestCase):
    def test_hotel_registration_creates_pending_account(self):
        response = self.client.post(
            reverse("accounts:register_hotel"),
            {
                "email": "newhotel@example.com",
                "password1": "Str0ng-Passw0rd!",
                "password2": "Str0ng-Passw0rd!",
                "name": "Spice Garden",
                "contact_person": "Ramesh",
                "phone": "9876543210",
                "address": "1 Main Road",
                "fssai_number": "ABC12345",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="newhotel@example.com")
        self.assertEqual(user.role, Role.HOTEL)
        self.assertEqual(user.verification_status, Verification.PENDING)
        self.assertTrue(HotelProfile.objects.filter(user=user).exists())

    def test_duplicate_email_is_rejected(self):
        create_hotel(email="dupe@example.com")
        response = self.client.post(
            reverse("accounts:register_hotel"),
            {
                "email": "dupe@example.com",
                "password1": "Str0ng-Passw0rd!",
                "password2": "Str0ng-Passw0rd!",
                "name": "Another Hotel",
                "contact_person": "X",
                "phone": "9876543211",
                "address": "2 Main Road",
                "fssai_number": "XYZ98765",
            },
        )
        self.assertEqual(response.status_code, 200)  # form re-rendered with an error
        self.assertEqual(User.objects.filter(email="dupe@example.com").count(), 1)


class VerificationGateTests(TestCase):
    def test_unverified_hotel_is_redirected_to_status(self):
        user = create_hotel(approved=False)
        self.client.login(username=user.email, password=PASSWORD)
        response = self.client.get(reverse("core:hotel_dashboard"))
        self.assertRedirects(response, reverse("accounts:status"))

    def test_verified_hotel_can_reach_dashboard(self):
        user = create_hotel(approved=True)
        self.client.login(username=user.email, password=PASSWORD)
        response = self.client.get(reverse("core:hotel_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_ngo_cannot_access_hotel_only_pages(self):
        user = create_ngo(approved=True)
        self.client.login(username=user.email, password=PASSWORD)
        response = self.client.get(reverse("core:hotel_dashboard"))
        self.assertEqual(response.status_code, 403)


class LoginTests(TestCase):
    def test_login_with_email_case_insensitive(self):
        user = create_hotel(email="Case@Example.com", approved=True)
        ok = self.client.login(username="case@example.com", password=PASSWORD)
        self.assertTrue(ok)

    def test_admin_login_redirects_to_console(self):
        admin = create_admin()
        self.client.login(username=admin.email, password=PASSWORD)
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, reverse("console:dashboard"))
