"""Drive-time from a venue to its nearest state capital, via OSRM (Gate 7,
2026-07-31 — TRD.md §2 exception, user sign-off "from nearest capital").

No new package: OSRM's public routing demo is called directly over the httpx
the project already depends on, the same posture as geocode.py's direct
Nominatim calls. Results are cached on disk keyed by rounded coordinates —
drive-time is recomputed only when a venue's coordinates change (a re-harvest
or a fresh geocode), never on every rebuild, so the public demo sees batch,
infrequent traffic (25 venues now, a handful per coverage addition).

Fallback if the public demo becomes unreliable (its own docs discourage
production reliance): a self-hosted OSRM + AU OSM extract run as a one-off
batch job. Named here so it isn't a scramble later; not built until needed.
"""

from __future__ import annotations

import json
import math
import time
from typing import Callable

import httpx

from admin.config import CAPITAL_CITIES, DRIVETIME_CACHE_PATH

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
MIN_INTERVAL_SECONDS = 1.0  # be a polite guest on the shared demo instance

LogFn = Callable[[str, str], None]

_last_request_time: float = 0.0


def _wait_for_politeness() -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def _cache_key(latitude: float, longitude: float) -> str:
    # Round to ~110 m — finer than drive-time resolution, coarse enough that a
    # trivial coordinate wobble on re-geocode reuses the cached route.
    return f"{round(latitude, 3)},{round(longitude, 3)}"


def _load_cache() -> dict[str, dict | None]:
    if not DRIVETIME_CACHE_PATH.exists():
        return {}
    return json.loads(DRIVETIME_CACHE_PATH.read_text(encoding="utf-8"))


def _save_cache(cache: dict[str, dict | None]) -> None:
    DRIVETIME_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIVETIME_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _osrm_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> tuple[int, float] | None:
    """(minutes, km) for the driving route, or None on any request failure."""
    _wait_for_politeness()
    url = f"{OSRM_URL}/{from_lon},{from_lat};{to_lon},{to_lat}"
    try:
        response = httpx.get(url, params={"overview": "false"}, timeout=15.0)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    route = data["routes"][0]
    return (round(route["duration"] / 60), round(route["distance"] / 1000, 1))


def drive_time(latitude: float | None, longitude: float | None, log: LogFn | None = None) -> dict | None:
    """Drive-time from a venue to its nearest capital by road.

    Returns `{"from": "Melbourne", "minutes": 100, "km": 111.4}` or None (no
    coordinates, or every OSRM request failed). "Nearest" is resolved by
    querying the two closest capitals by straight-line distance and keeping
    the shorter drive — so a near-border venue is timed from whichever capital
    is genuinely closer by road, not merely as-the-crow-flies."""
    if latitude is None or longitude is None:
        return None

    key = _cache_key(latitude, longitude)
    cache = _load_cache()
    if key in cache:
        return cache[key]

    ranked = sorted(
        CAPITAL_CITIES.values(),
        key=lambda c: _haversine_km(latitude, longitude, c["latitude"], c["longitude"]),
    )
    best: dict | None = None
    for capital in ranked[:2]:
        route = _osrm_route(latitude, longitude, capital["latitude"], capital["longitude"])
        if route is None:
            continue
        minutes, km = route
        if best is None or minutes < best["minutes"]:
            best = {"from": capital["name"], "minutes": minutes, "km": km}

    if best is None and log:
        log(f"drive-time: OSRM unreachable for {latitude:.4f},{longitude:.4f}", "warn")

    # Cache only real results; a transient OSRM failure should be retried next
    # run, not frozen as a permanent miss (unlike geocode's genuine no-match).
    if best is not None:
        cache[key] = best
        _save_cache(cache)
    return best
