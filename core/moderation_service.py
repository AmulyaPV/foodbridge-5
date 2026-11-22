"""Reporting a listing and the admin's decision on it."""
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Role, User

from .activity import log_activity
from .exceptions import FoodBridgeError
from .listings_service import remove_listing
from .models import ListingReport, ListingStatus, ReportStatus
from .notify import notify


def report_listing(listing, reporter, reason, details=""):
    if listing.hotel.user_id == reporter.pk:
        raise FoodBridgeError("You can't report your own listing.")
    if listing.status in (ListingStatus.CANCELLED, ListingStatus.REMOVED):
        raise FoodBridgeError("This listing has already been taken down.")
    try:
        with transaction.atomic():
            report = ListingReport.objects.create(
                listing=listing, reporter=reporter, reason=reason, details=details.strip()[:300]
            )
    except IntegrityError:
        raise FoodBridgeError("You've already reported this listing. An admin will review it.")
    log_activity(reporter, "listing.report", f"Listing #{listing.pk} reported: {report.get_reason_display()}", listing)
    for admin in User.objects.filter(role=Role.ADMIN):
        notify(admin, "report", f"Listing #{listing.pk} from {listing.hotel.name} was reported.", link="/manage/moderation/")
    return report


@transaction.atomic
def dismiss_report(report, actor, note=""):
    if report.status != ReportStatus.OPEN:
        raise FoodBridgeError("This report has already been reviewed.")
    report.status = ReportStatus.DISMISSED
    report.resolved_by = actor
    report.resolved_at = timezone.now()
    report.resolution_note = note.strip()[:300]
    report.save(update_fields=["status", "resolved_by", "resolved_at", "resolution_note"])
    log_activity(actor, "report.dismiss", f"Dismissed report on listing #{report.listing_id}", report.listing)
    return report


def remove_reported_listing(report, actor, reason):
    """Remove the listing and close every open report on it in one go."""
    if report.status != ReportStatus.OPEN:
        raise FoodBridgeError("This report has already been reviewed.")
    listing = report.listing
    if listing.status in (ListingStatus.POSTED, ListingStatus.FULFILLED):
        remove_listing(listing, actor, reason)
    now = timezone.now()
    ListingReport.objects.filter(listing=listing, status=ReportStatus.OPEN).update(
        status=ReportStatus.ACTIONED, resolved_by=actor, resolved_at=now, resolution_note=reason[:300]
    )
    return listing
