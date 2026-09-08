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


def _area_slugs_by_state() -> dict[str, list[str]]:
    """Region taxonomy slugs, per AU subdivision, read from regions.ts — the
    taxonomy's own file, so this cannot drift from what the routes generate."""
    text = REGIONS_TS.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for slug, state in re.findall(
        r'\{\s*slug:\s*"([a-z0-9-]+)",\s*name:\s*"[^"]+",\s*state:\s*"([A-Z]{2,3})"', text
    ):
        out.setdefault(state, []).append(slug)
    return out


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
    for state, areas in _area_slugs_by_state().items():
        clash = sorted(set(areas) & filters)
        if clash:
            failures.append(
                f"{state}: area slug(s) collide with feature-filter slug(s) at the same URL "
                f"level — one page would silently overwrite the other: {', '.join(clash)}"
            )
        duplicates = sorted({s for s in areas if areas.count(s) > 1})
        if duplicates:
            failures.append(f"{state}: duplicate area slug(s): {', '.join(duplicates)}")

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
    original = module._area_slugs_by_state
    try:
        module._area_slugs_by_state = lambda: {"VIC": ["magnesium-pool"]}
        caught = any("collide" in f for f in run())
        module._area_slugs_by_state = lambda: {"VIC": ["mornington-peninsula"]}
        clean = not any("collide" in f for f in run())
    finally:
        module._area_slugs_by_state = original
    ok = caught and clean
    print(f"  {'ok  ' if caught else 'FAIL'} a colliding area slug is rejected")
    print(f"  {'ok  ' if clean else 'FAIL'} a normal area slug passes")
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
