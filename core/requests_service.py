"""Everything about a recipient's request moving through its lifecycle: requested ->
confirmed -> on the way -> collected (or rejected / cancelled / expired), plus the
handover pickup code. Kept in one module because these steps all touch the same
two rows (FoodListing, PickupRequest) and must stay consistent under concurrency.

A "recipient" is either an NGO or an individual (see accounts.models.IndividualProfile).
"""
from django.db import transaction
from django.utils import timezone

from core.activity import log_activity

from .exceptions import FoodBridgeError
from .geo import estimate_travel_minutes
from .handover_service import confirm_handover, issue_code  # noqa: F401  (confirm_handover re-exported)
from .models import FoodListing, ListingStatus, PickupRequest, RequestStatus
from .notify import notify


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


def create_request(listing, recipient, amount):
    listing.mark_expired_if_needed()
    if listing.status != ListingStatus.POSTED:
        raise FoodBridgeError("This listing is no longer accepting requests.")
    if listing.is_past_safe_until:
        raise FoodBridgeError("This food has passed its safe-until time.")
    if amount > listing.servings_available:
        raise FoodBridgeError(f"Only {listing.servings_available} servings are left on this listing.")
    if amount > recipient.daily_capacity:
        if _is_ngo(recipient):
            raise FoodBridgeError(f"That's more than your daily capacity of {recipient.daily_capacity} servings.")
        raise FoodBridgeError(f"An individual can request up to {recipient.daily_capacity} servings at a time.")

    owner = {"ngo": recipient} if _is_ngo(recipient) else {"individual": recipient}
    if PickupRequest.objects.filter(listing=listing, status__in=RequestStatus.active(), **owner).exists():
        raise FoodBridgeError("You already have an open request on this listing.")

    blocked, _minutes, _source, message = safe_until_check(listing, recipient)
    if blocked:
        raise FoodBridgeError(message)

    request = PickupRequest.objects.create(listing=listing, amount=amount, **owner)
    log_activity(recipient.user, "request.create", f"{recipient.name} requested {amount} servings", request)
    notify(
        listing.hotel.user,
        "new_request",
        f"{recipient.name} requested {amount} servings from your listing.",
        link="/hotel/requests/",
    )
    return request


@transaction.atomic
def confirm_request(pickup_request_id, actor):
    """Locks the listing row so two confirmations can never both claim the same servings."""
    request = (
        PickupRequest.objects.select_for_update()
        .select_related("listing", "ngo__user", "individual__user")
        .get(pk=pickup_request_id)
    )
    listing = FoodListing.objects.select_for_update().get(pk=request.listing_id)

    if request.status != RequestStatus.REQUESTED:
        raise FoodBridgeError("This request has already been decided.")
    if listing.status not in (ListingStatus.POSTED, ListingStatus.FULFILLED):
        raise FoodBridgeError("This listing is no longer available, so the request can't be confirmed.")
    if request.amount > listing.servings_available:
        raise FoodBridgeError("Not enough servings are left to confirm this request.")
    if listing.is_past_safe_until:
        raise FoodBridgeError("This food has passed its safe-until time, so it can't be confirmed.")

    listing.servings_available -= request.amount
    if listing.servings_available == 0:
        listing.status = ListingStatus.FULFILLED
    listing.save(update_fields=["servings_available", "status"])

    request.status = RequestStatus.CONFIRMED
    request.was_approved = True
    request.approved_at = timezone.now()
    request.save(update_fields=["status", "was_approved", "approved_at"])
    issue_code(request)

    log_activity(actor, "request.confirm", f"Confirmed {request.recipient_name} for listing #{listing.pk}", request)
    notify(
        request.recipient_user,
        "confirmed",
        f"{listing.hotel.name} confirmed your request. Your pickup code is ready.",
        link="/ngo/requests/",
    )
    return request


def reject_request(pickup_request_id, actor, reason):
    with transaction.atomic():
        request = (
            PickupRequest.objects.select_for_update()
            .select_related("listing", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        if request.status != RequestStatus.REQUESTED:
            raise FoodBridgeError("This request has already been decided.")
        request.status = RequestStatus.REJECTED
        request.reject_reason = reason[:300]
        request.save(update_fields=["status", "reject_reason"])
        log_activity(actor, "request.reject", f"Rejected {request.recipient_name}'s request: {reason}", request)
    notify(
        request.recipient_user, "rejected",
        f"{request.listing.hotel.name} couldn't confirm your request: {reason}", link="/ngo/requests/",
    )
    return request


def cancel_request(pickup_request_id, actor, reason, notify_other_side=True):
    """Either side can cancel. If servings had already been reserved, they go back to the listing."""
    with transaction.atomic():
        request = (
            PickupRequest.objects.select_for_update()
            .select_related("listing__hotel__user", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        if request.status not in RequestStatus.active():
            raise FoodBridgeError("This request can no longer be cancelled.")
        was_confirmed = request.status in (RequestStatus.CONFIRMED, RequestStatus.ON_THE_WAY)
        request.status = RequestStatus.CANCELLED
        request.cancel_reason = reason[:300]
        request.save(update_fields=["status", "cancel_reason"])
        if was_confirmed:
            listing = FoodListing.objects.select_for_update().get(pk=request.listing_id)
            listing.servings_available += request.amount
            if listing.status == ListingStatus.FULFILLED:
                listing.status = ListingStatus.POSTED
            listing.save(update_fields=["servings_available", "status"])
    log_activity(actor, "request.cancel", f"Cancelled request #{request.pk}: {reason}", request)
    if notify_other_side and actor is not None:
        # tell whoever did NOT cancel
        if actor.pk == request.recipient_user.pk:
            notify(request.listing.hotel.user, "cancelled",
                   f"{request.recipient_name} cancelled their request: {reason}", link="/hotel/requests/")
        elif actor.pk == request.listing.hotel.user.pk:
            notify(request.recipient_user, "cancelled",
                   f"{request.listing.hotel.name} cancelled your request: {reason}", link="/ngo/requests/")
    return request


def mark_on_the_way(pickup_request_id, eta_minutes):
    request = PickupRequest.objects.select_related("listing", "listing__hotel__user", "ngo", "individual").get(
        pk=pickup_request_id
    )
    if request.status != RequestStatus.CONFIRMED:
        raise FoodBridgeError("Only a confirmed request can be marked as on the way.")
    request.status = RequestStatus.ON_THE_WAY
    request.eta_minutes = eta_minutes
    request.on_the_way_at = timezone.now()
    request.save(update_fields=["status", "eta_minutes", "on_the_way_at"])
    notify(
        request.listing.hotel.user,
        "on_the_way",
        f"{request.recipient_name} is on the way, about {eta_minutes} minutes out.",
        link="/hotel/requests/",
    )
    return request
