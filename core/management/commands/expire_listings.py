"""Mark listings (and their still-open requests) as expired once they pass their
safe-until time. Safe to run as often as you like, e.g. every few minutes from cron;
listings are also checked on read, so this is a tidy-up rather than the only check.

A fully-claimed listing whose pickups were never collected also expires here, so the
recipient's reliability score reflects the missed pickup."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.activity import log_activity
from core.models import FoodListing, ListingStatus, RequestStatus
from core.notify import notify


class Command(BaseCommand):
    help = "Mark listings past their safe-until time as expired, and expire their open requests."

    def handle(self, *args, **options):
        now = timezone.now()
        listing_count = 0
        request_count = 0
        stale = FoodListing.objects.filter(
            status__in=[ListingStatus.POSTED, ListingStatus.FULFILLED], safe_until__lte=now
        )
        for listing in stale:
            open_requests = list(listing.requests.filter(status__in=RequestStatus.active()))
            if listing.status == ListingStatus.FULFILLED and not open_requests:
                continue  # everything was collected: this is a finished donation, not an expired one
            listing.status = ListingStatus.EXPIRED
            listing.save(update_fields=["status"])
            log_activity(None, "listing.expire", f"Listing #{listing.pk} expired automatically", listing)
            listing_count += 1
            for request in open_requests:
                request.status = RequestStatus.EXPIRED
                request.save(update_fields=["status"])
                notify(
                    request.recipient_user, "expiring", f"Listing #{listing.pk} expired before pickup.", link="/ngo/requests/"
                )
                request_count += 1
        self.stdout.write(self.style.SUCCESS(f"Expired {listing_count} listing(s) and {request_count} open request(s)."))
