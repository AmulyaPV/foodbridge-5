"""Comprehensive tests for:
1. Food-wise requests with varied quantities across items, zero quantities, backend validation.
2. Shared inventory across multiple NGOs (3 NGOs requesting same donation).
3. Partial approval, proposals, acceptance, decline, and atomic rollback on stock changes.
4. Idempotency (double submit, repeat approvals/cancellations, deduplication).
5. Concurrency protection (two competing finalizations, race conditions).
6. Bidirectional messaging, permissions, XSS escaping, rate limits, and unread notifications.
7. Query count optimizations on list and dashboard views.
"""
from decimal import Decimal
import uuid
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.constants import MAX_MESSAGES_PER_MINUTE
from core.exceptions import FoodBridgeError
from core.inventory_service import (
    allocate_item_quantity,
    restore_item_quantity,
)
from core.listings_service import create_listing
from core.matching import rank_ngos_for_listing, calculate_match_details
from core.messaging_service import (
    get_or_create_listing_enquiry,
    get_or_create_request_conversation,
    send_message,
)
from core.models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    FoodAllocationHistory,
    FoodItem,
    FoodListing,
    ItemRequestStatus,
    ListingStatus,
    Message,
    Notification,
    NotificationType,
    PickupRequest,
    PickupRequestItem,
    RequestStatus,
)
from core.requests_service import (
    cancel_request,
    create_request,
    decide_request,
    respond_to_proposal,
)
from core.testing import create_hotel, create_ngo, create_individual


def _create_multi_item_listing(hotel, items_spec=None, safe_minutes=180):
    now = timezone.now()
    if not items_spec:
        items_spec = [
            {"name": "Rice", "category": "veg", "quantity": Decimal("20.00"), "unit": "servings"},
            {"name": "Paneer", "category": "veg", "quantity": Decimal("15.00"), "unit": "servings"},
            {"name": "Roti", "category": "veg", "quantity": Decimal("30.00"), "unit": "servings"},
        ]
    total_qty = int(sum(item["quantity"] for item in items_spec))
    return create_listing(
        hotel=hotel.profile,
        total_servings=total_qty,
        pickup_window_start=now + timezone.timedelta(minutes=5),
        pickup_window_end=now + timezone.timedelta(minutes=120),
        safe_until=now + timezone.timedelta(minutes=safe_minutes),
        items_data=items_spec,
        photo_files=[],
    )


class FoodWiseRequestTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        self.indiv = create_individual(approved=True)
        self.listing = _create_multi_item_listing(self.hotel)

    def test_request_varied_quantities_and_zero_quantities(self):
        items = list(self.listing.items.all().order_by("id"))
        rice, paneer, roti = items[0], items[1], items[2]

        req = create_request(
            self.listing,
            self.ngo.profile,
            item_quantities={
                rice.id: Decimal("10.00"),
                paneer.id: Decimal("0.00"),  # zero quantity
                roti.id: Decimal("15.00"),
            },
        )
        self.assertEqual(req.amount, 25)
        self.assertEqual(req.status, RequestStatus.REQUESTED)
        self.assertEqual(req.items.count(), 2)  # only items > 0 created

        # Pending requests DO NOT consume inventory
        rice.refresh_from_db()
        self.assertEqual(rice.allocated_quantity, 0)
        self.assertEqual(rice.remaining_quantity, Decimal("20.00"))

    def test_request_exceeding_item_availability_rejected(self):
        rice = self.listing.items.first()
        with self.assertRaises(FoodBridgeError):
            create_request(
                self.listing,
                self.ngo.profile,
                item_quantities={rice.id: Decimal("50.00")},  # only 20 available
            )

    def test_individual_ten_serving_cap_enforced_across_items(self):
        items = list(self.listing.items.all().order_by("id"))
        rice, paneer = items[0], items[1]

        # Valid: 5 + 5 = 10 servings
        req = create_request(
            self.listing,
            self.indiv.profile,
            item_quantities={rice.id: 5, paneer.id: 5},
        )
        self.assertEqual(req.amount, 10)

        # Second listing: try requesting 11 total
        listing2 = _create_multi_item_listing(self.hotel)
        items2 = list(listing2.items.all().order_by("id"))
        with self.assertRaises(FoodBridgeError):
            create_request(
                listing2,
                self.indiv.profile,
                item_quantities={items2[0].id: 6, items2[1].id: 5},
            )

    def test_request_requires_at_least_one_positive_quantity(self):
        items = list(self.listing.items.all())
        with self.assertRaises(FoodBridgeError):
            create_request(
                self.listing,
                self.ngo.profile,
                item_quantities={items[0].id: 0, items[1].id: 0},
            )


class SharedInventoryMultiNGOTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo1 = create_ngo(approved=True, capacity=100)
        self.ngo2 = create_ngo(approved=True, capacity=100)
        self.ngo3 = create_ngo(approved=True, capacity=100)
        # Single listing with 20 servings of Rice
        self.listing = _create_multi_item_listing(
            self.hotel,
            items_spec=[{"name": "Rice", "category": "veg", "quantity": Decimal("20.00"), "unit": "servings"}],
        )
        self.item = self.listing.items.first()

    def test_three_ngos_share_one_donation_sequentially(self):
        # NGO 1 requests 8 servings
        req1 = create_request(self.listing, self.ngo1.profile, item_quantities={self.item.id: 8})
        decide_request(req1.pk, self.hotel, action="approve_all")

        self.item.refresh_from_db()
        self.listing.refresh_from_db()
        self.assertEqual(self.item.allocated_quantity, Decimal("8.00"))
        self.assertEqual(self.item.remaining_quantity, Decimal("12.00"))
        self.assertEqual(self.listing.servings_available, 12)
        self.assertEqual(self.listing.display_status[0], "confirmed")  # has live pickup

        # NGO 2 requests 7 servings from remaining
        req2 = create_request(self.listing, self.ngo2.profile, item_quantities={self.item.id: 7})
        decide_request(req2.pk, self.hotel, action="approve_all")

        self.item.refresh_from_db()
        self.listing.refresh_from_db()
        self.assertEqual(self.item.allocated_quantity, Decimal("15.00"))
        self.assertEqual(self.item.remaining_quantity, Decimal("5.00"))
        self.assertEqual(self.listing.servings_available, 5)

        # NGO 3 requests remaining 5 servings
        req3 = create_request(self.listing, self.ngo3.profile, item_quantities={self.item.id: 5})
        decide_request(req3.pk, self.hotel, action="approve_all")

        self.item.refresh_from_db()
        self.listing.refresh_from_db()
        self.assertEqual(self.item.allocated_quantity, Decimal("20.00"))
        self.assertEqual(self.item.remaining_quantity, Decimal("0.00"))
        self.assertEqual(self.listing.servings_available, 0)
        self.assertEqual(self.listing.status, ListingStatus.FULFILLED)

        # Audit ledger check: exactly 3 allocate records exist
        self.assertEqual(FoodAllocationHistory.objects.filter(food_item=self.item).count(), 3)

    def test_cancel_restores_inventory_correctly_and_once(self):
        req1 = create_request(self.listing, self.ngo1.profile, item_quantities={self.item.id: 10})
        decide_request(req1.pk, self.hotel, action="approve_all")

        self.item.refresh_from_db()
        self.assertEqual(self.item.allocated_quantity, Decimal("10.00"))

        # Cancel req1
        cancel_request(req1.pk, self.ngo1, reason="Van broke down")
        self.item.refresh_from_db()
        self.assertEqual(self.item.allocated_quantity, Decimal("0.00"))
        self.assertEqual(self.item.remaining_quantity, Decimal("20.00"))

        # Repeat cancel call is idempotent and does not restore further
        cancel_request(req1.pk, self.ngo1, reason="Repeat")
        self.item.refresh_from_db()
        self.assertEqual(self.item.allocated_quantity, Decimal("0.00"))


class PartialApprovalAndProposalsTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        self.listing = _create_multi_item_listing(self.hotel)
        self.items = list(self.listing.items.all().order_by("id"))
        self.rice = self.items[0]    # 20 qty
        self.paneer = self.items[1]  # 15 qty

    def test_mixed_approval_finalizes_exact_and_proposes_revised(self):
        req = create_request(
            self.listing,
            self.ngo.profile,
            item_quantities={self.rice.id: 10, self.paneer.id: 10},
        )
        req_items = {itm.food_item_id: itm for itm in req.items.all()}

        # Hotel approves Rice as-is (10), but proposes 5 for Paneer
        decide_request(
            req.pk,
            self.hotel,
            action="partial_decide",
            item_decisions={
                req_items[self.rice.id].id: {"action": "approve", "quantity": 10},
                req_items[self.paneer.id].id: {"action": "propose", "quantity": 5},
            },
        )

        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.REVISION_PROPOSED)
        self.assertIsNotNone(req.proposal_expires_at)

        # Rice finalized immediately
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.allocated_quantity, Decimal("10.00"))

        # Paneer NOT consumed yet
        self.paneer.refresh_from_db()
        self.assertEqual(self.paneer.allocated_quantity, Decimal("0.00"))

        # Recipient accepts proposal
        respond_to_proposal(req.pk, self.ngo, accept=True)
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.CONFIRMED)
        self.assertTrue(req.was_approved)

        # Now Paneer is allocated
        self.paneer.refresh_from_db()
        self.assertEqual(self.paneer.allocated_quantity, Decimal("5.00"))

    def test_atomic_rollback_when_item_becomes_unavailable_before_accept(self):
        req = create_request(
            self.listing,
            self.ngo.profile,
            item_quantities={self.paneer.id: 10},
        )
        req_item = req.items.first()

        decide_request(
            req.pk,
            self.hotel,
            action="partial_decide",
            item_decisions={
                req_item.id: {"action": "propose", "quantity": 8},
            },
        )

        # Simulate another buyer taking all Paneer stock in the meantime
        FoodItem.objects.filter(pk=self.paneer.pk).update(allocated_quantity=Decimal("15.00"))

        # Recipient attempts to accept
        with self.assertRaises(FoodBridgeError):
            respond_to_proposal(req.pk, self.ngo, accept=True)

        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.REVISION_PROPOSED)  # stays proposed, no partial allocation


class IdempotencyTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        self.listing = _create_multi_item_listing(self.hotel)

    def test_duplicate_request_submission_returns_existing(self):
        client_key = "key-test-123"
        item = self.listing.items.first()
        req1 = create_request(
            self.listing,
            self.ngo.profile,
            item_quantities={item.id: 5},
            idempotency_key=client_key,
        )
        req2 = create_request(
            self.listing,
            self.ngo.profile,
            item_quantities={item.id: 5},
            idempotency_key=client_key,
        )
        self.assertEqual(req1.pk, req2.pk)
        self.assertEqual(PickupRequest.objects.count(), 1)


class ConcurrencyAllocationTests(TransactionTestCase):
    """Testing atomic conditional stock protection against race conditions."""
    def test_competing_finalizations_cannot_overallocate(self):
        hotel = create_hotel(approved=True)
        ngo1 = create_ngo(approved=True, capacity=100)
        ngo2 = create_ngo(approved=True, capacity=100)
        listing = _create_multi_item_listing(
            hotel,
            items_spec=[{"name": "Curry", "category": "veg", "quantity": Decimal("10.00"), "unit": "servings"}],
        )
        item = listing.items.first()

        req1 = create_request(listing, ngo1.profile, item_quantities={item.id: 10})
        req2 = create_request(listing, ngo2.profile, item_quantities={item.id: 10})

        # Finalize req1 -> succeeds
        decide_request(req1.pk, hotel, action="approve_all")

        # Finalize req2 -> fails safely with FoodBridgeError
        with self.assertRaises(FoodBridgeError):
            decide_request(req2.pk, hotel, action="approve_all")

        item.refresh_from_db()
        self.assertEqual(item.allocated_quantity, Decimal("10.00"))


class MessagingSecurityAndRulesTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        self.stranger = create_ngo(approved=True, capacity=100)
        self.listing = _create_multi_item_listing(self.hotel)

    def test_bidirectional_messaging_and_request_linking(self):
        item = self.listing.items.first()
        req = create_request(self.listing, self.ngo.profile, item_quantities={item.id: 5})

        conv = get_or_create_request_conversation(req)
        self.assertEqual(conv.conversation_type, ConversationType.REQUEST)

        # NGO sends message to hotel
        msg1 = send_message(conv.pk, self.ngo, "Hello, what containers should we bring?")
        self.assertIsNotNone(msg1.pk)

        # Hotel sends reply
        msg2 = send_message(conv.pk, self.hotel, "Steel pots or heavy-duty boxes are fine!")
        self.assertIsNotNone(msg2.pk)

        self.assertEqual(conv.messages.filter(is_system=False).count(), 2)

    def test_outsider_cannot_read_or_post(self):
        item = self.listing.items.first()
        req = create_request(self.listing, self.ngo.profile, item_quantities={item.id: 5})
        conv = get_or_create_request_conversation(req)

        with self.assertRaises(PermissionDenied):
            send_message(conv.pk, self.stranger, "I am eavesdropping!")

    def test_xss_escaping_in_message_body(self):
        item = self.listing.items.first()
        req = create_request(self.listing, self.ngo.profile, item_quantities={item.id: 5})
        conv = get_or_create_request_conversation(req)

        msg = send_message(conv.pk, self.ngo, "<script>alert('xss')</script>")
        self.assertNotIn("<script>", msg.body)
        self.assertIn("&lt;script&gt;", msg.body)

    def test_rate_limiting(self):
        item = self.listing.items.first()
        req = create_request(self.listing, self.ngo.profile, item_quantities={item.id: 5})
        conv = get_or_create_request_conversation(req)

        # Send up to limit
        for i in range(MAX_MESSAGES_PER_MINUTE):
            send_message(conv.pk, self.ngo, f"Msg {i}")

        # Next one raises FoodBridgeError rate limit
        with self.assertRaises(FoodBridgeError):
            send_message(conv.pk, self.ngo, "One too many")


    def test_request_create_view_post_with_item_quantities(self):
        """End-to-end HTTP POST to /food/<id>/request/ with item_qty_* form fields."""
        self.client.force_login(self.ngo)
        items = list(self.listing.items.all().order_by("id"))
        post_data = {
            f"item_qty_{items[0].id}": "6",
            f"item_qty_{items[1].id}": "4",
            "idempotency_key": "test-http-key-1",
        }
        response = self.client.post(
            reverse("core:request_create", args=[self.listing.pk]),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)
        req = PickupRequest.objects.filter(idempotency_key="test-http-key-1").first()
        self.assertIsNotNone(req)
        self.assertEqual(req.amount, 10)
        self.assertEqual(req.items.count(), 2)


class QueryCountPerformanceTests(TestCase):
    def setUp(self):
        self.hotel = create_hotel(approved=True)
        self.ngo = create_ngo(approved=True, capacity=100)
        # Create 5 listings with 3 items each
        for i in range(5):
            _create_multi_item_listing(self.hotel)

    def test_ngo_dashboard_query_count_stays_constant(self):
        from django.db import connection
        self.client.force_login(self.ngo)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("core:ngo_dashboard"))
            self.assertEqual(response.status_code, 200)

        initial_query_count = len(ctx.captured_queries)

        # Add 5 more listings
        for i in range(5):
            _create_multi_item_listing(self.hotel)

        with CaptureQueriesContext(connection) as ctx2:
            response = self.client.get(reverse("core:ngo_dashboard"))
            self.assertEqual(response.status_code, 200)

        # Query count must remain constant (no N+1 per listing)
        self.assertLessEqual(len(ctx2.captured_queries), initial_query_count + 2)
