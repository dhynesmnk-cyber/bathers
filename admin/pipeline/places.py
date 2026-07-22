"""Google Places existence/data verification (harvest-time quality check).

Optional: if GOOGLE_PLACES_API_KEY is unset, check_listing() always returns a
skipped result and nothing downstream is ever auto-flagged from it. No new
pip dependency — Places API (New) is called directly via httpx, the same
pattern geocode.py already uses for Nominatim.

A venue with no discoverable listing is not treated as "doesn't exist" if
the check itself failed (network error, bad response) — only a confirmed
empty result flags it. This mirrors the Gatekeeper's own rule: never invent
a negative finding from an inconclusive one.

rating/userRatingCount/reviews (2026-07-22) ride the same call and feed the
Architect's optional review-signal sentence (PROMPTS/architect.md, SCHEMA.md
§4) — note `places.reviews` is a higher-cost field on top of the base Places
Text Search call, and carries its own Places API attribution/display terms
distinct from the basic fields above; this was a deliberate, confirmed
trade-off, not an oversight.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import httpx

from admin.config import GOOGLE_PLACES_API_KEY, PLACES_DIR

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{photo_name}/media"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.regularOpeningHours.weekdayDescriptions",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.photos",
        "places.primaryType",
        "places.rating",
        "places.userRatingCount",
        "places.reviews",
    ]
)
REQUEST_TIMEOUT = 10.0
MAX_CANDIDATE_PHOTOS = 5  # matches images.MAX_CANDIDATES — combined pool is capped there
MAX_REVIEW_SNIPPETS = 3  # rating/count/reviews are a higher-cost Places SKU — kept terse


@dataclass
class PlacesPhoto:
    name: str  # API photo resource name, e.g. "places/ChIJ.../photos/AeJ..."
    attribution: str  # required wherever the photo is shown (Places API (New) terms)


@dataclass
class PlacesResult:
    skipped: bool
    found: bool
    place_id: str | None = None
    name: str | None = None
    formatted_address: str | None = None
    phone: str | None = None
    hours: list[str] | None = None
    website: str | None = None
    maps_url: str | None = None
    photos: list[PlacesPhoto] | None = None
    primary_type: str | None = None
    rating: float | None = None
    user_rating_count: int | None = None
    reviews: list[str] | None = None  # snippet text only — no reviewer names/photos carried
    error: str | None = None


def search_text(query: str, page_token: str | None = None) -> tuple[list[dict], str | None]:
    """Raw Places API (New) searchText call. Returns (places, next_page_token)."""
    body: dict = {"textQuery": query}
    if page_token:
        body["pageToken"] = page_token
    response = httpx.post(
        SEARCH_URL,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("places") or [], data.get("nextPageToken")


def fetch_photo_media_url(photo_name: str, max_width: int = 1600) -> str:
    """Builds the Places Photo media URL — it 302-redirects to the actual image,
    so it drops straight into images.download_candidates()'s existing GET path."""
    return f"{PHOTO_MEDIA_URL.format(photo_name=photo_name)}?maxWidthPx={max_width}&key={GOOGLE_PLACES_API_KEY}"


def _photos_from_place(place: dict) -> list[PlacesPhoto]:
    photos = []
    for photo in (place.get("photos") or [])[:MAX_CANDIDATE_PHOTOS]:
        photo_name = photo.get("name")
        if not photo_name:
            continue
        authors = [a.get("displayName") for a in (photo.get("authorAttributions") or []) if a.get("displayName")]
        attribution = ", ".join(authors) if authors else "Photo via Google"
        photos.append(PlacesPhoto(name=photo_name, attribution=f"Photo: {attribution} — via Google Places"))
    return photos


def _review_snippets(place: dict) -> list[str] | None:
    snippets = []
    for review in (place.get("reviews") or [])[:MAX_REVIEW_SNIPPETS]:
        text = ((review.get("text") or {}).get("text") or "").strip()
        if text:
            snippets.append(text)
    return snippets or None


def check_listing(name: str, suburb: str | None, state: str | None) -> PlacesResult:
    if not GOOGLE_PLACES_API_KEY:
        return PlacesResult(skipped=True, found=False)

    query = " ".join(part for part in (name, suburb, state, "Australia") if part)
    try:
        places, _ = search_text(query)
    except (httpx.HTTPError, ValueError) as exc:
        return PlacesResult(skipped=False, found=False, error=str(exc))

    if not places:
        return PlacesResult(skipped=False, found=False)

    place = places[0]
    hours = ((place.get("regularOpeningHours") or {}).get("weekdayDescriptions")) or None
    return PlacesResult(
        skipped=False,
        found=True,
        place_id=place.get("id"),
        name=(place.get("displayName") or {}).get("text"),
        formatted_address=place.get("formattedAddress"),
        phone=place.get("nationalPhoneNumber"),
        hours=hours,
        website=place.get("websiteUri"),
        maps_url=place.get("googleMapsUri"),
        photos=_photos_from_place(place) or None,
        primary_type=place.get("primaryType"),
        rating=place.get("rating"),
        user_rating_count=place.get("userRatingCount"),
        reviews=_review_snippets(place),
    )


_SLUG_INDEX_PATH = PLACES_DIR / "_slug_index.json"


def record_slug_key(slug: str, key: str) -> None:
    """Remembers which storage key a content slug's Places/image data lives
    under. The Harvester's extracted name (and therefore slug) can differ
    between runs on the same physical venue; the key (a stable Google Place
    ID when available) doesn't, so this is how a later slug-based lookup
    finds data saved under an earlier run's key."""
    if slug == key:
        return
    PLACES_DIR.mkdir(parents=True, exist_ok=True)
    index = json.loads(_SLUG_INDEX_PATH.read_text(encoding="utf-8")) if _SLUG_INDEX_PATH.exists() else {}
    index[slug] = key
    _SLUG_INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")


def resolve_key(slug: str) -> str:
    if not _SLUG_INDEX_PATH.exists():
        return slug
    index = json.loads(_SLUG_INDEX_PATH.read_text(encoding="utf-8"))
    return index.get(slug, slug)


def _check_path(key: str):
    return PLACES_DIR / f"{key}.json"


def save_check(key: str, result: PlacesResult) -> None:
    PLACES_DIR.mkdir(parents=True, exist_ok=True)
    _check_path(key).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")


def load_check(slug: str) -> PlacesResult | None:
    path = _check_path(resolve_key(slug))
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    photos = data.get("photos")
    if photos is not None:
        data = {**data, "photos": [PlacesPhoto(**p) for p in photos]}
    return PlacesResult(**data)
