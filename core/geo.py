"""Distance and travel-time estimates. Uses Google Distance Matrix when a key is
configured; otherwise falls back to a haversine-distance estimate so the site
keeps working fully offline."""
import math

from django.conf import settings

AVERAGE_CITY_SPEED_KMPH = 22
PREP_BUFFER_MINUTES = 5
EARTH_RADIUS_KM = 6371


def haversine_km(lat1, lng1, lat2, lng2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1, math.sqrt(a)))


def estimate_travel_minutes(origin_lat, origin_lng, dest_lat, dest_lng):
    """Returns (minutes, source) where source is "google" or "estimate"."""
    if None in (origin_lat, origin_lng, dest_lat, dest_lng):
        return None, "unavailable"

    if settings.GOOGLE_MAPS_API_KEY:
        minutes = _google_distance_matrix_minutes(origin_lat, origin_lng, dest_lat, dest_lng)
        if minutes is not None:
            return minutes, "google"

    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    minutes = (distance_km / AVERAGE_CITY_SPEED_KMPH) * 60 + PREP_BUFFER_MINUTES
    return round(minutes), "estimate"


def _google_distance_matrix_minutes(origin_lat, origin_lng, dest_lat, dest_lng):
    try:
        import requests

        response = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": f"{origin_lat},{origin_lng}",
                "destinations": f"{dest_lat},{dest_lng}",
                "key": settings.GOOGLE_MAPS_API_KEY,
            },
            timeout=5,
        )
        data = response.json()
        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            return None
        return round(element["duration"]["value"] / 60)
    except Exception:
        # Any network, parsing or quota problem: fall back to the haversine estimate.
        return None
