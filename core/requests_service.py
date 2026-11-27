"""Requests service: food-wise requesting, partial approval, revision proposals,
cancellations, idempotency, and concurrency protection."""
import logging
import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from core.activity import log_activity
from core.constants import PROPOSAL_EXPIRY_HOURS
from core.exceptions import FoodBridgeError
from core.geo import estimate_travel_minutes
from core.handover_service import confirm_handover, issue_code  # noqa: F401 (re-exported)
from core.inventory_service import (
    allocate_item_quantity,
    restore_item_quantity,
    _sync_listing_availability,
)
from core.messaging_service import (
    get_or_create_request_conversation,
    post_system_event,
)
from core.models import (
    FoodItem,
    FoodListing,
    ItemRequestStatus,
    ListingStatus,
    NotificationType,
    PickupProposal,
    PickupRequest,
    PickupRequestItem,
    RequestStatus,
    RequestStatusHistory,
)
from core.notify import notify

logger = logging.getLogger(__name__)


def _is_ngo(recipient):
    return recipient.__class__.__name__ == "NGOProfile"


def safe_until_check(listing, recipient):
    """Can this recipient realistically arrive before the food stops being safe?
    Returns (is_blocked: bool, minutes: int|None, source: str, message: str)."""
    hotel = listing.hotel
    minutes, source = estimate_travel_minutes(hotel.latitude, hotel.longitude, recipient.latitude, recipient.longitude)
    remaining_minutes = listing.seconds_until_unsafe / 60
    if minutes is None:
        return False, None, source, "Travel time couldn't be estimated (add a map pin for a precise check)."
    if minutes >= remaining_minutes:
        return (
            True,
            minutes,
            source,
            f"This food is safe for about {max(0, round(remaining_minutes))} more minutes, but the trip "
            f"from your location takes about {minutes} minutes. It likely won't arrive in time.",
        )
    return False, minutes, source, f"About {minutes} minutes away — well within the safe window."


def _log_status_history(request, old_status, new_status, actor=None, note=""):
    RequestStatusHistory.objects.create(
        pickup_request=request,
        old_status=old_status,
        new_status=new_status,
        actor=actor,
        note=note,
    )


