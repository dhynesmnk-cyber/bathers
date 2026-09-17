"""Google Search Console demand feed (Gate 15, 2026-09-17).

Replaces the documented placeholder this module was from Gate E4c. Feeds real
search demand into the opportunity queue as a **ranked prompt only** — it never
auto-creates an article. Demand surfaces an intent; a human still briefs it, and
the brief gate still governs. That rule predates this implementation and is not
softened by it.

No new dependency: the Search Console API is plain REST and the OAuth2 refresh
is a single form POST, so httpx does both — the same posture goatcounter.py,
places.py and geocode.py already take.

Optional, like every other integration here. With any of GSC_CLIENT_ID /
GSC_CLIENT_SECRET / GSC_REFRESH_TOKEN / GSC_SITE_URL unset, `is_configured()` is
False and `demand_signal()` returns []. Callers must read an empty list as "no
signal", never as "no demand" — the site may simply have no credentials wired,
or too little history to report. That distinction is what `status()` is for.

Never raises. A failed poll falls back to the last cached rows rather than
emptying the queue, and a poll that has never succeeded returns nothing.

**A caveat worth keeping.** The placeholder's docstring said the deeper blocker
was not credentials but accumulated query data, and that is still true: Search
Console reports nothing for queries the site has never ranked for, and little
for a young property. This module being wired does not mean the queue will fill;
it means it will fill when there is something to fill it with.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from urllib.parse import quote

import httpx

from admin.config import (
    GSC_CACHE_DIR,
    GSC_CLIENT_ID,
    GSC_CLIENT_SECRET,
    GSC_REFRESH_TOKEN,
    GSC_SITE_URL,
)

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
SEARCH_ANALYTICS_URL = (
    "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
)
# The property id goes in the path and is percent-encoded whole — both forms
# contain characters that would otherwise be read as path structure:
# "sc-domain:wherewebathe.com" has a colon, "https://wherewebathe.com/" has
# slashes. safe="" is deliberate; the default would leave the slashes alone.
REQUEST_TIMEOUT = 15.0
CACHE_PATH = GSC_CACHE_DIR / "demand.json"
DEFAULT_DAYS = 90
ROW_LIMIT = 500  # the API's own page is 25k; this is a queue prompt, not a report

# Search Console data lags ~2-3 days. Asking for today returns a short window of
# zeroes that looks like a demand collapse rather than a reporting delay.
LAG_DAYS = 3

# Words carried by almost every query about this site, so useless for telling
# one intent from another.
_STOPWORDS = frozenset(
    {"the", "a", "an", "in", "for", "of", "and", "or", "to", "best", "near", "me", "au"}
)


@dataclass
class DemandRow:
    """A search intent with demand evidence — the shape the opportunity queue
    merges alongside its registry-derived candidates."""

    query: str
    impressions: int
    clicks: int
    avg_position: float
    matched_query_key: str | None = None  # an existing comparison, if any


def is_configured() -> bool:
    """Whether a Search Console feed is wired."""
    return bool(GSC_CLIENT_ID and GSC_CLIENT_SECRET and GSC_REFRESH_TOKEN and GSC_SITE_URL)


def status() -> str:
    """One line for the admin UI. Distinguishes 'not wired' from 'wired but
    quiet', which an empty list alone cannot."""
    if not is_configured():
        return "not configured — set GSC_* in .env (see .env.example)"
    cached = _load_cache()
    if cached is None:
        return "configured, but no successful poll yet"
    return f"{len(cached)} quer{'y' if len(cached) == 1 else 'ies'} from the last successful poll"


