"""The Secure Handover Code: every rule about issuing, showing, checking, regenerating and
unlocking the 6-digit code lives here, so the views stay thin and the rules are easy to test.

Goals this module guarantees (see docs/handover-code.md):
  G1  Only the confirmed recipient can see the code; the hotel never does.
  G2  The code is random and unguessable, and is never stored in the database.
  G3  It works once, only while the food is still safe, and only for a live pickup.
  G4  Guessing is capped: 5 wrong entries lock the pickup and alert the admins.
  G5  Every attempt is recorded (who, when, from which IP, what happened).
  G6  A lost code can be replaced (max 2 times) without ever resetting the guess counter.
  G7  Only an admin can unlock, and unlocking always issues a brand-new code.
"""
import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from core.activity import log_activity

from .exceptions import FoodBridgeError
from .models import (
    MAX_PICKUP_ATTEMPTS,
    PICKUP_CODE_LENGTH,
    AttemptOutcome,
    CodeStatus,
    HandoverAttempt,
    HandoverCode,
    PickupRequest,
    RequestStatus,
)
from .notify import notify

LIVE_STATUSES = (RequestStatus.CONFIRMED, RequestStatus.ON_THE_WAY)


# ----------------------------------------------------------------------------- the code itself
def new_salt():
    """128 random bits from the operating system's secure generator (never `random`)."""
    return secrets.token_hex(16)


def derive_code(pickup_request_id, salt):
    """Turn (secret key, pickup id, random salt) into a 6-digit string. Same inputs, same code."""
    message = f"handover:{pickup_request_id}:{salt}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()
    number = int.from_bytes(digest[:8], "big") % (10**PICKUP_CODE_LENGTH)
    return f"{number:0{PICKUP_CODE_LENGTH}d}"


def code_matches(handover, entered):
    """Constant-time comparison on bytes (str compare_digest crashes on non-ASCII input)."""
    expected = derive_code(handover.pickup_request_id, handover.salt)
    return hmac.compare_digest((entered or "").strip().encode(), expected.encode())


def visible_code(pickup_request):
    """The code to show the NGO, or None when there is nothing valid to show."""
    handover = getattr(pickup_request, "handover", None)
    if handover is None or pickup_request.status not in LIVE_STATUSES or not handover.is_usable:
        return None
    return derive_code(pickup_request.pk, handover.salt)


# ----------------------------------------------------------------------------- issuing
def issue_code(pickup_request):
    """Called once, inside the approval transaction. The code dies when the food stops being safe."""
    return HandoverCode.objects.create(
        pickup_request=pickup_request,
        salt=new_salt(),
        expires_at=pickup_request.listing.safe_until,
    )


@transaction.atomic
def regenerate_code(pickup_request_id, actor):
    """The recipient lost or leaked their code. Old code stops working at once; the guess counter is NOT reset."""
    request = PickupRequest.objects.select_for_update().select_related("handover").get(pk=pickup_request_id)
    handover = request.handover
    if request.status not in LIVE_STATUSES:
        raise FoodBridgeError("This pickup is no longer active.")
    if handover.status == CodeStatus.LOCKED:
        raise FoodBridgeError("This code is locked. Only an admin can unlock it.")
    if handover.status == CodeStatus.USED:
        raise FoodBridgeError("This code has already been used.")
    if handover.is_expired:
        raise FoodBridgeError("The safe-until time has passed, so a new code can't be issued.")
    if handover.regenerations_left == 0:
        raise FoodBridgeError("You've used all your code replacements for this pickup. Contact an admin.")

    handover.salt = new_salt()
    handover.regenerations += 1
    handover.issued_at = timezone.now()
    handover.save(update_fields=["salt", "regenerations", "issued_at"])
    log_activity(actor, "code.regenerate", f"New handover code issued for pickup #{request.pk}", request)
    return handover


# ----------------------------------------------------------------------------- checking
def _record(handover, actor, outcome, ip):
    HandoverAttempt.objects.create(handover=handover, actor=actor, outcome=outcome, ip_address=ip or None)


