"""Operator-outreach lifecycle (Gate 13, 2026-09-08 — the deferred Gate 8).

The analogue of `claims.py` for the outreach flow: it wires `outreach_store`,
`notify` and `verification` together, and owns the one thing that actually
changes published content — upgrading a venue's confidence tiers to
`operator_confirmed` once an operator has confirmed the facts.

Two rules govern that upgrade, and both exist to keep `operator_confirmed`
meaning what it says:

- **Upgrade only.** `verification.build_verification` already refuses to lower a
  field's tier; the same posture is enforced here field by field, so a later
  re-harvest at `published_by_venue` can never quietly undo an operator's word.
- **Only fields the venue actually publishes.** Confirming a field a venue
  carries no value for would create provenance for nothing, so the set is
  intersected with `populated_verifiable_fields` before anything is written.

`operator_confirmed` is never set by this module on its own initiative. It is
reachable only from `responded`, which a human records after an operator has
actually replied (CLAUDE.md rule 6 — the pipeline documents, it does not invent).
"""

from __future__ import annotations

import datetime
from typing import Any

from admin.config import (
    CONFIDENCE_TIER_RANK,
    OUTREACH_CHANNELS,
    OUTREACH_FOLLOW_UP_DAYS,
    PUBLISHED_DIR,
)
from admin.pipeline import notify, outreach_store
from admin.pipeline.staging import render_mdx, split_frontmatter
from admin.pipeline.verification import populated_verifiable_fields


class OutreachError(Exception):
    pass


def _venue_path(slug: str):
    path = PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    return path


def venue_frontmatter(slug: str) -> dict[str, Any]:
    path = _venue_path(slug)
    frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"), slug)
    return frontmatter


def confirmable_fields(slug: str) -> list[str]:
    """What an operator could confirm for this venue — the verifiable fields it
    actually publishes a value for."""
    return populated_verifiable_fields(venue_frontmatter(slug))


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def send_outreach(slug: str, *, operator_email: str, operator_name: str = "", note: str = "") -> outreach_store.OutreachRow:
    """Email the operator and move the venue to `contacted`.

    The email goes out first: if SMTP is misconfigured the state must not claim
    a contact that never happened. `notify` swallows send failures by design
    (a failed notification must not 500 a caller), so this checks the outcome
    explicitly rather than assuming.
    """
    frontmatter = venue_frontmatter(slug)
    sent = notify.send_outreach_email(
        slug=slug,
        venue_name=frontmatter.get("name", slug),
        operator_email=operator_email,
        operator_name=operator_name,
        fields=confirmable_fields(slug),
        frontmatter=frontmatter,
    )
    if not sent:
        raise OutreachError(
            "no email was sent — SMTP is not configured (SMTP_HOST). Record a "
            "phone or in-person contact instead if you reached them another way."
        )
    return outreach_store.transition(
        slug, "contacted", channel="email", note=note or None,
        operator_name=operator_name or None, operator_email=operator_email,
    )


def record_contact(slug: str, *, channel: str, note: str = "", operator_name: str = "", operator_email: str = "") -> outreach_store.OutreachRow:
    """Record a contact made outside this app — a phone call, a conversation.

    The admin screen is the single source of truth for outcomes whatever the
    channel (Gate 8's contract), which only works if non-email contact can be
    entered by hand.
    """
    if channel not in OUTREACH_CHANNELS:
        raise OutreachError(f"channel must be one of {', '.join(OUTREACH_CHANNELS)}")
    _venue_path(slug)
    return outreach_store.transition(
        slug, "contacted", channel=channel, note=note or None,
        operator_name=operator_name or None, operator_email=operator_email or None,
    )


def record_response(slug: str, *, channel: str = "email", note: str = "") -> outreach_store.OutreachRow:
    if channel not in OUTREACH_CHANNELS:
        raise OutreachError(f"channel must be one of {', '.join(OUTREACH_CHANNELS)}")
    return outreach_store.transition(slug, "responded", channel=channel, note=note or None)


def record_no_response(slug: str, *, note: str = "") -> outreach_store.OutreachRow:
    return outreach_store.transition(slug, "no_response", note=note or None)


def record_declined(slug: str, *, note: str = "") -> outreach_store.OutreachRow:
    return outreach_store.transition(slug, "declined", note=note or None)


