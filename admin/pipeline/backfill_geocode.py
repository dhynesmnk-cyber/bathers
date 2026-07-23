"""One-shot coordinate backfill for published venues (2026-07-23).

Most early venues were harvested before the geocoder was configured, so
they carry `latitude: null` and never get a map marker. This walks
`_published`, geocodes every null-coordinate venue's address via the
existing geocode module (cache + 1 req/s politeness preserved), writes the
coordinates back through the staging render path (field order and date
handling preserved), and rebuilds the derived data.

Usage:
    python -m admin.pipeline.backfill_geocode [--dry-run]
        [--geocoder nominatim] [--user-agent "…"]

The optional overrides exist for machines whose .env has no geocoder
configured; they never touch .env itself.
"""

from __future__ import annotations

import argparse

from admin.config import PUBLISHED_DIR
from admin.pipeline import data_store, geocode
from admin.pipeline.staging import render_mdx, split_frontmatter


def _log(text: str, level: str = "info") -> None:
    print(f"[{level}] {text}")


def backfill(dry_run: bool = False) -> tuple[int, int]:
    updated = 0
    missed = 0
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        slug = path.stem
        data, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        if data.get("latitude") is not None and data.get("longitude") is not None:
            continue
        address = data.get("address") or ""
        coords = geocode.geocode_address(address, log=_log)
        if coords is None:
            missed += 1
            print(f"  MISS {slug}: no match for {address!r}")
            continue
        updated += 1
        print(f"  OK   {slug}: {coords[0]:.5f}, {coords[1]:.5f}")
        if not dry_run:
            data["latitude"], data["longitude"] = coords
            path.write_text(render_mdx(data, body), encoding="utf-8")
    if updated and not dry_run:
        count = data_store.rebuild()
        print(f"rebuilt derived data — {count} venue(s)")
    return updated, missed


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill null coordinates on published venues.")
    parser.add_argument("--dry-run", action="store_true", help="geocode and report, write nothing")
    parser.add_argument("--geocoder", help="override GEOCODER for this run (e.g. nominatim)")
    parser.add_argument("--user-agent", help="override GEOCODER_USER_AGENT for this run")
    args = parser.parse_args()
    if args.geocoder:
        geocode.GEOCODER = args.geocoder
    if args.user_agent:
        geocode.GEOCODER_USER_AGENT = args.user_agent
    updated, missed = backfill(dry_run=args.dry_run)
    print(f"done — {updated} updated, {missed} unmatched{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
