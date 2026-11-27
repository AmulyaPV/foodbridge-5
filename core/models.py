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
    def is_partially_allocated(self):
        """True if some servings have been allocated but not all."""
        return 0 < self.servings_available < self.total_servings

    @property
    def is_fully_allocated(self):
        """True only when all items have remaining 0."""
        return self.servings_available == 0

    @property
    def display_status(self):
        """(key, label) using the words in the project report: available, partially_allocated, requested, confirmed,
        collected or expired (plus cancelled / removed for listings that were taken down)."""
        if self.status == ListingStatus.REMOVED:
            return "removed", "Removed"
        if self.status == ListingStatus.CANCELLED:
            return "cancelled", "Cancelled"
        reqs = list(self.requests.all())
        pending = any(r.status in (RequestStatus.REQUESTED, RequestStatus.REVISION_PROPOSED) for r in reqs)
        live = any(r.status in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED, RequestStatus.ON_THE_WAY) for r in reqs)
        collected = any(r.status == RequestStatus.COLLECTED for r in reqs)
        if self.status == ListingStatus.EXPIRED or (self.status == ListingStatus.POSTED and self.is_past_safe_until):
            return ("collected", "Collected") if collected and self.servings_available == 0 else ("expired", "Expired")
        if self.status == ListingStatus.FULFILLED or self.is_fully_allocated:
            return ("confirmed", "Confirmed") if live else ("collected", "Collected")
        if live:
            return "confirmed", "Confirmed"
        if pending:
            return "requested", "Requested"
        if self.is_partially_allocated:
            return "partially_allocated", "Partially allocated"
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
        return (self.status == ListingStatus.POSTED or (self.status == ListingStatus.FULFILLED and self.servings_available > 0)) and not self.is_past_safe_until and self.servings_available > 0

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
    allocated_quantity = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    unit = models.CharField(max_length=10, choices=ServingUnit.choices, default=ServingUnit.SERVINGS)
    cooking_time_note = models.CharField(
        "Cooking time", max_length=120, blank=True, help_text='e.g. "Cooked today at 6:00 PM"'
    )
    allergens_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="fooditem_quantity_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_quantity__gte=0),
                name="fooditem_allocated_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_quantity__lte=models.F("quantity")),
                name="fooditem_allocated_lte_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def remaining_quantity(self):
        rem = self.quantity - self.allocated_quantity
        return max(rem, 0)

    @property
    def is_available(self):
        return self.remaining_quantity > 0


class ListingPhoto(models.Model):
    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="listings/%Y/%m/", validators=[validate_photo_file])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


