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
  access TEXT
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
  natural_spring INTEGER NOT NULL DEFAULT 0
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
    conn.execute(
        """
        INSERT INTO venues (slug, name, state, category, suburb, latitude, longitude, status, summary, has_image, hours, cost, access)
        VALUES (:slug, :name, :state, :category, :suburb, :latitude, :longitude, :status, :summary, :has_image, :hours, :cost, :access)
        ON CONFLICT(slug) DO UPDATE SET
          name = excluded.name, state = excluded.state, category = excluded.category, suburb = excluded.suburb,
          latitude = excluded.latitude, longitude = excluded.longitude,
          status = excluded.status, summary = excluded.summary, has_image = excluded.has_image,
          hours = excluded.hours, cost = excluded.cost, access = excluded.access
        """,
        {
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
        },
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
        INSERT INTO facilities (slug, parking, towels_provided, changerooms, bookings_required, wheelchair_access, outdoor_pool, indoor_pool, natural_spring)
        VALUES (:slug, :parking, :towels_provided, :changerooms, :bookings_required, :wheelchair_access, :outdoor_pool, :indoor_pool, :natural_spring)
        ON CONFLICT(slug) DO UPDATE SET
          parking = excluded.parking, towels_provided = excluded.towels_provided,
          changerooms = excluded.changerooms, bookings_required = excluded.bookings_required,
          wheelchair_access = excluded.wheelchair_access, outdoor_pool = excluded.outdoor_pool,
          indoor_pool = excluded.indoor_pool, natural_spring = excluded.natural_spring
        """,
        {
            "slug": slug,
            **{key: 1 if facilities.get(key) else 0 for key in FACILITY_KEYS},
        },
    )


def fetch_all_venues(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT v.slug, v.name, v.state, v.category, v.suburb, v.latitude, v.longitude,
               v.status, v.summary, v.has_image, v.hours, v.cost, v.access,
               a.magnesium_pool, a.infrared_sauna, a.traditional_sauna, a.cold_plunge, a.led_therapy,
               f.parking, f.towels_provided, f.changerooms, f.bookings_required, f.wheelchair_access,
               f.outdoor_pool, f.indoor_pool, f.natural_spring
        FROM venues v
        JOIN amenities a ON a.slug = v.slug
        JOIN facilities f ON f.slug = v.slug
        ORDER BY v.slug
        """
    ).fetchall()
    venues = []
    for (
        slug, name, state, category, suburb, latitude, longitude, status, summary, has_image, hours, cost, access,
        mg, ir, sa, cp, led,
        parking, towels, changerooms, bookings, wheelchair,
        outdoor_pool, indoor_pool, natural_spring,
    ) in rows:
        venues.append(
            {
                "slug": slug,
                "name": name,
                "state": state,
                "category": category,
                "suburb": suburb,
                "latitude": latitude,
                "longitude": longitude,
                "status": status,
                "summary": summary,
                "has_image": bool(has_image),
                "hours": hours,
                "cost": cost,
                "access": access,
                "amenities": {
                    "magnesium_pool": bool(mg),
                    "infrared_sauna": bool(ir),
                    "traditional_sauna": bool(sa),
                    "cold_plunge": bool(cp),
                    "led_therapy": bool(led),
                },
                "facilities": {
                    "parking": bool(parking),
                    "towels_provided": bool(towels),
                    "changerooms": bool(changerooms),
                    "bookings_required": bool(bookings),
                    "wheelchair_access": bool(wheelchair),
                    "outdoor_pool": bool(outdoor_pool),
                    "indoor_pool": bool(indoor_pool),
                    "natural_spring": bool(natural_spring),
                },
            }
        )
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
