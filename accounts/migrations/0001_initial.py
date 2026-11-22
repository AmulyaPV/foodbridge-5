import django.contrib.auth.models
import django.contrib.auth.validators
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import accounts.models
import core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        error_messages={"unique": "A user with that username already exists."},
                        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
                        max_length=150,
                        unique=True,
                        validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
                        verbose_name="username",
                    ),
                ),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="email address")),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether the user can log into this admin site.",
                        verbose_name="staff status",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                (
                    "role",
                    models.CharField(
                        choices=[("hotel", "Hotel"), ("ngo", "NGO"), ("admin", "Admin")],
                        db_index=True,
                        default="hotel",
                        max_length=10,
                    ),
                ),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending verification"),
                            ("approved", "Verified"),
                            ("rejected", "Rejected"),
                            ("suspended", "Suspended"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("verification_note", models.CharField(blank=True, max_length=300, verbose_name="Reason from admin")),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="verified_users",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "abstract": False,
            },
            managers=[
                ("objects", accounts.models.AccountManager()),
            ],
        ),
        migrations.CreateModel(
            name="HotelProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("contact_person", models.CharField(max_length=120)),
                ("phone", models.CharField(max_length=20, validators=[core.validators.validate_phone])),
                ("address", models.TextField()),
                (
                    "latitude",
                    models.FloatField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(-90), django.core.validators.MaxValueValidator(90)],
                    ),
                ),
                (
                    "longitude",
                    models.FloatField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(-180), django.core.validators.MaxValueValidator(180)],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "fssai_number",
                    models.CharField(
                        error_messages={"unique": "A hotel with this licence number is already registered."},
                        max_length=30,
                        unique=True,
                        validators=[core.validators.validate_licence_number],
                        verbose_name="Licence / FSSAI number",
                    ),
                ),
                ("photo", models.ImageField(blank=True, upload_to="hotels/%Y/%m/", validators=[core.validators.validate_photo_file])),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="hotel_profile", to="accounts.user"
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="NGOProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("contact_person", models.CharField(max_length=120)),
                ("phone", models.CharField(max_length=20, validators=[core.validators.validate_phone])),
                ("address", models.TextField()),
                (
                    "latitude",
                    models.FloatField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(-90), django.core.validators.MaxValueValidator(90)],
                    ),
                ),
                (
                    "longitude",
                    models.FloatField(
                        blank=True,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(-180), django.core.validators.MaxValueValidator(180)],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "registration_number",
                    models.CharField(
                        error_messages={"unique": "An NGO with this registration number is already registered."},
                        max_length=40,
                        unique=True,
                        validators=[core.validators.validate_registration_number],
                    ),
                ),
                (
                    "daily_capacity",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100000)],
                        verbose_name="Daily collection capacity (servings)",
                    ),
                ),
                ("service_area", models.CharField(max_length=200)),
                (
                    "certificate",
                    models.FileField(
                        blank=True, upload_to="ngo_certificates/%Y/%m/", validators=[core.validators.validate_certificate_file]
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="ngo_profile", to="accounts.user"
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.AddIndex(
            model_name="hotelprofile",
            index=models.Index(fields=["latitude", "longitude"], name="hotel_latlng_idx"),
        ),
        migrations.AddIndex(
            model_name="ngoprofile",
            index=models.Index(fields=["latitude", "longitude"], name="ngo_latlng_idx"),
        ),
    ]
