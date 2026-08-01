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
# Generated Open Graph share cards (Gate E4b, 2026-08-01) — 1200x630 PNGs
# rendered from an HTML template via the existing Playwright/chromium (the
# harvest fallback) so they use the real brand woff2 fonts, one per venue/article
# lacking a real photo. Committed + served by Netlify; deployed via the allow-list.
OG_CARDS_DIR = SITE_DIR / "public" / "og"

PUBLISHED_DIR = ROOT / "site" / "src" / "content" / "spas" / "_published"
STAGING_DIR = ROOT / "content-staging" / "_staging"
REJECTED_DIR = ROOT / "content-staging" / "_rejected"
DELETED_DIR = ROOT / "content-staging" / "_deleted"  # 2026-07-23 — delete-listing action parks removed venues here

# Blog (2026-07-21 addition) — mirrors the venue staging/published split:
# drafts live outside site/src/content until Publish moves them across.
BLOG_PUBLISHED_DIR = ROOT / "site" / "src" / "content" / "blog" / "_published"
BLOG_STAGING_DIR = ROOT / "content-staging" / "_blog_staging"
SITE_BLOG_IMAGES_DIR = ROOT / "site" / "public" / "blog-images"

# Editorial pipeline (Gate E2, 2026-08-01) — comparison articles are published
# into the blog collection but staged and fact-checked separately from
# hand-authored essays. Drafts + their fact-check reports live in
# content-staging (guarded, never committed) until approve moves the MDX to
# BLOG_PUBLISHED_DIR and the report to FACTCHECKS_DIR.
ARTICLE_STAGING_DIR = ROOT / "content-staging" / "_article_staging"
ARTICLE_REJECTED_DIR = ROOT / "content-staging" / "_article_rejected"
# Committed editorial record of each published article's claim-by-claim audit
# (data/, alongside directory.db) so /validate can prove every article's claims
# were checked. Not shipped to the public site (outside site/).
FACTCHECKS_DIR = ROOT / "data" / "factchecks"

DB_PATH = ROOT / "data" / "directory.db"
VENUES_JSON_PATH = ROOT / "site" / "src" / "data" / "venues.json"
VENUES_GEOJSON_PATH = ROOT / "site" / "public" / "venues.geojson"
FOREWORDS_JSON_PATH = ROOT / "site" / "src" / "data" / "forewords.json"
# Hybrid-article staleness metadata (Editorial Gate E1, 2026-08-01) — derived
# from venues.json + the comparison registry by site/scripts/refresh-articles.ts,
# committed and read by the site build. Same derived-artifact posture as
# venues.json; regenerated via admin/pipeline/article_store.py.
ARTICLES_META_JSON_PATH = ROOT / "site" / "src" / "data" / "articles-meta.json"

# Claim-request records (2026-07-25, TRD.md §8 exception) — a separate SQLite
# file from DB_PATH because data_store.rebuild() deletes and fully recreates
# directory.db on every venue write, which would destroy anything stored
# there. Gitignored (holds requester PII), never committed.
CLAIMS_DB_PATH = ROOT / "data" / "claims.db"

# Editorial pipeline working-state (Gate E4a, 2026-08-01) — the relational home
# for the opportunity queue's operator overrides (pin/dismiss) and the brief
# gate (auto-brief + approve/kill before drafting). Admin-only; the derived,
# committed truths stay elsewhere (articles-meta.json for staleness,
# data/factchecks/ for published reports). Gitignored like claims.db and never
# destructively rebuilt — a brief the operator wrote can't be reconstructed from
# published content.
ARTICLES_DB_PATH = ROOT / "data" / "articles.db"

