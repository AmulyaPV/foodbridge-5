"""A recipient's reliability score: how often a confirmed pickup is actually collected."""
from .models import PickupRequest, RequestStatus


def reliability_counts(recipient):
    """Works for an NGOProfile or an IndividualProfile."""
    owner = {"ngo": recipient} if recipient.__class__.__name__ == "NGOProfile" else {"individual": recipient}
    approved_ever = PickupRequest.objects.filter(was_approved=True, **owner)
    collected = approved_ever.filter(status=RequestStatus.COLLECTED).count()
    missed = approved_ever.filter(status__in=RequestStatus.missed()).count()
    return collected, missed


def reliability_score(recipient):
    """A number from 0 to 1. Recipients with no history yet start at a neutral 0.8."""
    collected, missed = reliability_counts(recipient)
    total = collected + missed
    if total == 0:
        return 0.8
    return collected / total


def reliability_percent(recipient):
    return round(reliability_score(recipient) * 100)
