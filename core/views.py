from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponseServerError
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.decorators import hotel_required, recipient_required, role_required
from accounts.models import Role, User, Verification

from .exceptions import FoodBridgeError
from .forms import (
    FoodItemFormSet,
    HandoverCodeForm,
    ListingEditForm,
    ListingForm,
    NGONeedForm,
    OnTheWayForm,
    PickupRequestForm,
    ReasonForm,
    ReportForm,
    RepostForm,
)
from .geo import haversine_km
from .handover_service import confirm_handover as confirm_handover_service
from .handover_service import regenerate_code, visible_code
from .listings_service import cancel_listing, create_listing, repost_listing
from .models import (
    MAX_PICKUP_ATTEMPTS,
    FoodCategory,
    FoodItem,
    FoodListing,
    ListingReport,
    ListingStatus,
    NeedStatus,
    NGONeed,
    Notification,
    PickupRequest,
    ReportStatus,
    RequestStatus,
)
from .moderation_service import report_listing
from .requests_service import cancel_request, confirm_request, create_request, reject_request, safe_until_check
from .requests_service import mark_on_the_way as mark_on_the_way_service


def _as_aware(value):
    if value and timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


def _local_input(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def landing(request):
    verified = User.objects.filter(verification_status=Verification.APPROVED)
    collected = PickupRequest.objects.filter(status=RequestStatus.COLLECTED)
    live_listings = list(
        FoodListing.objects.filter(status=ListingStatus.POSTED)
        .select_related("hotel")
        .prefetch_related("items", "requests", "photos")
        .order_by("-created_at")[:6]
    )
    for listing in live_listings:
        listing.mark_expired_if_needed()
    live_listings = [l for l in live_listings if l.is_live]

    recent_requests = list(
        PickupRequest.objects.select_related("listing__hotel", "ngo", "individual")
        .order_by("-requested_at")[:5]
    )

    context = {
        "hotel_count": verified.filter(role=Role.HOTEL).count(),
        "ngo_count": verified.filter(role=Role.NGO).count(),
        "individual_count": verified.filter(role=Role.INDIVIDUAL).count(),
        "servings_collected": collected.aggregate(total=Sum("amount"))["total"] or 0,
        "pickups_collected": collected.count(),
        "live_listings": live_listings,
        "recent_requests": recent_requests,
    }
    return render(request, "core/landing.html", context)


# ============================================================== Hotel: listings
@hotel_required
def hotel_dashboard(request):
    profile = request.user.profile
    listings = list(profile.listings.prefetch_related("items", "requests", "photos"))
    for listing in listings:
        listing.mark_expired_if_needed()
    live = [l for l in listings if l.is_live]
    context = {
        "listings": listings,
        "live_count": len(live),
        "servings_on_offer": sum(l.servings_available for l in live),
        "pending_count": PickupRequest.objects.filter(listing__hotel=profile, status=RequestStatus.REQUESTED).count(),
        "collected_servings": PickupRequest.objects.filter(listing__hotel=profile, status=RequestStatus.COLLECTED).aggregate(
            total=Sum("amount")
        )["total"]
        or 0,
    }
    return render(request, "core/hotel_dashboard.html", context)


@hotel_required
def listing_create(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        formset = FoodItemFormSet(request.POST, prefix="items", queryset=FoodItem.objects.none())
        if form.is_valid() and formset.is_valid():
            items_data = []
            for item_form in formset.forms:
                if item_form in formset.deleted_forms or not item_form.cleaned_data:
                    continue
                cleaned = {k: v for k, v in item_form.cleaned_data.items() if k not in ("id", "DELETE")}
                if cleaned.get("name"):
                    items_data.append(cleaned)
            if not items_data:
                messages.error(request, "Add at least one food item.")
            else:
                data = form.cleaned_data
                listing = create_listing(
                    hotel=profile,
                    total_servings=data["total_servings"],
                    pickup_window_start=_as_aware(data["pickup_window_start"]),
                    pickup_window_end=_as_aware(data["pickup_window_end"]),
                    safe_until=_as_aware(data["safe_until"]),
                    items_data=items_data,
                    photo_files=data.get("photos") or [],
                    title=data.get("title", ""),
                    pickup_location=data.get("pickup_location", ""),
                    contact_phone=data.get("contact_phone", ""),
                    storage_notes=data.get("storage_notes", ""),
                )
                messages.success(request, "Listing posted. Nearby NGOs are being notified.")
                return redirect("core:listing_detail", pk=listing.pk)
    else:
        form = ListingForm(initial={"pickup_location": profile.address, "contact_phone": profile.phone})
        formset = FoodItemFormSet(prefix="items", queryset=FoodItem.objects.none())
    return render(request, "core/listing_form.html", {"form": form, "formset": formset, "mode": "create"})


@hotel_required
def listing_edit(request, pk):
    profile = request.user.profile
    listing = get_object_or_404(FoodListing, pk=pk, hotel=profile)
    if listing.status != ListingStatus.POSTED:
        messages.error(request, "Only a live listing can be edited.")
        return redirect("core:listing_detail", pk=pk)
    if request.method == "POST":
        form = ListingEditForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            listing.title = data["title"].strip()
            listing.pickup_location = data["pickup_location"].strip()
            listing.contact_phone = data["contact_phone"].strip()
            listing.storage_notes = data["storage_notes"].strip()
            listing.pickup_window_start = _as_aware(data["pickup_window_start"])
            listing.pickup_window_end = _as_aware(data["pickup_window_end"])
            listing.safe_until = _as_aware(data["safe_until"])
            listing.save(
                update_fields=[
                    "title", "pickup_location", "contact_phone", "storage_notes",
                    "pickup_window_start", "pickup_window_end", "safe_until",
                ]
            )
            messages.success(request, "Listing updated.")
            return redirect("core:listing_detail", pk=pk)
    else:
        form = ListingEditForm(
            initial={
                "title": listing.title,
                "pickup_location": listing.pickup_location or profile.address,
                "contact_phone": listing.contact_phone or profile.phone,
                "storage_notes": listing.storage_notes,
                "pickup_window_start": _local_input(listing.pickup_window_start),
                "pickup_window_end": _local_input(listing.pickup_window_end),
                "safe_until": _local_input(listing.safe_until),
            }
        )
    return render(request, "core/listing_edit.html", {"form": form, "listing": listing})


@hotel_required
def listing_cancel(request, pk):
    profile = request.user.profile
    listing = get_object_or_404(FoodListing, pk=pk, hotel=profile)
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            try:
                cancel_listing(listing, request.user, form.cleaned_data["reason"])
                messages.success(request, "Listing closed. Anyone with an open request has been told.")
                return redirect("core:hotel_dashboard")
            except FoodBridgeError as error:
                messages.error(request, str(error))
    else:
        form = ReasonForm()
    return render(
        request,
        "core/reason_form.html",
        {
            "form": form, "title": "Close this listing", "cta": "Close listing",
            "intro": "Closing a listing takes it off the board and cancels any open requests on it. NGOs are told why.",
            "back_url": "core:hotel_dashboard",
        },
    )


@hotel_required
def listing_repost(request, pk):
    profile = request.user.profile
    original = get_object_or_404(FoodListing, pk=pk, hotel=profile)
    if request.method == "POST":
        form = RepostForm(request.POST)
        if form.is_valid():
            listing = repost_listing(
                original,
                pickup_window_start=_as_aware(form.cleaned_data["pickup_window_start"]),
                pickup_window_end=_as_aware(form.cleaned_data["pickup_window_end"]),
                safe_until=_as_aware(form.cleaned_data["safe_until"]),
            )
            messages.success(request, "Listing reposted with the same items.")
            return redirect("core:listing_detail", pk=listing.pk)
    else:
        form = RepostForm()
    return render(request, "core/listing_repost.html", {"form": form, "original": original})


@hotel_required
def hotel_requests(request):
    profile = request.user.profile
    base = PickupRequest.objects.filter(listing__hotel=profile).select_related(
        "listing", "ngo", "individual", "handover"
    )
    incoming = base.filter(status=RequestStatus.REQUESTED)
    in_progress = base.filter(status__in=[RequestStatus.CONFIRMED, RequestStatus.ON_THE_WAY])
    return render(request, "core/hotel_requests.html", {"incoming": incoming, "in_progress": in_progress})


@hotel_required
def request_confirm(request, pk):
    profile = request.user.profile
    pickup_request = get_object_or_404(PickupRequest, pk=pk, listing__hotel=profile)
    if request.method == "POST":
        try:
            confirm_request(pickup_request.pk, request.user)
            messages.success(request, "Request confirmed. The recipient now has a pickup code.")
        except FoodBridgeError as error:
            messages.error(request, str(error))
    return redirect("core:hotel_requests")


@hotel_required
def request_reject(request, pk):
    profile = request.user.profile
    pickup_request = get_object_or_404(PickupRequest, pk=pk, listing__hotel=profile)
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            try:
                reject_request(pickup_request.pk, request.user, form.cleaned_data["reason"])
                messages.success(request, "Request declined.")
                return redirect("core:hotel_requests")
            except FoodBridgeError as error:
                messages.error(request, str(error))
    else:
        form = ReasonForm()
    return render(
        request,
        "core/reason_form.html",
        {
            "form": form, "title": "Decline this request", "cta": "Decline request",
            "intro": f"{pickup_request.recipient_name} asked for {pickup_request.amount} servings. They'll see your reason.",
            "back_url": "core:hotel_requests",
        },
    )


@hotel_required
def confirm_handover(request, pk):
    profile = request.user.profile
    pickup_request = get_object_or_404(
        PickupRequest.objects.select_related("ngo", "individual", "listing", "handover"), pk=pk, listing__hotel=profile
    )
    if request.method == "POST":
        form = HandoverCodeForm(request.POST)
        if form.is_valid():
            try:
                confirm_handover_service(
                    pickup_request.pk, form.cleaned_data["code"], request.user, ip=request.META.get("REMOTE_ADDR")
                )
                messages.success(request, "Handover confirmed. Thank you for donating!")
                return redirect("core:hotel_requests")
            except FoodBridgeError as error:
                messages.error(request, str(error))
                return redirect("core:confirm_handover", pk=pickup_request.pk)  # fresh counters, no re-post on refresh
    else:
        form = HandoverCodeForm()
    handover = getattr(pickup_request, "handover", None)
    context = {
        "form": form,
        "pickup_request": pickup_request,
        "handover": handover,
        "attempts": handover.attempts.select_related("actor")[:8] if handover else [],
        "max_attempts": MAX_PICKUP_ATTEMPTS,
        "attempt_slots": range(1, MAX_PICKUP_ATTEMPTS + 1),
    }
    return render(request, "core/confirm_handover.html", context)


@hotel_required
def hotel_history(request):
    """Completed, cancelled and expired donations in one timeline, filterable by outcome."""
    profile = request.user.profile
    rows = []
    closed_requests = PickupRequest.objects.filter(
        listing__hotel=profile,
        status__in=[RequestStatus.COLLECTED, RequestStatus.REJECTED, RequestStatus.CANCELLED, RequestStatus.EXPIRED],
    ).select_related("listing", "ngo", "individual")
    for r in closed_requests:
        bucket = {"collected": "completed", "expired": "expired"}.get(r.status, "cancelled")
        rows.append(
            {
                "when": r.collected_at or r.requested_at, "title": r.listing.display_title, "listing_id": r.listing_id,
                "who": r.recipient_name, "servings": r.amount, "bucket": bucket, "status": r.status,
                "note": r.reject_reason or r.cancel_reason,
            }
        )
    closed_listings = (
        profile.listings.filter(status__in=[ListingStatus.EXPIRED, ListingStatus.CANCELLED, ListingStatus.REMOVED])
        .exclude(requests__status=RequestStatus.COLLECTED)
        .prefetch_related("items")
        .distinct()
    )
    for l in closed_listings:
        rows.append(
            {
                "when": l.created_at, "title": l.display_title, "listing_id": l.pk, "who": "Listing closed",
                "servings": l.total_servings, "bucket": "expired" if l.status == ListingStatus.EXPIRED else "cancelled",
                "status": l.status, "note": l.removal_reason or l.cancel_reason,
            }
        )
    rows.sort(key=lambda row: row["when"], reverse=True)
    counts = {key: sum(1 for row in rows if row["bucket"] == key) for key in ("completed", "cancelled", "expired")}
    counts["all"] = len(rows)
    show = request.GET.get("show", "all")
    if show in ("completed", "cancelled", "expired"):
        rows = [row for row in rows if row["bucket"] == show]
    else:
        show = "all"
    return render(request, "core/hotel_history.html", {"rows": rows, "counts": counts, "show": show})


@hotel_required
def impact_certificate(request):
    profile = request.user.profile
    collected = PickupRequest.objects.filter(listing__hotel=profile, status=RequestStatus.COLLECTED)
    total_servings = sum(r.amount for r in collected)
    recipients_served = len({r.ngo_id or f"i{r.individual_id}" for r in collected})
    pickups = collected.count()
    co2_kg_per_serving = 2.5  # estimate: average surplus-meal footprint avoided, for illustration only
    co2_estimate_kg = round(total_servings * co2_kg_per_serving, 1)
    context = {
        "hotel": profile,
        "total_servings": total_servings,
        "ngos_served": recipients_served,
        "pickups": pickups,
        "co2_estimate_kg": co2_estimate_kg,
        "co2_kg_per_serving": co2_kg_per_serving,
        "generated_at": timezone.now(),
    }
    return render(request, "core/impact_certificate.html", context)


# ============================================================== Recipients: browse & request
PICKUP_WITHIN_CHOICES = [(1, "1 hour"), (2, "2 hours"), (4, "4 hours"), (8, "8 hours")]
SORT_CHOICES = [("nearest", "Nearest first"), ("expiring", "Safe-until soonest"), ("servings", "Most servings")]


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@recipient_required
def ngo_dashboard(request):
    """Browse live food. Shared by NGOs and individual recipients."""
    profile = request.user.profile
    listings = list(
        FoodListing.objects.filter(status=ListingStatus.POSTED)
        .select_related("hotel")
        .prefetch_related("items", "requests", "photos")
    )
    listings = [listing for listing in listings if listing.visible_to(profile)]

    for listing in listings:
        listing.distance_km = (
            haversine_km(profile.latitude, profile.longitude, listing.hotel.latitude, listing.hotel.longitude)
            if profile.has_pin and listing.hotel.has_pin
            else None
        )

    g = request.GET
    q = g.get("q", "").strip()
    category = g.get("category") if g.get("category") in FoodCategory.values else ""
    max_distance = _to_float(g.get("max_distance"))
    min_safe_minutes = _to_int(g.get("min_safe_minutes"))
    min_servings = _to_int(g.get("min_servings"))
    pickup_within = _to_int(g.get("pickup_within"))
    sort = g.get("sort") if g.get("sort") in dict(SORT_CHOICES) else "nearest"

    if q:
        needle = q.lower()
        listings = [
            l for l in listings
            if needle in " ".join([l.hotel.name, l.location_text, l.display_title, l.hotel.address]).lower()
        ]
    if category:
        listings = [l for l in listings if any(i.category == category for i in l.items.all())]
    if max_distance is not None:
        listings = [l for l in listings if l.distance_km is not None and l.distance_km <= max_distance]
    if min_safe_minutes is not None:
        listings = [l for l in listings if l.seconds_until_unsafe / 60 >= min_safe_minutes]
    if min_servings is not None:
        listings = [l for l in listings if l.servings_available >= min_servings]
    if pickup_within is not None:
        cutoff = timezone.now() + timedelta(hours=pickup_within)
        listings = [l for l in listings if l.pickup_window_end <= cutoff]

    if sort == "expiring":
        listings.sort(key=lambda l: l.safe_until)
    elif sort == "servings":
        listings.sort(key=lambda l: -l.servings_available)
    else:
        listings.sort(key=lambda l: (l.distance_km is None, l.distance_km or 0))

    filter_count = sum(1 for v in (q, category, max_distance, min_safe_minutes, min_servings, pickup_within) if v not in ("", None))
    context = {
        "listings": listings,
        "q": q,
        "category": category,
        "max_distance": g.get("max_distance", ""),
        "min_safe_minutes": g.get("min_safe_minutes", ""),
        "min_servings": g.get("min_servings", ""),
        "pickup_within": pickup_within,
        "sort": sort,
        "categories": FoodCategory.choices,
        "pickup_within_choices": PICKUP_WITHIN_CHOICES,
        "sort_choices": SORT_CHOICES,
        "filter_count": filter_count,
        "first_look_note": any(l.first_look_active for l in listings) and request.user.is_ngo,
    }
    return render(request, "core/ngo_dashboard.html", context)


def listing_detail(request, pk):
    listing = get_object_or_404(
        FoodListing.objects.select_related("hotel").prefetch_related("items", "photos", "requests"), pk=pk
    )
    listing.mark_expired_if_needed()
    user = request.user

    is_owner = user.is_authenticated and user.is_hotel and user.is_verified and listing.hotel_id == getattr(user.profile, "pk", None)
    my_request = None
    travel_note = None
    request_form = None
    can_report = False
    my_open_report = False

    if user.is_authenticated and user.is_recipient and user.is_verified:
        profile = user.profile
        if not listing.visible_to(profile) and not is_owner:
            own = PickupRequest.objects.filter(listing=listing, status__in=RequestStatus.active()).filter(
                Q(ngo=profile) if user.is_ngo else Q(individual=profile)
            )
            if not own.exists():
                messages.info(request, "This listing isn't open to you yet. The closest matches get a 10-minute first look.")
                return redirect("core:ngo_dashboard")
        owner_filter = Q(ngo=profile) if user.is_ngo else Q(individual=profile)
        my_request = PickupRequest.objects.filter(listing=listing, status__in=RequestStatus.active()).filter(owner_filter).first()
        if listing.is_live and my_request is None:
            request_form = PickupRequestForm()
            _blocked, _minutes, _source, travel_note = safe_until_check(listing, profile)
        can_report = True
    elif not is_owner and not (user.is_authenticated and user.is_admin_role):
        if not listing.is_live:
            messages.info(request, "This listing is no longer available.")
            return redirect("core:landing")
    if user.is_authenticated and user.is_hotel and user.is_verified and not is_owner:
        can_report = True
    if can_report:
        my_open_report = ListingReport.objects.filter(listing=listing, reporter=user, status=ReportStatus.OPEN).exists()

    hotel_requests_qs = listing.requests.select_related("ngo", "individual") if is_owner else None
    return render(
        request,
        "core/listing_detail.html",
        {
            "listing": listing,
            "is_owner": is_owner,
            "my_request": my_request,
            "request_form": request_form,
            "travel_note": travel_note,
            "hotel_requests_qs": hotel_requests_qs,
            "can_report": can_report and listing.status in (ListingStatus.POSTED, ListingStatus.FULFILLED),
            "my_open_report": my_open_report,
            "max_servings": min(listing.servings_available, getattr(user.profile, "daily_capacity", listing.servings_available))
            if user.is_authenticated and user.is_recipient and user.profile
            else listing.servings_available,
        },
    )


@login_required
def listing_report(request, pk):
    user = request.user
    if user.role not in (Role.HOTEL, Role.NGO, Role.INDIVIDUAL) or not user.is_verified:
        messages.error(request, "Only verified accounts can report a listing.")
        return redirect("accounts:home")
    listing = get_object_or_404(FoodListing.objects.select_related("hotel"), pk=pk)
    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            try:
                report_listing(listing, user, form.cleaned_data["reason"], form.cleaned_data["details"])
                messages.success(request, "Thanks. An admin will review this listing.")
                return redirect("core:listing_detail", pk=pk)
            except FoodBridgeError as error:
                messages.error(request, str(error))
                return redirect("core:listing_detail", pk=pk)
    else:
        form = ReportForm()
    return render(request, "core/report_form.html", {"form": form, "listing": listing})


@recipient_required
def request_create(request, pk):
    profile = request.user.profile
    listing = get_object_or_404(FoodListing, pk=pk)
    if request.method == "POST":
        form = PickupRequestForm(request.POST)
        if form.is_valid():
            try:
                create_request(listing, profile, form.cleaned_data["amount"])
                messages.success(request, "Request sent. You'll be notified when the hotel responds.")
            except FoodBridgeError as error:
                messages.error(request, str(error))
        else:
            messages.error(request, "Enter a whole number of servings, 1 or more.")
    return redirect("core:listing_detail", pk=pk)


ACTIVE_STATUSES = RequestStatus.active()


@recipient_required
def my_requests(request):
    profile = request.user.profile
    owner = {"ngo": profile} if request.user.is_ngo else {"individual": profile}
    everything = list(
        PickupRequest.objects.filter(**owner).select_related("listing", "listing__hotel", "handover")
    )
    view = request.GET.get("view", "active")
    if view not in ("active", "history"):
        view = "active"
    active = [r for r in everything if r.status in ACTIVE_STATUSES]
    history = [r for r in everything if r.status not in ACTIVE_STATUSES]
    shown = active if view == "active" else history
    for pickup in shown:
        pickup.display_code = visible_code(pickup)  # None unless confirmed/on-the-way and the code is still valid
    context = {
        "pickup_requests": shown,
        "view": view,
        "active_count": len(active),
        "history_count": len(history),
        "collected_servings": sum(r.amount for r in everything if r.status == RequestStatus.COLLECTED),
        "on_the_way_form": OnTheWayForm(),
    }
    return render(request, "core/my_requests.html", context)


@recipient_required
def code_regenerate(request, pk):
    owner = {"ngo": request.user.profile} if request.user.is_ngo else {"individual": request.user.profile}
    pickup_request = get_object_or_404(PickupRequest, pk=pk, **owner)
    if request.method == "POST":
        try:
            regenerate_code(pickup_request.pk, request.user)
            messages.success(request, "New pickup code issued. The old one no longer works.")
        except FoodBridgeError as error:
            messages.error(request, str(error))
    return redirect("core:my_requests")


@recipient_required
def mark_on_the_way(request, pk):
    owner = {"ngo": request.user.profile} if request.user.is_ngo else {"individual": request.user.profile}
    pickup_request = get_object_or_404(PickupRequest, pk=pk, **owner)
    if request.method == "POST":
        form = OnTheWayForm(request.POST)
        if form.is_valid():
            try:
                mark_on_the_way_service(pickup_request.pk, form.cleaned_data["eta_minutes"])
                messages.success(request, "The hotel knows you're on your way.")
            except FoodBridgeError as error:
                messages.error(request, str(error))
        else:
            messages.error(request, "Enter how many minutes away you are (1 to 240).")
    return redirect("core:my_requests")


@login_required
def request_cancel(request, pk):
    user = request.user
    pickup_request = get_object_or_404(PickupRequest.objects.select_related("ngo", "individual", "listing"), pk=pk)
    profile_pk = getattr(user.profile, "pk", None)
    owns_as_recipient = (
        user.is_recipient
        and user.is_verified
        and profile_pk is not None
        and (pickup_request.ngo_id if user.is_ngo else pickup_request.individual_id) == profile_pk
    )
    owns_as_hotel = user.is_hotel and user.is_verified and pickup_request.listing.hotel_id == profile_pk
    if not (owns_as_recipient or owns_as_hotel):
        messages.error(request, "You can't cancel this request.")
        return redirect("accounts:home")
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip() or ("Cancelled by the recipient" if owns_as_recipient else "Cancelled by the hotel")
        try:
            cancel_request(pickup_request.pk, user, reason)
            messages.success(request, "Request cancelled.")
        except FoodBridgeError as error:
            messages.error(request, str(error))
    return redirect("core:my_requests" if owns_as_recipient else "core:hotel_requests")


# ============================================================== Needs board
@role_required(Role.HOTEL, Role.NGO)
def needs_board(request):
    user = request.user
    if request.method == "POST" and user.is_ngo:
        form = NGONeedForm(request.POST)
        if form.is_valid():
            need = form.save(commit=False)
            need.ngo = user.profile
            need.save()
            messages.success(request, "Need posted to the board.")
            return redirect("core:needs_board")
    else:
        form = NGONeedForm() if user.is_ngo else None

    needs = list(NGONeed.objects.filter(status=NeedStatus.OPEN).select_related("ngo").order_by("needed_by"))
    my_need_ids = {n.pk for n in needs if user.is_ngo and n.ngo_id == user.profile.pk}
    return render(request, "core/needs_board.html", {"needs": needs, "form": form, "my_need_ids": my_need_ids})


@role_required(Role.NGO)
def need_close(request, pk):
    profile = request.user.profile
    need = get_object_or_404(NGONeed, pk=pk, ngo=profile)
    if request.method == "POST":
        need.status = NeedStatus.CLOSED
        need.save(update_fields=["status"])
        messages.success(request, "Need marked as closed.")
    return redirect("core:needs_board")


# ============================================================== Notifications
@login_required
def notifications(request):
    items = list(request.user.notifications.all()[:100])
    unread_ids = [n.pk for n in items if not n.is_read]
    for n in items:
        n.was_unread = not n.is_read
    if unread_ids:
        Notification.objects.filter(pk__in=unread_ids).update(is_read=True)
    return render(request, "core/notifications.html", {"items": items})


# ============================================================== Error handlers
def error_400(request, exception=None):
    return render(request, "errors/400.html", status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return HttpResponseServerError(render_to_string("errors/500.html"))
