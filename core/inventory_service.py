"""Inventory management service: atomic allocations, restorations, and audit ledger."""
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import F, Sum

from core.exceptions import FoodBridgeError
from core.models import (
    FoodItem,
    FoodListing,
    ListingStatus,
    PickupRequestItem,
    FoodAllocationHistory,
    AllocationOperation,
)

logger = logging.getLogger(__name__)


def get_listing_inventory(listing):
    """
    Unified inventory function for a FoodListing.
    Computes per-item original, allocated, remaining, and availability status.
    Computes listing-level total original, allocated, remaining, and status
    (available / partially_allocated / fully_allocated).
    Prevents N+1 queries by leveraging prefetched items or querying items directly.
    """
    items = list(listing.items.all())
    items_data = []
    total_original = Decimal("0")
    total_allocated = Decimal("0")
    total_remaining = Decimal("0")

    for item in items:
        orig = item.quantity
        alloc = item.allocated_quantity
        rem = max(orig - alloc, Decimal("0"))
        is_avail = (rem > Decimal("0"))

        total_original += orig
        total_allocated += alloc
        total_remaining += rem

        items_data.append({
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "category_display": item.get_category_display(),
            "quantity": orig,
            "allocated": alloc,
            "remaining": rem,
            "unit": item.unit,
            "unit_display": item.get_unit_display(),
            "is_available": is_avail,
            "cooking_time_note": item.cooking_time_note,
            "allergens_note": item.allergens_note,
        })

    if total_remaining == Decimal("0"):
        inventory_status = "fully_allocated"
        status_display = "Fully claimed"
    elif total_allocated > Decimal("0"):
        inventory_status = "partially_allocated"
        status_display = "Partially allocated"
    else:
        inventory_status = "available"
        status_display = "Available"

    return {
        "listing_id": listing.id,
        "total_original": total_original,
        "total_allocated": total_allocated,
        "total_remaining": total_remaining,
        "servings_available": int(total_remaining),
        "status": inventory_status,
        "status_display": status_display,
        "items": items_data,
        "all_items_depleted": (total_remaining == Decimal("0")),
    }


def get_item_remaining(food_item_id):
    """Returns the live remaining quantity for a food item."""
    item = FoodItem.objects.get(pk=food_item_id)
    return item.remaining_quantity


@transaction.atomic
def allocate_item_quantity(request_item_id, quantity_to_allocate, actor=None, note=""):
    """
    Atomically allocates quantity for a PickupRequestItem from its FoodItem stock.
    Idempotent: if an ALLOCATE ledger entry already exists for this request_item,
    it returns the existing allocation without double-deducting.
    Uses conditional F() atomic updates to ensure remaining >= quantity.
    """
    qty = Decimal(str(quantity_to_allocate))
    if qty <= 0:
        return None

    req_item = (
        PickupRequestItem.objects.select_for_update()
        .select_related("food_item", "pickup_request__listing")
        .get(pk=request_item_id)
    )
    food_item = req_item.food_item

    # Idempotency check via unique ledger constraint
    existing_alloc = FoodAllocationHistory.objects.filter(
        request_item=req_item, operation_type=AllocationOperation.ALLOCATE
    ).first()
    if existing_alloc:
        return existing_alloc

    # Conditional update: only deduct if allocated_quantity + qty <= quantity
    updated_rows = FoodItem.objects.filter(
        pk=food_item.pk,
        quantity__gte=F("allocated_quantity") + qty,
    ).update(allocated_quantity=F("allocated_quantity") + qty)

    if updated_rows == 0:
        raise FoodBridgeError(
            f"Insufficient stock for '{food_item.name}'. Remaining: {food_item.remaining_quantity}, requested: {qty}."
        )

    # Refresh food_item state
    food_item.refresh_from_db()

    # Record immutable audit ledger
    alloc_record = FoodAllocationHistory.objects.create(
        request_item=req_item,
        food_item=food_item,
        operation_type=AllocationOperation.ALLOCATE,
        quantity=qty,
        note=note or f"Allocated {qty} {food_item.unit} for Request #{req_item.pickup_request_id}",
    )

    # Update request item final allocated quantity
    req_item.final_allocated_quantity = qty
    req_item.save(update_fields=["final_allocated_quantity", "updated_at"])

    # Update listing servings_available
    _sync_listing_availability(req_item.pickup_request.listing_id)

    return alloc_record


@transaction.atomic
def restore_item_quantity(request_item_id, actor=None, note=""):
    """
    Atomically restores allocated stock for a PickupRequestItem back to FoodItem.
    Idempotent: if a RESTORE ledger entry already exists, returns without modifying stock.
    Can only restore if an ALLOCATE occurred and final_allocated_quantity > 0.
    """
    req_item = (
        PickupRequestItem.objects.select_for_update()
        .select_related("food_item", "pickup_request__listing")
        .get(pk=request_item_id)
    )
    food_item = req_item.food_item

    # Check if already restored
    existing_restore = FoodAllocationHistory.objects.filter(
        request_item=req_item, operation_type=AllocationOperation.RESTORE
    ).first()
    if existing_restore:
        return existing_restore

    qty_to_restore = req_item.final_allocated_quantity
    if qty_to_restore <= 0:
        return None

    # Conditional update: ensure allocated_quantity >= qty_to_restore
    updated_rows = FoodItem.objects.filter(
        pk=food_item.pk,
        allocated_quantity__gte=qty_to_restore,
    ).update(allocated_quantity=F("allocated_quantity") - qty_to_restore)

    if updated_rows == 0:
        # Stock cannot be decreased below 0
        FoodItem.objects.filter(pk=food_item.pk).update(allocated_quantity=0)

    food_item.refresh_from_db()

    # Record audit ledger
    restore_record = FoodAllocationHistory.objects.create(
        request_item=req_item,
        food_item=food_item,
        operation_type=AllocationOperation.RESTORE,
        quantity=qty_to_restore,
        note=note or f"Restored {qty_to_restore} {food_item.unit} from Request #{req_item.pickup_request_id}",
    )

    req_item.final_allocated_quantity = Decimal("0")
    req_item.save(update_fields=["final_allocated_quantity", "updated_at"])

    _sync_listing_availability(req_item.pickup_request.listing_id)

    return restore_record


def _sync_listing_availability(listing_id):
    """Recalculates listing.servings_available based on sum of remaining item quantities."""
    listing = FoodListing.objects.select_for_update().get(pk=listing_id)
    total_remaining = sum(item.remaining_quantity for item in listing.items.all())
    listing.servings_available = int(total_remaining)
    if listing.servings_available == 0 and listing.status == ListingStatus.POSTED:
        listing.status = ListingStatus.FULFILLED
    elif listing.servings_available > 0 and listing.status == ListingStatus.FULFILLED:
        listing.status = ListingStatus.POSTED
    listing.save(update_fields=["servings_available", "status"])