@transaction.atomic
def create_request(listing, recipient, amount=None, item_quantities=None, idempotency_key=None):
    """
    Creates a food-wise pickup request.
    - item_quantities: dict of {food_item_id: requested_quantity}
    - If item_quantities is omitted but amount is given (backwards compatibility),
      all items or single item is populated.
    - Idempotency: checks idempotency_key and active request from same recipient.
    - Backend validation: non-negative quantities, at least one > 0, total <= capacity.
    - Pending requests NEVER consume inventory.
    """
    listing.mark_expired_if_needed()
    if listing.status != ListingStatus.POSTED and not (listing.status == ListingStatus.FULFILLED and listing.servings_available > 0):
        raise FoodBridgeError("This listing is no longer accepting requests.")
    if listing.is_past_safe_until:
        raise FoodBridgeError("This food has passed its safe-until time.")

    owner = {"ngo": recipient} if _is_ngo(recipient) else {"individual": recipient}

    # Idempotency check 1: Client key
    if idempotency_key:
        existing_req = PickupRequest.objects.filter(idempotency_key=idempotency_key).first()
        if existing_req:
            return existing_req

    # If amount was passed, validate against listing available servings
    if amount is not None and amount > listing.servings_available:
        raise FoodBridgeError(f"Only {listing.servings_available} servings are left on this listing.")

    # Check if recipient already has an active request on this listing
    if PickupRequest.objects.filter(listing=listing, status__in=RequestStatus.active(), **owner).exists():
        raise FoodBridgeError("You already have an open request on this listing.")

    # Check travel feasibility
    blocked, _minutes, _source, message = safe_until_check(listing, recipient)
    if blocked:
        raise FoodBridgeError(message)

    # Process items and quantities
    listing_items = {item.id: item for item in listing.items.all()}
    if not listing_items:
        raise FoodBridgeError("This listing has no food items.")

    validated_quantities = {}
    if item_quantities:
        for item_id_raw, qty_raw in item_quantities.items():
            try:
                item_id = int(item_id_raw)
                qty = Decimal(str(qty_raw or "0"))
            except (ValueError, TypeError):
                continue
            if item_id not in listing_items:
                continue
            if qty < 0:
                raise FoodBridgeError("Requested quantity cannot be negative.")
            item = listing_items[item_id]
            if qty > item.remaining_quantity:
                raise FoodBridgeError(
                    f"Requested {qty} for '{item.name}', but only {item.remaining_quantity} is currently available."
                )
            if qty > 0:
                validated_quantities[item_id] = qty
    else:
        # Legacy fallback
        total_amount = Decimal(str(amount or "1"))
        if len(listing_items) == 1:
            first_item = list(listing_items.values())[0]
            if total_amount > first_item.remaining_quantity:
                raise FoodBridgeError(f"Only {first_item.remaining_quantity} servings left on this listing.")
            validated_quantities[first_item.id] = total_amount
        else:
            # Distribute proportionally
            tot_listing = sum(item.remaining_quantity for item in listing_items.values()) or Decimal("1")
            for item in listing_items.values():
                item_share = (total_amount * (item.remaining_quantity / tot_listing)).quantize(Decimal("1.00"))
                if item_share > 0:
                    validated_quantities[item.id] = min(item_share, item.remaining_quantity)

    total_requested_servings = sum(validated_quantities.values())
    if total_requested_servings <= 0:
        raise FoodBridgeError("Please select at least one item with a quantity greater than 0.")

    # Capacity check
    if total_requested_servings > recipient.daily_capacity:
        if _is_ngo(recipient):
            raise FoodBridgeError(
                f"Total requested ({total_requested_servings}) exceeds daily capacity of {recipient.daily_capacity} servings."
            )
        raise FoodBridgeError(
            f"An individual recipient can request up to {recipient.daily_capacity} servings in total."
        )

    # Create PickupRequest
    request = PickupRequest.objects.create(
        listing=listing,
        amount=int(total_requested_servings),
        status=RequestStatus.REQUESTED,
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        **owner,
    )

    # Create PickupRequestItem rows
    for item_id, qty in validated_quantities.items():
        PickupRequestItem.objects.create(
            pickup_request=request,
            food_item_id=item_id,
            requested_quantity=qty,
            proposed_quantity=Decimal("0"),
            final_allocated_quantity=Decimal("0"),
            status=ItemRequestStatus.PENDING,
        )

    _log_status_history(request, "", RequestStatus.REQUESTED, actor=recipient.user, note="Request submitted")
    log_activity(recipient.user, "request.create", f"{recipient.name} requested {request.amount} servings", request)

    # Auto-create chat conversation
    conv = get_or_create_request_conversation(request)
    post_system_event(
        conv.id,
        f"{recipient.name} submitted a request for {request.amount} servings across {len(validated_quantities)} item(s).",
    )

    notify(
        listing.hotel.user,
        NotificationType.NEW_REQUEST,
        f"{recipient.name} requested {request.amount} servings from your listing.",
        link="/hotel/requests/",
    )
    return request


