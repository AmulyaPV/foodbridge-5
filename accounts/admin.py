from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import HotelProfile, IndividualProfile, NGOProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "role", "verification_status", "is_active", "date_joined")
    list_filter = ("role", "verification_status", "is_active")
    search_fields = ("email", "username")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("FoodBridge", {"fields": ("role", "verification_status", "verification_note", "verified_at", "verified_by")}),
    )


@admin.register(HotelProfile)
class HotelProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "fssai_number")
    search_fields = ("name", "fssai_number")


@admin.register(NGOProfile)
class NGOProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "registration_number", "daily_capacity")
    search_fields = ("name", "registration_number")


@admin.register(IndividualProfile)
class IndividualProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "household_size")
    search_fields = ("name", "phone")