# --------------------------------------------------------------------------
def _load_cache() -> list[dict] | None:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_cache(rows: list[DemandRow]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps([asdict(r) for r in rows], indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass  # a cache that cannot be written is not a reason to lose the rows


def _access_token() -> str | None:
    """Exchange the long-lived refresh token for a short-lived access token.

    The access token is used and discarded; only the refresh token is stored,
    and only in .env.
    """
    try:
        response = httpx.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": GSC_CLIENT_ID,
                "client_secret": GSC_CLIENT_SECRET,
                "refresh_token": GSC_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        return token if isinstance(token, str) and token else None
    except (httpx.HTTPError, ValueError):
        return None


# --------------------------------------------------------------------------
def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS}


def match_query_key(query: str, keys: list[str]) -> str | None:
    """The existing comparison this query is asking for, if any.

    Deliberately conservative: a key matches only when every one of its own slug
    words appears in the query. The two errors are not equal — a false match
    hides a genuine content gap behind an article that does not answer it, while
    a false miss only shows the operator an intent they recognise and dismiss.
    The cheap mistake is the one this prefers.
    """
    query_tokens = _tokens(query)
    best: str | None = None
    for key in keys:
        key_tokens = _tokens(key.replace("-", " "))
        if key_tokens and key_tokens <= query_tokens:
            # Prefer the most specific key that matches.
            if best is None or len(key_tokens) > len(_tokens(best.replace("-", " "))):
                best = key
    return best


def _existing_keys() -> list[str]:
    try:
        from admin.pipeline import article_store

        return list(article_store.read_meta().keys())
    except Exception:  # noqa: BLE001 — a missing registry must not break the poll
        return []


def demand_signal(days: int = DEFAULT_DAYS) -> list[DemandRow]:
    """Top queries from Search Console over the trailing window, ranked by
    impressions, each tagged with the comparison it already has (if any).

    Returns the last successful poll's rows if this one fails, and [] if there
    has never been one. Never raises.
    """
    if not is_configured():
        return []

    token = _access_token()
    if token is None:
        return _cached_rows()

    end = date.today() - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=days)
    try:
        response = httpx.post(
            SEARCH_ANALYTICS_URL.format(site=quote(GSC_SITE_URL, safe="")),
            headers={"Authorization": f"Bearer {token}"},
            json={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": ["query"],
                "rowLimit": ROW_LIMIT,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return _cached_rows()

    rows = parse_rows(payload, _existing_keys())
    _save_cache(rows)
    return rows


def parse_rows(payload: dict, keys: list[str]) -> list[DemandRow]:
    """Map a Search Analytics response into ranked DemandRows.

    Split out from the request so it can be tested against a recorded payload
    without touching the network.
    """
    out: list[DemandRow] = []
    for row in payload.get("rows", []) or []:
        query = (row.get("keys") or [""])[0]
        if not query:
            continue
        out.append(
            DemandRow(
                query=query,
                impressions=int(row.get("impressions", 0)),
                clicks=int(row.get("clicks", 0)),
                avg_position=round(float(row.get("position", 0.0)), 1),
                matched_query_key=match_query_key(query, keys),
            )
        )
    out.sort(key=lambda r: (-r.impressions, r.query))
    return out


def _cached_rows() -> list[DemandRow]:
    cached = _load_cache()
    if not cached:
        return []
    try:
        return [DemandRow(**row) for row in cached]
    except TypeError:
        return []


# --------------------------------------------------------------------------
def _self_test() -> int:
    """Exercises the parsing and matching against a recorded payload. Touches no
    network, so it runs in CI where no credentials exist."""
    problems: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            problems.append(label)

    keys = ["cheapest", "contrast-therapy", "indoor-pools", "magnesium-pool-compared"]
    payload = {
        "rows": [
            {"keys": ["cheapest bathhouse melbourne"], "impressions": 400, "clicks": 12, "position": 8.4},
            {"keys": ["contrast therapy sauna cold plunge"], "impressions": 900, "clicks": 30, "position": 4.2},
            {"keys": ["do hot springs help eczema"], "impressions": 150, "clicks": 2, "position": 22.7},
            {"keys": [""], "impressions": 5, "clicks": 0, "position": 50.0},
        ]
    }
    rows = parse_rows(payload, keys)

    check("a blank query is dropped", len(rows) == 3)
    check("rows rank by impressions", [r.impressions for r in rows] == [900, 400, 150])
    check(
        "a query matching an existing comparison is tagged",
        next(r for r in rows if "contrast" in r.query).matched_query_key == "contrast-therapy",
    )
    check(
        "a query with no comparison is left unmatched",
        next(r for r in rows if "eczema" in r.query).matched_query_key is None,
    )
    check(
        "matching is conservative, not fuzzy",
        match_query_key("bathhouse prices", keys) is None,
    )
    check(
        "the most specific matching key wins",
        match_query_key("magnesium pool compared cheapest", keys) == "magnesium-pool-compared",
    )
    check("an empty payload yields nothing", parse_rows({}, keys) == [])
    check("unconfigured returns no rows", demand_signal() == [] if not is_configured() else True)
    check("status distinguishes unwired from quiet", "not configured" in status() or is_configured())

    # The other half of the feature: how these rows land in the opportunity
    # queue. Asserted here because a demand feed nothing consumes is not a
    # feature, and because the queue must not become draftable by accident.
    import admin.pipeline.gsc as this_module
    from admin.pipeline import article_db

    baseline = article_db.opportunities()
    check("the queue is untouched with no feed", all(o["source"] == "registry" for o in baseline))

    real = this_module.demand_signal
    this_module.demand_signal = lambda *a, **k: [
        DemandRow("cheapest bathhouse melbourne", 400, 12, 8.4, "cheapest"),
        DemandRow("cheapest bathhouse sydney", 900, 20, 6.1, "cheapest"),
        DemandRow("sauna vs steam room", 800, 5, 14.0, None),
    ]
    try:
        merged = article_db.opportunities()
    finally:
        this_module.demand_signal = real

    demand_rows = [o for o in merged if o["source"] == "gsc"]
    matched = [o for o in merged if o["query_key"] == "cheapest"]

    check("an unmatched query becomes a queue row", len(demand_rows) == 1)
    check(
        "a demand row is never draftable",
        demand_rows and not any(o["draftable"] for o in demand_rows),
    )
    check(
        "the strongest query annotates a matched comparison",
        bool(matched) and matched[0]["demand"] is not None
        and matched[0]["demand"]["impressions"] == 900,
    )
    check(
        "a matched comparison keeps its own status",
        bool(matched) and matched[0]["status"] == baseline_status(baseline, "cheapest"),
    )
    # Sorting mixes rows whose query_key is None with rows whose key is a string;
    # a bare key would raise TypeError the first time a feed returned an
    # unmatched query, which is to say in production and not in any test.
    check("sorting survives a null query_key", len(merged) == len(baseline) + 1)

    print(f"gsc self-test: {len(problems)} problem(s)")
    return 1 if problems else 0


def baseline_status(rows: list[dict], key: str) -> str | None:
    for row in rows:
        if row.get("query_key") == key:
            return row.get("status")
    return None


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(f"Search Console: {status()}")
    rows = demand_signal()
    if not rows:
        print("No demand rows. This is 'no signal', not 'no demand'.")
        return
    print(f"\n{'impr':>6} {'clicks':>6} {'pos':>5}  query")
    for row in rows[:40]:
        tag = f"  → {row.matched_query_key}" if row.matched_query_key else "  (no comparison yet)"
        print(f"{row.impressions:6} {row.clicks:6} {row.avg_position:5}  {row.query}{tag}")


if __name__ == "__main__":
    main()
