"""The Secure Handover Code: generation, secrecy, single use, expiry, lockout, regeneration, unlock,
attempt logging and who is allowed to do what. Each test names the goal (G1..G7) it protects;
the goals are listed at the top of core/handover_service.py and in docs/handover-code.md."""
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.exceptions import FoodBridgeError
from core.handover_service import (
    code_matches,
    derive_code,
    regenerate_code,
    unlock_handover,
    visible_code,
)
from core.listings_service import create_listing
from core.models import (
    MAX_CODE_REGENERATIONS,
    MAX_PICKUP_ATTEMPTS,
    CodeStatus,
    HandoverAttempt,
    HandoverCode,
    PickupRequest,
    RequestStatus,
)
from core.requests_service import confirm_request, confirm_handover, create_request
from core.testing import PASSWORD, create_admin, create_hotel, create_ngo


def make_listing(hotel, safe_hours=2):
    now = timezone.now()
    return create_listing(
        hotel=hotel.profile,
        total_servings=10,
        pickup_window_start=now + timezone.timedelta(minutes=5),
        pickup_window_end=now + timezone.timedelta(minutes=90),
        safe_until=now + timezone.timedelta(hours=safe_hours),
        items_data=[{"name": "Dal", "category": "veg", "quantity": 10, "unit": "servings"}],
        photo_files=[],
    )


class HandoverBase(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=50)
        self.listing = make_listing(self.hotel)
        self.pickup = create_request(self.listing, self.ngo.profile, 3)
        confirm_request(self.pickup.pk, self.hotel)
        self.reload()

    def reload(self):
        self.pickup = PickupRequest.objects.select_related("handover").get(pk=self.pickup.pk)
        self.handover = self.pickup.handover
        self.code = derive_code(self.pickup.pk, self.handover.salt)

    def wrong_code(self):
        return "000000" if self.code != "000000" else "111111"

    def enter_wrong(self, times=1):
        for _ in range(times):
            with self.assertRaises(FoodBridgeError):
                confirm_handover(self.pickup.pk, self.wrong_code(), self.hotel)
        self.reload()


class IssuingTests(HandoverBase):
    def test_approval_issues_one_active_code_expiring_with_the_food(self):  # G2, G3
        self.assertEqual(HandoverCode.objects.filter(pickup_request=self.pickup).count(), 1)
        self.assertEqual(self.handover.status, CodeStatus.ACTIVE)
        self.assertEqual(self.handover.expires_at, self.listing.safe_until)

    def test_code_is_six_digits_and_stable_for_a_given_salt(self):  # G2
        self.assertRegex(self.code, r"^\d{6}$")
        self.assertEqual(self.code, derive_code(self.pickup.pk, self.handover.salt))

    def test_different_approvals_get_different_salts(self):  # G2
        other_ngo = create_ngo(approved=True, capacity=50)
        second = create_request(self.listing, other_ngo.profile, 2)
        confirm_request(second.pk, self.hotel)
        self.assertNotEqual(self.handover.salt, second.handover.salt)
        self.assertEqual(len(self.handover.salt), 32)

    def test_the_code_itself_is_never_written_to_the_database(self):  # G2
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM core_handovercode")
            row = [str(value) for value in cursor.fetchone()]
            cursor.execute("SELECT * FROM core_pickuprequest")
            request_row = [str(value) for value in cursor.fetchone()]
        self.assertNotIn(self.code, row)
        self.assertNotIn(self.code, request_row)

    def test_cannot_approve_food_that_is_already_unsafe(self):  # G3
        listing = make_listing(self.hotel, safe_hours=2)
        other = create_ngo(approved=True, capacity=50)
        pickup = create_request(listing, other.profile, 1)
        type(listing).objects.filter(pk=listing.pk).update(safe_until=timezone.now() - timezone.timedelta(minutes=1))
        with self.assertRaises(FoodBridgeError):
            confirm_request(pickup.pk, self.hotel)


