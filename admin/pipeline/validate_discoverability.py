"""Discoverability checks (Gate 6's title; mechanised 2026-09-16).

Folds /validate checks 8, 9 and 11 into a module with an exit code. All three
assert the same thing from different angles: **the built output matches what the
config tables say it should contain.**

They existed as prose greps in `.claude/commands/validate.md` from Gate 6 until
now, which meant nothing ran them and nothing went red. That is not a
hypothetical cost — check 10 spent its life the same way, and seven published
venues sat in no region and on no area page until 2026-09-16 as a result. These
three are the last of that set.

Check 9 in particular has a live reason to exist since Gate 16: "national" now
means Australia (`[scope]/index.astro` filters to DEFAULT_COUNTRY) and every
other country gets its filter pages under `/places/<world>/<country>/<slug>/`.
A route failing to generate on either side is caught by nothing else.

`run(dist)` returns failure strings; empty means pass.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from admin.config import (
    AMENITY_KEYS,
    DEFAULT_COUNTRY,
    PUBLISHED_DIR,
    SITE_DIST_DIR,
    place_path,
)
from admin.pipeline import config_ts
from admin.pipeline.data_store import iter_published

NOINDEX = '<meta name="robots" content="noindex, follow">'
SRC_DIRS = ("site/src/pages", "site/src/layouts", "site/src/components")


# --------------------------------------------------------------------------
# 8. Claim-page noindex
# --------------------------------------------------------------------------
def check_claim_noindex(dist: Path) -> list[str]:
    """Claim pages carry noindex; nothing else does.

    Both directions matter. A claim page without it competes with the venue's
    own page for the same query; a noindex that escapes onto a real page
    removes that page from search entirely, and would look like nothing at all
    in a green build.
    """
    failures: list[str] = []
    claim_pages = sorted(dist.glob("claim/*/index.html"))
    if not claim_pages:
        failures.append("no claim pages were built at all — the route may have been lost")

    for page in claim_pages:
        if NOINDEX not in page.read_text(encoding="utf-8"):
            failures.append(f"claim/{page.parent.name}/ is missing its noindex meta")

    for page in dist.rglob("index.html"):
        rel = page.relative_to(dist)
        if rel.parts and rel.parts[0] == "claim":
            continue
        if NOINDEX in page.read_text(encoding="utf-8"):
            failures.append(f"/{rel.parent}/ carries noindex but is not a claim page")
    return failures


# --------------------------------------------------------------------------
# 9. Route coverage, per country
# --------------------------------------------------------------------------
def _filters() -> list[tuple[str, str]]:
    """(slug, frontmatter predicate key) for every national filter route."""
    out = [(key.replace("_", "-"), key) for key in AMENITY_KEYS]
    for const in ("CROSS_CUTTING_FACILITY_FILTERS", "POOL_NATIONAL_FILTERS"):
        rows = config_ts.entries(const)
        if not rows:
            # A renamed or reformatted constant must fail loudly. Returning
            # nothing here would silently reduce this check to the amenities.
            out.append((f"!missing:{const}", ""))
            continue
        out.extend((row["slug"], row["key"]) for row in rows)
    return out


def _has(venue: dict, key: str) -> bool:
    return bool((venue.get("amenities") or {}).get(key) or (venue.get("facilities") or {}).get(key))


def check_route_coverage(dist: Path) -> list[str]:
    """Every filter with >=1 published venue in a country has that country's
    page built AND listed in sitemap.xml.

    Built-but-unlisted is as much a failure as missing: a page no sitemap
    mentions is a page the crawler may never reach, which is the entire point
    of generating it.
    """
    failures: list[str] = []
    sitemap_path = dist / "sitemap.xml"
    if not sitemap_path.exists():
        return ["sitemap.xml was not built"]
    sitemap = sitemap_path.read_text(encoding="utf-8")

    by_country: dict[str, list[dict]] = {}
    for _slug, data in iter_published(PUBLISHED_DIR):
        by_country.setdefault(data.get("country", DEFAULT_COUNTRY), []).append(data)

    for slug, key in _filters():
        if slug.startswith("!missing:"):
            failures.append(
                f"{slug.split(':', 1)[1]} is absent from site/src/config.ts or no longer "
                f"matches the expected literal shape — this check cannot see it"
            )
            continue
        for country, venues in by_country.items():
            if not any(_has(v, key) for v in venues):
                continue
            # AU's filters keep their short top-level slugs; every other
            # country's live under its own branch of /places/ (Gate 16).
            path = f"/{slug}/" if country == DEFAULT_COUNTRY else place_path(country, slug)
            if not (dist / path.strip("/") / "index.html").exists():
                failures.append(
                    f"{country}: '{slug}' has published venues but {path} was not built"
                )
            elif path not in sitemap:
                failures.append(f"{country}: {path} was built but is not in sitemap.xml")
    return failures


# --------------------------------------------------------------------------
# 11. Abbreviation cleanup
# --------------------------------------------------------------------------
def _notation_pattern() -> re.Pattern[str]:
    """Two or more amenity short codes joined by the notation separator.

    A single "SA" is ordinary text — it is also South Australia — so only the
    joined form is banned, which is what Gate 6 actually removed. Codes are read
    from config.ts rather than hardcoded, so a renamed code is still caught.
    """
    codes = config_ts.amenity_notation_shorts()
    alt = "|".join(re.escape(c) for c in codes)
    return re.compile(rf"\b(?:{alt})\b\s*·\s*\b(?:{alt})\b")


def check_abbreviations(dist: Path) -> list[str]:
    """The cryptic notation must not reach rendered output or component source.

    Full-word labels ("Magnesium pool") and pool-type shorts ("Indoor") are
    fine — only the Mg · IR · SA · CP · LED string Gate 6 removed is banned.
    """
    failures: list[str] = []
    codes = config_ts.amenity_notation_shorts()
    if not codes:
        return ["AMENITY_NOTATION short codes could not be read from site/src/config.ts"]

    pattern = _notation_pattern()
    for page in sorted(dist.rglob("*.html")):
        hit = pattern.search(page.read_text(encoding="utf-8"))
        if hit:
            failures.append(f"built /{page.relative_to(dist).parent}/ renders '{hit.group(0)}'")

    from admin.config import ROOT

    for rel in SRC_DIRS:
        for src in sorted((ROOT / rel).rglob("*")):
            if src.suffix not in (".astro", ".ts", ".tsx"):
                continue
            hit = pattern.search(src.read_text(encoding="utf-8"))
            if hit:
                failures.append(f"{src.relative_to(ROOT)} contains '{hit.group(0)}'")
    return failures


def run(dist: Path = SITE_DIST_DIR) -> list[str]:
    if not dist.exists():
        return [f"no build at {dist} — run `cd site && npm run build` first"]
    return (
        check_claim_noindex(dist)
        + check_route_coverage(dist)
        + check_abbreviations(dist)
    )


# --------------------------------------------------------------------------
def _self_test() -> int:
    """Each check must fire against a corrupted copy of the real build and stay
    quiet against the real one. A check that only ever passes is
    indistinguishable from one that checks nothing."""
    import shutil
    import tempfile

    problems: list[str] = []

    def report(label: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            problems.append(label)

    if not SITE_DIST_DIR.exists():
        print("FAIL self-test needs a build — run `cd site && npm run build` first")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(SITE_DIST_DIR, dist)
        report("a clean build passes", not run(dist))

        # 8a — a claim page loses its noindex
        claim = next(dist.glob("claim/*/index.html"))
        original = claim.read_text(encoding="utf-8")
        claim.write_text(original.replace(NOINDEX, ""), encoding="utf-8")
        report("a claim page missing noindex is caught",
               any("missing its noindex" in f for f in check_claim_noindex(dist)))
        claim.write_text(original, encoding="utf-8")

        # 8b — noindex escapes onto a real page
        home = dist / "index.html"
        home_original = home.read_text(encoding="utf-8")
        home.write_text(home_original.replace("<head>", f"<head>{NOINDEX}", 1), encoding="utf-8")
        report("noindex on a non-claim page is caught",
               any("not a claim page" in f for f in check_claim_noindex(dist)))
        home.write_text(home_original, encoding="utf-8")

        # 9a — a filter page with published venues disappears
        built = [s for s, k in _filters() if (dist / s / "index.html").exists()]
        if not built:
            report("a national filter page exists to remove", False)
        else:
            victim = dist / built[0]
            shutil.rmtree(victim)
            report("a missing national filter page is caught",
                   any("was not built" in f for f in check_route_coverage(dist)))
            shutil.copytree(SITE_DIST_DIR / built[0], victim)

        # 9b — a built page drops out of the sitemap
        sitemap = dist / "sitemap.xml"
        sm_original = sitemap.read_text(encoding="utf-8")
        if built:
            sitemap.write_text(sm_original.replace(f"/{built[0]}/", "/gone/"), encoding="utf-8")
            report("a built page absent from sitemap.xml is caught",
                   any("not in sitemap.xml" in f for f in check_route_coverage(dist)))
            sitemap.write_text(sm_original, encoding="utf-8")

        # 11 — the notation string reaches a rendered page
        codes = config_ts.amenity_notation_shorts()
        home.write_text(
            home_original.replace("<body", f"<body data-x='{codes[0]} · {codes[1]}'", 1),
            encoding="utf-8",
        )
        report("the amenity notation rendered in output is caught",
               any("renders" in f for f in check_abbreviations(dist)))
        home.write_text(home_original, encoding="utf-8")

        report("the build is clean again after every repair", not run(dist))

    print(f"discoverability self-test: {len(problems)} problem(s)")
    return 1 if problems else 0


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    failures = run()
    for line in failures:
        print(f"FAIL {line}")
    print(f"discoverability: {len(failures)} problem(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
