from django.contrib import admin

from .models import (
    ActivityLog,
    FoodItem,
    FoodListing,
    HandoverAttempt,
    HandoverCode,
    ListingMatch,
    ListingReport,
    ListingPhoto,
    NGONeed,
    Notification,
    PickupRequest,
)


class FoodItemInline(admin.TabularInline):
    model = FoodItem
    extra = 0


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 0


@admin.register(FoodListing)
class FoodListingAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "hotel", "status", "servings_available", "total_servings", "safe_until")
    list_filter = ("status",)
    search_fields = ("hotel__name",)
    inlines = [FoodItemInline, ListingPhotoInline]


@admin.register(PickupRequest)
class PickupRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "ngo", "individual", "amount", "status", "requested_at")
    list_filter = ("status",)


@admin.register(NGONeed)
class NGONeedAdmin(admin.ModelAdmin):
    list_display = ("ngo", "servings_needed", "needed_by", "status")
    list_filter = ("status",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "message")
    list_filter = ("action",)
    search_fields = ("message",)


admin.site.register(ListingMatch)


class HandoverAttemptInline(admin.TabularInline):
    model = HandoverAttempt
    extra = 0
    can_delete = False
    readonly_fields = ("actor", "outcome", "ip_address", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HandoverCode)
class HandoverCodeAdmin(admin.ModelAdmin):
    """Read-only on purpose: the salt is hidden and nothing here can reveal or change a code."""

    list_display = ("pickup_request", "status", "failed_attempts", "regenerations", "issued_at", "expires_at")
    list_filter = ("status",)
    exclude = ("salt",)
    readonly_fields = (
        "pickup_request", "status", "issued_at", "expires_at", "failed_attempts", "regenerations",
        "locked_at", "used_at", "used_by",
    )
    inlines = [HandoverAttemptInline]

    def has_add_permission(self, request):
        return False


@admin.register(ListingReport)
class ListingReportAdmin(admin.ModelAdmin):
    list_display = ("listing", "reporter", "reason", "status", "created_at")
    list_filter = ("status", "reason")
