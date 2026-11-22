from .models import Notification


def notify(user, kind, message, link=""):
    Notification.objects.create(user=user, kind=kind, message=message[:250], link=link[:200])
