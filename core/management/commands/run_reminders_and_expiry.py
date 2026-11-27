"""Background management command for:
- Expiring listings that have passed their safe-until deadline.
- Expiring open requests and revision proposals that have timed out.
- Sending pickup reminders (for confirmed pickups approaching pickup window end or safe_until).
- Scheduled via cron: */5 * * * * python manage.py run_reminders_and_expiry
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.activity import log_activity
from core.messaging_service import post_system_event
from core.models import (
    FoodListing,
    ItemRequestStatus,
    ListingStatus,
    Notification,
    NotificationType,
    PickupRequest,
    RequestStatus,
)
from core.notify import notify


class Command(BaseCommand):
    help = "Expire past-due listings, proposals, and send pickup reminders."

    def handle(self, *args, **options):
        now = timezone.now()
        listing_expired_count = 0
        proposal_expired_count = 0
        reminder_count = 0

        # 1. Expire listings past safe_until
        stale_listings = FoodListing.objects.filter(
            status__in=[ListingStatus.POSTED, ListingStatus.FULFILLED],
            safe_until__lte=now,
        )
        for listing in stale_listings:
            open_requests = list(listing.requests.filter(status__in=RequestStatus.active()))
            if listing.status == ListingStatus.FULFILLED and not open_requests:
                continue

            listing.status = ListingStatus.EXPIRED
            listing.save(update_fields=["status"])
            log_activity(None, "listing.expire", f"Listing #{listing.pk} expired automatically", listing)
            listing_expired_count += 1

            for req in open_requests:
                req.status = RequestStatus.EXPIRED
                req.save(update_fields=["status"])
                notify(
                    req.recipient_user,
                    NotificationType.EXPIRING,
                    f"Listing #{listing.pk} expired before collection was completed.",
                    link="/ngo/requests/",
                )

        # 2. Expire revision proposals past proposal_expires_at
        stale_proposals = PickupRequest.objects.filter(
            status=RequestStatus.REVISION_PROPOSED,
            proposal_expires_at__lte=now,
        )
        for req in stale_proposals:
            req.status = RequestStatus.EXPIRED
            req.save(update_fields=["status"])
            req.items.filter(status=ItemRequestStatus.PARTIAL_PROPOSED).update(
                status=ItemRequestStatus.DECLINED
            )
            conv = req.conversations.first()
            if conv:
                post_system_event(conv.id, "The revision proposal timed out and expired.")
            notify(
                req.recipient_user,
                NotificationType.EXPIRING,
                f"Revised proposal for listing #{req.listing_id} has expired.",
                link="/ngo/requests/",
            )
            proposal_expired_count += 1

        # 3. Pickup reminders for confirmed pickups ~30 mins before safe_until
        thirty_mins_ahead = now + timezone.timedelta(minutes=30)
        imminent_pickups = PickupRequest.objects.filter(
            status__in=[RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED],
            listing__safe_until__lte=thirty_mins_ahead,
            listing__safe_until__gt=now,
        ).select_related("ngo__user", "individual__user", "listing")

        for pickup in imminent_pickups:
            # Check if reminder already sent
            already_reminded = Notification.objects.filter(
                user=pickup.recipient_user,
                kind=NotificationType.PICKUP_REMINDER,
                link="/ngo/requests/",
            ).exists()
            if not already_reminded:
                notify(
                    pickup.recipient_user,
                    NotificationType.PICKUP_REMINDER,
                    f"Reminder: Food on listing #{pickup.listing_id} must be collected soon! Safe until {pickup.listing.safe_until.strftime('%H:%M')}.",
                    link="/ngo/requests/",
                )
                reminder_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Summary: {listing_expired_count} listings expired, {proposal_expired_count} proposals expired, {reminder_count} reminders sent."
            )
        )
