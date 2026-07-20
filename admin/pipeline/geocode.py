"""Address -> lat/lng via Nominatim (.env.example GEOCODER=nominatim). Optional:
if GEOCODER is unset, `geocode_address` always returns None and the reviewer
sets coordinates from the map thumbnail (SCHEMA.md §4). No geocoding package
dependency — Nominatim's HTTP API is called directly via httpx, which the
project already depends on.
"""

from __future__ import annotations

import time
from typing import Callable

import httpx

from admin.config import GEOCODER, GEOCODER_USER_AGENT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_SECONDS = 1.0  # Nominatim usage policy: max 1 req/sec

LogFn = Callable[[str, str], None]

_last_request_time: float = 0.0


def _wait_for_politeness() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def geocode_address(address: str, log: LogFn | None = None) -> tuple[float, float] | None:
    """Returns None both when Nominatim genuinely has no match (expected,
    silent — the reviewer fills it in) and when the request itself fails.
    Those are different situations for the operator, though not for the
    caller's control flow: a failed *request* (bad UA, rate limit, network)
    means every subsequent geocode this session will likely also fail, which
    "no results for this address" doesn't imply. Log the former via `log` if
    given, so it's visible instead of looking identical to a normal miss."""
    if GEOCODER != "nominatim" or not address:
        return None
    _wait_for_politeness()
    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "au"},
            headers={"User-Agent": GEOCODER_USER_AGENT or "spa-directory-admin (local)"},
            timeout=10.0,
        )
        response.raise_for_status()
        results = response.json()
    except httpx.HTTPStatusError as exc:
        if log:
            log(f"geocoding request failed — Nominatim returned {exc.response.status_code}", "warn")
        return None
    except (httpx.HTTPError, ValueError) as exc:
        if log:
            log(f"geocoding request failed — {exc}", "warn")
        return None
    if not results:
        return None
    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, ValueError):
        return None
