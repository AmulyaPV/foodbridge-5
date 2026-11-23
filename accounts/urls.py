from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_choose, name="register"),
    path("register/hotel/", views.register_hotel, name="register_hotel"),
    path("register/ngo/", views.register_ngo, name="register_ngo"),
    path("register/individual/", views.register_individual, name="register_individual"),
    path("login/", views.FoodBridgeLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("home/", views.home, name="home"),
    path("status/", views.status, name="status"),
]
