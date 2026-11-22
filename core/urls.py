from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing, name="landing"),

    # Hotel
    path("hotel/listings/", views.hotel_dashboard, name="hotel_dashboard"),
    path("hotel/listings/new/", views.listing_create, name="listing_create"),
    path("hotel/listings/<int:pk>/edit/", views.listing_edit, name="listing_edit"),
    path("hotel/listings/<int:pk>/cancel/", views.listing_cancel, name="listing_cancel"),
    path("hotel/listings/<int:pk>/repost/", views.listing_repost, name="listing_repost"),
    path("hotel/requests/", views.hotel_requests, name="hotel_requests"),
    path("hotel/requests/<int:pk>/confirm/", views.request_confirm, name="request_confirm"),
    path("hotel/requests/<int:pk>/reject/", views.request_reject, name="request_reject"),
    path("hotel/requests/<int:pk>/handover/", views.confirm_handover, name="confirm_handover"),
    path("hotel/history/", views.hotel_history, name="hotel_history"),
    path("hotel/impact-certificate/", views.impact_certificate, name="impact_certificate"),

    # NGO
    path("food/", views.ngo_dashboard, name="ngo_dashboard"),
    path("food/<int:pk>/", views.listing_detail, name="listing_detail"),
    path("food/<int:pk>/request/", views.request_create, name="request_create"),
    path("food/<int:pk>/report/", views.listing_report, name="listing_report"),
    path("ngo/requests/", views.my_requests, name="my_requests"),
    path("ngo/requests/<int:pk>/on-the-way/", views.mark_on_the_way, name="mark_on_the_way"),
    path("ngo/requests/<int:pk>/code/regenerate/", views.code_regenerate, name="code_regenerate"),

    # Shared
    path("requests/<int:pk>/cancel/", views.request_cancel, name="request_cancel"),
    path("needs/", views.needs_board, name="needs_board"),
    path("needs/<int:pk>/close/", views.need_close, name="need_close"),
    path("notifications/", views.notifications, name="notifications"),
]
