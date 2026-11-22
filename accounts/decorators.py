from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Role


def role_required(*roles, verified=True):
    """Only let these roles in. Hotels and NGOs must also be verified (admins always are)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.role not in roles:
                raise PermissionDenied
            if verified and user.role != Role.ADMIN and not user.is_verified:
                return redirect("accounts:status")
            return view(request, *args, **kwargs)

        return login_required(wrapper)

    return decorator


hotel_required = role_required(Role.HOTEL)
ngo_required = role_required(Role.NGO)
admin_required = role_required(Role.ADMIN)
recipient_required = role_required(Role.NGO, Role.INDIVIDUAL)