class ConfirmTests(HandoverBase):
    def test_correct_code_marks_collected_and_records_who(self):  # G3, G5
        confirm_handover(self.pickup.pk, self.code, self.hotel, ip="10.0.0.7")
        self.reload()
        self.assertEqual(self.pickup.status, RequestStatus.COLLECTED)
        self.assertEqual(self.handover.status, CodeStatus.USED)
        self.assertEqual(self.handover.used_by, self.hotel)
        attempt = HandoverAttempt.objects.get()
        self.assertEqual((attempt.outcome, attempt.ip_address, attempt.actor), ("success", "10.0.0.7", self.hotel))

    def test_surrounding_spaces_are_ignored(self):
        confirm_handover(self.pickup.pk, f" {self.code} ", self.hotel)
        self.reload()
        self.assertEqual(self.pickup.status, RequestStatus.COLLECTED)

    def test_code_cannot_be_reused(self):  # G3
        confirm_handover(self.pickup.pk, self.code, self.hotel)
        with self.assertRaises(FoodBridgeError):
            confirm_handover(self.pickup.pk, self.code, self.hotel)

    def test_wrong_code_counts_an_attempt_and_is_logged_without_the_typed_code(self):  # G4, G5
        self.enter_wrong()
        self.assertEqual(self.handover.failed_attempts, 1)
        self.assertEqual(self.handover.status, CodeStatus.ACTIVE)
        attempt = HandoverAttempt.objects.get()
        self.assertEqual(attempt.outcome, "wrong")
        self.assertFalse(hasattr(attempt, "code"))
        self.assertFalse(hasattr(attempt, "entered_code"))

    def test_non_ascii_input_is_just_a_wrong_code_not_a_crash(self):
        with self.assertRaises(FoodBridgeError):
            confirm_handover(self.pickup.pk, "١٢٣٤٥٦", self.hotel)  # Arabic-Indic digits
        self.reload()
        self.assertEqual(self.handover.failed_attempts, 1)

    def test_five_wrong_attempts_lock_and_alert_admins(self):  # G4
        admin = create_admin()
        self.enter_wrong(MAX_PICKUP_ATTEMPTS)
        self.assertEqual(self.handover.status, CodeStatus.LOCKED)
        self.assertIsNotNone(self.handover.locked_at)
        self.assertTrue(admin.notifications.filter(kind="lockout").exists())
        with self.assertRaises(FoodBridgeError):  # even the right code is refused while locked
            confirm_handover(self.pickup.pk, self.code, self.hotel)
        self.reload()
        self.assertEqual(self.pickup.status, RequestStatus.CONFIRMED)
        self.assertEqual(self.handover.attempts.filter(outcome="blocked").count(), 1)

    def test_expired_code_is_refused_and_logged(self):  # G3
        HandoverCode.objects.filter(pk=self.handover.pk).update(expires_at=timezone.now() - timezone.timedelta(seconds=1))
        with self.assertRaises(FoodBridgeError):
            confirm_handover(self.pickup.pk, self.code, self.hotel)
        self.reload()
        self.assertEqual(self.pickup.status, RequestStatus.CONFIRMED)
        self.assertEqual(self.handover.attempts.get().outcome, "expired")
        self.assertIsNone(visible_code(self.pickup))

    def test_cancelled_pickup_cannot_be_confirmed(self):  # G3
        PickupRequest.objects.filter(pk=self.pickup.pk).update(status=RequestStatus.CANCELLED)
        with self.assertRaises(FoodBridgeError):
            confirm_handover(self.pickup.pk, self.code, self.hotel)


class RegenerationTests(HandoverBase):
    def test_new_code_replaces_the_old_one_immediately(self):  # G6
        old_code = self.code
        regenerate_code(self.pickup.pk, self.ngo)
        self.reload()
        self.assertNotEqual(self.code, old_code)
        self.assertEqual(self.handover.regenerations, 1)
        self.assertFalse(code_matches(self.handover, old_code))
        self.assertTrue(code_matches(self.handover, self.code))

    def test_guess_counter_is_not_reset_by_regenerating(self):  # G6 — otherwise 5 guesses could be repeated forever
        self.enter_wrong(2)
        regenerate_code(self.pickup.pk, self.ngo)
        self.reload()
        self.assertEqual(self.handover.failed_attempts, 2)

    def test_regeneration_limit(self):  # G6
        for _ in range(MAX_CODE_REGENERATIONS):
            regenerate_code(self.pickup.pk, self.ngo)
        with self.assertRaises(FoodBridgeError):
            regenerate_code(self.pickup.pk, self.ngo)

    def test_cannot_regenerate_a_locked_code(self):  # G7
        self.enter_wrong(MAX_PICKUP_ATTEMPTS)
        with self.assertRaises(FoodBridgeError):
            regenerate_code(self.pickup.pk, self.ngo)

    def test_cannot_regenerate_after_collection(self):
        confirm_handover(self.pickup.pk, self.code, self.hotel)
        with self.assertRaises(FoodBridgeError):
            regenerate_code(self.pickup.pk, self.ngo)


