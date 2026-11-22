from django.urls import path

from . import views

app_name = "console"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("verification/", views.verification_queue, name="verification_queue"),
    path("verification/<int:user_id>/", views.verification_decide, name="verification_decide"),
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/reactivate/", views.user_reactivate, name="user_reactivate"),
    path("reports/", views.reports_page, name="reports"),
    path("reports/export.csv", views.reports_csv, name="reports_csv"),
    path("listings/", views.listings_page, name="listings"),
    path("listings/<int:pk>/remove/", views.listing_remove, name="listing_remove"),
    path("moderation/", views.moderation_queue, name="moderation"),
    path("moderation/<int:pk>/", views.moderation_decide, name="moderation_decide"),
    path("activity/", views.activity_log, name="activity_log"),
    path("locked-pickups/", views.locked_pickups, name="locked_pickups"),
    path("locked-pickups/<int:pk>/unlock/", views.unlock_pickup, name="unlock_pickup"),
]
