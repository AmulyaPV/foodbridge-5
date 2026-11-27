from django.conf import settings

from accounts.models import Role

_LOCAL_BOOTSTRAP = settings.BASE_DIR / "static" / "vendor" / "bootstrap" / "css" / "bootstrap.min.css"


def site(request):
    """Values every template can use."""
    context = {
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
        "MAPS_ENABLED": bool(settings.GOOGLE_MAPS_API_KEY),
        "LOCAL_BOOTSTRAP": _LOCAL_BOOTSTRAP.exists(),
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        context["unread_notifications"] = user.notifications.filter(is_read=False).count()
        # Unread messages count
        from core.models import ConversationParticipant, Message
        user_conv_ids = ConversationParticipant.objects.filter(user=user, is_blocked=False).values_list("conversation_id", flat=True)
        unread_msg_count = 0
        for p in ConversationParticipant.objects.filter(user=user, is_blocked=False):
            qs = Message.objects.filter(conversation_id=p.conversation_id).exclude(sender=user)
            if p.last_read_at:
                qs = qs.filter(created_at__gt=p.last_read_at)
            unread_msg_count += qs.count()
        context["unread_messages"] = unread_msg_count

        if user.role == Role.HOTEL and user.is_verified and getattr(user, "hotel_profile", None):
            from core.models import PickupRequest, RequestStatus

            context["pending_requests"] = PickupRequest.objects.filter(
                listing__hotel=user.hotel_profile, status=RequestStatus.REQUESTED
            ).count()
        if user.role == Role.ADMIN:
            from accounts.models import User, Verification
            from core.models import ListingReport, ReportStatus

            context["admin_pending"] = (
                User.objects.filter(verification_status=Verification.PENDING).exclude(role=Role.ADMIN).count()
            )
            context["admin_open_reports"] = ListingReport.objects.filter(status=ReportStatus.OPEN).count()
    return context