TEMP_DATA_DIR = ROOT / "temp_data"
IMAGES_DIR = TEMP_DATA_DIR / "images"
FAILED_DIR = TEMP_DATA_DIR / "failed"
PLACES_DIR = TEMP_DATA_DIR / "places"
GOATCOUNTER_CACHE_DIR = TEMP_DATA_DIR / "goatcounter"
BLOG_IMAGES_TEMP_DIR = TEMP_DATA_DIR / "blog_images"
GEOCODE_CACHE_PATH = TEMP_DATA_DIR / "geocode_cache.json"  # 2026-07-22 — see geocode.py
DRIVETIME_CACHE_PATH = TEMP_DATA_DIR / "drivetime_cache.json"  # Gate 7 — see drivetime.py
CLAIMS_TEMP_DIR = TEMP_DATA_DIR / "claims"  # uploaded claim photos, pending publish

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
# Editorial pipeline (Gate E2, 2026-08-01). MODEL_ARTICLE drafts comparison-
# article prose in the house voice; MODEL_FACTCHECK is a *separate* role that
# audits that draft against the venue data — deliberately not the drafting model
# reviewing itself (drafting models are poor judges of their own confabulation).
# Default both to whatever MODEL_ARCHITECT resolves to (the site's working prose
# model) so a real .env that overrides only MODEL_ARCHITECT still gets a valid id
# here; override independently in .env when a different model is wanted.
MODEL_ARTICLE = _ENV.get("MODEL_ARTICLE", MODEL_ARCHITECT)
MODEL_FACTCHECK = _ENV.get("MODEL_FACTCHECK", MODEL_ARCHITECT)
# Brief gate (Gate E4a, 2026-08-01). Drafts a short editorial brief for an
# opportunity — the cheapest stop, killed or approved before any drafting spend.
# Defaults to MODEL_ARTICLE (the working prose model) so an .env overriding only
# the article model still gets a valid id; override in .env to run it cheaper.
MODEL_BRIEF = _ENV.get("MODEL_BRIEF", MODEL_ARTICLE)
# Free-form essay (2026-08-01). MODEL_ESSAY drafts a voiced blog essay in the
# house style (no data table, no query_key); MODEL_ESSAY_CHECK is a *separate*
# integrity role that flags first-person visit claims, invented venue facts and
# named cultural references for the human — the "rarely named" guardrail. Default
# to the article/factcheck models so an .env overriding only those still gets
# valid ids here; override independently in .env when a different model is wanted.
MODEL_ESSAY = _ENV.get("MODEL_ESSAY", MODEL_ARTICLE)
MODEL_ESSAY_CHECK = _ENV.get("MODEL_ESSAY_CHECK", MODEL_FACTCHECK)
ADMIN_PORT = int(_ENV.get("ADMIN_PORT", "8787"))
ADMIN_USERNAME = _ENV.get("ADMIN_USERNAME", "")
ADMIN_PASSWORD = _ENV.get("ADMIN_PASSWORD", "")
GEOCODER = _ENV.get("GEOCODER", "")
GEOCODER_USER_AGENT = _ENV.get("GEOCODER_USER_AGENT", "")
GOOGLE_PLACES_API_KEY = _ENV.get("GOOGLE_PLACES_API_KEY", "")
GOATCOUNTER_API_TOKEN = _ENV.get("GOATCOUNTER_API_TOKEN", "")
GOATCOUNTER_SITE = _ENV.get("GOATCOUNTER_SITE", "")

# Claim-listing form/payment flow (2026-07-25, TRD.md §8 exception).
STRIPE_SECRET_KEY = _ENV.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = _ENV.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ONEOFF = _ENV.get("STRIPE_PRICE_ONEOFF", "")
STRIPE_PRICE_SUBSCRIPTION = _ENV.get("STRIPE_PRICE_SUBSCRIPTION", "")
SMTP_HOST = _ENV.get("SMTP_HOST", "")
SMTP_PORT = int(_ENV.get("SMTP_PORT", "587"))
SMTP_USERNAME = _ENV.get("SMTP_USERNAME", "")
SMTP_PASSWORD = _ENV.get("SMTP_PASSWORD", "")
SMTP_FROM = _ENV.get("SMTP_FROM", "")
CLAIM_NOTIFY_EMAIL = _ENV.get("CLAIM_NOTIFY_EMAIL", "") or "d.hynes.mnk@gmail.com"
ADMIN_BASE_URL = _ENV.get("ADMIN_BASE_URL", "").rstrip("/")
# Deployed public-site origin — the Done panel's "view" links target it.
# Defaults to the production custom domain; override in .env, or set empty
# to fall back to /site-dist.
SITE_URL = (_ENV.get("SITE_URL") or "https://wherewebathe.com").rstrip("/")

# Netlify deploy verification (the site host — repo-connected, builds on
# push to main). The site id isn't secret (.netlify/state.json is just
# gitignored); the token is, and lives only in .env / Fly secrets. With no
# token the deploy strip still pushes — it just can't confirm the build.
NETLIFY_SITE_ID = _ENV.get("NETLIFY_SITE_ID", "e710bf24-5877-4f2e-b564-034ce83b2400")
NETLIFY_AUTH_TOKEN = _ENV.get("NETLIFY_AUTH_TOKEN", "")

# IndexNow (Gate 6, SEO/AI-citation remediation, 2026-07-31) — the key is not
# secret by design (IndexNow verifies ownership by serving it back at
# keyLocation, so it has to be publicly readable); committed here and mirrored
# at site/public/<key>.txt rather than kept in .env like the real secrets above.
INDEXNOW_KEY = "46ade4a8f66d85e6cadb3c48c44b17b7"

AMENITY_KEYS = (
    "magnesium_pool",
    "infrared_sauna",
    "traditional_sauna",
    "cold_plunge",
    "led_therapy",
)

# Venue categories (2026-07-22 addition, day_spa retired 2026-07-26) — see SCHEMA.md §2.
CATEGORY_KEYS = ("thermal_springs", "bathhouse", "hotel_spa", "other")

