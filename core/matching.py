"""Smart Match: rank verified NGOs for a freshly posted listing and give the
best few a 10-minute first look before everyone else can see it."""
from accounts.models import NGOProfile, Verification

from .geo import haversine_km
from .models import FIRST_LOOK_TOP_N, ListingMatch
from .notify import notify
from .reliability import reliability_score


def _score(ngo, listing, distance_km):
    distance_score = 1 / (1 + distance_km) if distance_km is not None else 0.3  # unknown location: middling score
    capacity = max(ngo.daily_capacity, 1)
    fit_score = min(capacity, listing.total_servings) / max(capacity, listing.total_servings)
    return 0.5 * distance_score + 0.2 * fit_score + 0.3 * reliability_score(ngo)


def rank_ngos_for_listing(listing):
    """Returns [(ngo, score, distance_km), ...] best first, for every verified NGO."""
    hotel = listing.hotel
    candidates = NGOProfile.objects.filter(user__verification_status=Verification.APPROVED).select_related("user")
    ranked = []
    for ngo in candidates:
        distance_km = None
        if hotel.has_pin and ngo.has_pin:
            distance_km = haversine_km(hotel.latitude, hotel.longitude, ngo.latitude, ngo.longitude)
        ranked.append((ngo, _score(ngo, listing, distance_km), distance_km))
    ranked.sort(key=lambda row: row[1], reverse=True)
    return ranked


def run_smart_match(listing):
    """Creates the ListingMatch "first look" rows and notifies the chosen NGOs.
    Safe to call even when nobody can be ranked (e.g. no verified NGOs yet)."""
    ranked = rank_ngos_for_listing(listing)
    top = ranked[:FIRST_LOOK_TOP_N]
    matches = [
        ListingMatch(listing=listing, ngo=ngo, rank=index + 1, distance_km=distance_km)
        for index, (ngo, _score_value, distance_km) in enumerate(top)
    ]
    ListingMatch.objects.bulk_create(matches)
    for ngo, _score_value, _distance_km in top:
        notify(
            ngo.user,
            "match",
            f"New food near you from {listing.hotel.name} — you get first look for 10 minutes.",
            link="/food/",
        )
    return matches
