"""Users, roles, verification state and the hotel / NGO profiles."""
from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.validators import (
    validate_certificate_file,
    validate_licence_number,
    validate_phone,
    validate_photo_file,
    validate_registration_number,
)


class Role(models.TextChoices):
    HOTEL = "hotel", "Hotel / restaurant"
    NGO = "ngo", "NGO"
    INDIVIDUAL = "individual", "Individual recipient"
    ADMIN = "admin", "Admin"


class Verification(models.TextChoices):
    PENDING = "pending", "Pending verification"
    APPROVED = "approved", "Verified"
    REJECTED = "rejected", "Rejected"
    SUSPENDED = "suspended", "Suspended"


class AccountManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """One login model for everyone. `role` decides what the person can do."""

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.HOTEL, db_index=True)
    verification_status = models.CharField(
        max_length=10, choices=Verification.choices, default=Verification.PENDING, db_index=True
    )
    verification_note = models.CharField("Reason from admin", max_length=300, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_users"
    )

    objects = AccountManager()

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = Role.ADMIN
        if self.role == Role.ADMIN:  # admins never wait for verification
            self.verification_status = Verification.APPROVED
        super().save(*args, **kwargs)

    @property
    def is_hotel(self):
        return self.role == Role.HOTEL

    @property
    def is_ngo(self):
        return self.role == Role.NGO

    @property
    def is_individual(self):
        return self.role == Role.INDIVIDUAL

    @property
    def is_recipient(self):
        """NGOs and individual recipients are the two kinds of people who can request food."""
        return self.role in (Role.NGO, Role.INDIVIDUAL)

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN

    @property
    def is_verified(self):
        return self.verification_status == Verification.APPROVED

    @property
    def profile(self):
        if self.role == Role.HOTEL:
            return getattr(self, "hotel_profile", None)
        if self.role == Role.NGO:
            return getattr(self, "ngo_profile", None)
        if self.role == Role.INDIVIDUAL:
            return getattr(self, "individual_profile", None)
        return None

    @property
    def display_name(self):
        profile = self.profile
        if profile is not None:
            return profile.name
        return self.get_full_name() or self.email or self.username


class BaseProfile(models.Model):
    """Fields that hotels and NGOs share."""

    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, validators=[validate_phone])
    address = models.TextField()
    latitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    @property
    def has_pin(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def email(self):
        return self.user.email


class HotelProfile(BaseProfile):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hotel_profile")
    fssai_number = models.CharField(
        "Licence / FSSAI number",
        max_length=30,
        unique=True,
        validators=[validate_licence_number],
        error_messages={"unique": "A hotel with this licence number is already registered."},
    )
    photo = models.ImageField(upload_to="hotels/%Y/%m/", blank=True, validators=[validate_photo_file])

    # Pickup Location Management
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    google_place_id = models.CharField(max_length=255, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["latitude", "longitude"], name="hotel_latlng_idx")]


class NGOProfile(BaseProfile):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ngo_profile")
    registration_number = models.CharField(
        max_length=40,
        unique=True,
        validators=[validate_registration_number],
        error_messages={"unique": "An NGO with this registration number is already registered."},
    )
    daily_capacity = models.PositiveIntegerField(
        "Daily collection capacity (servings)",
        validators=[MinValueValidator(1), MaxValueValidator(100000)],
    )
    service_area = models.CharField(max_length=200)
    certificate = models.FileField(
        upload_to="ngo_certificates/%Y/%m/", blank=True, validators=[validate_certificate_file]
    )

    # NGO Food Preference Profile (boosts smart match score, does not restrict requesting)
    preferred_categories = models.CharField(
        "Preferred food categories",
        max_length=100,
        blank=True,
        help_text="Comma-separated categories, e.g. 'veg,vegan'",
    )
    dietary_restrictions = models.CharField(
        "Dietary restrictions accepted/handled",
        max_length=200,
        blank=True,
        help_text="e.g. 'Nut-free, Halal, Jain'",
    )
    beneficiary_count = models.PositiveIntegerField(
        "Average beneficiaries served per distribution",
        default=0,
        help_text="Estimated people fed per regular distribution",
    )
    typical_servings = models.PositiveIntegerField(
        "Typical servings requested per pickup",
        default=0,
        help_text="Ideal target batch size",
    )
    preferred_collection_areas = models.CharField(
        "Preferred collection localities / pin codes",
        max_length=250,
        blank=True,
        help_text="Comma-separated areas",
    )

    class Meta:
        indexes = [models.Index(fields=["latitude", "longitude"], name="ngo_latlng_idx")]


class IndividualProfile(BaseProfile):
    """A person (or household) who needs food and is not part of an NGO.

    Individuals are verified by an admin like everyone else, may only ask for a small number of
    servings per request, and never get the 10-minute Smart Match "first look" (that is for NGOs).
    """

    MAX_SERVINGS_PER_REQUEST = 10

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="individual_profile")
    household_size = models.PositiveSmallIntegerField(
        "People in your household",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
    )
    supporting_document = models.FileField(
        "Supporting document (optional)",
        upload_to="individual_documents/%Y/%m/",
        blank=True,
        validators=[validate_certificate_file],
        help_text="Any ID or letter from a local office that helps an admin verify you. Photo or PDF.",
    )

    class Meta:
        indexes = [models.Index(fields=["latitude", "longitude"], name="indiv_latlng_idx")]

    def save(self, *args, **kwargs):
        self.contact_person = self.name  # a person is their own contact
        super().save(*args, **kwargs)

    @property
    def daily_capacity(self):
        return self.MAX_SERVINGS_PER_REQUEST