CATEGORY_LABELS = {
    "thermal_springs": "Thermal springs",
    "bathhouse": "Bathhouse",
    "hotel_spa": "Hotel spa",
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
    "pregnancy_safe",
    "step_free_entry",
    "hoist_available",
    "accessible_changerooms",
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
    # 2026-07-26 addition (SCHEMA.md §1a) — manual reviewer-set flag only,
    # never Harvester/Architect/Gatekeeper-derived: no structured
    # temperature/depth field exists to determine this automatically.
    "pregnancy_safe": "Pregnancy-safe bathing",
    # 2026-07-26 additions (SCHEMA.md §1a) — ordinary Architect-settable facts.
    "step_free_entry": "Step-free entry",
    "hoist_available": "Hoist available",
    "accessible_changerooms": "Accessible changerooms",
}

# Dress code / session-gender (2026-07-26 addition, SCHEMA.md §2) — mirrors
# site/src/config.ts's DRESS_CODE_KEYS/SESSION_GENDER_KEYS exactly.
DRESS_CODE_KEYS = ("nude", "swimwear", "swimwear_optional", "mixed")

DRESS_CODE_LABELS = {
    "nude": "Nude",
    "swimwear": "Swimwear required",
    "swimwear_optional": "Swimwear optional",
    "mixed": "Mixed (varies by area/session)",
}

SESSION_GENDER_KEYS = ("mixed", "single_sex", "varies")

SESSION_GENDER_LABELS = {
    "mixed": "Mixed",
    "single_sex": "Single-sex",
    "varies": "Varies (see note)",
}

# ---------------------------------------------------------------------------
# Gate 7 (verification metadata / structured facts, 2026-07-31). Mirrors
# site/src/config.ts's CONFIDENCE_TIERS / VERIFIABLE_FIELDS / CAPITAL_CITIES
# exactly (SCHEMA.md "one contract" rule — same two-mirrors posture as the
# amenity/facility/dress-code constants above).
# ---------------------------------------------------------------------------

# Per-field verification confidence, weakest → strongest. `observed_on_visit`
# exists for completeness but is never set by the pipeline: this project does
# not make first-hand visits (CLAUDE.md rule 6), so a field only ever reaches
# it by a manual reviewer who genuinely visited. `operator_confirmed` is the
# target state, reached via Gate 8 outreach.
CONFIDENCE_TIERS = ("unverified", "published_by_venue", "observed_on_visit", "operator_confirmed")

CONFIDENCE_TIER_LABELS = {
    "unverified": "Unverified",
    "published_by_venue": "Published by the venue",
    "observed_on_visit": "Observed on a visit",
    "operator_confirmed": "Confirmed by the operator",
}

# Rank for the Gate 8 "upgrade, never silently downgrade" logic.
CONFIDENCE_TIER_RANK = {tier: i for i, tier in enumerate(CONFIDENCE_TIERS)}

# The venue-sourced factual claims a `verification:` block can key on
# (SCHEMA.md §2a). Deliberately not every frontmatter field — name/state/
# address are self-evident; amenity/facility booleans are covered by the
# venue-level `verified` date; `drive_time` is OSRM-computed, not a venue
# claim, so it carries its own implicit provenance rather than a tier. These
# are the citation-bearing facts a comparison page or an AI answer leans on,
# so each carries its own source/tier/date.
VERIFIABLE_FIELDS = (
    "price",
    "hours",
    "temperatures",
    "dress_code",
    "session_gender",
    "silence_policy",
    "phone_policy",
    "minimum_age",
)

# State capital CBDs — drive-time reference origins (Gate 7, user sign-off
# 2026-07-31: "from nearest capital"). Also usable as a display anchor.
CAPITAL_CITIES = {
    "VIC": {"name": "Melbourne", "latitude": -37.8136, "longitude": 144.9631},
    "NSW": {"name": "Sydney", "latitude": -33.8688, "longitude": 151.2093},
    "QLD": {"name": "Brisbane", "latitude": -27.4698, "longitude": 153.0251},
    "SA": {"name": "Adelaide", "latitude": -34.9285, "longitude": 138.6007},
    "WA": {"name": "Perth", "latitude": -31.9523, "longitude": 115.8613},
    "TAS": {"name": "Hobart", "latitude": -42.8826, "longitude": 147.3257},
    "NT": {"name": "Darwin", "latitude": -12.4637, "longitude": 130.8444},
    "ACT": {"name": "Canberra", "latitude": -35.2809, "longitude": 149.1300},
}

# Rough per-state bounding boxes (lat_min, lat_max, lng_min, lng_max) — the
# quality guard on auto-geocoded coordinates (Gate 7 validator). Deliberately
# generous: catches a geocode that landed in the wrong state or ocean, not the
# odd near-border venue.
STATE_BBOX = {
    "VIC": (-39.3, -33.9, 140.8, 150.1),
    "NSW": (-37.6, -28.1, 140.9, 153.7),
    "QLD": (-29.3, -9.0, 137.9, 153.6),
    "SA": (-38.2, -25.9, 128.9, 141.1),
    "WA": (-35.2, -13.5, 112.8, 129.1),
    "TAS": (-43.8, -39.4, 143.7, 148.6),
    "NT": (-26.1, -10.9, 128.9, 138.1),
    "ACT": (-36.0, -35.1, 148.7, 149.5),
}
