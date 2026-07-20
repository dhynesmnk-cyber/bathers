"""GoatCounter Stats API polling — per-venue Book Now click counts
(TRD.md §8 exception: click tracking on the Book Now button only).

Optional: if GOATCOUNTER_API_TOKEN/GOATCOUNTER_SITE are unset,
fetch_click_counts() returns an empty dict and the admin UI shows a
"not configured" state, same posture as places.py's optional integrations.
No new pip dependency — httpx, same as places.py/geocode.py.
"""

from __future__ import annotations

import json

import httpx

from admin.config import GOATCOUNTER_API_TOKEN, GOATCOUNTER_CACHE_DIR, GOATCOUNTER_SITE

STATS_URL = "https://{site}.goatcounter.com/api/v0/stats/hits"
CLICK_PATH_PREFIX = "book-now-click/"
REQUEST_TIMEOUT = 10.0
CACHE_PATH = GOATCOUNTER_CACHE_DIR / "cache.json"
MAX_PATHS = 100  # GoatCounter's own per-request ceiling (limit: 1-100)

# /api/v0/stats/hits defaults `start` to "one week ago" — without setting it
# explicitly, this would silently report only the last 7 days of clicks as
# if it were the all-time total. There is no cursor ("after") parameter on
# this endpoint; its own pagination model is `exclude_paths` (path IDs
# already seen). Not implemented here — this project tracks exactly one
# GoatCounter path per published venue, so a single request at MAX_PATHS is
# expected to cover every venue for the foreseeable scale of this directory.
# Verified directly against GoatCounter's published OpenAPI spec
# (https://www.goatcounter.com/api.json) and /help/api, 2026-07-20.
SINCE = "2020-01-01T00:00:00Z"


def configured() -> bool:
    return bool(GOATCOUNTER_API_TOKEN and GOATCOUNTER_SITE)


def fetch_click_counts() -> dict[str, int]:
    """Polls the Stats API's /stats/hits endpoint for book-now-click/<slug>
    paths, summing counts per slug. Never raises — a failed poll falls back
    to the last-known cache rather than blowing up the admin UI."""
    if not configured():
        return {}

    counts: dict[str, int] = {}
    url = STATS_URL.format(site=GOATCOUNTER_SITE)
    headers = {"Authorization": f"Bearer {GOATCOUNTER_API_TOKEN}"}

    try:
        response = httpx.get(
            url,
            headers=headers,
            params={"start": SINCE, "limit": MAX_PATHS},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        return get_cached_counts()

    for hit in data.get("hits") or []:
        path = (hit.get("path") or "").lstrip("/")
        if not path.startswith(CLICK_PATH_PREFIX):
            continue
        slug = path[len(CLICK_PATH_PREFIX):]
        counts[slug] = counts.get(slug, 0) + int(hit.get("count") or 0)

    _save_cache(counts)
    return counts


def get_cached_counts() -> dict[str, int]:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def _save_cache(counts: dict[str, int]) -> None:
    GOATCOUNTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(counts, indent=2), encoding="utf-8")
