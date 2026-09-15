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
    SITE_URL,
    CLAIM_NOTIFY_EMAIL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
    VERIFIABLE_FIELD_LABELS,
)
from admin.pipeline.claims_store import ClaimRequest

PLAN_LABELS = {"one_off": "one-off $25 processing fee", "subscription": "$5/month unlimited-changes subscription"}


def _send(to_addr: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Returns whether the message actually went out.

    The claim-flow callers ignore this and always have (a failed notification
    must never 500 a public submission endpoint). Gate 13's outreach flow does
    not: it records a state transition saying an operator was contacted, and
    that must not be written when nothing was sent.
    """
    if not SMTP_HOST:
        return False  # unconfigured in local dev — no-op rather than error the caller

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
        return True
    except (OSError, smtplib.SMTPException) as exc:
        _logger.error("failed to send %r to %s: %s", subject, to_addr, exc)
        return False


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


# ---------------------------------------------------------------------------
# Operator outreach (Gate 13, 2026-09-08)
# ---------------------------------------------------------------------------



def _field_value(frontmatter: dict[str, Any], field: str) -> str:
    """What we currently publish for a field, as a reader would see it. Quoting
    it back is the whole point of the email: an operator can correct a specific
    wrong figure far more easily than answer 'is your listing right?'."""
    if field == "price":
        return str(frontmatter.get("cost") or "").strip() or "(nothing recorded)"
    if field == "temperatures":
        temps = frontmatter.get("temperatures") or {}
        parts = [str(v) for v in (temps.get("sauna_display"), temps.get("cold_plunge_display")) if v]
        for low, high, label in (
            ("sauna_min_c", "sauna_max_c", "sauna"),
            ("cold_plunge_min_c", "cold_plunge_max_c", "cold plunge"),
        ):
            lo, hi = temps.get(low), temps.get(high)
            if lo is not None and hi is not None:
                parts.append(f"{label} {lo} to {hi} degrees" if lo != hi else f"{label} {lo} degrees")
        return "; ".join(parts) or "(nothing recorded)"
    value = frontmatter.get(field)
    if value in (None, "", {}):
        return "(nothing recorded)"
    return str(value)


def send_outreach_email(
    *,
    slug: str,
    venue_name: str,
    operator_email: str,
    operator_name: str,
    fields: list[str],
    frontmatter: dict[str, Any],
) -> bool:
    """Ask an operator to confirm or correct what we publish about their venue.

    Deliberately quotes the current values back rather than linking and asking
    them to check: a wrong price is easy to spot in a list and easy to reply to.

    The listing is free and stays free whatever they do with this email, so the
    email says so plainly before it mentions the paid claim option. An operator
    who reads this as an invoice, or as pay-to-be-listed, would be right to be
    annoyed and wrong about the facts.
    """
    site = SITE_URL or "https://wherewebathe.com"
    greeting = f"Hello {operator_name}," if operator_name.strip() else "Hello,"
    lines = [f"{VERIFIABLE_FIELD_LABELS.get(f, f)}: {_field_value(frontmatter, f)}" for f in fields]
    recorded = "\n".join(f"  - {line}" for line in lines) or "  (we hold no detail beyond the basics)"

    body_text = f"""{greeting}

I run Where We Bathe, a free directory of Australian bathhouses, saunas and hot
springs. {venue_name} is listed at {site}/spa/{slug}/.

The listing is free, we take nothing for it, and nothing on the site ranks
because a venue paid. I am writing because I would rather publish what you tell
me than what I could work out from your website.

Here is what we currently have on record:

{recorded}

If any of that is wrong or out of date, reply and tell me what it should be. If
it is all correct, a one line "that's right" is enough. Either way I will mark
those details as confirmed by you, and the page will say so.

If you would also like to send through changes yourself in future, there is a
paid option at {site}/claim/{slug}/. That is entirely separate. Confirming these
details costs nothing and your listing does not change if you ignore it.

Thanks,
Where We Bathe
{site}
"""

    recorded_html = "".join(f"<li>{html.escape(line)}</li>" for line in lines) or "<li>(we hold no detail beyond the basics)</li>"
    body_html = f"""<p>{html.escape(greeting)}</p>
<p>I run Where We Bathe, a free directory of Australian bathhouses, saunas and hot springs.
{html.escape(venue_name)} is listed at <a href="{site}/spa/{slug}/">{site}/spa/{slug}/</a>.</p>
<p>The listing is free, we take nothing for it, and nothing on the site ranks because a venue paid.
I am writing because I would rather publish what you tell me than what I could work out from your website.</p>
<p>Here is what we currently have on record:</p>
<ul>{recorded_html}</ul>
<p>If any of that is wrong or out of date, reply and tell me what it should be. If it is all correct,
a one line &quot;that&#39;s right&quot; is enough. Either way I will mark those details as confirmed by you,
and the page will say so.</p>
<p>If you would also like to send through changes yourself in future, there is a paid option at
<a href="{site}/claim/{slug}/">{site}/claim/{slug}/</a>. That is entirely separate. Confirming these
details costs nothing and your listing does not change if you ignore it.</p>
<p>Thanks,<br />Where We Bathe<br /><a href="{site}">{site}</a></p>
"""
    return _send(operator_email, f"{venue_name} — the details we publish about you", body_text, body_html)


# --- SMTP preflight (Gate 13, 2026-09-15) --------------------------------
# Wiring a mail provider up is four settings and a DNS record, and every way it
# fails looks the same from the admin screen: the button refuses and the venue
# stays uncontacted. This turns each failure into its own message, and does it
# without sending anything until asked.
#
# No setting's value is ever printed — CLAUDE.md rule 5. Presence, and the one
# structural mistake worth naming (port 465), is enough to diagnose all of it.

def config_report() -> tuple[list[str], list[str]]:
    """(lines, problems) — what is configured, and what will stop a send."""
    lines: list[str] = []
    problems: list[str] = []

    for label, value, required in (
        ("SMTP_HOST", SMTP_HOST, True),
        ("SMTP_USERNAME", SMTP_USERNAME, False),
        ("SMTP_PASSWORD", SMTP_PASSWORD, False),
        ("SMTP_FROM", SMTP_FROM, False),
    ):
        lines.append(f"  {'set  ' if value else 'unset'} {label}")
    lines.append("  (values are never printed — CLAUDE.md rule 5)")

    if not SMTP_HOST:
        problems.append(
            "SMTP_HOST is unset, so _send() returns False without trying and the outreach "
            "button will refuse. Set it with: fly secrets set -a bathers-admin SMTP_HOST=..."
        )
    if SMTP_USERNAME and not SMTP_PASSWORD:
        problems.append("SMTP_USERNAME is set but SMTP_PASSWORD is not — login() would fail")
    if SMTP_PASSWORD and not SMTP_USERNAME:
        problems.append("SMTP_PASSWORD is set but SMTP_USERNAME is not — the password is never used")
    if not SMTP_FROM and not SMTP_USERNAME:
        problems.append(
            "neither SMTP_FROM nor SMTP_USERNAME is set, so the message would have no From header"
        )
    if SMTP_PORT == 465:
        problems.append(
            "port 465 is implicit TLS, and _send() always calls starttls() — the connection will "
            "hang or be refused. Use 587."
        )
    return lines, problems


def connection_check() -> tuple[bool, str]:
    """Connect, STARTTLS and (if credentials are set) log in. Sends nothing."""
    if not SMTP_HOST:
        return False, "SMTP_HOST is unset — nothing to connect to"
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                return True, "connected, STARTTLS negotiated, credentials accepted"
            return True, "connected and STARTTLS negotiated (no credentials set, so no login attempted)"
    except smtplib.SMTPAuthenticationError as exc:
        return False, (
            f"the server rejected the credentials ({exc.smtp_code}). For Gmail this usually means "
            "an account password was used instead of an App Password."
        )
    except smtplib.SMTPException as exc:
        return False, f"SMTP error: {exc}"
    except OSError as exc:
        return False, f"could not reach {SMTP_HOST} on port {SMTP_PORT}: {exc}"


def send_test_email(to_addr: str) -> bool:
    """A plain message proving the path works, end to end."""
    site = SITE_URL or "https://wherewebathe.com"
    return _send(
        to_addr,
        "Where We Bathe — SMTP test",
        "This is a test from the Where We Bathe admin.\n\n"
        "If you are reading it, outgoing mail works: the outreach flow can send, "
        "and claim notifications will arrive.\n\n"
        f"{site}\n",
        "<p>This is a test from the Where We Bathe admin.</p>"
        "<p>If you are reading it, outgoing mail works: the outreach flow can send, "
        "and claim notifications will arrive.</p>"
        f'<p><a href="{site}">{site}</a></p>',
    )


def send_outreach_preview(to_addr: str, slug: str) -> bool:
    """The real outreach email for `slug`, sent to you instead of the operator.

    Goes nowhere near the state machine: no transition, no `outreach_log` entry,
    nothing recorded against the venue. That matters because the log is
    append-only by design, so a test sent through the admin button leaves a
    permanent line in a real venue's history.
    """
    from admin.config import PUBLISHED_DIR
    from admin.pipeline import outreach
    from admin.pipeline.staging import split_frontmatter

    path = PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise SystemExit(f"no published venue with slug {slug!r}")
    frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"), slug)
    fields = outreach.populated_verifiable_fields(frontmatter)
    if not fields:
        print(f"note: {slug} publishes no confirmable fields, so the list will be empty")
    return send_outreach_email(
        slug=slug,
        venue_name=frontmatter.get("name", slug),
        operator_email=to_addr,
        operator_name="",
        fields=fields,
        frontmatter=frontmatter,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check the SMTP configuration, and optionally send a test.")
    parser.add_argument("--to", help="send a test message to this address")
    parser.add_argument(
        "--as-outreach",
        metavar="SLUG",
        help="send the real outreach email for this venue to --to, without touching its outreach state",
    )
    args = parser.parse_args()

    lines, problems = config_report()
    print("SMTP configuration:")
    for line in lines:
        print(line)

    if problems:
        print(f"\n{len(problems)} problem(s) will stop a send:")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)

    ok, detail = connection_check()
    print(f"\nconnection: {'ok' if ok else 'FAILED'} — {detail}")
    if not ok:
        raise SystemExit(1)

    if not args.to:
        print("\nconfiguration and connection are good. Add --to you@example.com to send a test.")
        return

    if args.as_outreach:
        sent = send_outreach_preview(args.to, args.as_outreach)
        what = f"outreach email for {args.as_outreach}"
    else:
        sent = send_test_email(args.to)
        what = "test message"
    print(f"{what}: {'sent' if sent else 'NOT SENT — see the log above'}")
    raise SystemExit(0 if sent else 1)


if __name__ == "__main__":
    main()
