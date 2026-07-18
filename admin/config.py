"""Centralised cross-cutting paths/constants (CLAUDE.md rule 4 — no
hardcoded relative paths in feature code). Field names and amenity keys
mirror SCHEMA.md and site/src/config.ts exactly."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SITE_DIR = ROOT / "site"
SITE_DIST_DIR = SITE_DIR / "dist"
SITE_FONTS_DIR = SITE_DIR / "public" / "fonts"
SITE_IMAGES_DIR = SITE_DIR / "public" / "images"

PUBLISHED_DIR = ROOT / "site" / "src" / "content" / "spas" / "_published"
STAGING_DIR = ROOT / "content-staging" / "_staging"
REJECTED_DIR = ROOT / "content-staging" / "_rejected"

DB_PATH = ROOT / "data" / "directory.db"
VENUES_JSON_PATH = ROOT / "site" / "src" / "data" / "venues.json"
VENUES_GEOJSON_PATH = ROOT / "site" / "public" / "venues.geojson"

TEMP_DATA_DIR = ROOT / "temp_data"
IMAGES_DIR = TEMP_DATA_DIR / "images"
FAILED_DIR = TEMP_DATA_DIR / "failed"

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
GEOCODER = _ENV.get("GEOCODER", "")
GEOCODER_USER_AGENT = _ENV.get("GEOCODER_USER_AGENT", "")

AMENITY_KEYS = (
    "magnesium_pool",
    "infrared_sauna",
    "traditional_sauna",
    "cold_plunge",
    "led_therapy",
)

STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT")
