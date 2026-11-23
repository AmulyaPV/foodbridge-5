from django.contrib import messages
from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render

from core.activity import log_activity

from .forms import (
    EmailLoginForm,
    HotelProfileForm,
    HotelRegisterForm,
    IndividualProfileForm,
    IndividualRegisterForm,
    NGOProfileForm,
    NGORegisterForm,
)
from .models import Role, Verification


class FoodBridgeLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


def register_choose(request):
    """Three doors in: hotel / restaurant, NGO, individual."""
    if request.user.is_authenticated:
        return redirect("accounts:home")
    return render(request, "accounts/register_choose.html")


def _register(request, account_form_class, profile_form_class, role_label, role_key):
    if request.user.is_authenticated:
        return redirect("accounts:home")
    if request.method == "POST":
        account_form = account_form_class(request.POST)
        profile_form = profile_form_class(request.POST, request.FILES)
        if account_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user = account_form.save()
                profile = profile_form.save(commit=False)
                profile.user = user
                profile.save()
            login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
            log_activity(user, "register", f"{role_label} registered: {profile.name}", user)
            messages.success(request, "Account created. An admin will verify you shortly.")
            return redirect("accounts:status")
    else:
        account_form = account_form_class()
        profile_form = profile_form_class()
    return render(
        request,
        "accounts/register.html",
        {"account_form": account_form, "profile_form": profile_form, "role_label": role_label, "role_key": role_key},
    )


def register_hotel(request):
    return _register(request, HotelRegisterForm, HotelProfileForm, "Hotel / restaurant", "hotel")


def register_ngo(request):
    return _register(request, NGORegisterForm, NGOProfileForm, "NGO", "ngo")


def register_individual(request):
    return _register(request, IndividualRegisterForm, IndividualProfileForm, "Individual", "individual")


def logout_view(request):
    if request.method == "POST":
        auth_logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect("core:landing")
    return render(request, "accounts/logout.html")


@login_required
def home(request):
    """Send everyone to the right first page for their role."""
    user = request.user
    if user.role == Role.ADMIN:
        return redirect("console:dashboard")
    if not user.is_verified:
        return redirect("accounts:status")
    if user.role == Role.HOTEL:
        return redirect("core:hotel_dashboard")
    if user.role in (Role.NGO, Role.INDIVIDUAL):
        return redirect("core:ngo_dashboard")
    return redirect("core:landing")


@login_required
def status(request):
    if request.user.is_verified and request.user.role != Role.ADMIN:
        return redirect("accounts:home")
    return render(request, "accounts/status.html", {"Verification": Verification})