def confirm_fields(
    slug: str,
    fields: list[str],
    *,
    note: str = "",
    confirmed_on: datetime.date | None = None,
) -> tuple[outreach_store.OutreachRow, list[str]]:
    """Record an operator's confirmation and upgrade those fields' tiers.

    Returns the row and the fields actually upgraded — which can be fewer than
    asked for, since a field the venue publishes no value for is dropped rather
    than given provenance for nothing.
    """
    row = outreach_store.get(slug)
    if row is None or row.state != "responded":
        raise OutreachError(
            f"{slug}: an operator confirmation is only recordable from 'responded' "
            f"(currently {row.state if row else 'not_contacted'})"
        )

    path = _venue_path(slug)
    frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
    populated = set(populated_verifiable_fields(frontmatter))
    wanted = [f for f in fields if f in populated]
    if not wanted:
        raise OutreachError(
            f"{slug}: none of {', '.join(fields) or '(nothing)'} is a field this venue publishes a value for"
        )

    date = (confirmed_on or datetime.date.today()).isoformat()
    who = row.operator_name or row.operator_email or "the venue operator"
    source = f"Confirmed by {who} ({row.operator_email or 'no email recorded'}), {date}"

    # Stamped field by field, deliberately NOT via build_verification: that
    # function re-stamps every populated field at the tier it is handed, which is
    # right for a harvest pass re-reading a whole page and badly wrong here. It
    # would mark fields the operator never mentioned as operator-confirmed, which
    # is precisely the false provenance this module exists to avoid.
    verification = dict(frontmatter.get("verification") or {})
    upgraded: list[str] = []
    for field in wanted:
        prior = verification.get(field) or {}
        if CONFIDENCE_TIER_RANK.get(prior.get("tier"), -1) > CONFIDENCE_TIER_RANK["operator_confirmed"]:
            continue  # already at a stronger tier — never downgrade
        verification[field] = {"source": source, "tier": "operator_confirmed", "date": date}
        upgraded.append(field)
    if not upgraded:
        raise OutreachError(f"{slug}: every named field already carries a stronger tier")
    frontmatter["verification"] = verification
    wanted = upgraded
    path.write_text(render_mdx(frontmatter, body), encoding="utf-8")

    updated = outreach_store.transition(
        slug, "operator_confirmed", channel="email", note=note or None, confirmed_fields=wanted
    )
    return updated, wanted


# ---------------------------------------------------------------------------
# Screen data
# ---------------------------------------------------------------------------


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        when = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - when).days


def overview() -> list[dict[str, Any]]:
    """Every published venue with its outreach state, for the admin screen.

    Driven by `_published/` rather than by the table, so a newly published venue
    appears immediately as `not_contacted` without anything having to remember
    to insert it.
    """
    rows = {r.slug: r for r in outreach_store.list_rows()}
    out: list[dict[str, Any]] = []
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        slug = path.stem
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        row = rows.get(slug)
        days = _days_since(row.contacted_at) if row else None
        confirmed = [
            field
            for field, record in (frontmatter.get("verification") or {}).items()
            if isinstance(record, dict) and record.get("tier") == "operator_confirmed"
        ]
        out.append({
            "slug": slug,
            "name": frontmatter.get("name", slug),
            "state_province": frontmatter.get("state_province"),
            "country": frontmatter.get("country", "AU"),
            "city": frontmatter.get("city"),
            "state": row.state if row else "not_contacted",
            "operator_name": row.operator_name if row else None,
            "operator_email": row.operator_email if row else None,
            "contacted_at": row.contacted_at if row else None,
            "days_since_contact": days,
            "needs_follow_up": bool(
                row and row.state == "contacted" and days is not None and days >= OUTREACH_FOLLOW_UP_DAYS
            ),
            "confirmed_fields": sorted(confirmed),
            "confirmable_fields": populated_verifiable_fields(frontmatter),
            "note": row.note if row else None,
        })
    return out


def detail(slug: str) -> dict[str, Any]:
    row = outreach_store.ensure(slug)
    frontmatter = venue_frontmatter(slug)
    return {
        "slug": slug,
        "name": frontmatter.get("name", slug),
        "state": row.state,
        "operator_name": row.operator_name,
        "operator_email": row.operator_email,
        "contacted_at": row.contacted_at,
        "responded_at": row.responded_at,
        "resolved_at": row.resolved_at,
        "note": row.note,
        "confirmed_fields": row.confirmed_fields,
        "confirmable_fields": populated_verifiable_fields(frontmatter),
        "verification": frontmatter.get("verification") or {},
        "log": outreach_store.log_for(slug),
    }
