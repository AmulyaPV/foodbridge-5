"""Messaging, food-wise requesting, partial approval, and pickup views."""
import json
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import hotel_required, recipient_required
from accounts.models import Role
from core.exceptions import FoodBridgeError
from core.messaging_service import (
    get_or_create_listing_enquiry,
    get_or_create_request_conversation,
    get_or_create_support_conversation,
    post_system_event,
    send_message,
)
from core.models import (
    Conversation,
    ConversationParticipant,
    FoodListing,
    ItemRequestStatus,
    ListingStatus,
    Message,
    PickupProposal,
    PickupRequest,
    PickupRequestItem,
    RequestStatus,
)
from core.requests_service import (
    create_request as create_request_service,
    decide_request as decide_request_service,
    respond_to_proposal as respond_to_proposal_service,
    cancel_request as cancel_request_service,
)


# ----------------------------------------------------------------------------- Conversations
@login_required
def conversation_list(request):
    """Lists conversations for the logged in user with unread counts and last message."""
    user = request.user
    if user.is_admin_role:
        # Admins see support conversations or reported conversations
        convs = Conversation.objects.filter(
            Q(conversation_type="support") | Q(participants__user=user)
        ).distinct().order_by("-updated_at")
    else:
        convs = Conversation.objects.filter(
            participants__user=user
        ).order_by("-updated_at")

    conversation_data = []
    for conv in convs:
        participant = conv.participants.filter(user=user).first()
        last_msg = conv.messages.order_by("-created_at").first()
        unread_count = 0
        if participant and participant.last_read_at:
            unread_count = conv.messages.filter(created_at__gt=participant.last_read_at).exclude(sender=user).count()
        elif participant:
            unread_count = conv.messages.exclude(sender=user).count()

        other_participant = conv.participants.exclude(user=user).select_related("user").first()
        other_name = other_participant.user.display_name if other_participant else "Support"
        other_role = other_participant.user.get_role_display() if other_participant else "System"

        conversation_data.append({
            "conversation": conv,
            "other_name": other_name,
            "other_role": other_role,
            "last_message": last_msg,
            "unread_count": unread_count,
        })

    return render(request, "core/conversation_list.html", {"conversations": conversation_data})


@login_required
def conversation_detail(request, pk):
    """View conversation thread and interactive chat interface."""
    user = request.user
    conv = get_object_or_404(
        Conversation.objects.select_related("listing__hotel", "pickup_request"),
        pk=pk,
    )
    participant = conv.participants.filter(user=user).first()
    if not participant and not user.is_admin_role:
        raise PermissionDenied("You are not part of this conversation.")

    if participant:
        participant.last_read_at = timezone.now()
        participant.save(update_fields=["last_read_at"])

    # Load recent 100 messages
    messages_qs = conv.messages.select_related("sender").order_by("created_at")[:100]

    other_participant = conv.participants.exclude(user=user).select_related("user").first()
    other_user = other_participant.user if other_participant else None

    # Proposals linked to this request if applicable
    proposals = []
    if conv.pickup_request:
        proposals = conv.pickup_request.pickup_proposals.order_by("-created_at")

    return render(
        request,
        "core/conversation_detail.html",
        {
            "conversation": conv,
            "participant": participant,
            "messages": messages_qs,
            "other_user": other_user,
            "proposals": proposals,
        },
    )


