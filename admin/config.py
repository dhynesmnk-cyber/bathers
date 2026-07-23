"""Centralised cross-cutting paths/constants (CLAUDE.md rule 4 — no
hardcoded relative paths in feature code). Field names and amenity keys
mirror SCHEMA.md and site/src/config.ts exactly."""

import socket
from pathlib import Path

# Some sandboxed dev environments advertise an IPv6 route that's actually a
# black hole (packets vanish silently — no RST, no ICMP unreachable). curl
# falls back to IPv4 automatically (RFC 8305 "happy eyeballs"); Python's
# socket/httpx stack does not, and hangs past any per-call timeout because
# the hang happens in the underlying connect(), which the timeout doesn't
# reliably interrupt in that failure mode. Every external call this project
# makes (Places, GoatCounter, Nominatim, the harvester's own scraping) goes
# through httpx, so force IPv4-only DNS resolution process-wide, here, before
# any pipeline module runs. Harmless on environments where IPv6 works fine —
# this project has no IPv6-only dependency.
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_only_getaddrinfo

ROOT = Path(__file__).resolve().parent.parent

SITE_DIR = ROOT / "site"
SITE_DIST_DIR = SITE_DIR / "dist"
SITE_FONTS_DIR = SITE_DIR / "public" / "fonts"
SITE_IMAGES_DIR = SITE_DIR / "public" / "images"

PUBLISHED_DIR = ROOT / "site" / "src" / "content" / "spas" / "_published"
STAGING_DIR = ROOT / "content-staging" / "_staging"
REJECTED_DIR = ROOT / "content-staging" / "_rejected"
DELETED_DIR = ROOT / "content-staging" / "_deleted"  # 2026-07-23 — delete-listing action parks removed venues here

# Blog (2026-07-21 addition) — mirrors the venue staging/published split:
# drafts live outside site/src/content until Publish moves them across.
BLOG_PUBLISHED_DIR = ROOT / "site" / "src" / "content" / "blog" / "_published"
BLOG_STAGING_DIR = ROOT / "content-staging" / "_blog_staging"
SITE_BLOG_IMAGES_DIR = ROOT / "site" / "public" / "blog-images"

DB_PATH = ROOT / "data" / "directory.db"
VENUES_JSON_PATH = ROOT / "site" / "src" / "data" / "venues.json"
VENUES_GEOJSON_PATH = ROOT / "site" / "public" / "venues.geojson"
FOREWORDS_JSON_PATH = ROOT / "site" / "src" / "data" / "forewords.json"

TEMP_DATA_DIR = ROOT / "temp_data"
IMAGES_DIR = TEMP_DATA_DIR / "images"
FAILED_DIR = TEMP_DATA_DIR / "failed"
PLACES_DIR = TEMP_DATA_DIR / "places"
GOATCOUNTER_CACHE_DIR = TEMP_DATA_DIR / "goatcounter"
BLOG_IMAGES_TEMP_DIR = TEMP_DATA_DIR / "blog_images"
GEOCODE_CACHE_PATH = TEMP_DATA_DIR / "geocode_cache.json"  # 2026-07-22 — see geocode.py

PROMPTS_DIR = ROOT / "PROMPTS"


def _load_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser for .env (TRD.md §7 — API key from .env only;
    no python-dotenv dependency needed for a format this simple)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


_ENV = _load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = _ENV.get("ANTHROPIC_API_KEY", "")
MODEL_HARVESTER = _ENV.get("MODEL_HARVESTER", "claude-haiku-4-5")
MODEL_ARCHITECT = _ENV.get("MODEL_ARCHITECT", "claude-sonnet-4-6")
MODEL_GATEKEEPER = _ENV.get("MODEL_GATEKEEPER", "claude-haiku-4-5")
ADMIN_PORT = int(_ENV.get("ADMIN_PORT", "8787"))
ADMIN_USERNAME = _ENV.get("ADMIN_USERNAME", "")
ADMIN_PASSWORD = _ENV.get("ADMIN_PASSWORD", "")
GEOCODER = _ENV.get("GEOCODER", "")
GEOCODER_USER_AGENT = _ENV.get("GEOCODER_USER_AGENT", "")
GOOGLE_PLACES_API_KEY = _ENV.get("GOOGLE_PLACES_API_KEY", "")
GOATCOUNTER_API_TOKEN = _ENV.get("GOATCOUNTER_API_TOKEN", "")
GOATCOUNTER_SITE = _ENV.get("GOATCOUNTER_SITE", "")
# Deployed public-site origin — the Done panel's "view" links target it.
# Defaults to the Netlify production URL; override in .env (e.g. once a
# custom domain exists), or set empty to fall back to /site-dist.
SITE_URL = (_ENV.get("SITE_URL") or "https://bathers-directory.netlify.app").rstrip("/")

# Netlify deploy verification (the site host — repo-connected, builds on
# push to main). The site id isn't secret (.netlify/state.json is just
# gitignored); the token is, and lives only in .env / Fly secrets. With no
# token the deploy strip still pushes — it just can't confirm the build.
NETLIFY_SITE_ID = _ENV.get("NETLIFY_SITE_ID", "e710bf24-5877-4f2e-b564-034ce83b2400")
NETLIFY_AUTH_TOKEN = _ENV.get("NETLIFY_AUTH_TOKEN", "")

AMENITY_KEYS = (
    "magnesium_pool",
    "infrared_sauna",
    "traditional_sauna",
    "cold_plunge",
    "led_therapy",
)

# Venue categories (2026-07-22 addition) — see SCHEMA.md §2.
CATEGORY_KEYS = ("thermal_springs", "bathhouse", "day_spa", "other")

CATEGORY_LABELS = {
    "thermal_springs": "Thermal springs",
    "bathhouse": "Bathhouse",
    "day_spa": "Day spa",
    "other": "Other",
}

STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT")

STATE_NAMES = {
    "VIC": "Victoria",
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "SA": "South Australia",
    "WA": "Western Australia",
    "TAS": "Tasmania",
    "NT": "Northern Territory",
    "ACT": "Australian Capital Territory",
}

AMENITY_FULL_NAMES = {
    "magnesium_pool": "magnesium pool",
    "infrared_sauna": "infrared sauna",
    "traditional_sauna": "traditional sauna",
    "cold_plunge": "cold plunge",
    "led_therapy": "LED light therapy",
}

# Facilities (2026-07-21 addition) — practical/logistics info, distinct from
# the bathing-experience amenities above; optional, absent on older venues.
FACILITY_KEYS = (
    "parking",
    "towels_provided",
    "changerooms",
    "bookings_required",
    "wheelchair_access",
    "outdoor_pool",
    "indoor_pool",
    "natural_spring",
)

FACILITY_LABELS = {
    "parking": "Parking",
    "towels_provided": "Towels provided",
    "changerooms": "Changerooms",
    "bookings_required": "Bookings required",
    "wheelchair_access": "Wheelchair access",
    "outdoor_pool": "Outdoor pool",
    "indoor_pool": "Indoor pool",
    "natural_spring": "Natural spring",
}
