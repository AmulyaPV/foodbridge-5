"""Service functions for live GPS pickup tracking."""
import logging
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

from core.exceptions import FoodBridgeError
from core.geo import haversine_km
from core.models import (
    PickupRequest,
    PickupTrackingSession,
    RequestStatus,
    TrackingSessionStatus,
    NotificationType,
)
from core.notify import notify

logger = logging.getLogger("core.tracking")

RATE_LIMIT_SECONDS = 3
ARRIVAL_THRESHOLD_METERS = 150


def start_tracking_session(pickup_request_id, recipient_user):
    """Starts or resumes a tracking session for an approved pickup request."""
    with transaction.atomic():
        req = (
            PickupRequest.objects.select_for_update()
            .select_related("listing__hotel__user", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        # Verify ownership
        is_owner = (
            (req.ngo and req.ngo.user == recipient_user)
            or (req.individual and req.individual.user == recipient_user)
        )
        if not is_owner:
            raise FoodBridgeError("You do not own this pickup request.")

        # Verify eligible status
        if req.status not in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED, RequestStatus.ON_THE_WAY):
            raise FoodBridgeError("Tracking is only available for confirmed or active pickup requests.")

        if req.listing.is_past_safe_until:
            raise FoodBridgeError("Cannot track: safe-until food time has passed.")

        # Check existing active session
        session = req.tracking_sessions.filter(
            status__in=[
                TrackingSessionStatus.WAITING,
                TrackingSessionStatus.AWAITING_PERMISSION,
                TrackingSessionStatus.ACTIVE,
                TrackingSessionStatus.LOCATION_UNAVAILABLE,
                TrackingSessionStatus.DELAYED,
                TrackingSessionStatus.ARRIVING_SOON,
                TrackingSessionStatus.ARRIVED,
            ]
        ).first()

        if not session:
            role = "ngo" if req.ngo else "individual"
            session = PickupTrackingSession.objects.create(
                pickup_request=req,
                hotel=req.listing.hotel,
                recipient=recipient_user,
                recipient_role=role,
                status=TrackingSessionStatus.ACTIVE,
            )
            # Notify hotel
            hotel_user = req.listing.hotel.user
            recipient_name = req.recipient_name
            notify(
                hotel_user,
                NotificationType.ON_THE_WAY,
                f"{recipient_name} started live pickup journey for {req.listing.display_title}.",
                link="/hotel/requests/",
            )
        else:
            if session.status != TrackingSessionStatus.ACTIVE:
                session.status = TrackingSessionStatus.ACTIVE
                session.save(update_fields=["status"])

        return session


def update_tracking_location(pickup_request_id, recipient_user, latitude, longitude, accuracy=None):
    """Updates recipient live GPS coordinates with rate limiting and arrival detection."""
    # Validate coordinate ranges
    try:
        lat = float(latitude)
        lng = float(longitude)
        acc = float(accuracy) if accuracy is not None else None
    except (ValueError, TypeError):
        raise FoodBridgeError("Invalid GPS coordinates format.")

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise FoodBridgeError("Coordinates out of valid range.")
    if lat == 0 and lng == 0:
        raise FoodBridgeError("Invalid coordinate values (0, 0).")

    # Rate limit check (reject updates faster than ~3s)
    cache_key = f"trk_rl_{pickup_request_id}_{recipient_user.id}"
    if cache.get(cache_key):
        # We don't fail hard, we simply ignore or return current session state to avoid spam
        pass
    cache.set(cache_key, "1", timeout=RATE_LIMIT_SECONDS)

    with transaction.atomic():
        req = (
            PickupRequest.objects.select_for_update()
            .select_related("listing__hotel__user", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        is_owner = (
            (req.ngo and req.ngo.user == recipient_user)
            or (req.individual and req.individual.user == recipient_user)
        )
        if not is_owner:
            raise FoodBridgeError("You do not own this pickup request.")

        session = req.tracking_sessions.filter(
            status__in=[
                TrackingSessionStatus.WAITING,
                TrackingSessionStatus.AWAITING_PERMISSION,
                TrackingSessionStatus.ACTIVE,
                TrackingSessionStatus.LOCATION_UNAVAILABLE,
                TrackingSessionStatus.DELAYED,
                TrackingSessionStatus.ARRIVING_SOON,
                TrackingSessionStatus.ARRIVED,
            ]
        ).first()

        if not session:
            raise FoodBridgeError("No active tracking session found.")

        # Update coordinates
        now = timezone.now()
        session.current_latitude = lat
        session.current_longitude = lng
        session.accuracy = acc
        session.last_updated = now

        # Calculate distance to hotel
        hotel = req.listing.hotel
        if hotel.has_pin:
            dist_km = haversine_km(lat, lng, hotel.latitude, hotel.longitude)
            dist_meters = int(dist_km * 1000)
            session.last_distance_meters = dist_meters

            # Arrival or near-arrival check
            if dist_meters <= ARRIVAL_THRESHOLD_METERS:
                if session.status != TrackingSessionStatus.ARRIVED:
                    session.status = TrackingSessionStatus.ARRIVED
                    notify(
                        hotel.user,
                        NotificationType.ON_THE_WAY,
                        f"{req.recipient_name} has arrived at your pickup location!",
                        link="/hotel/requests/",
                    )
            elif dist_meters <= 500:
                if session.status not in (TrackingSessionStatus.ARRIVING_SOON, TrackingSessionStatus.ARRIVED):
                    session.status = TrackingSessionStatus.ARRIVING_SOON
                    notify(
                        hotel.user,
                        NotificationType.ON_THE_WAY,
                        f"{req.recipient_name} is arriving soon (~{dist_meters}m away).",
                        link="/hotel/requests/",
                    )
            else:
                if session.status in (TrackingSessionStatus.ARRIVING_SOON, TrackingSessionStatus.ARRIVED):
                    session.status = TrackingSessionStatus.ACTIVE
        else:
            session.status = TrackingSessionStatus.ACTIVE

        session.save(update_fields=[
            "current_latitude",
            "current_longitude",
            "accuracy",
            "last_updated",
            "status",
            "last_distance_meters",
        ])

        return session


def stop_tracking_session(pickup_request_id, user, reason="user_stopped"):
    """Stops tracking voluntarily or due to cancellation/completion."""
    with transaction.atomic():
        req = (
            PickupRequest.objects.select_for_update()
            .select_related("listing__hotel__user", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        is_recipient = (
            (req.ngo and req.ngo.user == user)
            or (req.individual and req.individual.user == user)
        )
        is_hotel = (req.listing.hotel.user == user)
        if not (is_recipient or is_hotel or user.is_staff or user.is_admin_role):
            raise FoodBridgeError("Permission denied to stop tracking.")

        sessions = req.tracking_sessions.filter(
            status__in=[
                TrackingSessionStatus.WAITING,
                TrackingSessionStatus.AWAITING_PERMISSION,
                TrackingSessionStatus.ACTIVE,
                TrackingSessionStatus.LOCATION_UNAVAILABLE,
                TrackingSessionStatus.DELAYED,
                TrackingSessionStatus.ARRIVING_SOON,
                TrackingSessionStatus.ARRIVED,
            ]
        )
        count = 0
        now = timezone.now()
        for s in sessions:
            if reason == "cancelled":
                s.status = TrackingSessionStatus.CANCELLED
            elif reason == "completed":
                s.status = TrackingSessionStatus.COMPLETED
            else:
                s.status = TrackingSessionStatus.STOPPED
            s.ended_at = now
            s.save(update_fields=["status", "ended_at"])
            count += 1

        if count > 0 and is_recipient and reason == "user_stopped":
            notify(
                req.listing.hotel.user,
                NotificationType.ON_THE_WAY,
                f"{req.recipient_name} stopped sharing live location.",
                link="/hotel/requests/",
            )

        return count
