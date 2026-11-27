"""Views and API endpoints for Google Maps Directions and Live GPS Tracking."""
import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from accounts.decorators import hotel_required, recipient_required
from accounts.models import HotelProfile
from core.exceptions import FoodBridgeError
from core.models import PickupRequest, RequestStatus, TrackingSessionStatus
from core.tracking_service import (
    start_tracking_session,
    update_tracking_location,
    stop_tracking_session,
)


# ----------------------------------------------------------------------------- Hotel Location Management
@hotel_required
def hotel_location_manage(request):
    """Allows hotels to search address with Places Autocomplete, drag pin, and save pickup coordinates."""
    profile = request.user.profile
    if request.method == "POST":
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        postal_code = request.POST.get("postal_code", "").strip()
        google_place_id = request.POST.get("google_place_id", "").strip()
        lat_raw = request.POST.get("latitude", "").strip()
        lng_raw = request.POST.get("longitude", "").strip()

        if not address:
            messages.error(request, "Please enter a valid pickup address.")
            return redirect("core:hotel_location_manage")

        lat = None
        lng = None
        if lat_raw and lng_raw:
            try:
                lat = float(lat_raw)
                lng = float(lng_raw)
                if not (-90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0)):
                    messages.error(request, "Coordinates are invalid or out of range.")
                    return redirect("core:hotel_location_manage")
            except ValueError:
                messages.error(request, "Coordinates must be numbers.")
                return redirect("core:hotel_location_manage")

        profile.address = address
        profile.city = city
        profile.state = state
        profile.postal_code = postal_code
        profile.google_place_id = google_place_id
        profile.latitude = lat
        profile.longitude = lng
        profile.location_updated_at = timezone.now()
        profile.save(update_fields=[
            "address", "city", "state", "postal_code", "google_place_id",
            "latitude", "longitude", "location_updated_at"
        ])

        messages.success(request, "Pickup location updated successfully.")
        return redirect("core:hotel_dashboard")

    return render(request, "core/hotel_location_manage.html", {
        "profile": profile,
        "GOOGLE_MAPS_BROWSER_API_KEY": settings.GOOGLE_MAPS_BROWSER_API_KEY,
    })


# ----------------------------------------------------------------------------- Directions & Live Journey (Recipient)
@recipient_required
def request_directions(request, pk):
    """View directions for an approved pickup request (NGO or Individual)."""
    user = request.user
    req = get_object_or_404(
        PickupRequest.objects.select_related("listing__hotel", "ngo", "individual"),
        pk=pk,
    )
    is_owner = (
        (req.ngo and req.ngo.user == user)
        or (req.individual and req.individual.user == user)
    )
    if not is_owner:
        raise PermissionDenied("You do not own this pickup request.")

    if req.status not in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED, RequestStatus.ON_THE_WAY):
        messages.warning(request, "Directions are only available once the hotel confirms your request.")
        return redirect("core:my_requests")

    active_session = req.tracking_sessions.filter(
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

    hotel = req.listing.hotel
    destination_str = f"{hotel.latitude},{hotel.longitude}" if hotel.has_pin else hotel.address

    return render(request, "core/request_directions.html", {
        "pickup_request": req,
        "listing": req.listing,
        "hotel": hotel,
        "active_session": active_session,
        "destination_str": destination_str,
        "GOOGLE_MAPS_BROWSER_API_KEY": settings.GOOGLE_MAPS_BROWSER_API_KEY,
    })


# ----------------------------------------------------------------------------- Tracking AJAX Endpoints
@require_POST
def api_start_tracking(request, pk):
    """Start live GPS journey."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)
    try:
        session = start_tracking_session(pk, user)
        return JsonResponse({
            "success": True,
            "session_id": session.pk,
            "status": session.status,
            "message": "Live journey started.",
        })
    except FoodBridgeError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except PermissionDenied as e:
        return JsonResponse({"error": str(e)}, status=403)


@require_POST
def api_update_location(request, pk):
    """Receive live coordinates from recipient's browser."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)

    try:
        data = json.loads(request.body) if request.body else request.POST
        lat = data.get("latitude")
        lng = data.get("longitude")
        acc = data.get("accuracy")
        session = update_tracking_location(pk, user, lat, lng, acc)
        return JsonResponse({
            "success": True,
            "session_id": session.pk,
            "status": session.status,
            "distance_meters": session.last_distance_meters,
            "last_updated": session.last_updated.isoformat() if session.last_updated else None,
        })
    except FoodBridgeError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def api_stop_tracking(request, pk):
    """Stop live location sharing."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)

    try:
        stop_tracking_session(pk, user, reason="user_stopped")
        return JsonResponse({"success": True, "message": "Location sharing stopped."})
    except FoodBridgeError as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_GET
def api_tracking_status(request, pk):
    """Hotel polling endpoint to get live position and ETA of incoming recipient."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)

    req = get_object_or_404(
        PickupRequest.objects.select_related("listing__hotel__user", "ngo", "individual"),
        pk=pk,
    )
    # Ensure hotel ownership or recipient ownership
    is_hotel = (req.listing.hotel.user == user)
    is_recipient = (
        (req.ngo and req.ngo.user == user)
        or (req.individual and req.individual.user == user)
    )
    if not (is_hotel or is_recipient or user.is_admin_role):
        return JsonResponse({"error": "Permission denied for this pickup request."}, status=403)

    session = req.tracking_sessions.order_by("-started_at").first()
    if not session:
        return JsonResponse({"active": False, "status": "no_session"})

    return JsonResponse({
        "active": session.is_active,
        "is_stale": session.is_stale,
        "status": session.status,
        "status_display": session.get_status_display(),
        "latitude": session.current_latitude,
        "longitude": session.current_longitude,
        "accuracy": session.accuracy,
        "distance_meters": session.last_distance_meters,
        "last_updated": session.last_updated.isoformat() if session.last_updated else None,
        "last_updated_human": session.last_updated.strftime("%H:%M:%S") if session.last_updated else "Never",
        "recipient_name": req.recipient_name,
        "request_status": req.status,
    })
