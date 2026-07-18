"""Google Places existence/data verification (harvest-time quality check).

Optional: if GOOGLE_PLACES_API_KEY is unset, check_listing() always returns a
skipped result and nothing downstream is ever auto-flagged from it. No new
pip dependency — Places API (New) is called directly via httpx, the same
pattern geocode.py already uses for Nominatim.

A venue with no discoverable listing is not treated as "doesn't exist" if
the check itself failed (network error, bad response) — only a confirmed
empty result flags it. This mirrors the Gatekeeper's own rule: never invent
a negative finding from an inconclusive one.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import httpx

from admin.config import GOOGLE_PLACES_API_KEY, PLACES_DIR

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.regularOpeningHours.weekdayDescriptions",
        "places.websiteUri",
        "places.googleMapsUri",
    ]
)
REQUEST_TIMEOUT = 10.0


@dataclass
class PlacesResult:
    skipped: bool
    found: bool
    name: str | None = None
    formatted_address: str | None = None
    phone: str | None = None
    hours: list[str] | None = None
    website: str | None = None
    maps_url: str | None = None
    error: str | None = None


def check_listing(name: str, suburb: str | None, state: str | None) -> PlacesResult:
    if not GOOGLE_PLACES_API_KEY:
        return PlacesResult(skipped=True, found=False)

    query = " ".join(part for part in (name, suburb, state, "Australia") if part)
    try:
        response = httpx.post(
            SEARCH_URL,
            json={"textQuery": query},
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return PlacesResult(skipped=False, found=False, error=str(exc))

    places = data.get("places") or []
    if not places:
        return PlacesResult(skipped=False, found=False)

    place = places[0]
    hours = ((place.get("regularOpeningHours") or {}).get("weekdayDescriptions")) or None
    return PlacesResult(
        skipped=False,
        found=True,
        name=(place.get("displayName") or {}).get("text"),
        formatted_address=place.get("formattedAddress"),
        phone=place.get("nationalPhoneNumber"),
        hours=hours,
        website=place.get("websiteUri"),
        maps_url=place.get("googleMapsUri"),
    )


def _check_path(slug: str):
    return PLACES_DIR / f"{slug}.json"


def save_check(slug: str, result: PlacesResult) -> None:
    PLACES_DIR.mkdir(parents=True, exist_ok=True)
    _check_path(slug).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")


def load_check(slug: str) -> PlacesResult | None:
    path = _check_path(slug)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return PlacesResult(**data)
