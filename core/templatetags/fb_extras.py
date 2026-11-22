from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.reliability import reliability_percent as _reliability_percent

register = template.Library()

# label and colour for each account verification state
VERIFICATION = {
    "pending": ("Pending verification", "amber"),
    "approved": ("Verified", "green"),
    "rejected": ("Rejected", "red"),
    "suspended": ("Suspended", "dark"),
}


@register.simple_tag
def verification_badge(status):
    label, colour = VERIFICATION.get(status, (str(status).title(), "grey"))
    return format_html('<span class="fb-badge fb-badge--{}">{}</span>', colour, label)


# label and colour for each pickup-request status
REQUEST_STATUS = {
    "requested": ("Requested", "amber"),
    "confirmed": ("Confirmed", "green"),
    "rejected": ("Declined", "red"),
    "on_the_way": ("On the way", "blue"),
    "collected": ("Collected", "green"),
    "cancelled": ("Cancelled", "dark"),
    "expired": ("Expired", "dark"),
}


@register.simple_tag
def request_status_badge(status):
    label, colour = REQUEST_STATUS.get(status, (str(status).title(), "grey"))
    return format_html('<span class="fb-badge fb-badge--{}">{}</span>', colour, label)


# the listing words used in the project report: available, requested, confirmed, collected, expired
LISTING_STATUS_COLOUR = {
    "available": "green",
    "requested": "amber",
    "confirmed": "blue",
    "collected": "green",
    "expired": "dark",
    "cancelled": "dark",
    "removed": "red",
}


@register.simple_tag
def listing_status_badge(listing):
    key, label = listing.display_status
    return format_html('<span class="fb-badge fb-badge--{}">{}</span>', LISTING_STATUS_COLOUR.get(key, "grey"), label)


@register.filter
def reliability_percent(profile):
    return _reliability_percent(profile)


@register.filter
def field(form, name):
    """{{ form|field:"email" }} gives the bound field called email."""
    return form[name]


@register.filter
def is_checkbox(bound_field):
    return bound_field.field.widget.__class__.__name__ == "CheckboxInput"


@register.filter
def bs(bound_field):
    """Render a form field with the right Bootstrap 5 class."""
    widget = bound_field.field.widget
    kind = widget.__class__.__name__
    if kind in {"RadioSelect", "CheckboxSelectMultiple"}:
        return bound_field
    if kind == "CheckboxInput":
        base = "form-check-input"
    elif kind in {"Select", "SelectMultiple"}:
        base = "form-select"
    else:
        base = "form-control"
    classes = f"{widget.attrs.get('class', '')} {base}".strip()
    if bound_field.errors:
        classes += " is-invalid"
    return bound_field.as_widget(attrs={"class": classes})


@register.filter
def hms(seconds):
    """3725 -> '1h 02m', 540 -> '9m 00s', 0 -> 'now'. Used for the first paint of every clock."""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return "none left"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


@register.filter
def clock_state(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "ok"
    if seconds <= 0:
        return "late"
    return "late" if seconds < 900 else "soon" if seconds < 2700 else "ok"


@register.filter
def epoch(value):
    """A datetime as epoch seconds (what the clocks read)."""
    return int(value.timestamp()) if value else ""


# ------------------------------------------------------------------ icons: one stroke set, 24px grid
ICONS = {
    "list": '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    "inbox": '<path d="M3 13l3-8h12l3 8v6H3z"/><path d="M3 13h5l1 3h6l1-3h5"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v5l3 2"/>',
    "board": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "leaf": '<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19c3-5 6-8 10-10"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/>',
    "bell": '<path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 5h12l-2 4 2 4H5"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.5 2.7-6 6-6s6 2.5 6 6"/><circle cx="17" cy="9" r="2.4"/><path d="M16 14c3 0 5 2 5 5"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
    "pulse": '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "pin": '<path d="M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "home": '<path d="M4 11l8-7 8 7v9H4z"/><path d="M10 20v-6h4v6"/>',
    "out": '<path d="M9 4H5v16h4"/><path d="M16 8l4 4-4 4M20 12H9"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z"/>',
    "route": '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6"/>',
}


@register.simple_tag
def icon(name, size=20):
    body = ICONS.get(name, "")
    return mark_safe(
        f'<svg class="fb-icon" width="{int(size)}" height="{int(size)}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


@register.simple_tag
def clock_pct(listing):
    """How much of the listing's safe window is still left, as a whole percent (first paint of the bar)."""
    from django.utils import timezone

    total = (listing.safe_until - listing.created_at).total_seconds()
    left = (listing.safe_until - timezone.now()).total_seconds()
    if total <= 0:
        return 0
    return max(0, min(100, round(left / total * 100)))
