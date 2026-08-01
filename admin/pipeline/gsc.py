"""Google Search Console feedback seam (Editorial Gate E4c, 2026-08-01) — a
DOCUMENTED PLACEHOLDER, not an integration.

The post-publish loop the roadmap imagined feeds real search demand back into the
opportunity queue: queries where the site ranks on page two, or impressions with
no matching comparison article, would become new opportunities. That needs Search
Console API credentials (OAuth) and, more fundamentally, accumulated query data
this young site does not yet have — so per the E4 scope decision it is deferred,
and this module is the seam it will land in.

Nothing here calls any Google API. `demand_signal()` returns an empty list today.
When a real feed is wired — GSC, or the existing GoatCounter analytics
(admin/pipeline/goatcounter.py) — it should return `DemandRow`s that
admin/pipeline/article_db.py's `opportunities()` can merge as a ranked prompt
alongside the registry-derived candidates. It must never auto-create articles:
demand only surfaces an intent for a human to brief; the brief gate still applies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DemandRow:
    """A search intent with demand evidence — the shape a real GSC/analytics feed
    would emit into the opportunity queue. Unused until the feed exists."""

    query: str
    impressions: int
    clicks: int
    avg_position: float
    matched_query_key: str | None = None  # an existing comparison, if any


def is_configured() -> bool:
    """Whether a Search Console feed is wired. Always False until credentials and
    accumulated query data exist (see the module docstring)."""
    return False


def demand_signal() -> list[DemandRow]:
    """The GSC/analytics demand feed for the opportunity queue. Empty until the
    seam is implemented; callers must treat an empty list as 'no signal', never
    as 'no demand'."""
    return []
