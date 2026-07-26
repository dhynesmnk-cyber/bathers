"""One-time scope-narrowing cleanup (TRD.md §8, 2026-07-26 scope note): the
directory now only covers venues with a pool or a sauna as a central
offering. This is a deliberate, narrow exception to CLAUDE.md rule 5
("never touch `_published` by hand") — recategorisation and the amenity
fix go through the same `staging.split_frontmatter`/`render_mdx` helpers a
normal approve would use, and removals go through the existing
`staging.delete_published()` (parks the MDX in `content-staging/_deleted/`,
timestamped, never destroyed).

Dry-run by default; pass --apply to actually write. Usage:

    python -m admin.pipeline.scope_cleanup_2026_07_26            # preview only
    python -m admin.pipeline.scope_cleanup_2026_07_26 --apply    # write + rebuild
"""

from __future__ import annotations

import argparse

from admin.config import CATEGORY_KEYS, PUBLISHED_DIR
from admin.pipeline import data_store
from admin.pipeline.staging import delete_published, render_mdx, split_frontmatter

# day_spa retired in favour of hotel_spa — these are hotel/lodge venues with
# a real pool or sauna circuit, not a treatment-only day spa.
RECATEGORIZE = {
    "chuan-spa": "hotel_spa",
    "crown-spa-melbourne": "hotel_spa",
    "mineral-springs-hotel": "hotel_spa",
    "the-mineral-spa": "hotel_spa",
    "lake-house-daylesford": "hotel_spa",
    "waldheim-alpine-spa": "hotel_spa",
}

# Data bug found during the scope audit — an unambiguous sauna venue with
# every amenity boolean left false, most likely missed during harvesting.
AMENITY_FIXES = {
    "peninsula-sauna": {"traditional_sauna": True},
}

# No pool or sauna as a central offering (6 with zero pool/sauna signal at
# all, plus 2 where a sauna is one line on an otherwise treatment-led menu,
# not the reason to visit) — see TRD.md §8's 2026-07-26 scope note.
REMOVE = [
    "hidden-cove-day-spa-and-retreat",
    "holism-retreat",
    "ikigai-head-spa-and-wellness",
    "saltair-day-spa-melbourne",
    "silo-day-spa",
    "v-hotel-spa",
    "city-cave-braybrook",
    "relax-day-spa-melbourne-cbd",
]


def run(apply: bool) -> None:
    for slug, category in RECATEGORIZE.items():
        if category not in CATEGORY_KEYS:
            raise ValueError(f"{slug}: '{category}' is not a valid category")
        path = PUBLISHED_DIR / f"{slug}.mdx"
        if not path.exists():
            print(f"skip {slug} — not found in _published")
            continue
        data, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        if data.get("category") == category:
            print(f"skip {slug} — already category={category}")
            continue
        old = data.get("category")
        data["category"] = category
        print(f"{'write' if apply else 'would write'} {slug} — category {old} -> {category}")
        if apply:
            path.write_text(render_mdx(data, body), encoding="utf-8")

    for slug, fixes in AMENITY_FIXES.items():
        path = PUBLISHED_DIR / f"{slug}.mdx"
        if not path.exists():
            print(f"skip {slug} — not found in _published")
            continue
        data, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        amenities = data.get("amenities") or {}
        changes = []
        for key, value in fixes.items():
            if amenities.get(key) != value:
                amenities[key] = value
                changes.append(f"{key}={value}")
        if not changes:
            print(f"skip {slug} — amenities already correct")
            continue
        data["amenities"] = amenities
        print(f"{'write' if apply else 'would write'} {slug} — {', '.join(changes)}")
        if apply:
            path.write_text(render_mdx(data, body), encoding="utf-8")

    if apply:
        count = data_store.rebuild()
        print(f"rebuilt {count} venue(s)")
    else:
        print("dry run (recategorise/fix) — pass --apply to write and rebuild")

    for slug in REMOVE:
        path = PUBLISHED_DIR / f"{slug}.mdx"
        if not path.exists():
            print(f"skip {slug} — not found in _published")
            continue
        print(f"{'remove' if apply else 'would remove'} {slug}")
        if apply:
            delete_published(slug)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually write/remove the files and rebuild the DB")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
