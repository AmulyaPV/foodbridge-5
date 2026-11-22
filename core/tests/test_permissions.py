"""Per-role permissions: who can reach which pages."""
from django.test import TestCase
from django.urls import reverse

from core.testing import PASSWORD, create_admin, create_hotel, create_ngo


class PermissionTests(TestCase):
    def test_admin_console_requires_admin_role(self):
        hotel = create_hotel(approved=True)
        self.client.login(username=hotel.email, password=PASSWORD)
        response = self.client.get(reverse("console:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_reach_console(self):
        admin = create_admin()
        self.client.login(username=admin.email, password=PASSWORD)
        response = self.client.get(reverse("console:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("core:ngo_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_ngo_requires_verification_for_dashboard(self):
        ngo = create_ngo(approved=False)
        self.client.login(username=ngo.email, password=PASSWORD)
        response = self.client.get(reverse("core:ngo_dashboard"))
        self.assertRedirects(response, reverse("accounts:status"))
