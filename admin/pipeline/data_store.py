"""Owns all SQLite and JSON/GeoJSON generation (TRD.md §5).

Regeneration is always a full rebuild from `_published` frontmatter — the
published MDX directory is the source of truth, and `directory.db` is
disposable. Frontmatter field names mirror SCHEMA.md §2/§3 exactly.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import yaml

_logger = logging.getLogger("admin.data_store")

from admin.config import (
    AMENITY_KEYS,
    DB_PATH,
    FACILITY_KEYS,
    PUBLISHED_DIR,
    VENUES_GEOJSON_PATH,
    VENUES_JSON_PATH,
)

REQUIRED_FIELDS = ("name", "state", "category", "suburb", "summary", "amenities")

# Scalar columns on the venues table, in order (excluding the slug PK). Built
# once so the INSERT/UPDATE SQL and the params dict can't drift apart.
VENUE_SCALAR_COLUMNS = (
    "name", "state", "category", "suburb", "latitude", "longitude", "status", "summary", "has_image",
    "hours", "cost", "access",
    "dress_code", "session_gender", "session_gender_note", "silence_policy", "phone_policy", "minimum_age",
    "sauna_min_c", "sauna_max_c", "sauna_display",
    "cold_plunge_min_c", "cold_plunge_max_c", "cold_plunge_display",
    "price_adult_drop_in_aud", "price_standard_session_aud",
    "drive_time_from", "drive_time_minutes", "drive_time_km",
)


def _venue_params(slug: str, data: dict[str, Any]) -> dict[str, Any]:
    """Flatten frontmatter (including the nested temperatures/price/drive_time
    objects) into one row-params dict keyed by VENUE_SCALAR_COLUMNS + slug."""
    temps = data.get("temperatures") or {}
    price = data.get("price") or {}
    dt = data.get("drive_time") or {}
    return {
        "slug": slug,
        "name": data["name"],
        "state": data["state"],
        "category": data["category"],
        "suburb": data["suburb"],
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "status": data.get("status", "unclaimed"),
        "summary": data["summary"],
        "has_image": 1 if data.get("image") else 0,
        "hours": data.get("hours"),
        "cost": data.get("cost"),
        "access": data.get("access"),
        "dress_code": data.get("dress_code"),
        "session_gender": data.get("session_gender"),
        "session_gender_note": data.get("session_gender_note"),
        "silence_policy": data.get("silence_policy"),
        "phone_policy": data.get("phone_policy"),
        "minimum_age": data.get("minimum_age"),
        "sauna_min_c": temps.get("sauna_min_c"),
        "sauna_max_c": temps.get("sauna_max_c"),
        "sauna_display": temps.get("sauna_display"),
        "cold_plunge_min_c": temps.get("cold_plunge_min_c"),
        "cold_plunge_max_c": temps.get("cold_plunge_max_c"),
        "cold_plunge_display": temps.get("cold_plunge_display"),
        "price_adult_drop_in_aud": price.get("adult_drop_in_aud"),
        "price_standard_session_aud": price.get("standard_session_aud"),
        "drive_time_from": dt.get("from"),
        "drive_time_minutes": dt.get("minutes"),
        "drive_time_km": dt.get("km"),
    }

SCHEMA_SQL = """
CREATE TABLE venues (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  state TEXT NOT NULL,
  category TEXT NOT NULL,
  suburb TEXT NOT NULL,
  latitude REAL,
  longitude REAL,
  status TEXT NOT NULL DEFAULT 'unclaimed',
  summary TEXT NOT NULL,
  has_image INTEGER NOT NULL DEFAULT 0,
  hours TEXT,
  cost TEXT,
  access TEXT,
  -- Gate 7 (2026-07-31): promoted from rendered-only into SQLite so they're
  -- queryable by the comparison pages (SCHEMA.md §3). Temperatures/price/
  -- drive-time are flattened here (the nested objects are reconstructed for
  -- venues.json in fetch_all_venues).
  dress_code TEXT,
  session_gender TEXT,
  session_gender_note TEXT,
  silence_policy TEXT,
  phone_policy TEXT,
  minimum_age INTEGER,
  sauna_min_c REAL,
  sauna_max_c REAL,
  sauna_display TEXT,
  cold_plunge_min_c REAL,
  cold_plunge_max_c REAL,
  cold_plunge_display TEXT,
  price_adult_drop_in_aud REAL,
  price_standard_session_aud REAL,
  drive_time_from TEXT,
  drive_time_minutes INTEGER,
  drive_time_km REAL
);
CREATE TABLE amenities (
  slug TEXT PRIMARY KEY REFERENCES venues(slug) ON DELETE CASCADE,
  magnesium_pool INTEGER NOT NULL,
  infrared_sauna INTEGER NOT NULL,
  traditional_sauna INTEGER NOT NULL,
  cold_plunge INTEGER NOT NULL,
  led_therapy INTEGER NOT NULL
);
CREATE TABLE facilities (
  slug TEXT PRIMARY KEY REFERENCES venues(slug) ON DELETE CASCADE,
  parking INTEGER NOT NULL DEFAULT 0,
  towels_provided INTEGER NOT NULL DEFAULT 0,
  changerooms INTEGER NOT NULL DEFAULT 0,
  bookings_required INTEGER NOT NULL DEFAULT 0,
  wheelchair_access INTEGER NOT NULL DEFAULT 0,
  outdoor_pool INTEGER NOT NULL DEFAULT 0,
  indoor_pool INTEGER NOT NULL DEFAULT 0,
  natural_spring INTEGER NOT NULL DEFAULT 0,
  pregnancy_safe INTEGER NOT NULL DEFAULT 0,
  step_free_entry INTEGER NOT NULL DEFAULT 0,
  hoist_available INTEGER NOT NULL DEFAULT 0,
  accessible_changerooms INTEGER NOT NULL DEFAULT 0
);
"""


def parse_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    slug = path.stem
    if not text.startswith("---"):
        raise ValueError(f"{slug}: missing frontmatter delimiter")
    _, frontmatter_yaml, _body = text.split("---", 2)
    data = yaml.safe_load(frontmatter_yaml) or {}
    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValueError(f"{slug}: missing required field '{field}'")
    missing_amenities = [key for key in AMENITY_KEYS if key not in data["amenities"]]
    if missing_amenities:
        raise ValueError(f"{slug}: amenities missing keys {missing_amenities}")
    return data


def iter_published(published_dir: Path):
    """Skips and logs (rather than raises on) any file that fails to parse —
    the DB is disposable and rebuildable from `_published` (TRD §5), and one
    corrupted/hand-edited file shouldn't take the entire rebuild — every
    other venue's data — down with it."""
    for path in sorted(published_dir.glob("*.mdx")):
        try:
            yield path.stem, parse_frontmatter(path)
        except ValueError as exc:
            _logger.warning("rebuild: skipping %s — %s", path.stem, exc)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def upsert_venue(conn: sqlite3.Connection, slug: str, data: dict[str, Any]) -> None:
    cols = ("slug", *VENUE_SCALAR_COLUMNS)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in VENUE_SCALAR_COLUMNS)
    conn.execute(
        f"INSERT INTO venues ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(slug) DO UPDATE SET {updates}",
        _venue_params(slug, data),
    )
    amenities = data["amenities"]
    conn.execute(
        """
        INSERT INTO amenities (slug, magnesium_pool, infrared_sauna, traditional_sauna, cold_plunge, led_therapy)
        VALUES (:slug, :magnesium_pool, :infrared_sauna, :traditional_sauna, :cold_plunge, :led_therapy)
        ON CONFLICT(slug) DO UPDATE SET
          magnesium_pool = excluded.magnesium_pool, infrared_sauna = excluded.infrared_sauna,
          traditional_sauna = excluded.traditional_sauna, cold_plunge = excluded.cold_plunge,
          led_therapy = excluded.led_therapy
        """,
        {
            "slug": slug,
            **{key: 1 if amenities[key] else 0 for key in AMENITY_KEYS},
        },
    )
    facilities = data.get("facilities") or {}
    conn.execute(
        """
        INSERT INTO facilities (slug, parking, towels_provided, changerooms, bookings_required, wheelchair_access, outdoor_pool, indoor_pool, natural_spring, pregnancy_safe, step_free_entry, hoist_available, accessible_changerooms)
        VALUES (:slug, :parking, :towels_provided, :changerooms, :bookings_required, :wheelchair_access, :outdoor_pool, :indoor_pool, :natural_spring, :pregnancy_safe, :step_free_entry, :hoist_available, :accessible_changerooms)
        ON CONFLICT(slug) DO UPDATE SET
          parking = excluded.parking, towels_provided = excluded.towels_provided,
          changerooms = excluded.changerooms, bookings_required = excluded.bookings_required,
          wheelchair_access = excluded.wheelchair_access, outdoor_pool = excluded.outdoor_pool,
          indoor_pool = excluded.indoor_pool, natural_spring = excluded.natural_spring,
          pregnancy_safe = excluded.pregnancy_safe, step_free_entry = excluded.step_free_entry,
          hoist_available = excluded.hoist_available, accessible_changerooms = excluded.accessible_changerooms
        """,
        {
            "slug": slug,
            **{key: 1 if facilities.get(key) else 0 for key in FACILITY_KEYS},
        },
    )


