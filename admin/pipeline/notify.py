"""Outgoing claim-flow email — stdlib smtplib only, no new dependency
(TRD.md §8, 2026-07-25 exception)."""

from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

_logger = logging.getLogger("admin.notify")

from admin.config import (
    ADMIN_BASE_URL,
    CLAIM_NOTIFY_EMAIL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
)
from admin.pipeline.claims_store import ClaimRequest

PLAN_LABELS = {"one_off": "one-off $25 processing fee", "subscription": "$5/month unlimited-changes subscription"}


def _send(to_addr: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    if not SMTP_HOST:
        return  # unconfigured in local dev — silently no-op rather than error the caller

    message = EmailMessage()
    message["From"] = SMTP_FROM or SMTP_USERNAME
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        # multipart/alternative via stdlib email — no new dependency. Mail
        # clients that render HTML (effectively all of them) show this;
        # text-only clients fall back to the plain part set above.
        message.add_alternative(body_html, subtype="html")

    # A mail failure must never take down the caller — the claim/approval/
    # denial it's reporting on has already happened and is safely recorded;
    # losing the notification is recoverable (the admin can still see
    # everything in the /claims screen), a 500 on a public submission
    # endpoint is not. Log and move on rather than propagate.
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.starttls()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        _logger.error("failed to send %r to %s: %s", subject, to_addr, exc)


def _format_diff(diff: dict[str, Any]) -> str:
    if not diff:
        return "(no field changes — photo only)"
    lines = []
    for field, change in diff.items():
        lines.append(f"  {field}: {change['old']!r} -> {change['new']!r}")
    return "\n".join(lines)


def send_claim_notification_email(request: ClaimRequest, venue_name: str, diff: dict[str, Any]) -> None:
    admin_link = f"\n\nReview: {ADMIN_BASE_URL}/claims/{request.id}" if ADMIN_BASE_URL else ""
    photo_note = "\n\nA photo was attached to this request." if request.has_photo else ""
    # Action links require ADMIN_BASE_URL (optional) — without it there's
    # nowhere for them to point, so fall back to the admin-only review link
    # above rather than emit broken URLs.
    action_links = ""
    if ADMIN_BASE_URL and request.action_token:
        action_links = (
            f"\n\nApprove: {ADMIN_BASE_URL}/claim-action/{request.id}/approve?token={request.action_token}"
            f"\nDeny: {ADMIN_BASE_URL}/claim-action/{request.id}/deny?token={request.action_token}"
            f"\n(opens a confirmation page — nothing happens until you click the button there)"
        )
    body = (
        f"New claim request for {venue_name} ({request.slug}).\n\n"
        f"From: {request.requester_name} <{request.requester_email}>\n"
        f"Plan: {PLAN_LABELS.get(request.plan_type, request.plan_type)}\n\n"
        f"Requested changes:\n{_format_diff(diff)}"
        f"{photo_note}{action_links}{admin_link}"
    )
    _send(CLAIM_NOTIFY_EMAIL, f"Claim request: {venue_name}", body)


def send_approval_payment_email(request: ClaimRequest, venue_name: str, checkout_url: str) -> None:
    plan_label = PLAN_LABELS.get(request.plan_type, request.plan_type)
    text_body = (
        f"YOUR UPDATE ISN'T LIVE YET — one step left.\n\n"
        f"Your requested changes to the {venue_name} listing have been approved, but they will "
        f"not publish until payment is completed for the {plan_label}.\n\n"
        f"Finish here: {checkout_url}\n\n"
        f"Your changes go live automatically, with no further action, the moment payment is confirmed."
    )
    safe_venue = html.escape(venue_name)
    safe_plan = html.escape(plan_label)
    html_body = (
        f"<p><strong>Your update isn't live yet — one step left.</strong></p>"
        f"<p>Your requested changes to the {safe_venue} listing have been approved, but they "
        f"will not publish until payment is completed for the {safe_plan}.</p>"
        f'<p><a href="{checkout_url}">Click here to finalise your payment with Stripe</a></p>'
        f"<p>Your changes go live automatically, with no further action, the moment payment is confirmed.</p>"
    )
    _send(
        request.requester_email,
        f"Action needed — finish your {venue_name} listing update",
        text_body,
        html_body,
    )


def send_approval_no_payment_email(request: ClaimRequest, venue_name: str) -> None:
    body = (
        f"Your requested changes to the {venue_name} listing have been approved.\n\n"
        f"As an active subscriber, no payment is needed — your update will go live shortly."
    )
    _send(request.requester_email, f"Your listing update for {venue_name} is approved", body)


def send_denial_email(request: ClaimRequest, venue_name: str) -> None:
    reason = f"\n\nReason: {request.review_note}" if request.review_note else ""
    body = f"Your requested changes to the {venue_name} listing were not approved.{reason}\n\nYou have not been charged."
    _send(request.requester_email, f"Your listing update request for {venue_name}", body)


def send_published_email(request: ClaimRequest, venue_name: str) -> None:
    body = f"Your requested changes to the {venue_name} listing are now live."
    _send(request.requester_email, f"Your {venue_name} listing update is live", body)
