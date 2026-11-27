"""Smart Match: rank verified NGOs for a freshly posted listing and give the
best few a 10-minute first look before everyone else can see it.

Documented weighted sum (weights sum to 100):
- item compatibility: 25
- quantity coverage: 25
- distance: 15
- pickup feasibility/time: 10
- safety deadline: 10
- recipient capacity: 5
- reliability: 10

NGO food preference profile (preferred items, categories, dietary restrictions,
beneficiary count, typical servings, preferred collection areas) BOOSTS scores.
It NEVER blocks an NGO from requesting other available foods.
"""
from django.utils import timezone
from accounts.models import NGOProfile, Verification

from .constants import MATCH_WEIGHTS
from .geo import haversine_km, estimate_travel_minutes
from .models import FIRST_LOOK_TOP_N, ListingMatch
from .notify import notify
from .reliability import reliability_score


def calculate_match_details(ngo, listing, distance_km=None):
    """
    Computes transparent multi-factor match score and detailed explanation.
    Returns:
        dict with:
            score (0 to 100),
            breakdown (factor: score),
            explanation (plain language string),
            items_status (dict of item availability)
    """
    listing_items = list(listing.items.all())
    listing_cats = {item.category.lower() for item in listing_items}
    listing_servings = listing.servings_available or listing.total_servings

    # 1. Item compatibility (0 - 25)
    # Check if NGO preferred categories match listing categories
    ngo_prefs = [c.strip().lower() for c in (ngo.preferred_categories or "").split(",") if c.strip()]
    if not ngo_prefs:
        # Default neutral compatibility if no preferences set
        comp_ratio = 0.8
    else:
        matched_cats = listing_cats.intersection(set(ngo_prefs))
        comp_ratio = len(matched_cats) / max(len(listing_cats), 1)
        # Small boost if specific dietary restrictions match
        if ngo.dietary_restrictions:
            comp_ratio = min(1.0, comp_ratio + 0.1)
    score_comp = comp_ratio * MATCH_WEIGHTS["item_compatibility"]

    # 2. Quantity coverage (0 - 25)
    # How well does listing meet NGO typical servings / beneficiary count?
    target_servings = ngo.typical_servings or ngo.beneficiary_count or ngo.daily_capacity or 20
    qty_ratio = min(listing_servings, target_servings) / max(listing_servings, target_servings)
    score_qty = qty_ratio * MATCH_WEIGHTS["quantity_coverage"]

    # 3. Distance (0 - 15)
    hotel = listing.hotel
    if distance_km is None and hotel.has_pin and ngo.has_pin:
        distance_km = haversine_km(hotel.latitude, hotel.longitude, ngo.latitude, ngo.longitude)

    if distance_km is not None:
        dist_factor = 1.0 / (1.0 + (distance_km / 5.0))  # 5km baseline
    else:
        dist_factor = 0.5  # Unknown distance
    score_dist = dist_factor * MATCH_WEIGHTS["distance"]

    # 4. Pickup feasibility / time (0 - 10)
    travel_mins, _source = estimate_travel_minutes(hotel.latitude, hotel.longitude, ngo.latitude, ngo.longitude)
    remaining_mins = max(0, listing.seconds_until_unsafe / 60)
    if travel_mins is not None and remaining_mins > 0:
        if travel_mins < remaining_mins:
            feasibility = min(1.0, (remaining_mins - travel_mins) / remaining_mins)
        else:
            feasibility = 0.0
    else:
        feasibility = 0.7  # Feasible by default
    score_feasibility = feasibility * MATCH_WEIGHTS["pickup_feasibility"]

    # 5. Safety deadline (0 - 10)
    # Listings with comfortable safe window score higher for coordination
    if remaining_mins >= 180:
        safety_factor = 1.0
    elif remaining_mins >= 60:
        safety_factor = 0.8
    elif remaining_mins > 0:
        safety_factor = 0.5
    else:
        safety_factor = 0.0
    score_safety = safety_factor * MATCH_WEIGHTS["safety_deadline"]

    # 6. Recipient capacity (0 - 5)
    capacity = max(ngo.daily_capacity, 1)
    cap_ratio = min(capacity, listing_servings) / max(capacity, listing_servings)
    score_cap = cap_ratio * MATCH_WEIGHTS["recipient_capacity"]

    # 7. Reliability (0 - 10)
    rel = reliability_score(ngo)  # returns 0.0 to 1.0
    score_rel = rel * MATCH_WEIGHTS["reliability"]

    # Total score out of 100
    total_score = round(score_comp + score_qty + score_dist + score_feasibility + score_safety + score_cap + score_rel, 1)

    # Explanation text
    explanations = []
    if distance_km is not None:
        explanations.append(f"{round(distance_km, 1)} km away")
    if comp_ratio >= 0.9:
        explanations.append("matches preferred dietary categories")
    if rel >= 0.8:
        explanations.append("excellent collection reliability")
    if travel_mins is not None:
        explanations.append(f"~{travel_mins} min travel time")
    if not explanations:
        explanations.append("general match based on capacity and distance")

    explanation_str = "; ".join(explanations)

    items_status = [
        {
            "name": item.name,
            "category": item.get_category_display(),
            "quantity": item.quantity,
            "allocated": item.allocated_quantity,
            "remaining": item.remaining_quantity,
            "unit": item.unit,
        }
        for item in listing_items
    ]

    return {
        "score": total_score,
        "percentage": int(round(total_score)),
        "distance_km": distance_km,
        "travel_minutes": travel_mins,
        "breakdown": {
            "item_compatibility": round(score_comp, 1),
            "quantity_coverage": round(score_qty, 1),
            "distance": round(score_dist, 1),
            "pickup_feasibility": round(score_feasibility, 1),
            "safety_deadline": round(score_safety, 1),
            "recipient_capacity": round(score_cap, 1),
            "reliability": round(score_rel, 1),
        },
        "explanation": explanation_str,
        "items_status": items_status,
    }


def rank_ngos_for_listing(listing):
    """
    Returns [(ngo, match_dict, distance_km), ...] best first, for every verified NGO.
    """
    hotel = listing.hotel
    candidates = NGOProfile.objects.filter(user__verification_status=Verification.APPROVED).select_related("user")
    ranked = []
    for ngo in candidates:
        distance_km = None
        if hotel.has_pin and ngo.has_pin:
            distance_km = haversine_km(hotel.latitude, hotel.longitude, ngo.latitude, ngo.longitude)
        match_info = calculate_match_details(ngo, listing, distance_km)
        ranked.append((ngo, match_info, distance_km))

    ranked.sort(key=lambda row: row[1]["score"], reverse=True)
    return ranked


def run_smart_match(listing):
    """
    Creates the ListingMatch 'first look' rows and notifies the chosen NGOs.
    Safe to call even when nobody can be ranked.
    """
    ranked = rank_ngos_for_listing(listing)
    top = ranked[:FIRST_LOOK_TOP_N]
    matches = [
        ListingMatch(listing=listing, ngo=ngo, rank=index + 1, distance_km=distance_km)
        for index, (ngo, _match_info, distance_km) in enumerate(top)
    ]
    ListingMatch.objects.bulk_create(matches)
    for ngo, _match_info, _distance_km in top:
        notify(
            ngo.user,
            "match",
            f"New food posted by {listing.hotel.name}: {listing.display_title} ({listing.servings_available} servings).",
            link="/food/",
        )
    return matches
