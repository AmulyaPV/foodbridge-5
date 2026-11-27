from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import Role


def _is_ajax(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "").lower()
    )


def role_required(*roles, verified=True):
    """Only let these roles in. Hotels and NGOs must also be verified (admins always are)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if _is_ajax(request):
                    return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if user.role not in roles:
                if _is_ajax(request):
                    return JsonResponse({"error": "Permission denied for this role"}, status=403)
                raise PermissionDenied
            if verified and user.role != Role.ADMIN and not user.is_verified:
                if _is_ajax(request):
                    return JsonResponse({"error": "Account verification required", "verified": False}, status=403)
                return redirect("accounts:status")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


hotel_required = role_required(Role.HOTEL)
ngo_required = role_required(Role.NGO)
admin_required = role_required(Role.ADMIN)
recipient_required = role_required(Role.NGO, Role.INDIVIDUAL)
