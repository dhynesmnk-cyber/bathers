"""Address -> lat/lng via Nominatim (.env.example GEOCODER=nominatim). Optional:
if GEOCODER is unset, `geocode_address` always returns None and the reviewer
sets coordinates from the map thumbnail (SCHEMA.md §4). No geocoding package
dependency — Nominatim's HTTP API is called directly via httpx, which the
project already depends on.
"""

from __future__ import annotations

import time

import httpx

from admin.config import GEOCODER, GEOCODER_USER_AGENT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_INTERVAL_SECONDS = 1.0  # Nominatim usage policy: max 1 req/sec

_last_request_time: float = 0.0


def _wait_for_politeness() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def geocode_address(address: str) -> tuple[float, float] | None:
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
    except (httpx.HTTPError, ValueError):
        return None
    if not results:
        return None
    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, ValueError):
        return None