@transaction.atomic
def decide_request(pickup_request_id, actor, action="approve_all", item_decisions=None, reason=""):
    """
    Unified hotel decision service supporting:
    - approve_all: approve full requested quantities for all items immediately.
    - partial_decide: mixed approval / proposal per item:
        item_decisions is a dict: {req_item_id: {"action": "approve"|"propose"|"reject", "quantity": qty}}
        Items approved as-requested finalize immediately.
        Items with revised quantities become PARTIAL_PROPOSED and wait for recipient acceptance.
    - reject: rejects whole request.
    """
    request = (
        PickupRequest.objects.select_for_update()
        .select_related("listing__hotel__user", "ngo__user", "individual__user")
        .get(pk=pickup_request_id)
    )
    listing = FoodListing.objects.select_for_update().get(pk=request.listing_id)

    # Idempotency: if already decided into same state
    if action == "reject" and request.status == RequestStatus.REJECTED:
        return request
    if action == "approve_all" and request.status == RequestStatus.CONFIRMED:
        return request

    if request.status not in (RequestStatus.REQUESTED, RequestStatus.REVISION_PROPOSED):
        raise FoodBridgeError("This request has already been finalized and cannot be modified.")
    if listing.is_past_safe_until:
        raise FoodBridgeError("This food has passed its safe-until time.")

    old_status = request.status
    req_items = list(request.items.select_for_update().select_related("food_item"))
    conv = get_or_create_request_conversation(request)

    if action == "reject":
        request.status = RequestStatus.REJECTED
        request.reject_reason = reason[:300] or "Declined by donor"
        request.save(update_fields=["status", "reject_reason"])
        for item in req_items:
            item.status = ItemRequestStatus.REJECTED
            item.save(update_fields=["status", "updated_at"])
        _log_status_history(request, old_status, RequestStatus.REJECTED, actor=actor, note=reason)
        post_system_event(conv.id, f"Hotel declined the request: {reason or 'No reason provided'}")
        notify(
            request.recipient_user,
            NotificationType.REJECTED,
            f"{listing.hotel.name} couldn't confirm your request: {reason or 'Declined'}",
            link="/ngo/requests/",
        )
        return request

    if action == "approve_all":
        # Check stock and allocate all items immediately
        for item in req_items:
            allocate_item_quantity(item.id, item.requested_quantity, actor=actor, note="Approved all as requested")
            item.proposed_quantity = item.requested_quantity
            item.status = ItemRequestStatus.APPROVED
            item.save(update_fields=["proposed_quantity", "status", "updated_at"])

        request.status = RequestStatus.CONFIRMED
        request.was_approved = True
        request.approved_at = timezone.now()
        request.save(update_fields=["status", "was_approved", "approved_at"])
        issue_code(request)

        _log_status_history(request, old_status, RequestStatus.CONFIRMED, actor=actor, note="Approved all items")
        post_system_event(conv.id, "Hotel confirmed all requested items. Handover pickup code has been issued.")
        notify(
            request.recipient_user,
            NotificationType.CONFIRMED,
            f"{listing.hotel.name} confirmed your full request. Your pickup code is ready.",
            link="/ngo/requests/",
        )
        return request

    if action == "partial_decide":
        if not item_decisions:
            raise FoodBridgeError("No item decisions provided.")

        has_proposals = False
        has_immediate_allocations = False
        any_item_approved = False

        # Set proposal expiry (sooner of 12h or safe_until)
        twelve_hours = timezone.now() + timezone.timedelta(hours=PROPOSAL_EXPIRY_HOURS)
        proposal_expiry = min(twelve_hours, listing.safe_until)

        for req_item in req_items:
            dec = item_decisions.get(str(req_item.id)) or item_decisions.get(req_item.id)
            if not dec:
                continue

            dec_action = dec.get("action", "reject")
            dec_qty = Decimal(str(dec.get("quantity") or "0"))

            if dec_action == "reject" or dec_qty <= 0:
                req_item.status = ItemRequestStatus.REJECTED
                req_item.proposed_quantity = Decimal("0")
                req_item.save(update_fields=["status", "proposed_quantity", "updated_at"])

            elif dec_action == "approve" and dec_qty == req_item.requested_quantity:
                # Exactly as requested: finalize immediately
                allocate_item_quantity(req_item.id, dec_qty, actor=actor, note="Partial decision: exact match approved")
                req_item.proposed_quantity = dec_qty
                req_item.status = ItemRequestStatus.APPROVED
                req_item.save(update_fields=["proposed_quantity", "status", "updated_at"])
                has_immediate_allocations = True
                any_item_approved = True

            else:
                # Revised quantity: propose to recipient, DO NOT consume stock yet
                food_item = req_item.food_item
                if dec_qty > food_item.remaining_quantity:
                    raise FoodBridgeError(
                        f"Cannot propose {dec_qty} for '{food_item.name}'. Only {food_item.remaining_quantity} available."
                    )
                req_item.proposed_quantity = dec_qty
                req_item.status = ItemRequestStatus.PARTIAL_PROPOSED
                req_item.save(update_fields=["proposed_quantity", "status", "updated_at"])
                has_proposals = True
                any_item_approved = True

        if not any_item_approved:
            request.status = RequestStatus.REJECTED
            request.reject_reason = "No items approved"
            request.save(update_fields=["status", "reject_reason"])
            _log_status_history(request, old_status, RequestStatus.REJECTED, actor=actor, note="All items rejected")
            post_system_event(conv.id, "Hotel rejected all items.")
            notify(request.recipient_user, NotificationType.REJECTED, f"{listing.hotel.name} declined your request.", link="/ngo/requests/")
            return request

        if has_proposals:
            request.status = RequestStatus.REVISION_PROPOSED
            request.proposal_expires_at = proposal_expiry
            request.save(update_fields=["status", "proposal_expires_at"])
            _log_status_history(request, old_status, RequestStatus.REVISION_PROPOSED, actor=actor, note="Alternative quantities proposed")
            post_system_event(conv.id, f"Hotel proposed revised quantities. Please review and accept/decline before {proposal_expiry.strftime('%H:%M, %d %b')}.")
            notify(
                request.recipient_user,
                NotificationType.REVISION_PROPOSED,
                f"{listing.hotel.name} proposed revised quantities for your request. Please review.",
                link="/ngo/requests/",
            )
        else:
            # Only exact approvals were made
            request.status = RequestStatus.CONFIRMED
            request.was_approved = True
            request.approved_at = timezone.now()
            request.save(update_fields=["status", "was_approved", "approved_at"])
            issue_code(request)
            _log_status_history(request, old_status, RequestStatus.CONFIRMED, actor=actor, note="Approved exact items")
            post_system_event(conv.id, "Hotel approved requested items. Pickup code is ready.")
            notify(
                request.recipient_user,
                NotificationType.CONFIRMED,
                f"{listing.hotel.name} confirmed your request. Pickup code is ready.",
                link="/ngo/requests/",
            )

        return request

    raise FoodBridgeError(f"Unknown action '{action}'")


