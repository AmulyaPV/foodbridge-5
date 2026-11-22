from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Log in with an email address (any letter case). Plain usernames still work for superusers."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        username = username.strip()
        user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).order_by("id").first()
        if user is None:
            User().set_password(password)  # same work as a real check, so timing doesn't reveal unknown emails
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
