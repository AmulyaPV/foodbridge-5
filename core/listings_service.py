from django.db import transaction

from core.activity import log_activity

from .exceptions import FoodBridgeError
from .matching import run_smart_match
from .models import FoodListing, ListingStatus, RequestStatus
from .notify import notify


@transaction.atomic
def create_listing(
    hotel,
    total_servings,
    pickup_window_start,
    pickup_window_end,
    safe_until,
    items_data,
    photo_files,
    title="",
    pickup_location="",
    contact_phone="",
    storage_notes="",
):
    listing = FoodListing.objects.create(
        hotel=hotel,
        title=title.strip(),
        pickup_location=pickup_location.strip(),
        contact_phone=contact_phone.strip(),
        storage_notes=storage_notes.strip(),
        total_servings=total_servings,
        servings_available=total_servings,
        pickup_window_start=pickup_window_start,
        pickup_window_end=pickup_window_end,
        safe_until=safe_until,
    )
    # If total_servings is provided and items_data has items whose quantity doesn't match total_servings,
    # normalize single-item quantity to total_servings if only 1 item was given with a mismatched default
    if len(items_data) == 1 and items_data[0].get("quantity") != total_servings:
        # Check if caller passed a total different from the item quantity
        item_copy = dict(items_data[0])
        item_copy["quantity"] = total_servings
        listing.items.create(**item_copy)
    else:
        for item in items_data:
            listing.items.create(**item)
    for photo in photo_files:
        listing.photos.create(image=photo)
    log_activity(hotel.user, "listing.create", f"{hotel.name} posted a listing for {total_servings} servings", listing)
    run_smart_match(listing)
    return listing


def repost_listing(original, pickup_window_start, pickup_window_end, safe_until):
    """Clone a previous listing's items in one tap; photos are not copied (they may be stale)."""
    items_data = [
        {
            "name": item.name,
            "category": item.category,
            "quantity": item.quantity,
            "unit": item.unit,
            "cooking_time_note": item.cooking_time_note,
            "allergens_note": item.allergens_note,
        }
        for item in original.items.all()
    ]
    return create_listing(
        hotel=original.hotel,
        total_servings=original.total_servings,
        pickup_window_start=pickup_window_start,
        pickup_window_end=pickup_window_end,
        safe_until=safe_until,
        items_data=items_data,
        photo_files=[],
        title=original.title,
        pickup_location=original.pickup_location,
        contact_phone=original.contact_phone,
        storage_notes=original.storage_notes,
    )


def _take_down(listing, actor, new_status, reason, allowed, log_action, log_message, tell_recipients, tell_text):
    """Shared by cancel (the hotel) and remove (an admin): flip the status, cancel every open request
    so servings and codes stop being usable, and tell the people affected."""
    from .requests_service import cancel_request

    if listing.status not in allowed:
        raise FoodBridgeError("This listing can't be changed any more.")
    with transaction.atomic():
        listing.status = new_status
        if new_status == ListingStatus.REMOVED:
            listing.removal_reason = reason[:300]
        else:
            listing.cancel_reason = reason[:300]
        listing.save(update_fields=["status", "removal_reason", "cancel_reason"])
        affected = list(listing.requests.filter(status__in=RequestStatus.active()).select_related("ngo__user", "individual__user"))
        for request in affected:
            cancel_request(request.pk, actor, tell_text, notify_other_side=False)
    log_activity(actor, log_action, log_message, listing)
    for request in affected:
        notify(request.recipient_user, "listing_removed", f"{listing.hotel.name}: {tell_recipients}", link="/ngo/requests/")
    return listing


def cancel_listing(listing, actor, reason):
    return _take_down(
        listing, actor, ListingStatus.CANCELLED, reason, {ListingStatus.POSTED},
        "listing.cancel", f"Cancelled listing #{listing.pk}: {reason}",
        "the hotel cancelled this listing, so your request was cancelled.",
        "The hotel cancelled this listing.",
    )


def remove_listing(listing, actor, reason):
    """Admin action: take a listing down (it disappears from search) and tell the hotel why."""
    _take_down(
        listing, actor, ListingStatus.REMOVED, reason, {ListingStatus.POSTED, ListingStatus.FULFILLED},
        "listing.remove", f"Admin removed listing #{listing.pk}: {reason}",
        "an admin removed this listing, so your request was cancelled.",
        "An admin removed this listing.",
    )
    notify(listing.hotel.user, "listing_removed", f"An admin removed your listing #{listing.pk}: {reason}", link="/hotel/listings/")
    return listing
