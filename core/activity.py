from .models import ActivityLog


def log_activity(actor, action, message, target=None):
    """Write one line to the activity log. `target` is any saved model instance."""
    ActivityLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        message=message[:300],
        target_type=target._meta.model_name if target is not None else "",
        target_id=target.pk if target is not None else None,
    )
