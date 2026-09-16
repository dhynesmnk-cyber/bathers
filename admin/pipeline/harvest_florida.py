"""Florida discovery and harvest driver (Gate 16, 2026-09-15).

A thin driver over what already exists: `discovery.discover_venues` for finding
candidates and `orchestrator.run_harvest_pipeline` for turning one URL into a
staged draft. It adds no pipeline logic of its own and no dependency — the only
thing it knows that those modules don't is which Florida regions to sweep, and
that the answer is `US`.

**It never publishes.** Every draft lands in `content-staging/_staging/` exactly
as a single harvest from the admin UI would, for a human to review and approve.
That is the same rule the admin flow follows and it is not negotiable here: the
venues are real businesses.

Region strings come from `site/src/data/regions.ts`, the taxonomy's own file, so
this cannot sweep a region the site has no page for. Reading them out rather
than repeating them here is the same posture `validate_places` takes.

Usage
-----
    # See what Places returns, harvest nothing. Costs Places calls only.
    python3 -m admin.pipeline.harvest_florida --discover

    # Discover, then harvest each candidate into _staging/. Costs Anthropic
    # tokens per venue — start with --limit.
    python3 -m admin.pipeline.harvest_florida --harvest --limit 5

    # Harvest specific URLs (the SEED.md seeds, once verified live).
    python3 -m admin.pipeline.harvest_florida --harvest --url https://…

Requires GOOGLE_PLACES_API_KEY for discovery and ANTHROPIC_API_KEY for harvest;
both are read from `.env` by admin/config.py. With neither set this prints what
it would do and exits — see FLORIDA-RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import re
import sys

from admin.config import SITE_DIR, STAGING_DIR
from admin.pipeline import discovery, places
from admin.pipeline.orchestrator import run_harvest_pipeline

COUNTRY = "US"
SUBDIVISION = "FL"
REGIONS_TS = SITE_DIR / "src" / "data" / "regions.ts"

# Florida's bathing is springs-led rather than bathhouse-led, so the default
# discovery keywords are widened here. "day spa" stays out, as it has since
# 2026-07-26 (TRD.md §8) — it pulls in nail salons.
FLORIDA_KEYWORDS = (
    "bathhouse",
    "hot springs",
    "mineral springs",
    "thermal baths",
    "sauna",
    "cold plunge",
    "banya",
)


def florida_regions() -> list[str]:
    """Region display names for FL, read from the taxonomy's own file."""
    text = REGIONS_TS.read_text(encoding="utf-8")
    return [
        name
        for name, country, subdivision in re.findall(
            r'\{\s*slug:\s*"[a-z0-9-]+",\s*name:\s*"([^"]+)",\s*country:\s*"([A-Z]{2})",'
            r'\s*subdivision:\s*"([A-Z]{2,3})"',
            text,
        )
        if country == COUNTRY and subdivision == SUBDIVISION
    ]


def discover(regions: list[str], keywords: list[str]) -> list[discovery.DiscoveryCandidate]:
    """Sweep each region, deduped across the whole run.

    discover_venues already dedupes by place_id and by website domain against
    everything published or staged; this adds dedup ACROSS regions, since
    neighbouring Florida regions overlap at their edges.
    """
    seen: set[str] = set()
    out: list[discovery.DiscoveryCandidate] = []
    for region in regions:
        found = discovery.discover_venues(region, keywords, COUNTRY)
        fresh = [c for c in found if c.place_id not in seen]
        seen.update(c.place_id for c in fresh)
        out.extend(fresh)
        print(f"  {region:28} {len(found):3} found, {len(fresh):3} new")
    return out


def _staged_slugs() -> set[str]:
    return {p.stem for p in STAGING_DIR.glob("*.mdx")} if STAGING_DIR.exists() else set()


def harvest(urls: list[str], limit: int | None) -> int:
    """Run each URL through the existing pipeline. Returns a process exit code.

    run_harvest_pipeline yields LogLine and nothing else — it signals failure by
    emitting an error-level line, not by a return value. So success is measured
    by what actually appeared in _staging/ rather than by reading the log: a
    file on disk is the fact, the log is the commentary.

    One failure does not stop the run. A sweep of twenty should not end on the
    first site with an unreadable menu.
    """
    selected = urls[:limit] if limit else urls
    staged: list[str] = []
    failed: list[tuple[str, str]] = []

    for i, url in enumerate(selected, 1):
        print(f"\n[{i}/{len(selected)}] {url}")
        before = _staged_slugs()
        last_error = ""
        try:
            for line in run_harvest_pipeline(url):
                print(f"    {line.level:5} {line.text}")
                if line.level == "error":
                    last_error = line.text
        except Exception as exc:  # noqa: BLE001 — one bad URL must not end the sweep
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"    error {last_error}")

        new_slugs = _staged_slugs() - before
        if new_slugs:
            slug = next(iter(new_slugs))
            staged.append(slug)
            print(f"    -> staged as {slug}")
        else:
            failed.append((url, last_error or "no draft appeared in _staging/"))
            print("    -> nothing staged")

    print(f"\n{len(staged)}/{len(selected)} staged into {STAGING_DIR}")
    for slug in staged:
        print(f"  staged  {slug}")
    for url, why in failed:
        print(f"  failed  {url}\n            {why}")
    print(
        "\nNothing is published. Every draft is in _staging/ for review — see "
        "FLORIDA-RUNBOOK.md for what to check before approving."
    )
    return 0 if staged else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--discover", action="store_true", help="list candidates, harvest nothing")
    parser.add_argument("--harvest", action="store_true", help="harvest candidates into _staging/")
    parser.add_argument("--url", action="append", default=[], help="harvest this URL (repeatable)")
    parser.add_argument("--limit", type=int, help="cap how many venues are harvested")
    parser.add_argument("--region", action="append", default=[], help="sweep only this region")
    args = parser.parse_args()

    if not (args.discover or args.harvest):
        parser.error("choose --discover or --harvest")

    if args.url:
        if not args.harvest:
            parser.error("--url only applies with --harvest")
        sys.exit(harvest(args.url, args.limit))

    regions = args.region or florida_regions()
    print(f"Florida regions to sweep ({len(regions)}):")
    for r in regions:
        print(f"  - {r}")

    if not places.GOOGLE_PLACES_API_KEY:
        print(
            "\nGOOGLE_PLACES_API_KEY is not set, so discovery would return nothing.\n"
            "Set it in .env and re-run, or pass --url to harvest a known URL.\n"
            "See FLORIDA-RUNBOOK.md."
        )
        sys.exit(1)

    print(f"\nKeywords: {', '.join(FLORIDA_KEYWORDS)}\n")
    candidates = discover(regions, list(FLORIDA_KEYWORDS))
    print(f"\n{len(candidates)} candidate(s) after dedup:\n")
    for c in candidates:
        print(f"  {c.name}\n    {c.website}\n    {c.formatted_address or '(no address)'}")

    if args.discover:
        print("\nDiscovery only — nothing harvested.")
        sys.exit(0)

    sys.exit(harvest([c.website for c in candidates], args.limit))


if __name__ == "__main__":
    main()
