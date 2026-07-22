"""Address -> lat/lng via Nominatim (.env.example GEOCODER=nominatim). Optional:
if GEOCODER is unset, `geocode_address` always returns None and the venue is
published with no map marker (SCHEMA.md §2 — coordinates are optional since
2026-07-22; there is no manual reviewer fallback any more). No geocoding
package dependency — Nominatim's HTTP API is called directly via httpx, which
the project already depends on.
"""

from __future__ import annotations

import json
import re
import time
from typing import Callable

import httpx

from admin.config import GEOCODE_CACHE_PATH, GEOCODER, GEOCODER_USER_AGENT

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


def _cache_key(address: str) -> str:
    return re.sub(r"\s+", " ", address).strip().lower()


def _load_cache() -> dict[str, list[float] | None]:
    if not GEOCODE_CACHE_PATH.exists():
        return {}
    return json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))


def _save_cache(cache: dict[str, list[float] | None]) -> None:
    GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOCODE_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def geocode_address(address: str, log: LogFn | None = None) -> tuple[float, float] | None:
    """Returns None both when Nominatim genuinely has no match (expected,
    silent — the venue simply gets no map marker) and when the request itself
    fails. Those are different situations for the operator, though not for
    the caller's control flow: a failed *request* (bad UA, rate limit,
    network) means every subsequent geocode this session will likely also
    fail, which "no results for this address" doesn't imply. Log the former
    via `log` if given, so it's visible instead of looking identical to a
    normal miss.

    Results (including genuine misses) are cached on disk keyed by normalised
    address — this is now the only source of coordinates (no manual reviewer
    fallback), so repeatedly geocoding the same address across pipeline runs
    would otherwise mean unnecessary Nominatim traffic and politeness waits."""
    if GEOCODER != "nominatim" or not address:
        return None
    key = _cache_key(address)
    cache = _load_cache()
    if key in cache:
        cached = cache[key]
        return (cached[0], cached[1]) if cached is not None else None
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
    coords: tuple[float, float] | None
    if not results:
        coords = None
    else:
        try:
            coords = (float(results[0]["lat"]), float(results[0]["lon"]))
        except (KeyError, ValueError):
            coords = None
    cache[key] = list(coords) if coords is not None else None
    _save_cache(cache)
    return coords