# ----------------------------------------------------------------------------- requests
class RequestStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    REVISION_PROPOSED = "revision_proposed", "Revision Proposed"
    PARTIALLY_APPROVED = "partially_approved", "Partially Approved"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"
    ON_THE_WAY = "on_the_way", "On the way"
    COLLECTED = "collected", "Collected"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"

    @classmethod
    def active(cls):
        return [cls.REQUESTED, cls.REVISION_PROPOSED, cls.PARTIALLY_APPROVED, cls.CONFIRMED, cls.ON_THE_WAY]

    @classmethod
    def actionable_for_recipient(cls):
        return [cls.REVISION_PROPOSED]

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
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.REQUESTED, db_index=True)

    idempotency_key = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    proposal_expires_at = models.DateTimeField(null=True, blank=True)

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
        indexes = [
            models.Index(fields=["status", "listing"], name="req_status_listing_idx"),
            models.Index(fields=["status"], name="request_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "ngo"],
                condition=models.Q(status__in=["requested", "revision_proposed", "partially_approved", "confirmed", "on_the_way"]),
                name="one_active_request_per_ngo_per_listing",
            ),
            models.UniqueConstraint(
                fields=["listing", "individual"],
                condition=models.Q(status__in=["requested", "revision_proposed", "partially_approved", "confirmed", "on_the_way"]),
                name="one_active_request_per_individual_per_listing",
            ),
            models.CheckConstraint(
                condition=(models.Q(ngo__isnull=False, individual__isnull=True) | models.Q(ngo__isnull=True, individual__isnull=False)),
                name="request_has_exactly_one_recipient",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uniq_request_idempotency_key",
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
        """Confirmed, partially approved, or on the way: the states in which a handover code means something."""
        return self.status in (RequestStatus.CONFIRMED, RequestStatus.PARTIALLY_APPROVED, RequestStatus.ON_THE_WAY)

    @property
    def step_index(self):
        try:
            # Map partially_approved to confirmed step in visual stepper
            st = self.status
            if st == RequestStatus.PARTIALLY_APPROVED:
                st = RequestStatus.CONFIRMED
            return self.STEP_ORDER.index(st)
        except ValueError:
            return -1  # rejected / cancelled / expired / revision_proposed

    @property
    def is_proposal_expired(self):
        if self.status != RequestStatus.REVISION_PROPOSED:
            return False
        if not self.proposal_expires_at:
            return False
        return timezone.now() >= self.proposal_expires_at or self.listing.is_past_safe_until

    @property
    def total_allocated_servings(self):
        return sum(item.final_allocated_quantity for item in self.items.all())


# ----------------------------------------------------------------------------- food-wise request items & ledger
class ItemRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    PARTIAL_PROPOSED = "partial_proposed", "Partial Proposed"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class PickupRequestItem(models.Model):
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="request_items")
    requested_quantity = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    proposed_quantity = models.DecimalField(max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    final_allocated_quantity = models.DecimalField(max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=ItemRequestStatus.choices, default=ItemRequestStatus.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["food_item_id"]
        indexes = [
            models.Index(fields=["food_item", "status"], name="reqitem_food_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["pickup_request", "food_item"], name="uniq_request_food_item"),
        ]

    def __str__(self):
        return f"Req #{self.pickup_request_id} Item #{self.food_item_id}: req={self.requested_quantity}, final={self.final_allocated_quantity} ({self.status})"


class RequestStatusHistory(models.Model):
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.CASCADE, related_name="status_history")
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Request #{self.pickup_request_id}: {self.old_status} -> {self.new_status} at {self.created_at}"


class AllocationOperation(models.TextChoices):
    ALLOCATE = "allocate", "Allocate"
    RESTORE = "restore", "Restore"


class FoodAllocationHistory(models.Model):
    request_item = models.ForeignKey(PickupRequestItem, on_delete=models.CASCADE, related_name="allocation_logs")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="allocation_logs")
    operation_type = models.CharField(max_length=10, choices=AllocationOperation.choices, db_index=True)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)])
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["food_item", "created_at"], name="alloc_item_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["request_item", "operation_type"],
                name="uniq_request_item_alloc_op",
            ),
        ]

    def __str__(self):
        return f"{self.operation_type} {self.quantity} for FoodItem #{self.food_item_id} (ReqItem #{self.request_item_id})"



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
    PARTIALLY_APPROVED = "partially_approved", "Request partially approved"
    REVISION_PROPOSED = "revision_proposed", "Revised quantity proposed"
    PROPOSAL_ACCEPTED = "proposal_accepted", "Proposal accepted"
    PROPOSAL_DECLINED = "proposal_declined", "Proposal declined"
    REJECTED = "rejected", "Request rejected"
    ON_THE_WAY = "on_the_way", "NGO on the way"
    COLLECTED = "collected", "Pickup collected"
    EXPIRING = "expiring", "Listing expiring soon"
    VERIFICATION = "verification", "Verification result"
    LOCKOUT = "lockout", "Pickup code locked"
    CANCELLED = "cancelled", "Request cancelled"
    LISTING_REMOVED = "listing_removed", "Listing removed or cancelled"
    REPORT = "report", "Listing reported"
    NEW_MESSAGE = "new_message", "New message"
    CONVERSATION_STARTED = "conversation_started", "Conversation started"
    PICKUP_SCHEDULE = "pickup_schedule", "Pickup schedule updated"
    PICKUP_REMINDER = "pickup_reminder", "Pickup reminder"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=NotificationType.choices)
    message = models.CharField(max_length=250)
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "created_at"], name="notif_user_unread_date_idx"),
            models.Index(fields=["user", "is_read"], name="notif_user_unread_idx"),
        ]

    def __str__(self):
        return self.message


