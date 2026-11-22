from django.utils import timezone

from core.activity import log_activity

from .models import Verification


def set_verification(user, status, actor, note=""):
    """Change a user's verification state and record who did it."""
    user.verification_status = status
    user.verification_note = note.strip()[:300]
    fields = ["verification_status", "verification_note"]
    if status == Verification.APPROVED:
        user.verified_at = timezone.now()
        user.verified_by = actor if actor.pk != user.pk else None
        fields += ["verified_at", "verified_by"]
    user.save(update_fields=fields)
    message = f"{user.display_name}: {Verification(status).label}"
    log_activity(actor, f"verification.{status}", f"{message} ({note.strip()})" if note.strip() else message, user)
