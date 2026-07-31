"""Internal-linking graph check (Gate 10, 2026-07-31). Verifies the *rendered*
link graph in the built site — not a reimplementation of the comparison
predicates, so it can't drift from what actually ships:

- every published venue is linked from >=3 aggregation pages (comparison,
  region roll-up, state, or national amenity/facility list) — no orphans;
- every comparison page is reachable from the /compare/ hub, and every region
  roll-up from the /region/ hub.

Run after `npm run build` (folded into /validate). `run(dist)` returns failure
strings; empty = pass.
"""

from __future__ import annotations

import re
from pathlib import Path

from admin.config import PUBLISHED_DIR, ROOT, STATES

DIST = ROOT / "site" / "dist"
MIN_AGGREGATION_PAGES = 3

_SPA_LINK = re.compile(r'href="(?:https?://[^/]+)?/spa/([a-z0-9-]+)/?"')


def _links_in(page: Path) -> set[str]:
    if not page.exists():
        return set()
    return set(_SPA_LINK.findall(page.read_text(encoding="utf-8")))


def _aggregation_pages(dist: Path) -> dict[str, Path]:
    """label -> index.html for every venue-listing aggregation page."""
    pages: dict[str, Path] = {}
    for kind in ("compare", "region"):
        for d in sorted((dist / kind).glob("*/")):
            pages[f"{kind}/{d.name}"] = d / "index.html"
    for state in STATES:
        p = dist / state.lower() / "index.html"
        if p.exists():
            pages[f"state/{state}"] = p
    # National amenity/facility lists live at /<slug>/ (Gate 6) — include any
    # top-level dir whose page links venues but isn't a venue/section page.
    reserved = {"spa", "compare", "region", "category", "glossary", "blog", "claim", *(s.lower() for s in STATES)}
    for d in sorted(dist.glob("*/")):
        if d.name in reserved:
            continue
        idx = d / "index.html"
        if idx.exists() and _links_in(idx):
            pages[f"national/{d.name}"] = idx
    return pages


def run(dist: Path = DIST) -> list[str]:
    failures: list[str] = []
    if not dist.exists():
        return [f"no build at {dist} — run `npm run build` first"]

    published = {p.stem for p in PUBLISHED_DIR.glob("*.mdx")}
    pages = _aggregation_pages(dist)

    # venue -> aggregation pages linking it
    membership: dict[str, set[str]] = {slug: set() for slug in published}
    for label, page in pages.items():
        for slug in _links_in(page):
            if slug in membership:
                membership[slug].add(label)

    for slug in sorted(published):
        n = len(membership[slug])
        if n < MIN_AGGREGATION_PAGES:
            failures.append(f"venue '{slug}' is linked from only {n} aggregation page(s) ({', '.join(sorted(membership[slug])) or 'none'}) — needs >= {MIN_AGGREGATION_PAGES}")

    # hub reachability: each comparison/region page must be linked from its hub
    for hub_name, prefix in (("compare/index.html", "/compare/"), ("region/index.html", "/region/")):
        hub = dist / hub_name
        hub_html = hub.read_text(encoding="utf-8") if hub.exists() else ""
        for label, page in pages.items():
            kind = label.split("/", 1)[0]
            if (kind == "compare" and prefix == "/compare/") or (kind == "region" and prefix == "/region/"):
                slug = label.split("/", 1)[1]
                if f'{prefix}{slug}/' not in hub_html:
                    failures.append(f"{label} is not reachable from {hub_name} (orphan aggregation page)")
    return failures


def main() -> None:
    failures = run()
    if failures:
        print(f"LINK GRAPH FAIL — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("link graph: pass")


if __name__ == "__main__":
    main()
