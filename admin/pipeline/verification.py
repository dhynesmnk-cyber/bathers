"""Per-field verification metadata + computed change-log (Gate 7, 2026-07-31,
SCHEMA.md §2a).

Two mechanisms, both keyed by the VERIFIABLE_FIELDS set (config.py):

- `build_verification` stamps a `{source, tier, date}` record onto each
  currently-populated verifiable field. Used at harvest time (tier
  `published_by_venue`, source = the harvested URL) and at Gate-7 backfill.
  Gate 8 outreach later upgrades individual fields to `operator_confirmed`.

- `compute_change_log` is the *computed* change-log the roadmap chose over a
  hand-maintained one: given the previous and next frontmatter, it emits one
  `{field, from, to, date, trigger}` entry per verifiable field whose value
  actually changed. This matches the "frontmatter is truth, DB is disposable"
  architecture — nobody maintains a log by hand; it falls out of a re-harvest
  or an outreach update. On first draft/backfill there is no previous value,
  so it emits nothing.
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Any

from admin.config import CONFIDENCE_TIER_RANK, VERIFIABLE_FIELDS


def _iso(d: Any) -> str:
    return d.isoformat() if isinstance(d, date_cls) else str(d)


def populated_verifiable_fields(fm: dict[str, Any]) -> list[str]:
    """Which verifiable fields carry a real value on this venue. `price` is
    considered populated when either the freeform `cost` string or the
    structured `price` object is present — both are pricing claims."""
    present: list[str] = []
    for field in VERIFIABLE_FIELDS:
        if field == "price":
            cost = fm.get("cost")
            if (isinstance(cost, str) and cost.strip() and cost.strip() != "null") or fm.get("price"):
                present.append("price")
        elif field in fm and fm[field] not in (None, "", {}):
            present.append(field)
    return present


def build_verification(
    fm: dict[str, Any],
    source: str,
    tier: str,
    date: Any,
    existing: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """A `verification:` block covering every populated verifiable field.

    `existing` (a venue's current verification block) is preserved where it is
    already at an equal-or-stronger tier — a re-harvest that re-reads a page
    must never silently downgrade a field a human/operator already confirmed
    (CONFIDENCE_TIER_RANK). Fields no longer populated are dropped."""
    existing = existing or {}
    out: dict[str, dict[str, Any]] = {}
    for field in populated_verifiable_fields(fm):
        prior = existing.get(field)
        if prior and CONFIDENCE_TIER_RANK.get(prior.get("tier"), -1) >= CONFIDENCE_TIER_RANK.get(tier, -1):
            out[field] = prior
        else:
            out[field] = {"source": source, "tier": tier, "date": _iso(date)}
    return out


def _verifiable_value(fm: dict[str, Any], field: str) -> Any:
    """The comparable value for change-log purposes."""
    if field == "price":
        return fm.get("price") if fm.get("price") else fm.get("cost")
    return fm.get(field)


def compute_change_log(
    old_fm: dict[str, Any] | None,
    new_fm: dict[str, Any],
    date: Any,
    trigger: str,
) -> list[dict[str, Any]]:
    """One entry per verifiable field whose value changed old→new. Empty on
    first draft (old_fm is None) or when nothing moved."""
    if not old_fm:
        return []
    entries: list[dict[str, Any]] = []
    for field in VERIFIABLE_FIELDS:
        before = _verifiable_value(old_fm, field)
        after = _verifiable_value(new_fm, field)
        if before != after:
            entries.append(
                {"field": field, "from": before, "to": after, "date": _iso(date), "trigger": trigger}
            )
    return entries