def confirm_handover(pickup_request_id, entered_code, actor, ip=None):
    """The hotel types the code the NGO shows. Correct -> collected. Wrong x5 -> locked.

    Wrong-code bookkeeping (counter, lock, admin alert, attempt log) must be COMMITTED, so the error
    is raised only AFTER the transaction block has finished; raising inside transaction.atomic()
    would roll everything back and the lockout would never trigger.
    """
    failure = None
    with transaction.atomic():
        request = (
            PickupRequest.objects.select_for_update()
            .select_related("listing", "listing__hotel", "ngo__user", "individual__user")
            .get(pk=pickup_request_id)
        )
        if request.status not in LIVE_STATUSES:
            raise FoodBridgeError("This pickup isn't awaiting handover.")
        try:
            handover = HandoverCode.objects.select_for_update().get(pickup_request=request)
        except HandoverCode.DoesNotExist:
            raise FoodBridgeError("This pickup has no handover code.")

        if handover.status == CodeStatus.USED:
            raise FoodBridgeError("This pickup code has already been used.")
        if handover.status == CodeStatus.LOCKED:
            _record(handover, actor, AttemptOutcome.BLOCKED, ip)
            failure = "This pickup is locked after too many wrong attempts. Contact an admin."
        elif handover.is_expired:
            _record(handover, actor, AttemptOutcome.EXPIRED, ip)
            failure = "The safe-until time has passed, so this food can no longer be handed over."
        elif code_matches(handover, entered_code):
            now = timezone.now()
            handover.status = CodeStatus.USED
            handover.used_at = now
            handover.used_by = actor
            handover.save(update_fields=["status", "used_at", "used_by"])
            request.status = RequestStatus.COLLECTED
            request.collected_at = now
            request.save(update_fields=["status", "collected_at"])
            _record(handover, actor, AttemptOutcome.SUCCESS, ip)

            # Stop live tracking session on completed handover
            from core.tracking_service import stop_tracking_session
            try:
                stop_tracking_session(request.pk, actor, reason="completed")
            except Exception:
                pass
            log_activity(actor, "pickup.collected", f"Handover confirmed for pickup #{request.pk}", request)
        else:
            handover.failed_attempts += 1
            _record(handover, actor, AttemptOutcome.WRONG, ip)
            if handover.failed_attempts >= MAX_PICKUP_ATTEMPTS:
                handover.status = CodeStatus.LOCKED
                handover.locked_at = timezone.now()
                handover.save(update_fields=["failed_attempts", "status", "locked_at"])
                for admin in User.objects.filter(role=Role.ADMIN):
                    notify(
                        admin, "lockout",
                        f"Pickup #{request.pk} was locked after {MAX_PICKUP_ATTEMPTS} wrong code attempts.",
                        link="/manage/locked-pickups/",
                    )
                log_activity(
                    actor, "pickup.locked", f"Pickup #{request.pk} locked after {MAX_PICKUP_ATTEMPTS} wrong attempts", request
                )
                failure = "Too many wrong attempts. This pickup is now locked and an admin has been notified."
            else:
                handover.save(update_fields=["failed_attempts"])
                failure = (
                    f"That code doesn't match. {handover.attempts_left} attempt(s) left before this pickup locks."
                )

    if failure:
        raise FoodBridgeError(failure)
    notify(request.recipient_user, "collected", f"Pickup confirmed at {request.listing.hotel.name}. Thank you!", link="/ngo/requests/")
    return request


# ----------------------------------------------------------------------------- admin unlock
@transaction.atomic
def unlock_handover(pickup_request_id, actor):
    """Admin only (enforced in the view). Resets the counter AND issues a new code, so anything a
    guesser learned about the old one is worthless."""
    request = PickupRequest.objects.select_for_update().select_related("handover", "ngo__user", "individual__user").get(pk=pickup_request_id)
    handover = request.handover
    if handover.status != CodeStatus.LOCKED:
        raise FoodBridgeError("This pickup isn't locked.")
    if timezone.now() >= handover.expires_at:
        raise FoodBridgeError("The safe-until time has passed, so unlocking can't help. Cancel the pickup instead.")
    handover.status = CodeStatus.ACTIVE
    handover.failed_attempts = 0
    handover.locked_at = None
    handover.salt = new_salt()
    handover.issued_at = timezone.now()
    handover.save(update_fields=["status", "failed_attempts", "locked_at", "salt", "issued_at"])
    log_activity(actor, "pickup.unlocked", f"Pickup #{request.pk} unlocked and a new code issued", request)
    notify(request.recipient_user, "confirmed", "An admin reset your pickup code. Open My requests to see the new one.", link="/ngo/requests/")
    return handover