@require_POST
def api_send_message(request, pk):
    """AJAX endpoint for sending a message in a conversation."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)
    body = request.POST.get("body", "").strip()
    client_uuid = request.POST.get("client_uuid", "").strip() or None

    try:
        msg = send_message(pk, user, body, client_uuid=client_uuid)
        return JsonResponse({
            "success": True,
            "message": {
                "id": msg.id,
                "sender": msg.sender.display_name if msg.sender else "System",
                "is_me": (msg.sender == user),
                "is_system": msg.is_system,
                "body": msg.body,
                "created_at": msg.created_at.strftime("%H:%M"),
            }
        })
    except (FoodBridgeError, PermissionDenied) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
def api_poll_messages(request, pk):
    """AJAX endpoint fetching messages newer than after_id."""
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"error": "Authentication required", "authenticated": False}, status=401)
    conv = get_object_or_404(Conversation, pk=pk)
    participant = conv.participants.filter(user=user).first()
    if not participant and not user.is_admin_role:
        raise PermissionDenied("You are not part of this conversation.")

    if participant:
        participant.last_read_at = timezone.now()
        participant.save(update_fields=["last_read_at"])

    after_id = request.GET.get("after_id", "0")
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    new_msgs = conv.messages.filter(id__gt=after_id).select_related("sender").order_by("id")
    data = [
        {
            "id": m.id,
            "sender": m.sender.display_name if m.sender else "System",
            "is_me": (m.sender == user),
            "is_system": m.is_system,
            "body": m.body,
            "created_at": m.created_at.strftime("%H:%M"),
        }
        for m in new_msgs
    ]
    return JsonResponse({"success": True, "messages": data})


@login_required
def contact_hotel_for_listing(request, pk):
    """Opens or starts a listing enquiry chat with the hotel."""
    listing = get_object_or_404(FoodListing, pk=pk)
    try:
        conv = get_or_create_listing_enquiry(listing, request.user)
        return redirect("core:conversation_detail", pk=conv.pk)
    except FoodBridgeError as e:
        messages.error(request, str(e))
        return redirect("core:listing_detail", pk=pk)


@login_required
@require_POST
def propose_pickup_time(request, pk):
    """Propose or update a planned pickup time inside conversation."""
    req = get_object_or_404(PickupRequest, pk=pk)
    proposed_time_str = request.POST.get("proposed_time")
    notes = request.POST.get("notes", "").strip()

    if not proposed_time_str:
        messages.error(request, "Please choose a pickup time.")
        return redirect("core:my_requests")

    try:
        prop = PickupProposal.objects.create(
            pickup_request=req,
            proposed_by=request.user,
            proposed_time=proposed_time_str,
            notes=notes,
        )
        conv = get_or_create_request_conversation(req)
        post_system_event(
            conv.id,
            f"{request.user.display_name} proposed pickup time: {prop.proposed_time.strftime('%d %b, %H:%M')}. Notes: {notes or 'None'}",
        )
        messages.success(request, "Pickup proposal sent.")
    except Exception as e:
        messages.error(request, f"Could not schedule proposal: {e}")

    return redirect("core:conversation_detail", pk=conv.pk)


# ----------------------------------------------------------------------------- Hotel Partial Decisions & Recipient Proposals
@hotel_required
def hotel_decide_request(request, pk):
    """Hotel reviews incoming food-wise request and submits approval / partial proposals."""
    profile = request.user.profile
    pickup_request = get_object_or_404(
        PickupRequest.objects.select_related("listing", "ngo", "individual"),
        pk=pk,
        listing__hotel=profile,
    )
    items = pickup_request.items.select_related("food_item").all()

    if request.method == "POST":
        action = request.POST.get("action", "partial_decide")
        reason = request.POST.get("reason", "").strip()

        if action == "approve_all":
            try:
                decide_request_service(pickup_request.pk, request.user, action="approve_all")
                messages.success(request, "All requested items confirmed. Pickup code issued to recipient.")
                return redirect("core:hotel_requests")
            except FoodBridgeError as e:
                messages.error(request, str(e))

        elif action == "reject":
            try:
                decide_request_service(pickup_request.pk, request.user, action="reject", reason=reason)
                messages.success(request, "Request declined.")
                return redirect("core:hotel_requests")
            except FoodBridgeError as e:
                messages.error(request, str(e))

        elif action == "partial_decide":
            item_decisions = {}
            for item in items:
                dec_action = request.POST.get(f"item_action_{item.id}", "approve")
                dec_qty = request.POST.get(f"item_qty_{item.id}", item.requested_quantity)
                item_decisions[item.id] = {
                    "action": dec_action,
                    "quantity": dec_qty,
                }

            try:
                decide_request_service(
                    pickup_request.pk,
                    request.user,
                    action="partial_decide",
                    item_decisions=item_decisions,
                    reason=reason,
                )
                messages.success(request, "Request processed according to item decisions.")
                return redirect("core:hotel_requests")
            except FoodBridgeError as e:
                messages.error(request, str(e))

    return render(
        request,
        "core/hotel_request_decide.html",
        {
            "pickup_request": pickup_request,
            "items": items,
        },
    )


@recipient_required
def recipient_review_proposal(request, pk):
    """Recipient reviews a hotel's revised quantity proposal to accept or decline."""
    owner = {"ngo": request.user.profile} if request.user.is_ngo else {"individual": request.user.profile}
    pickup_request = get_object_or_404(
        PickupRequest.objects.select_related("listing__hotel"),
        pk=pk,
        **owner,
    )
    items = pickup_request.items.select_related("food_item").all()

    if request.method == "POST":
        decision = request.POST.get("decision")
        accept = (decision == "accept")
        try:
            respond_to_proposal_service(pickup_request.pk, request.user, accept=accept)
            if accept:
                messages.success(request, "Proposal accepted! Your pickup code has been issued.")
            else:
                messages.info(request, "You declined the proposed quantities.")
            return redirect("core:my_requests")
        except FoodBridgeError as e:
            messages.error(request, str(e))

    return render(
        request,
        "core/proposal_review.html",
        {
            "pickup_request": pickup_request,
            "items": items,
        },
    )
