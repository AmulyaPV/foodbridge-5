"""Messaging service: conversations, messages, security, deduplication, and polling."""
import uuid
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from core.constants import MAX_MESSAGES_PER_MINUTE, MAX_MESSAGE_LENGTH
from core.exceptions import FoodBridgeError
from core.models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    FoodListing,
    Message,
    Notification,
    NotificationType,
    PickupRequest,
)
from core.notify import notify


def get_or_create_request_conversation(pickup_request):
    """
    Ensures a conversation exists for the given pickup request.
    Participants are the hotel user and the recipient user.
    """
    hotel_user = pickup_request.listing.hotel.user
    recipient_user = pickup_request.recipient_user

    conv = Conversation.objects.filter(
        conversation_type=ConversationType.REQUEST,
        pickup_request=pickup_request,
    ).first()

    if not conv:
        conv = Conversation.objects.create(
            conversation_type=ConversationType.REQUEST,
            pickup_request=pickup_request,
            listing=pickup_request.listing,
        )
        ConversationParticipant.objects.get_or_create(conversation=conv, user=hotel_user)
        ConversationParticipant.objects.get_or_create(conversation=conv, user=recipient_user)

    return conv


def get_or_create_listing_enquiry(listing, user):
    """
    Ensures an enquiry conversation exists between a user and the listing's hotel.
    """
    hotel_user = listing.hotel.user
    if user == hotel_user:
        raise FoodBridgeError("You cannot message yourself about your own listing.")

    conv = (
        Conversation.objects.filter(
            conversation_type=ConversationType.LISTING_ENQUIRY,
            listing=listing,
            participants__user=user,
        )
        .filter(participants__user=hotel_user)
        .first()
    )

    if not conv:
        conv = Conversation.objects.create(
            conversation_type=ConversationType.LISTING_ENQUIRY,
            listing=listing,
        )
        ConversationParticipant.objects.get_or_create(conversation=conv, user=hotel_user)
        ConversationParticipant.objects.get_or_create(conversation=conv, user=user)

    return conv


def get_or_create_support_conversation(user):
    """Support conversation between user and administrator."""
    conv = Conversation.objects.filter(
        conversation_type=ConversationType.SUPPORT,
        participants__user=user,
    ).first()

    if not conv:
        conv = Conversation.objects.create(
            conversation_type=ConversationType.SUPPORT,
        )
        ConversationParticipant.objects.get_or_create(conversation=conv, user=user)

    return conv


def send_message(conversation_id, sender_user, body, client_uuid=None, is_system=False):
    """
    Sends a message in a conversation.
    - Security: checks sender is an unblocked participant or admin.
    - Idempotency: dedupes on (conversation, client_uuid).
    - Rate limit: ~20 msgs per minute.
    - Escapes body content, max 2000 chars.
    - Throttles 'new message' notifications (at most 1 unread notification per conversation).
    """
    conv = Conversation.objects.get(pk=conversation_id)

    # Check participant permissions
    if not is_system and sender_user is not None:
        part = ConversationParticipant.objects.filter(conversation=conv, user=sender_user).first()
        if not part and not sender_user.is_superuser and sender_user.role != "admin":
            raise PermissionDenied("You are not a participant in this conversation.")
        if part and part.is_blocked:
            raise PermissionDenied("You have been blocked from sending messages in this conversation.")

        # Rate limiting check
        one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
        recent_count = Message.objects.filter(
            conversation=conv, sender=sender_user, created_at__gte=one_minute_ago
        ).count()
        if recent_count >= MAX_MESSAGES_PER_MINUTE:
            raise FoodBridgeError("You are sending messages too quickly. Please wait a moment.")

    # Deduplication
    if client_uuid:
        existing = Message.objects.filter(conversation=conv, client_uuid=client_uuid).first()
        if existing:
            return existing

    clean_body = escape(body.strip())[:MAX_MESSAGE_LENGTH]
    if not clean_body:
        raise FoodBridgeError("Message cannot be empty.")

    with transaction.atomic():
        msg = Message.objects.create(
            conversation=conv,
            sender=sender_user if not is_system else None,
            body=clean_body,
            client_uuid=client_uuid or (str(uuid.uuid4()) if not is_system else None),
            is_system=is_system,
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=["updated_at"])

        # Update last_read_at for sender
        if sender_user and not is_system:
            ConversationParticipant.objects.filter(conversation=conv, user=sender_user).update(
                last_read_at=timezone.now()
            )

    # Throttled notifications to other participants
    if not is_system and sender_user:
        other_participants = conv.participants.exclude(user=sender_user).select_related("user")
        for p in other_participants:
            # Check if there is already an unread NEW_MESSAGE notification for this user and conversation
            notif_link = f"/messages/{conv.pk}/"
            already_notified = Notification.objects.filter(
                user=p.user,
                kind=NotificationType.NEW_MESSAGE,
                link=notif_link,
                is_read=False,
            ).exists()
            if not already_notified:
                notify(
                    p.user,
                    NotificationType.NEW_MESSAGE,
                    f"New message from {sender_user.display_name}: {clean_body[:40]}...",
                    link=notif_link,
                )

    return msg


def post_system_event(conversation_id, text):
    """Utility to post automated audit/status events into request chat."""
    return send_message(conversation_id, None, text, is_system=True)