# ----------------------------------------------------------------------------- messaging & pickup coordination
class ConversationType(models.TextChoices):
    REQUEST = "request", "Request coordination"
    LISTING_ENQUIRY = "listing_enquiry", "Listing enquiry"
    SUPPORT = "support", "Support conversation"


class Conversation(models.Model):
    conversation_type = models.CharField(max_length=20, choices=ConversationType.choices, default=ConversationType.REQUEST, db_index=True)
    pickup_request = models.ForeignKey(PickupRequest, null=True, blank=True, on_delete=models.CASCADE, related_name="conversations")
    listing = models.ForeignKey(FoodListing, null=True, blank=True, on_delete=models.CASCADE, related_name="conversations")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation #{self.pk} ({self.get_conversation_type_display()})"


class ConversationParticipant(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversation_memberships")
    is_blocked = models.BooleanField(default=False)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="uniq_conversation_user"),
        ]

    def __str__(self):
        return f"{self.user.username} in Conv #{self.conversation_id}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_messages"
    )
    body = models.TextField(max_length=2000)
    client_uuid = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    is_system = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="msg_conv_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "client_uuid"],
                condition=models.Q(client_uuid__isnull=False),
                name="uniq_conv_client_uuid",
            ),
        ]

    def __str__(self):
        sender_name = self.sender.username if self.sender else "System"
        return f"Msg #{self.pk} by {sender_name} at {self.created_at}"


class PickupProposal(models.Model):
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.CASCADE, related_name="pickup_proposals")
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    proposed_time = models.DateTimeField()
    notes = models.CharField(max_length=300, blank=True)
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pickup proposal for Req #{self.pickup_request_id}: {self.proposed_time}"


class TrackingSessionStatus(models.TextChoices):
    WAITING = "waiting", "Waiting for pickup"
    AWAITING_PERMISSION = "awaiting_permission", "Awaiting location permission"
    ACTIVE = "active", "Tracking active"
    LOCATION_UNAVAILABLE = "location_unavailable", "Location unavailable"
    DELAYED = "delayed", "Location update delayed"
    ARRIVING_SOON = "arriving_soon", "Arriving soon"
    ARRIVED = "arrived", "Arrived"
    COMPLETED = "completed", "Pickup completed"
    STOPPED = "stopped", "Tracking stopped"
    CANCELLED = "cancelled", "Request cancelled"


class PickupTrackingSession(models.Model):
    pickup_request = models.ForeignKey(PickupRequest, on_delete=models.CASCADE, related_name="tracking_sessions")
    hotel = models.ForeignKey("accounts.HotelProfile", on_delete=models.CASCADE, related_name="tracking_sessions")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tracking_sessions")
    recipient_role = models.CharField(max_length=20)
    current_latitude = models.FloatField(null=True, blank=True)
    current_longitude = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True, help_text="GPS accuracy in meters")
    started_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=TrackingSessionStatus.choices,
        default=TrackingSessionStatus.ACTIVE,
        db_index=True,
    )
    last_eta_seconds = models.PositiveIntegerField(null=True, blank=True)
    last_distance_meters = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["pickup_request", "status"], name="trk_req_status_idx"),
            models.Index(fields=["last_updated"], name="trk_last_updated_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["pickup_request"],
                condition=models.Q(status__in=[
                    "waiting",
                    "awaiting_permission",
                    "active",
                    "location_unavailable",
                    "delayed",
                    "arriving_soon",
                    "arrived",
                ]),
                name="one_active_tracking_session_per_request",
            )
        ]

    def __str__(self):
        return f"Tracking #{self.pk} for Req #{self.pickup_request_id} ({self.status})"

    @property
    def is_active(self):
        return self.status in {
            TrackingSessionStatus.WAITING,
            TrackingSessionStatus.AWAITING_PERMISSION,
            TrackingSessionStatus.ACTIVE,
            TrackingSessionStatus.LOCATION_UNAVAILABLE,
            TrackingSessionStatus.DELAYED,
            TrackingSessionStatus.ARRIVING_SOON,
            TrackingSessionStatus.ARRIVED,
        }

    @property
    def is_stale(self):
        """Returns True if the session is active but has had no GPS update in over 45 seconds."""
        if not self.last_updated or not self.is_active:
            return False
        return (timezone.now() - self.last_updated).total_seconds() > 45