def _nonempty(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Drop all-null nested objects so venues.json omits `temperatures: {}`
    etc. rather than carrying empty shells — same 'omit if thin' posture as
    the frontmatter (SCHEMA.md)."""
    kept = {k: v for k, v in obj.items() if v is not None}
    return kept or None


def fetch_all_venues(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT v.*,
               a.magnesium_pool, a.infrared_sauna, a.traditional_sauna, a.cold_plunge, a.led_therapy,
               f.parking, f.towels_provided, f.changerooms, f.bookings_required, f.wheelchair_access,
               f.outdoor_pool, f.indoor_pool, f.natural_spring, f.pregnancy_safe,
               f.step_free_entry, f.hoist_available, f.accessible_changerooms
        FROM venues v
        JOIN amenities a ON a.slug = v.slug
        JOIN facilities f ON f.slug = v.slug
        ORDER BY v.slug
        """
    ).fetchall()
    venues = []
    for r in rows:
        venue: dict[str, Any] = {
            "slug": r["slug"],
            "name": r["name"],
            "state": r["state"],
            "category": r["category"],
            "suburb": r["suburb"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "status": r["status"],
            "summary": r["summary"],
            "has_image": bool(r["has_image"]),
            "hours": r["hours"],
            "cost": r["cost"],
            "access": r["access"],
            "dress_code": r["dress_code"],
            "session_gender": r["session_gender"],
            "session_gender_note": r["session_gender_note"],
            "silence_policy": r["silence_policy"],
            "phone_policy": r["phone_policy"],
            "minimum_age": r["minimum_age"],
            "amenities": {key: bool(r[key]) for key in AMENITY_KEYS},
            "facilities": {key: bool(r[key]) for key in FACILITY_KEYS},
        }
        temperatures = _nonempty({
            "sauna_min_c": r["sauna_min_c"], "sauna_max_c": r["sauna_max_c"], "sauna_display": r["sauna_display"],
            "cold_plunge_min_c": r["cold_plunge_min_c"], "cold_plunge_max_c": r["cold_plunge_max_c"],
            "cold_plunge_display": r["cold_plunge_display"],
        })
        if temperatures:
            venue["temperatures"] = temperatures
        price = _nonempty({
            "adult_drop_in_aud": r["price_adult_drop_in_aud"],
            "standard_session_aud": r["price_standard_session_aud"],
        })
        if price:
            venue["price"] = price
        if r["drive_time_from"] is not None:
            venue["drive_time"] = {
                "from": r["drive_time_from"], "minutes": r["drive_time_minutes"], "km": r["drive_time_km"],
            }
        venues.append(venue)
    return venues


def write_venues_json(venues: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(venues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_venues_geojson(venues: list[dict[str, Any]], path: Path) -> None:
    # A null coordinate (geocoding found no match, SCHEMA.md §2) means "no map
    # marker" — a Point with a null coordinate is invalid GeoJSON, so those
    # venues are omitted here entirely; they still appear in venues.json.
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [v["longitude"], v["latitude"]]},
                "properties": {
                    "slug": v["slug"],
                    "name": v["name"],
                    "state": v["state"],
                    "category": v["category"],
                    "suburb": v["suburb"],
                    "status": v["status"],
                    "summary": v["summary"],
                    "has_image": v["has_image"],
                    "amenities": v["amenities"],
                    "facilities": v["facilities"],
                },
            }
            for v in venues
            if v["latitude"] is not None and v["longitude"] is not None
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geojson, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rebuild(
    published_dir: Path = PUBLISHED_DIR,
    db_path: Path = DB_PATH,
    json_path: Path = VENUES_JSON_PATH,
    geojson_path: Path = VENUES_GEOJSON_PATH,
) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        for slug, data in iter_published(published_dir):
            try:
                upsert_venue(conn, slug, data)
            except (sqlite3.Error, KeyError, TypeError) as exc:
                _logger.warning("rebuild: skipping %s — %s", slug, exc)
        conn.commit()
        venues = fetch_all_venues(conn)
    finally:
        conn.close()
    write_venues_json(venues, json_path)
    write_venues_geojson(venues, geojson_path)
    return len(venues)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild directory.db + venues.json/geojson from _published MDX frontmatter."
    )
    parser.add_argument("--rebuild", action="store_true", required=True)
    parser.parse_args()
    count = rebuild()
    print(f"Rebuilt {count} venue(s) -> {DB_PATH}, {VENUES_JSON_PATH}, {VENUES_GEOJSON_PATH}")


if __name__ == "__main__":
    main()
