"""The shared FoodBridge domain: listings, requests, needs, notifications, activity."""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.validators import validate_photo_file

FIRST_LOOK_MINUTES = 10
FIRST_LOOK_TOP_N = 5
PICKUP_CODE_LENGTH = 6
MAX_PICKUP_ATTEMPTS = 5      # wrong entries (in total, per pickup) before the code locks
MAX_CODE_REGENERATIONS = 2   # how many times an NGO may ask for a fresh code per pickup


# ----------------------------------------------------------------------------- activity log
class ActivityLog(models.Model):
    """A short, human-readable record of an important action (who did what, when)."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity"
    )
    action = models.CharField(max_length=50, db_index=True)
    message = models.CharField(max_length=300)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action}: {self.message}"


# ----------------------------------------------------------------------------- listings
class FoodCategory(models.TextChoices):
    VEG = "veg", "Vegetarian"
    NON_VEG = "non_veg", "Non-vegetarian"
    VEGAN = "vegan", "Vegan"


class ServingUnit(models.TextChoices):
    SERVINGS = "servings", "servings"
    KG = "kg", "kg"
    PACKETS = "packets", "packets"


class ListingStatus(models.TextChoices):
    POSTED = "posted", "Posted"
    FULFILLED = "fulfilled", "Fully claimed"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"
    REMOVED = "removed", "Removed by admin"


class FoodListing(models.Model):
    hotel = models.ForeignKey("accounts.HotelProfile", on_delete=models.CASCADE, related_name="listings")
    title = models.CharField(
        "Food name", max_length=120, blank=True, help_text='A short headline, e.g. "Veg biryani and raita"'
    )
    pickup_location = models.TextField(
        blank=True, help_text="Where the food is collected. Leave empty to use the hotel's address."
    )
    contact_phone = models.CharField(
        max_length=20, blank=True, help_text="Who to call at pickup. Leave empty to use the hotel's phone."
    )
    storage_notes = models.TextField(
        "Storage and handling notes", blank=True, max_length=500,
        help_text='e.g. "Kept hot above 60 °C, packed in sealed steel containers"',
    )
    total_servings = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    servings_available = models.PositiveIntegerField()
    pickup_window_start = models.DateTimeField()
    pickup_window_end = models.DateTimeField()
    safe_until = models.DateTimeField(help_text="When this food stops being safe to eat")
    status = models.CharField(max_length=10, choices=ListingStatus.choices, default=ListingStatus.POSTED, db_index=True)
    removal_reason = models.CharField(max_length=300, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "safe_until"], name="listing_status_safe_idx"),
        ]

    def __str__(self):
        return f"Listing #{self.pk} by {self.hotel.name}"

    # --- Report vocabulary: what the listing is called on every page -------------
    @property
    def display_title(self):
        if self.title:
            return self.title
        names = [item.name for item in self.items.all()]
        return ", ".join(names[:3]) + (f" +{len(names) - 3} more" if len(names) > 3 else "") if names else f"Listing #{self.pk}"

    @property
    def category_choices(self):
        """The distinct food categories on this listing, as (value, label) pairs, in item order."""
        labels = dict(FoodCategory.choices)
        seen = []
        for item in self.items.all():
            if item.category not in seen:
                seen.append(item.category)
        return [(value, labels[value]) for value in seen]

    @property
    def location_text(self):
        return self.pickup_location.strip() or self.hotel.address

    @property
    def contact_number(self):
        return self.contact_phone.strip() or self.hotel.phone

    @property
    def display_status(self):
        """(key, label) using the words in the project report: available, requested, confirmed,
        collected or expired (plus cancelled / removed for listings that were taken down)."""
        if self.status == ListingStatus.REMOVED:
            return "removed", "Removed"
        if self.status == ListingStatus.CANCELLED:
            return "cancelled", "Cancelled"
        reqs = list(self.requests.all())
        pending = any(r.status == RequestStatus.REQUESTED for r in reqs)
        live = any(r.status in (RequestStatus.CONFIRMED, RequestStatus.ON_THE_WAY) for r in reqs)
        collected = any(r.status == RequestStatus.COLLECTED for r in reqs)
        if self.status == ListingStatus.EXPIRED or (self.status == ListingStatus.POSTED and self.is_past_safe_until):
            return ("collected", "Collected") if collected and self.servings_available == 0 else ("expired", "Expired")
        if self.status == ListingStatus.FULFILLED:
            return ("confirmed", "Confirmed") if live else ("collected", "Collected")
        if pending:
            return "requested", "Requested"
        if live:
            return "confirmed", "Confirmed"
        return "available", "Available"

    # --- Safe-Until Clock -------------------------------------------------------
    @property
    def seconds_until_unsafe(self):
        return int((self.safe_until - timezone.now()).total_seconds())

    @property
    def is_past_safe_until(self):
        return self.seconds_until_unsafe <= 0

    @property
    def is_live(self):
        return self.status == ListingStatus.POSTED and not self.is_past_safe_until and self.servings_available > 0

    # --- Smart Match --------------------------------------------------------------
    @property
    def first_look_ends_at(self):
        return self.created_at + timezone.timedelta(minutes=FIRST_LOOK_MINUTES)

    @property
    def first_look_active(self):
        return timezone.now() < self.first_look_ends_at

    def visible_to(self, recipient_profile):
        """A recipient can see this listing once it's live. All verified NGOs see it immediately.
        Individuals wait for the 10-minute first-look window to end."""
        if not self.is_live:
            return False
        if recipient_profile.__class__.__name__ == "NGOProfile":
            return True
        return not self.first_look_active

    def mark_expired_if_needed(self):
        if self.status == ListingStatus.POSTED and self.is_past_safe_until:
            self.status = ListingStatus.EXPIRED
            self.save(update_fields=["status"])
            return True
        return False


class ListingMatch(models.Model):
    """The NGOs picked for a listing's 10-minute first-look window, best match first."""

    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name="matches")
    ngo = models.ForeignKey("accounts.NGOProfile", on_delete=models.CASCADE, related_name="first_look_matches")
    rank = models.PositiveSmallIntegerField()
    distance_km = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(fields=("listing", "ngo"), name="core_listingmatch_listing_ngo_uniq"),
        ]