@transaction.atomic
def respond_to_proposal(pickup_request_id, recipient_user, accept=True):
    """
    Recipient explicitly accepts or declines a revised quantity proposal.
    - If accepted: in ONE atomic transaction, re-checks availability for ALL accepted items,
      applies deductions with conditional updates, and writes ledger entries.
      If ANY item has become unavailable, rolls back everything and raises a clear error.
    - If declined: sets status to DECLINED/CANCELLED, leaves inventory completely untouched.
    - Checks proposal expiry: rejects if past proposal_expires_at or safe_until.
    """
    request = (
        PickupRequest.objects.select_for_update()
        .select_related("listing__hotel__user", "ngo__user", "individual__user")
        .get(pk=pickup_request_id)
    )
    listing = FoodListing.objects.select_for_update().get(pk=request.listing_id)
    conv = get_or_create_request_conversation(request)

    if request.recipient_user != recipient_user:
        raise FoodBridgeError("You do not have permission to respond to this proposal.")

    if request.status != RequestStatus.REVISION_PROPOSED:
        if accept and request.status in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED):
            return request  # Idempotent
        if not accept and request.status == RequestStatus.CANCELLED:
            return request
        raise FoodBridgeError("There is no active revision proposal for this request.")

    # Expiry check
    if request.is_proposal_expired or listing.is_past_safe_until:
        request.status = RequestStatus.EXPIRED
        request.save(update_fields=["status"])
        _log_status_history(request, RequestStatus.REVISION_PROPOSED, RequestStatus.EXPIRED, actor=recipient_user, note="Proposal expired")
        post_system_event(conv.id, "The proposal expired before being accepted.")
        raise FoodBridgeError("This revision proposal has expired.")

    old_status = request.status
    proposed_items = list(
        request.items.select_for_update()
        .filter(status=ItemRequestStatus.PARTIAL_PROPOSED)
        .select_related("food_item")
    )

    if not accept:
        # Recipient declined
        for item in proposed_items:
            item.status = ItemRequestStatus.DECLINED
            item.save(update_fields=["status", "updated_at"])

        # Check if there were any previously confirmed items in this request
        confirmed_count = request.items.filter(status=ItemRequestStatus.APPROVED).count()
        if confirmed_count > 0:
            request.status = RequestStatus.PARTIALLY_APPROVED
            issue_code(request)
        else:
            request.status = RequestStatus.CANCELLED
            request.cancel_reason = "Recipient declined revised quantities"

        request.save(update_fields=["status", "cancel_reason"])
        _log_status_history(request, old_status, request.status, actor=recipient_user, note="Proposal declined")
        post_system_event(conv.id, f"{recipient_user.display_name} declined the proposed revised quantities.")
        notify(
            listing.hotel.user,
            NotificationType.PROPOSAL_DECLINED,
            f"{request.recipient_name} declined the revised proposal for listing #{listing.pk}.",
            link="/hotel/requests/",
        )
        return request

    # Recipient accepted: Validate stock for ALL items before allocating
    unavailable_items = []
    for req_item in proposed_items:
        if req_item.proposed_quantity > req_item.food_item.remaining_quantity:
            unavailable_items.append(
                f"'{req_item.food_item.name}' (available: {req_item.food_item.remaining_quantity}, needed: {req_item.proposed_quantity})"
            )

    if unavailable_items:
        details = ", ".join(unavailable_items)
        raise FoodBridgeError(
            f"Availability changed while reviewing proposal: {details}. Please decline or ask for a new proposal."
        )

    # Allocate all proposed items atomically
    for req_item in proposed_items:
        allocate_item_quantity(
            req_item.id,
            req_item.proposed_quantity,
            actor=recipient_user,
            note="Recipient accepted revision proposal",
        )
        req_item.status = ItemRequestStatus.ACCEPTED
        req_item.save(update_fields=["status", "updated_at"])

    request.status = RequestStatus.CONFIRMED
    request.was_approved = True
    request.approved_at = timezone.now()
    request.save(update_fields=["status", "was_approved", "approved_at"])
    issue_code(request)

    _log_status_history(request, old_status, RequestStatus.CONFIRMED, actor=recipient_user, note="Proposal accepted")
    post_system_event(conv.id, f"{recipient_user.display_name} accepted the proposal. Pickup code is generated.")
    notify(
        listing.hotel.user,
        NotificationType.PROPOSAL_ACCEPTED,
        f"{request.recipient_name} accepted the revised proposal. Pickup is confirmed.",
        link="/hotel/requests/",
    )
    return request


