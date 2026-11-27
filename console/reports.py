"""Aggregate queries for the admin reports page and CSV export — nothing here is
hard-coded; every number comes from the database at request time."""
import csv

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse

from core.models import FoodListing, ListingStatus, PickupRequest, RequestStatus


def summary():
    """The headline numbers the report promises: listings created, donations collected, servings redistributed,
    allocated vs remaining servings, and conversations count."""
    collected = PickupRequest.objects.filter(status=RequestStatus.COLLECTED)
    total_posted = FoodListing.objects.aggregate(total=Sum("total_servings"))["total"] or 0
    total_avail = FoodListing.objects.filter(status=ListingStatus.POSTED).aggregate(avail=Sum("servings_available"))["avail"] or 0
    total_allocated = total_posted - total_avail if total_posted >= total_avail else 0

    from core.models import Conversation
    total_convs = Conversation.objects.count()

    return {
        "listings_created": FoodListing.objects.count(),
        "listings_live": FoodListing.objects.filter(status=ListingStatus.POSTED).count(),
        "listings_expired": FoodListing.objects.filter(status=ListingStatus.EXPIRED).count(),
        "donations_collected": collected.count(),
        "servings_redistributed": collected.aggregate(total=Sum("amount"))["total"] or 0,
        "servings_posted": total_posted,
        "servings_allocated": total_allocated,
        "servings_remaining": total_avail,
        "total_conversations": total_convs,
        "requests_total": PickupRequest.objects.count(),
        "requests_open": PickupRequest.objects.filter(status__in=RequestStatus.active()).count(),
    }


def monthly_summary():
    """One row per month: listings created, pickups collected and servings redistributed."""
    rows = {}
    for row in FoodListing.objects.annotate(month=TruncMonth("created_at")).values("month").annotate(n=Count("id")):
        rows.setdefault(row["month"], {"month": row["month"], "listings": 0, "pickups": 0, "servings": 0})["listings"] = row["n"]
    collected = (
        PickupRequest.objects.filter(status=RequestStatus.COLLECTED)
        .annotate(month=TruncMonth("collected_at"))
        .values("month")
        .annotate(servings=Sum("amount"), pickups=Count("id"))
    )
    for row in collected:
        entry = rows.setdefault(row["month"], {"month": row["month"], "listings": 0, "pickups": 0, "servings": 0})
        entry["pickups"] = row["pickups"]
        entry["servings"] = row["servings"]
    return sorted(rows.values(), key=lambda r: r["month"])


def top_hotels(limit=10):
    return (
        PickupRequest.objects.filter(status=RequestStatus.COLLECTED)
        .values("listing__hotel__name")
        .annotate(servings=Sum("amount"), pickups=Count("id"))
        .order_by("-servings")[:limit]
    )


def top_recipients(limit=10):
    """NGOs and individuals together, by servings collected."""
    totals = {}
    for r in PickupRequest.objects.filter(status=RequestStatus.COLLECTED).select_related("ngo", "individual"):
        key = (r.recipient_kind, r.recipient_name)
        entry = totals.setdefault(key, {"name": r.recipient_name, "kind": r.recipient_kind, "servings": 0, "pickups": 0})
        entry["servings"] += r.amount
        entry["pickups"] += 1
    return sorted(totals.values(), key=lambda e: -e["servings"])[:limit]


def donations_csv():
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="foodbridge_donations.csv"'
    writer = csv.writer(response)
    writer.writerow(["Pickup ID", "Food", "Hotel", "Recipient", "Recipient type", "Servings", "Requested at", "Collected at"])
    rows = (
        PickupRequest.objects.filter(status=RequestStatus.COLLECTED)
        .select_related("listing__hotel", "ngo", "individual")
        .prefetch_related("listing__items")
    )
    for r in rows:
        writer.writerow(
            [r.pk, r.listing.display_title, r.listing.hotel.name, r.recipient_name, r.recipient_kind, r.amount, r.requested_at, r.collected_at]
        )
    return response
