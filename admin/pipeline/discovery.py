"""Admin-side venue discovery (TRD.md §8 exception): finds candidate venue
URLs via Google Places Text Search, for a human to review before queuing
each one into the existing single-job harvest flow (UX.md §1.1a). Discovery
never harvests or stages anything itself — it only returns a list.

Reuses places.search_text(), the same GOOGLE_PLACES_API_KEY integration
already approved for verification and candidate photos. No new dependency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from admin.config import PUBLISHED_DIR, STAGING_DIR
from admin.pipeline import places
from admin.pipeline.staging import split_frontmatter

DEFAULT_KEYWORDS = ("day spa", "bathhouse", "hot springs", "thermal baths")
MAX_PAGES = 3  # ~20 results/page — a sane cap on paginated Text Search billing
PAGE_TOKEN_DELAY_SECONDS = 2.0  # Places API needs a short delay before a nextPageToken is valid


@dataclass
class DiscoveryCandidate:
    place_id: str
    name: str
    website: str
    formatted_address: str | None
    maps_url: str | None


def _domain(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return url.lower()


def _known_domains() -> set[str]:
    """Websites of every venue already published or staged — discovery must
    never resurface a venue that's already in the pipeline."""
    domains: set[str] = set()
    for path in list(PUBLISHED_DIR.glob("*.mdx")) + list(STAGING_DIR.glob("*.mdx")):
        try:
            data, _ = split_frontmatter(path.read_text(encoding="utf-8"), path.stem)
        except ValueError:
            continue
        website = data.get("website")
        if website:
            domains.add(_domain(website))
    return domains


def discover_venues(region: str, keywords: list[str] | None = None) -> list[DiscoveryCandidate]:
    """Searches Places Text Search for `<keyword> in <region>, Australia` for
    each keyword, paginating up to MAX_PAGES per keyword, deduped by place_id
    and by website domain against everything already published/staged."""
    if not places.GOOGLE_PLACES_API_KEY:
        return []

    terms = keywords or list(DEFAULT_KEYWORDS)
    seen_place_ids: set[str] = set()
    seen_domains: set[str] = _known_domains()
    results: list[DiscoveryCandidate] = []

    for term in terms:
        query = f"{term} in {region}, Australia"
        page_token: str | None = None
        for page_num in range(MAX_PAGES):
            if page_num > 0 and page_token:
                time.sleep(PAGE_TOKEN_DELAY_SECONDS)
            try:
                raw_places, page_token = places.search_text(query, page_token=page_token)
            except (httpx.HTTPError, ValueError):
                break
            for place in raw_places:
                place_id = place.get("id")
                website = place.get("websiteUri")
                if not place_id or not website or place_id in seen_place_ids:
                    continue
                domain = _domain(website)
                if domain in seen_domains:
                    continue
                seen_place_ids.add(place_id)
                seen_domains.add(domain)
                results.append(
                    DiscoveryCandidate(
                        place_id=place_id,
                        name=(place.get("displayName") or {}).get("text") or "(unnamed)",
                        website=website,
                        formatted_address=place.get("formattedAddress"),
                        maps_url=place.get("googleMapsUri"),
                    )
                )
            if not page_token:
                break

    return results