@transaction.atomic
def cancel_request(pickup_request_id, actor, reason="", notify_other_side=True):
    """
    Cancels a request.
    - If confirmed/partially approved/on the way: restores allocated quantities exactly once.
    - If already collected: blocked and raises error (never restores inventory).
    - Idempotent: repeat call returns cleanly.
    """
    request = (
        PickupRequest.objects.select_for_update()
        .select_related("listing__hotel__user", "ngo__user", "individual__user")
        .get(pk=pickup_request_id)
    )

    if request.status == RequestStatus.COLLECTED:
        raise FoodBridgeError("Cannot cancel a completed collection.")
    if request.status == RequestStatus.CANCELLED:
        return request  # Idempotent

    if request.status not in RequestStatus.active():
        raise FoodBridgeError("This request can no longer be cancelled.")

    was_allocated = request.status in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED, RequestStatus.ON_THE_WAY)
    old_status = request.status
    request.status = RequestStatus.CANCELLED
    request.cancel_reason = reason[:300]
    request.save(update_fields=["status", "cancel_reason"])

    # Restore allocated quantities via audit ledger
    if was_allocated:
        for req_item in request.items.select_for_update():
            if req_item.final_allocated_quantity > 0:
                restore_item_quantity(req_item.id, actor=actor, note=f"Restored on cancel: {reason}")
            req_item.status = ItemRequestStatus.CANCELLED
            req_item.save(update_fields=["status", "updated_at"])

    # Stop live tracking if active
    from core.tracking_service import stop_tracking_session
    try:
        stop_tracking_session(request.pk, actor, reason="cancelled")
    except Exception:
        pass

    _log_status_history(request, old_status, RequestStatus.CANCELLED, actor=actor, note=reason)
    log_activity(actor, "request.cancel", f"Cancelled request #{request.pk}: {reason}", request)

    conv = get_or_create_request_conversation(request)
    post_system_event(conv.id, f"Request was cancelled: {reason or 'No reason provided'}")

    if notify_other_side and actor is not None:
        target_user = request.listing.hotel.user if actor.pk == request.recipient_user.pk else request.recipient_user
        link = "/hotel/requests/" if target_user == request.listing.hotel.user else "/ngo/requests/"
        notify(
            target_user,
            NotificationType.CANCELLED,
            f"Request #{request.pk} was cancelled: {reason}",
            link=link,
        )

    return request


def mark_on_the_way(pickup_request_id, actor=None, eta_minutes=None):
    # Support both (id, actor, eta) and (id, eta)
    if isinstance(actor, (int, str)) and eta_minutes is None:
        eta_minutes = int(actor)
        actor = None

    with transaction.atomic():
        request = (
            PickupRequest.objects.select_for_update()
            .select_related("listing__hotel__user", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        if request.status not in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED):
            raise FoodBridgeError("Only confirmed pickups can be marked on the way.")
        old_status = request.status
        request.status = RequestStatus.ON_THE_WAY
        request.eta_minutes = eta_minutes
        request.on_the_way_at = timezone.now()
        request.save(update_fields=["status", "eta_minutes", "on_the_way_at"])
        user_actor = actor if getattr(actor, "is_authenticated", False) else request.recipient_user
        _log_status_history(request, old_status, RequestStatus.ON_THE_WAY, actor=user_actor, note=f"ETA: {eta_minutes} mins")

    conv = get_or_create_request_conversation(request)
    post_system_event(conv.id, f"{request.recipient_name} is on the way (ETA: ~{eta_minutes or 30} mins).")

    log_activity(user_actor, "request.on_the_way", f"{request.recipient_name} is on the way (ETA ~{eta_minutes}m)", request)
    notify(
        request.listing.hotel.user,
        NotificationType.ON_THE_WAY,
        f"{request.recipient_name} is on the way to collect listing #{request.listing_id} (ETA ~{eta_minutes or 30}m).",
        link="/hotel/requests/",
    )
    return request


def confirm_request(pickup_request_id, actor):
    """Legacy helper redirecting to decide_request(approve_all)."""
    return decide_request(pickup_request_id, actor, action="approve_all")


def reject_request(pickup_request_id, actor, reason):
    """Legacy helper redirecting to decide_request(reject)."""
    return decide_request(pickup_request_id, actor, action="reject", reason=reason)