class UnlockTests(HandoverBase):
    def test_unlock_resets_counter_and_issues_a_new_code(self):  # G7
        self.enter_wrong(MAX_PICKUP_ATTEMPTS)
        old_code = self.code
        admin = create_admin()
        unlock_handover(self.pickup.pk, admin)
        self.reload()
        self.assertEqual(self.handover.status, CodeStatus.ACTIVE)
        self.assertEqual(self.handover.failed_attempts, 0)
        self.assertNotEqual(self.code, old_code)
        self.assertTrue(self.ngo.notifications.exists())
        confirm_handover(self.pickup.pk, self.code, self.hotel)

    def test_cannot_unlock_something_that_is_not_locked(self):
        with self.assertRaises(FoodBridgeError):
            unlock_handover(self.pickup.pk, create_admin())


class VisibilityAndPermissionTests(HandoverBase):
    def client_for(self, user):
        client = Client()
        self.assertTrue(client.login(username=user.username, password=PASSWORD))
        return client

    def test_only_the_approved_ngo_sees_the_code(self):  # G1
        ngo_page = self.client_for(self.ngo).get(reverse("core:my_requests")).content.decode()
        hotel_pages = [
            self.client_for(self.hotel).get(reverse("core:hotel_requests")).content.decode(),
            self.client_for(self.hotel).get(reverse("core:confirm_handover", args=[self.pickup.pk])).content.decode(),
        ]
        self.assertIn(self.code, ngo_page)
        for page in hotel_pages:
            self.assertNotIn(self.code, page)
        other_ngo = create_ngo(approved=True)
        self.assertNotIn(self.code, self.client_for(other_ngo).get(reverse("core:my_requests")).content.decode())

    def test_code_disappears_once_collected(self):
        confirm_handover(self.pickup.pk, self.code, self.hotel)
        page = self.client_for(self.ngo).get(reverse("core:my_requests")).content.decode()
        self.assertNotIn(self.code, page)

    def test_ngo_can_regenerate_via_the_view_but_hotel_cannot(self):  # G1, G6
        url = reverse("core:code_regenerate", args=[self.pickup.pk])
        self.assertEqual(self.client_for(self.hotel).post(url).status_code, 403)
        self.assertEqual(self.client_for(create_ngo(approved=True)).post(url).status_code, 404)
        self.assertEqual(self.client_for(self.ngo).post(url).status_code, 302)
        self.reload()
        self.assertEqual(self.handover.regenerations, 1)

    def test_regenerate_requires_post(self):
        self.client_for(self.ngo).get(reverse("core:code_regenerate", args=[self.pickup.pk]))
        self.reload()
        self.assertEqual(self.handover.regenerations, 0)

    def test_only_the_owning_hotel_can_open_the_handover_page(self):
        stranger = create_hotel(approved=True)
        response = self.client_for(stranger).get(reverse("core:confirm_handover", args=[self.pickup.pk]))
        self.assertEqual(response.status_code, 404)

    def test_hotel_view_rejects_malformed_codes_without_using_an_attempt(self):  # form validation
        client = self.client_for(self.hotel)
        for bad in ["12345", "abcdef", "1234567"]:
            client.post(reverse("core:confirm_handover", args=[self.pickup.pk]), {"code": bad})
        self.reload()
        self.assertEqual(self.handover.failed_attempts, 0)

    def test_view_records_ip_and_redirects_after_a_wrong_code(self):  # G5
        client = self.client_for(self.hotel)
        response = client.post(reverse("core:confirm_handover", args=[self.pickup.pk]), {"code": self.wrong_code()})
        self.assertRedirects(response, reverse("core:confirm_handover", args=[self.pickup.pk]))
        self.reload()
        self.assertEqual(self.handover.attempts.get().ip_address, "127.0.0.1")
        page = client.get(reverse("core:confirm_handover", args=[self.pickup.pk])).content.decode()
        self.assertIn("4 of 5 attempts left", page)

    def test_only_admins_can_unlock(self):  # G7
        self.enter_wrong(MAX_PICKUP_ATTEMPTS)
        url = reverse("console:unlock_pickup", args=[self.pickup.pk])
        self.assertEqual(self.client_for(self.hotel).post(url).status_code, 403)
        self.assertEqual(self.client_for(self.ngo).post(url).status_code, 403)
        self.client_for(create_admin()).post(url)
        self.reload()
        self.assertEqual(self.handover.status, CodeStatus.ACTIVE)

    def test_admin_sees_attempt_history_for_locked_pickups(self):
        self.enter_wrong(MAX_PICKUP_ATTEMPTS)
        page = self.client_for(create_admin()).get(reverse("console:locked_pickups")).content.decode()
        self.assertIn(f"Pickup #{self.pickup.pk}", page)
        self.assertIn("Wrong code", page)
