"""Claim-request lifecycle orchestration (TRD.md §8, 2026-07-25 exception) —
the analogue of staging.py for the visitor-submitted claim flow. Owns
submission, approval/denial, Stripe payment, and the shared publish path,
wiring together claims_store, staging, images, stripe_client and notify.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from admin.config import CLAIMS_TEMP_DIR, SITE_URL, STRIPE_PRICE_ONEOFF, STRIPE_PRICE_SUBSCRIPTION
from admin.pipeline import images, notify, staging, stripe_client
from admin.pipeline import claims_store
from admin.pipeline.claims_store import ClaimRequest

ALLOWED_PATCH_FIELDS = {
    "name", "address", "suburb", "hours", "cost", "access",
    "amenities", "facilities", "summary",
}

RATE_LIMIT_WINDOW_SECONDS = 3600
RATE_LIMIT_MAX_PER_WINDOW = 5


class InvalidPatch(Exception):
    pass


class RateLimitExceeded(Exception):
    pass


def _venue_name(slug: str) -> str:
    return staging.get_published(slug).frontmatter.get("name", slug)


def compute_diff(slug: str, patch: dict[str, Any]) -> dict[str, Any]:
    """{field: {old, new}} against the venue's CURRENT published
    frontmatter (read live, not the frontmatter at submission time) —
    amenities/facilities diffed per sub-key. Fields with no actual change
    are omitted, so the review pane and notification email only ever show
    real deltas."""
    current = staging.get_published(slug).frontmatter
    diff: dict[str, Any] = {}
    for field, new_value in patch.items():
        old_value = current.get(field)
        if field in ("amenities", "facilities") and isinstance(new_value, dict):
            sub_diff = {}
            for key, val in new_value.items():
                old_val = (old_value or {}).get(key)
                if old_val != val:
                    sub_diff[key] = {"old": old_val, "new": val}
            if sub_diff:
                diff[field] = sub_diff
        elif old_value != new_value:
            diff[field] = {"old": old_value, "new": new_value}
    return diff


def submit_request(
    *,
    slug: str,
    requester_name: str,
    requester_email: str,
    plan_type: str,
    patch: dict[str, Any],
    photo_bytes: bytes | None = None,
    photo_content_type: str | None = None,
    photo_caption: str | None = None,
    honeypot_value: str = "",
) -> ClaimRequest:
    staging.get_published(slug)  # raises FileNotFoundError if the slug doesn't exist

    invalid_keys = set(patch) - ALLOWED_PATCH_FIELDS
    if invalid_keys:
        raise InvalidPatch(f"unexpected patch field(s): {', '.join(sorted(invalid_keys))}")
    if plan_type not in ("one_off", "subscription"):
        raise InvalidPatch("plan_type must be 'one_off' or 'subscription'")

    if claims_store.count_recent_for_slug(slug, RATE_LIMIT_WINDOW_SECONDS) >= RATE_LIMIT_MAX_PER_WINDOW:
        raise RateLimitExceeded(slug)

    honeypot_tripped = bool(honeypot_value.strip())
    has_photo = photo_bytes is not None

    request = claims_store.create_request(
        slug=slug,
        requester_name=requester_name,
        requester_email=requester_email,
        plan_type=plan_type,
        patch=patch,
        has_photo=has_photo,
        photo_caption=photo_caption,
        honeypot_tripped=honeypot_tripped,
    )

    if has_photo:
        ext = (photo_content_type or "image/jpeg").split("/")[-1].split(";")[0] or "jpg"
        photo_dir = CLAIMS_TEMP_DIR / str(request.id)
        photo_dir.mkdir(parents=True, exist_ok=True)
        photo_path = photo_dir / f"photo.{ext}"
        photo_path.write_bytes(photo_bytes)
        claims_store.set_photo_path(request.id, str(photo_path))
        request = claims_store.get_request(request.id)

    if honeypot_tripped:
        # A bot fills hidden fields; a real visitor never sees this one. Store
        # the row as denied and skip the owner's inbox entirely, but return a
        # normal-looking request either way — nothing here signals to the
        # caller (or the bot) that it was filtered.
        claims_store.update_status(request.id, "denied", review_note="honeypot")
        return claims_store.get_request(request.id)

    notify.send_claim_notification_email(request, _venue_name(slug), compute_diff(slug, patch))
    return request


def approve_request(request_id: int, review_note: str = "") -> ClaimRequest:
    request = claims_store.get_request(request_id)
    venue_name = _venue_name(request.slug)

    subscription = stripe_client.find_active_subscription_by_email(request.requester_email)
    if subscription is not None:
        claims_store.set_stripe_customer(request_id, subscription["customer_id"])
        claims_store.mark_returning_subscriber(request_id)
        request = claims_store.update_status(request_id, "approved", review_note=review_note)
        notify.send_approval_no_payment_email(request, venue_name)
        return request

    price_id = STRIPE_PRICE_ONEOFF if request.plan_type == "one_off" else STRIPE_PRICE_SUBSCRIPTION
    mode = "payment" if request.plan_type == "one_off" else "subscription"
    session = stripe_client.create_checkout_session(
        price_id=price_id,
        mode=mode,
        customer_email=request.requester_email,
        success_url=f"{SITE_URL}/spa/{request.slug}/?claim=success",
        cancel_url=f"{SITE_URL}/spa/{request.slug}/?claim=cancelled",
        metadata={"claim_request_id": str(request_id), "slug": request.slug},
    )
    claims_store.set_stripe_session(request_id, session["id"], session.get("customer"))
    request = claims_store.update_status(request_id, "awaiting_payment", review_note=review_note)
    notify.send_approval_payment_email(request, venue_name, session["url"])
    return request


def deny_request(request_id: int, review_note: str) -> ClaimRequest:
    request = claims_store.update_status(request_id, "denied", review_note=review_note)
    notify.send_denial_email(request, _venue_name(request.slug))
    return request


def publish_request(request_id: int) -> None:
    """The single shared publish path — called by both the Stripe webhook
    (paid, non-subscriber requests) and the subscriber's manual Publish
    click (no payment, but still a deliberate action). Writes straight to
    the published MDX/DB/JSON; auto-deploying the result to the live site is
    scheduled separately by the caller (admin/app.py), since that needs a
    FastAPI BackgroundTasks handle this module doesn't have."""
    request = claims_store.get_request(request_id)
    patch = dict(request.patch)
    patch["status"] = "claimed"
    staging.update_published(request.slug, patch)

    if request.has_photo and request.photo_path:
        venue = staging.get_published(request.slug)
        fields = images.publish_uploaded_image(
            request.slug,
            Path(request.photo_path),
            source_url=venue.frontmatter["website"],
            caption=request.photo_caption or "",
        )
        staging.publish_image_fields_on_published(request.slug, fields)

    claims_store.update_status(request_id, "published")
    notify.send_published_email(request, _venue_name(request.slug))


def handle_checkout_completed(session_id: str, stripe_customer_id: str | None) -> None:
    """Stripe fires checkout.session.completed at-least-once — this must be
    safe to call twice for the same session. No-ops unless the matching row
    is still 'awaiting_payment'."""
    request = claims_store.get_by_session_id(session_id)
    if request is None or request.status != "awaiting_payment":
        return
    claims_store.set_stripe_session(request.id, session_id, stripe_customer_id)
    claims_store.update_status(request.id, "paid")
    publish_request(request.id)
