from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import admin_required
from accounts.forms import VerificationDecisionForm
from accounts.models import Role, User, Verification
from accounts.services import set_verification
from core.exceptions import FoodBridgeError
from core.handover_service import unlock_handover
from core.listings_service import remove_listing
from core.models import ActivityLog, CodeStatus, FoodListing, HandoverCode, ListingReport, ListingStatus, ReportStatus
from core.moderation_service import dismiss_report, remove_reported_listing

from . import reports
from .forms import ModerationDecisionForm, RemoveListingForm

RECIPIENT_ROLES = [Role.HOTEL, Role.NGO, Role.INDIVIDUAL]


@admin_required
def dashboard(request):
    pending = User.objects.filter(verification_status=Verification.PENDING).exclude(role=Role.ADMIN)
    context = {
        "pending_count": pending.count(),
        "hotel_count": User.objects.filter(role=Role.HOTEL, verification_status=Verification.APPROVED).count(),
        "ngo_count": User.objects.filter(role=Role.NGO, verification_status=Verification.APPROVED).count(),
        "individual_count": User.objects.filter(role=Role.INDIVIDUAL, verification_status=Verification.APPROVED).count(),
        "open_reports": ListingReport.objects.filter(status=ReportStatus.OPEN).count(),
        "live_listings": FoodListing.objects.filter(status=ListingStatus.POSTED).count(),
        "locked_count": HandoverCode.objects.filter(status=CodeStatus.LOCKED).count(),
        "recent_activity": ActivityLog.objects.select_related("actor")[:12],
    }
    return render(request, "console/dashboard.html", context)


@admin_required
def verification_queue(request):
    users = (
        User.objects.filter(role__in=RECIPIENT_ROLES)
        .exclude(verification_status=Verification.APPROVED)
        .select_related("hotel_profile", "ngo_profile", "individual_profile")
        .order_by("date_joined")
    )
    return render(request, "console/verification_queue.html", {"users": users})


@admin_required
def verification_decide(request, user_id):
    target = get_object_or_404(User.objects.filter(role__in=RECIPIENT_ROLES), pk=user_id)
    if request.method == "POST":
        form = VerificationDecisionForm(request.POST)
        if form.is_valid():
            mapping = {
                "approve": Verification.APPROVED,
                "reject": Verification.REJECTED,
                "suspend": Verification.SUSPENDED,
            }
            status = mapping[form.cleaned_data["decision"]]
            set_verification(target, status, request.user, form.cleaned_data["note"])
            messages.success(request, f"{target.display_name} is now {Verification(status).label.lower()}.")
            return redirect("console:verification_queue")
    else:
        form = VerificationDecisionForm()
    return render(request, "console/verification_decide.html", {"target": target, "form": form})


@admin_required
def user_list(request):
    users = User.objects.filter(role__in=RECIPIENT_ROLES).select_related("hotel_profile", "ngo_profile", "individual_profile")
    role_filter = request.GET.get("role")
    if role_filter in set(RECIPIENT_ROLES):
        users = users.filter(role=role_filter)
    return render(request, "console/user_list.html", {"users": users, "role_filter": role_filter})


@admin_required
def user_reactivate(request, user_id):
    target = get_object_or_404(User.objects.filter(role__in=RECIPIENT_ROLES), pk=user_id)
    if request.method == "POST":
        set_verification(target, Verification.APPROVED, request.user, "Reactivated by admin")
        messages.success(request, f"{target.display_name} reactivated.")
    return redirect("console:user_list")


@admin_required
def reports_page(request):
    context = {
        "summary": reports.summary(),
        "monthly": reports.monthly_summary(),
        "top_hotels": reports.top_hotels(),
        "top_recipients": reports.top_recipients(),
    }
    return render(request, "console/reports.html", context)


@admin_required
def reports_csv(request):
    return reports.donations_csv()


@admin_required
def activity_log(request):
    entries = ActivityLog.objects.select_related("actor")[:300]
    return render(request, "console/activity_log.html", {"entries": entries})


@admin_required
def locked_pickups(request):
    locked = (
        HandoverCode.objects.filter(status=CodeStatus.LOCKED)
        .select_related("pickup_request__listing__hotel", "pickup_request__ngo")
        .prefetch_related("attempts__actor")
        .order_by("-locked_at")
    )
    return render(request, "console/locked_pickups.html", {"locked": locked})


@admin_required
def unlock_pickup(request, pk):
    if request.method == "POST":
        try:
            unlock_handover(pk, request.user)
            messages.success(request, f"Pickup #{pk} unlocked. The NGO has a new code and the hotel can try again.")
        except FoodBridgeError as error:
            messages.error(request, str(error))
    return redirect("console:locked_pickups")


# ----------------------------------------------------------------------------- listings and moderation
@admin_required
def listings_page(request):
    """Every listing on the platform, with a Remove action for anything that shouldn't be there."""
    listings = (
        FoodListing.objects.select_related("hotel")
        .prefetch_related("items", "requests", "reports")
        .order_by("-created_at")
    )
    status = request.GET.get("status", "")
    if status in ListingStatus.values:
        listings = listings.filter(status=status)
    else:
        status = ""
    q = request.GET.get("q", "").strip()
    if q:
        listings = listings.filter(hotel__name__icontains=q) | listings.filter(title__icontains=q)
    return render(
        request,
        "console/listings.html",
        {"listings": listings[:200], "status": status, "q": q, "statuses": ListingStatus.choices},
    )


@admin_required
def listing_remove(request, pk):
    listing = get_object_or_404(FoodListing.objects.select_related("hotel"), pk=pk)
    if request.method == "POST":
        form = RemoveListingForm(request.POST)
        if form.is_valid():
            try:
                remove_listing(listing, request.user, form.cleaned_data["reason"])
                ListingReport.objects.filter(listing=listing, status=ReportStatus.OPEN).update(
                    status=ReportStatus.ACTIONED, resolved_by=request.user, resolution_note=form.cleaned_data["reason"][:300]
                )
                messages.success(request, f"Listing #{listing.pk} removed. {listing.hotel.name} has been told why.")
                return redirect("console:listings")
            except FoodBridgeError as error:
                messages.error(request, str(error))
    else:
        form = RemoveListingForm()
    return render(request, "console/listing_remove.html", {"listing": listing, "form": form})


@admin_required
def moderation_queue(request):
    show = request.GET.get("show", "open")
    reports_qs = ListingReport.objects.select_related("listing__hotel", "reporter", "resolved_by").prefetch_related("listing__items")
    if show == "closed":
        reports_qs = reports_qs.exclude(status=ReportStatus.OPEN)
    else:
        show = "open"
        reports_qs = reports_qs.filter(status=ReportStatus.OPEN)
    return render(request, "console/moderation.html", {"reports": reports_qs[:100], "show": show})


@admin_required
def moderation_decide(request, pk):
    report = get_object_or_404(ListingReport.objects.select_related("listing__hotel", "reporter"), pk=pk)
    if request.method == "POST":
        form = ModerationDecisionForm(request.POST)
        if form.is_valid():
            note = form.cleaned_data["note"]
            try:
                if form.cleaned_data["decision"] == "remove":
                    remove_reported_listing(report, request.user, note)
                    messages.success(request, f"Listing #{report.listing_id} removed and its reports closed.")
                else:
                    dismiss_report(report, request.user, note)
                    messages.success(request, "Report dismissed. The listing stays up.")
                return redirect("console:moderation")
            except FoodBridgeError as error:
                messages.error(request, str(error))
    else:
        form = ModerationDecisionForm()
    return render(request, "console/moderation_decide.html", {"report": report, "form": form})
