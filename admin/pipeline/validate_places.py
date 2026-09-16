"""Place-hierarchy integrity (2026-09-08 — TRD.md §1).

The /places/ tree collapses two different kinds of page into one URL slot: a
subdivision's areas (`.../victoria/mornington-peninsula/`) and its feature
filters (`.../victoria/magnesium-pool/`). That keeps URLs short, and is safe
only while the two slug sets never intersect. Area names are places and filter
slugs are features, so they cannot collide in practice — this module exists so
that "cannot in practice" never quietly becomes "did", which would silently
drop one of the two pages from the build with no error anywhere.

Also asserts the tree is honest in both directions: every published venue's
country and subdivision resolve to a real page, and every generated place page
is reachable from its own parent. A hierarchy is only navigable if every level
actually links the one below it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from admin.config import (
    AMENITY_KEYS,
    DEFAULT_COUNTRY,
    PUBLISHED_DIR,
    SITE_DIR,
    SUBDIVISION_NAMES,
    WORLD_REGIONS,
    place_path,
    subdivision_slug,
    world_region_for_country,
)
from admin.pipeline.data_store import parse_frontmatter

DIST = SITE_DIR / "dist"
REGIONS_TS = SITE_DIR / "src" / "data" / "regions.ts"
CONFIG_TS = SITE_DIR / "src" / "config.ts"


def _area_slugs_by_subdivision() -> dict[tuple[str, str], list[str]]:
    """Region taxonomy slugs, per (country, subdivision), read from regions.ts —
    the taxonomy's own file, so this cannot drift from what the routes generate.

    Keyed by country as well as code (Gate 16): the subdivision code alone is
    not unique, so an AU "WA" region and a US "WA" region would land in one
    bucket and their slugs would be checked for collisions against each other
    while the real collisions — within a single subdivision's own URL level —
    went unexamined."""
    text = REGIONS_TS.read_text(encoding="utf-8")
    out: dict[tuple[str, str], list[str]] = {}
    for slug, country, subdivision in re.findall(
        r'\{\s*slug:\s*"([a-z0-9-]+)",\s*name:\s*"[^"]+",\s*country:\s*"([A-Z]{2})",'
        r'\s*subdivision:\s*"([A-Z]{2,3})"',
        text,
    ):
        out.setdefault((country, subdivision), []).append(slug)
    return out


def _region_cities() -> dict[tuple[str, str], list[tuple[str, list[str]]]]:
    """(country, subdivision) -> [(region slug, its cities)], from regions.ts."""
    text = REGIONS_TS.read_text(encoding="utf-8")
    out: dict[tuple[str, str], list[tuple[str, list[str]]]] = {}
    for slug, country, subdivision, cities in re.findall(
        r'\{\s*slug:\s*"([a-z0-9-]+)",\s*name:\s*"[^"]+",\s*country:\s*"([A-Z]{2})",'
        r'\s*subdivision:\s*"([A-Z]{2,3})",\s*cities:\s*\[(.*?)\]',
        text,
        re.S,
    ):
        names = [c.strip().strip('"') for c in cities.split(",") if c.strip().strip('"')]
        out.setdefault((country, subdivision), []).append((slug, names))
    return out


def _check_region_coverage() -> list[str]:
    """Every published venue's city resolves to exactly one region, and no city
    is claimed by two regions of the same subdivision.

    This was /validate check 10, written as prose and never mechanised — which
    is precisely how seven published venues (Boomi, Burren Junction, Braybrook,
    Southbank, Point Lonsdale, Northcote, Beechworth) sat in no region at all,
    on no area page, for as long as they did. A check nobody runs is a check
    nobody fails.

    An empty `cities` list is fine: several regions are scaffolded ahead of the
    venues that will fill them, which is deliberate and predates this.
    """
    failures: list[str] = []
    by_sub = _region_cities()

    for (country, subdivision), regions in by_sub.items():
        seen: dict[str, str] = {}
        for slug, cities in regions:
            for city in cities:
                key = city.lower()
                if key in seen and seen[key] != slug:
                    failures.append(
                        f"{country}/{subdivision}: '{city}' is claimed by both "
                        f"'{seen[key]}' and '{slug}' — a venue there would resolve "
                        f"to two regions"
                    )
                seen[key] = slug

    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        fm = parse_frontmatter(path)
        country = fm.get("country", DEFAULT_COUNTRY)
        subdivision = fm.get("state_province")
        city = (fm.get("city") or "").strip().lower()
        if not city:
            continue
        hits = [
            slug
            for slug, cities in by_sub.get((country, subdivision), [])
            if any(c.lower() == city for c in cities)
        ]
        if not hits:
            failures.append(
                f"{path.stem}: '{fm.get('city')}' ({country}/{subdivision}) is in no "
                f"region — the venue appears on no area page"
            )
        elif len(hits) > 1:
            failures.append(
                f"{path.stem}: '{fm.get('city')}' resolves to {len(hits)} regions "
                f"({', '.join(hits)}) — it must resolve to exactly one"
            )
    return failures


def _filter_slugs() -> set[str]:
    """Every slug the leaf route can emit for a feature filter.

    Pool types and cross-cutting facilities live only in site/src/config.ts, so
    they are read out of it rather than copied here — a hardcoded mirror would
    be exactly the drift this module is meant to prevent.
    """
    slugs = {key.replace("_", "-") for key in AMENITY_KEYS}
    text = CONFIG_TS.read_text(encoding="utf-8")
    for const in ("CROSS_CUTTING_FACILITY_FILTERS", "POOL_TYPES"):
        block = text.split(f"export const {const}", 1)
        if len(block) < 2:
            continue
        body = block[1].split("] as const;", 1)[0]
        slugs |= set(re.findall(r'slug:\s*"([a-z0-9-]+)"', body))
    return slugs


def run() -> list[str]:
    failures: list[str] = []

    # 1. Area and filter slugs must not collide within a subdivision.
    filters = _filter_slugs()
    for (country, subdivision), areas in _area_slugs_by_subdivision().items():
        where = f"{country}/{subdivision}"
        clash = sorted(set(areas) & filters)
        if clash:
            failures.append(
                f"{where}: area slug(s) collide with feature-filter slug(s) at the same URL "
                f"level — one page would silently overwrite the other: {', '.join(clash)}"
            )
        duplicates = sorted({s for s in areas if areas.count(s) > 1})
        if duplicates:
            failures.append(f"{where}: duplicate area slug(s): {', '.join(duplicates)}")

    # 1b. Subdivision slugs and country-wide filter slugs share the tier below a
    # country (Gate 16: /places/north-america/united-states/florida/ and
    # .../magnesium-pool/ are siblings). Same slot, same hazard as 1 above —
    # a collision would silently drop whichever page Astro generated second.
    for country in SUBDIVISION_NAMES:
        if country == DEFAULT_COUNTRY:
            continue  # its filters live at the top level, not under /places/
        subdivision_slugs = {
            subdivision_slug(country, code) for code in SUBDIVISION_NAMES[country]
        }
        clash = sorted(subdivision_slugs & filters)
        if clash:
            failures.append(
                f"{country}: subdivision slug(s) collide with country-wide feature-filter "
                f"slug(s) at the same URL level — one page would silently overwrite the "
                f"other: {', '.join(clash)}"
            )

    # 1c. Region coverage — /validate check 10, mechanised 2026-09-16.
    failures.extend(_check_region_coverage())

    # 2. Every published venue's place must resolve to a declared one.
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        fm = parse_frontmatter(path)
        country = fm.get("country", "AU")
        code = fm.get("state_province")
        if world_region_for_country(country) is None:
            failures.append(f"{path.stem}: country {country!r} is in no world region")
            continue
        if code not in SUBDIVISION_NAMES.get(country, {}):
            failures.append(f"{path.stem}: {code!r} is not a subdivision of {country}")

    # 3. Built output: every level links the one below it.
    if DIST.exists():
        hub = DIST / "places" / "index.html"
        if not hub.exists():
            failures.append("no /places/ hub was built")
        else:
            hub_html = hub.read_text(encoding="utf-8")
            for region in WORLD_REGIONS:
                region_dir = DIST / "places" / region["slug"]
                if not (region_dir / "index.html").exists():
                    continue  # no venues in this world region yet — not a failure
                if f'/places/{region["slug"]}/' not in hub_html:
                    failures.append(f"/places/{region['slug']}/ is not linked from the /places/ hub")
                region_html = (region_dir / "index.html").read_text(encoding="utf-8")
                for country in region["countries"]:
                    country_path = place_path(country)
                    if not (DIST / country_path.strip("/") / "index.html").exists():
                        continue
                    if country_path not in region_html:
                        failures.append(f"{country_path} is not linked from /places/{region['slug']}/")
                    country_html = (DIST / country_path.strip("/") / "index.html").read_text(encoding="utf-8")
                    for code in SUBDIVISION_NAMES[country]:
                        sub_path = place_path(country, code)
                        if not (DIST / sub_path.strip("/") / "index.html").exists():
                            continue
                        if sub_path not in country_html:
                            failures.append(f"{sub_path} is not linked from {country_path}")
                        sub_html = (DIST / sub_path.strip("/") / "index.html").read_text(encoding="utf-8")
                        leaf_dir = DIST / sub_path.strip("/")
                        for leaf in sorted(p for p in leaf_dir.iterdir() if p.is_dir()):
                            leaf_path = place_path(country, code, leaf.name)
                            if leaf_path not in sub_html:
                                failures.append(f"{leaf_path} is not linked from {sub_path}")
    return failures


def _self_test() -> int:
    """Proves the collision check actually catches a collision — the failure it
    exists for produces no build error on its own."""
    module = sys.modules[__name__]
    original = module._area_slugs_by_subdivision
    try:
        module._area_slugs_by_subdivision = lambda: {("AU", "VIC"): ["magnesium-pool"]}
        caught = any("collide" in f for f in run())
        # And the same collision under a second country, which is the case the
        # bare-code keying could not have distinguished.
        module._area_slugs_by_subdivision = lambda: {("US", "FL"): ["cold-plunge"]}
        caught_us = any("collide" in f for f in run())
        module._area_slugs_by_subdivision = lambda: {
            ("AU", "VIC"): ["mornington-peninsula"],
            ("US", "FL"): ["north-central-florida"],
        }
        clean = not any("collide" in f for f in run())
    finally:
        module._area_slugs_by_subdivision = original
    # Region coverage, both directions: a venue in no region, and a city two
    # regions both claim.
    original_cities = module._region_cities
    try:
        stripped = {
            k: [(s, [c for c in cities if c.lower() != "southbank"]) for s, cities in v]
            for k, v in original_cities().items()
        }
        module._region_cities = lambda: stripped
        caught_orphan = any("is in no region" in f for f in run())

        doubled = {
            k: [(s, cities + ["Daylesford"] if s == "melbourne" else cities) for s, cities in v]
            for k, v in original_cities().items()
        }
        module._region_cities = lambda: doubled
        caught_overlap = any("claimed by both" in f for f in run())
    finally:
        module._region_cities = original_cities

    # And the country-level tier: a filter slug that matches a subdivision slug.
    original_filters = module._filter_slugs
    try:
        module._filter_slugs = lambda: original_filters() | {"florida"}
        caught_country = any("subdivision slug" in f for f in run())
    finally:
        module._filter_slugs = original_filters

    ok = caught and caught_us and clean and caught_country and caught_orphan and caught_overlap
    print(f"  {'ok  ' if caught else 'FAIL'} a colliding AU area slug is rejected")
    print(f"  {'ok  ' if caught_us else 'FAIL'} a colliding US area slug is rejected")
    print(f"  {'ok  ' if clean else 'FAIL'} normal area slugs in both countries pass")
    print(f"  {'ok  ' if caught_country else 'FAIL'} a filter slug colliding with a subdivision slug is rejected")
    print(f"  {'ok  ' if caught_orphan else 'FAIL'} a venue whose city is in no region is rejected")
    print(f"  {'ok  ' if caught_overlap else 'FAIL'} a city claimed by two regions is rejected")
    return 0 if ok else 1


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    failures = run()
    if failures:
        print(f"PLACE HIERARCHY FAIL — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("place hierarchy: pass")


if __name__ == "__main__":
    main()