class FoodItem(models.Model):
    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=FoodCategory.choices)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit = models.CharField(max_length=10, choices=ServingUnit.choices, default=ServingUnit.SERVINGS)
    cooking_time_note = models.CharField(
        "Cooking time", max_length=120, blank=True, help_text='e.g. "Cooked today at 6:00 PM"'
    )
    allergens_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class ListingPhoto(models.Model):
    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="listings/%Y/%m/", validators=[validate_photo_file])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


# ----------------------------------------------------------------------------- requests
class RequestStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"
    ON_THE_WAY = "on_the_way", "On the way"
    COLLECTED = "collected", "Collected"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"

    @classmethod
    def active(cls):
        return [cls.REQUESTED, cls.CONFIRMED, cls.ON_THE_WAY]

    @classmethod
    def missed(cls):
        """Counted against a recipient's reliability: confirmed, then never collected."""
        return [cls.CANCELLED, cls.EXPIRED]


class PickupRequest(models.Model):
    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name="requests")
    ngo = models.ForeignKey(
        "accounts.NGOProfile", on_delete=models.CASCADE, related_name="requests", null=True, blank=True
    )
    individual = models.ForeignKey(
        "accounts.IndividualProfile", on_delete=models.CASCADE, related_name="requests", null=True, blank=True
    )
    amount = models.PositiveIntegerField("Servings requested", validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=RequestStatus.choices, default=RequestStatus.REQUESTED, db_index=True)

    reject_reason = models.CharField(max_length=300, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    eta_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    on_the_way_at = models.DateTimeField(null=True, blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField("confirmed at", null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    was_approved = models.BooleanField(default=False)  # "was confirmed": kept even if later cancelled, for reliability scoring

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["status"], name="request_status_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "ngo"],
                condition=models.Q(status__in=["requested", "confirmed", "on_the_way"]),
                name="one_active_request_per_ngo_per_listing",
            ),
            models.UniqueConstraint(
                fields=["listing", "individual"],
                condition=models.Q(status__in=["requested", "confirmed", "on_the_way"]),
                name="one_active_request_per_individual_per_listing",
            ),
            models.CheckConstraint(
                condition=(models.Q(ngo__isnull=False, individual__isnull=True) | models.Q(ngo__isnull=True, individual__isnull=False)),
                name="request_has_exactly_one_recipient",
            ),
        ]

    def __str__(self):
        return f"Request #{self.pk}: {self.recipient_name} -> listing #{self.listing_id}"

    STEP_ORDER = ["requested", "confirmed", "on_the_way", "collected"]

    # --- the person or organisation collecting (an NGO or an individual) ----------
    @property
    def recipient(self):
        return self.ngo if self.ngo_id else self.individual

    @property
    def recipient_name(self):
        return self.recipient.name

    @property
    def recipient_user(self):
        return self.recipient.user

    @property
    def recipient_kind(self):
        return "NGO" if self.ngo_id else "Individual"

    @property
    def is_live(self):
        """Confirmed or on the way: the only states in which a handover code means anything."""
        return self.status in (RequestStatus.CONFIRMED, RequestStatus.ON_THE_WAY)

    @property
    def step_index(self):
        try:
            return self.STEP_ORDER.index(self.status)
        except ValueError:
            return -1  # rejected / cancelled / expired: no step is "current"


# ----------------------------------------------------------------------------- handover security
class CodeStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    USED = "used", "Used"
    LOCKED = "locked", "Locked"


class HandoverCode(models.Model):
    """The security code that proves the right NGO really turned up for an approved pickup.

    The 6 digits themselves are NOT stored. Only a random 128-bit `salt` is saved; the code is
    re-derived from (SECRET_KEY, pickup id, salt) whenever it has to be shown to the NGO or checked
    against what the hotel typed. A database dump or the admin panel therefore never reveals a code.
    """

    pickup_request = models.OneToOneField(PickupRequest, on_delete=models.CASCADE, related_name="handover")
    salt = models.CharField(max_length=32)
    status = models.CharField(max_length=8, choices=CodeStatus.choices, default=CodeStatus.ACTIVE, db_index=True)
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(help_text="Same moment the food stops being safe")
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    regenerations = models.PositiveSmallIntegerField(default=0)
    locked_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Handover code for request #{self.pickup_request_id} ({self.get_status_display()})"

    @property
    def is_expired(self):
        return self.status == CodeStatus.ACTIVE and timezone.now() >= self.expires_at

    @property
    def attempts_left(self):
        return max(0, MAX_PICKUP_ATTEMPTS - self.failed_attempts)

    @property
    def regenerations_left(self):
        return max(0, MAX_CODE_REGENERATIONS - self.regenerations)

    @property
    def is_usable(self):
        return self.status == CodeStatus.ACTIVE and not self.is_expired


class AttemptOutcome(models.TextChoices):
    SUCCESS = "success", "Correct code"
    WRONG = "wrong", "Wrong code"
    EXPIRED = "expired", "Code expired"
    BLOCKED = "blocked", "Blocked (locked)"


class HandoverAttempt(models.Model):
    """One row per time a hotel typed a code. The code that was typed is deliberately never saved."""

    handover = models.ForeignKey(HandoverCode, on_delete=models.CASCADE, related_name="attempts")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    outcome = models.CharField(max_length=10, choices=AttemptOutcome.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_outcome_display()} at {self.created_at:%d %b %H:%M:%S}"


# ----------------------------------------------------------------------------- needs board
class NeedStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class NGONeed(models.Model):
    ngo = models.ForeignKey("accounts.NGOProfile", on_delete=models.CASCADE, related_name="needs")
    servings_needed = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    needed_by = models.DateTimeField()
    notes = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=NeedStatus.choices, default=NeedStatus.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["needed_by"]

    def __str__(self):
        return f"{self.ngo.name} needs {self.servings_needed} servings by {self.needed_by:%d %b, %H:%M}"

    @property
    def is_past_due(self):
        return timezone.now() > self.needed_by


# ----------------------------------------------------------------------------- reports on listings
class ReportReason(models.TextChoices):
    UNSAFE = "unsafe", "Food looks or sounds unsafe"
    MISLEADING = "misleading", "Details are wrong or misleading"
    INAPPROPRIATE = "inappropriate", "Inappropriate content"
    OTHER = "other", "Something else"


class ReportStatus(models.TextChoices):
    OPEN = "open", "Open"
    ACTIONED = "actioned", "Listing removed"
    DISMISSED = "dismissed", "Dismissed"


class ListingReport(models.Model):
    """A user flags a listing; an admin reviews it and removes the listing or dismisses the flag."""

    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listing_reports")
    reason = models.CharField(max_length=15, choices=ReportReason.choices)
    details = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=ReportStatus.choices, default=ReportStatus.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "reporter"],
                condition=models.Q(status="open"),
                name="one_open_report_per_user_per_listing",
            )
        ]

    def __str__(self):
        return f"Report on listing #{self.listing_id}: {self.get_reason_display()}"


# ----------------------------------------------------------------------------- notifications
class NotificationType(models.TextChoices):
    MATCH = "match", "New listing match"
    NEW_REQUEST = "new_request", "New request"
    CONFIRMED = "confirmed", "Request confirmed"
    REJECTED = "rejected", "Request rejected"
    ON_THE_WAY = "on_the_way", "NGO on the way"
    COLLECTED = "collected", "Pickup collected"
    EXPIRING = "expiring", "Listing expiring soon"
    VERIFICATION = "verification", "Verification result"
    LOCKOUT = "lockout", "Pickup code locked"
    CANCELLED = "cancelled", "Request cancelled"
    LISTING_REMOVED = "listing_removed", "Listing removed or cancelled"
    REPORT = "report", "Listing reported"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=NotificationType.choices)
    message = models.CharField(max_length=250)
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read"], name="notif_user_unread_idx")]

    def __str__(self):
        return self.message
