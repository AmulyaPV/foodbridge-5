import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import core.models
import core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(db_index=True, max_length=50)),
                ("message", models.CharField(max_length=300)),
                ("target_type", models.CharField(blank=True, max_length=40)),
                ("target_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activity",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="FoodListing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_servings", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("servings_available", models.PositiveIntegerField()),
                ("pickup_window_start", models.DateTimeField()),
                ("pickup_window_end", models.DateTimeField()),
                ("safe_until", models.DateTimeField(help_text="When this food stops being safe to eat")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("posted", "Posted"),
                            ("fulfilled", "Fully claimed"),
                            ("expired", "Expired"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="posted",
                        max_length=10,
                    ),
                ),
                ("cancel_reason", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "hotel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="listings", to="accounts.hotelprofile"
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="FoodItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                (
                    "category",
                    models.CharField(
                        choices=[("veg", "Vegetarian"), ("non_veg", "Non-vegetarian"), ("vegan", "Vegan")], max_length=10
                    ),
                ),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(0.01)])),
                (
                    "unit",
                    models.CharField(
                        choices=[("servings", "servings"), ("kg", "kg"), ("packets", "packets")],
                        default="servings",
                        max_length=10,
                    ),
                ),
                (
                    "cooking_time_note",
                    models.CharField(
                        blank=True, help_text='e.g. "Cooked today at 6:00 PM"', max_length=120, verbose_name="Cooking time"
                    ),
                ),
                ("allergens_note", models.CharField(blank=True, max_length=200)),
                (
                    "listing",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="core.foodlisting"),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ListingPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="listings/%Y/%m/", validators=[core.validators.validate_photo_file])),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "listing",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="core.foodlisting"),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="ListingMatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveSmallIntegerField()),
                ("distance_km", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "listing",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches", to="core.foodlisting"),
                ),
                (
                    "ngo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="first_look_matches", to="accounts.ngoprofile"
                    ),
                ),
            ],
            options={"ordering": ["rank"]},
        ),
        migrations.AddConstraint(
            model_name="listingmatch",
            constraint=models.UniqueConstraint(fields=("listing", "ngo"), name="core_listingmatch_listing_ngo_uniq"),
        ),
        migrations.CreateModel(
            name="PickupRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name="Servings requested")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("requested", "Requested"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("on_the_way", "On the way"),
                            ("collected", "Collected"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        db_index=True,
                        default="requested",
                        max_length=12,
                    ),
                ),
                ("pickup_code", models.CharField(blank=True, max_length=6)),
                ("code_used", models.BooleanField(default=False)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("locked", models.BooleanField(default=False)),
                ("reject_reason", models.CharField(blank=True, max_length=300)),
                ("cancel_reason", models.CharField(blank=True, max_length=300)),
                ("eta_minutes", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("on_the_way_at", models.DateTimeField(blank=True, null=True)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("collected_at", models.DateTimeField(blank=True, null=True)),
                ("was_approved", models.BooleanField(default=False)),
                (
                    "listing",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requests", to="core.foodlisting"),
                ),
                (
                    "ngo",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requests", to="accounts.ngoprofile"),
                ),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.AddIndex(
            model_name="pickuprequest",
            index=models.Index(fields=["status"], name="request_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="pickuprequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["requested", "approved", "on_the_way"])),
                fields=("listing", "ngo"),
                name="one_active_request_per_ngo_per_listing",
            ),
        ),
        migrations.AddIndex(
            model_name="foodlisting",
            index=models.Index(fields=["status", "safe_until"], name="listing_status_safe_idx"),
        ),
        migrations.CreateModel(
            name="NGONeed",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("servings_needed", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("needed_by", models.DateTimeField()),
                ("notes", models.CharField(blank=True, max_length=300)),
                (
                    "status",
                    models.CharField(choices=[("open", "Open"), ("closed", "Closed")], db_index=True, default="open", max_length=10),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "ngo",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="needs", to="accounts.ngoprofile"),
                ),
            ],
            options={"ordering": ["needed_by"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("match", "New listing match"),
                            ("new_request", "New request"),
                            ("approved", "Request approved"),
                            ("rejected", "Request rejected"),
                            ("on_the_way", "NGO on the way"),
                            ("collected", "Pickup collected"),
                            ("expiring", "Listing expiring soon"),
                            ("verification", "Verification result"),
                            ("lockout", "Pickup code locked"),
                        ],
                        max_length=20,
                    ),
                ),
                ("message", models.CharField(max_length=250)),
                ("link", models.CharField(blank=True, max_length=200)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "is_read"], name="notif_user_unread_idx"),
        ),
    ]
