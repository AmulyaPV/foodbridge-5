"""Management command to reconcile and audit inventory discrepancies:
- Compares stored FoodItem.allocated_quantity against the sum of final allocations from FoodAllocationHistory.
- Compares stored FoodListing.servings_available against the sum of live item remaining quantities.
- Compares FoodListing.status against whether remaining servings exist.
- Dry-run by default. Modifies data only when --apply is explicitly passed inside transaction.atomic().
- Idempotent: running twice makes zero further modifications.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import (
    AllocationOperation,
    FoodAllocationHistory,
    FoodItem,
    FoodListing,
    ListingStatus,
    PickupRequestItem,
)
from core.inventory_service import get_listing_inventory


class Command(BaseCommand):
    help = "Reconcile stored inventory counters and listing status against the immutable ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the corrections to the database. Without this flag, runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        mode_str = "APPLY MODE" if apply_changes else "DRY-RUN MODE (No changes will be saved)"
        self.stdout.write(self.style.NOTICE(f"\n--- Starting Inventory Reconciliation [{mode_str}] ---"))

        item_discrepancies = []
        listing_discrepancies = []

        # 1. Audit FoodItem allocated_quantity vs FoodAllocationHistory ledger
        for item in FoodItem.objects.select_related("listing").all().order_by("id"):
            # Compute total allocated from ledger
            allocations = FoodAllocationHistory.objects.filter(
                food_item=item,
                operation_type=AllocationOperation.ALLOCATE,
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")

            restorations = FoodAllocationHistory.objects.filter(
                food_item=item,
                operation_type=AllocationOperation.RESTORE,
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")

            computed_allocated = max(allocations - restorations, Decimal("0"))
            stored_allocated = item.allocated_quantity

            if computed_allocated != stored_allocated:
                item_discrepancies.append({
                    "item": item,
                    "stored_allocated": stored_allocated,
                    "computed_allocated": computed_allocated,
                })

        # 2. Audit FoodListing servings_available vs sum of FoodItem remaining quantities
        for listing in FoodListing.objects.prefetch_related("items").all().order_by("id"):
            inv = get_listing_inventory(listing)
            computed_available = inv["servings_available"]
            stored_available = listing.servings_available

            status_mismatch = False
            target_status = listing.status
            if listing.status in (ListingStatus.POSTED, ListingStatus.FULFILLED):
                if computed_available == 0 and listing.status == ListingStatus.POSTED:
                    target_status = ListingStatus.FULFILLED
                    status_mismatch = True
                elif computed_available > 0 and listing.status == ListingStatus.FULFILLED:
                    target_status = ListingStatus.POSTED
                    status_mismatch = True

            if computed_available != stored_available or status_mismatch:
                listing_discrepancies.append({
                    "listing": listing,
                    "stored_available": stored_available,
                    "computed_available": computed_available,
                    "stored_status": listing.status,
                    "target_status": target_status,
                })

        # Report findings
        self.stdout.write(f"\nFoodItem Discrepancies Found: {len(item_discrepancies)}")
        for d in item_discrepancies:
            itm = d["item"]
            self.stdout.write(
                f"  - Item #{itm.id} '{itm.name}' (Listing #{itm.listing_id}): "
                f"Stored Allocated={d['stored_allocated']} -> Ledger Allocated={d['computed_allocated']}"
            )

        self.stdout.write(f"\nFoodListing Discrepancies Found: {len(listing_discrepancies)}")
        for d in listing_discrepancies:
            lst = d["listing"]
            self.stdout.write(
                f"  - Listing #{lst.id} '{lst.title}': "
                f"Stored Available={d['stored_available']} -> Computed Available={d['computed_available']} "
                f"| Status: {d['stored_status']} -> {d['target_status']}"
            )

        # Apply corrections if requested
        if apply_changes:
            with transaction.atomic():
                for d in item_discrepancies:
                    FoodItem.objects.filter(pk=d["item"].pk).update(
                        allocated_quantity=d["computed_allocated"]
                    )
                for d in listing_discrepancies:
                    FoodListing.objects.filter(pk=d["listing"].pk).update(
                        servings_available=d["computed_available"],
                        status=d["target_status"],
                    )
            self.stdout.write(self.style.SUCCESS(
                f"\nSuccessfully reconciled {len(item_discrepancies)} items and {len(listing_discrepancies)} listings."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "\nDry-run complete. Run with '--apply' to write corrections to the database."
            ))
