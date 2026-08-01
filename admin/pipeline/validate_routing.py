"""Routing hygiene check (Editorial Gate E3, 2026-08-01). Runs after
`npm run build`, folded into /validate as check 20. Two assertions on the built
site:

- No internal ``<a href>`` emits a query-param URL. Gate E3 pointed the homepage
  and corner-menu chooser links at static national routes (amenity and
  pool-setting pages) so crawlers never discover the client-only
  ``/?amenities=`` / ``/?pooltype=`` filter space; this proves none crept back.
  External links (``https://…?utm=…``) are out of scope — only site-internal
  hrefs are checked.
- The homepage canonicalises to the apex root ``/``. The client filter writes
  query-string history state onto the homepage; every such variant must fold
  back to ``/`` for crawlers, so the emitted ``<link rel="canonical">`` must be
  the bare root with no query or fragment.

``run(dist)`` returns failure strings; empty = pass. ``_selftest`` proves both
checks fire against a corrupted fixture (the "fails on a corrupted fixture"
rule the E-track validation additions require).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from admin.config import ROOT

DIST = ROOT / "site" / "dist"

_HREF_RE = re.compile(r'<a\b[^>]*\bhref="([^"]*)"', re.I)
_CANONICAL_RE = re.compile(r'<link\b[^>]*\brel="canonical"[^>]*\bhref="([^"]*)"', re.I)


def _is_internal(href: str) -> bool:
    """External and non-navigational schemes may legitimately carry a query
    string (analytics, share intents); only site-internal targets are in scope."""
    return not href.startswith(("http://", "https://", "//", "mailto:", "tel:", "data:"))


def queryparam_links(html: str) -> list[str]:
    """Internal hrefs carrying a query string (the closed /?param space)."""
    return [href for href in _HREF_RE.findall(html) if _is_internal(href) and "?" in href]


def canonical_issue(html: str) -> str | None:
    """None when the canonical is the apex root '/'; else a failure string."""
    m = _CANONICAL_RE.search(html)
    if not m:
        return 'homepage has no <link rel="canonical">'
    href = m.group(1)
    parsed = urlparse(href)
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        return f"homepage canonical is not the apex root '/': {href!r}"
    return None


def check_no_queryparam_links(dist: Path) -> list[str]:
    errors: list[str] = []
    for page in sorted(dist.rglob("*.html")):
        for href in queryparam_links(page.read_text(encoding="utf-8")):
            errors.append(f"{page.relative_to(dist)}: internal link emits a query-param URL: {href!r}")
    return errors


def check_homepage_canonical(dist: Path) -> list[str]:
    home = dist / "index.html"
    if not home.exists():
        return ["dist/index.html missing — run `npm run build` first"]
    issue = canonical_issue(home.read_text(encoding="utf-8"))
    return [issue] if issue else []


def run(dist: Path = DIST) -> list[str]:
    if not dist.exists():
        return [f"{dist} missing — run `npm run build` first"]
    return check_no_queryparam_links(dist) + check_homepage_canonical(dist)


def _selftest() -> list[str]:
    """Both checks must catch a deliberately corrupted fixture and pass a clean one."""
    failures: list[str] = []
    if not queryparam_links('<a href="/?amenities=cold_plunge#results-heading">x</a>'):
        failures.append("selftest: query-param scanner missed an internal ?param href")
    clean = '<a href="/cold-plunge/">a</a><a href="https://x.example/?utm=1">e</a><a href="#top">t</a>'
    if queryparam_links(clean):
        failures.append(f"selftest: query-param scanner false-positived: {queryparam_links(clean)}")
    if not canonical_issue('<link rel="canonical" href="https://wherewebathe.com/?pooltype=indoor">'):
        failures.append("selftest: canonical check missed a query-param homepage canonical")
    if canonical_issue('<link rel="canonical" href="https://wherewebathe.com/">'):
        failures.append("selftest: canonical check false-positived on the apex root")
    return failures


def main() -> int:
    errors = _selftest() + run()
    if errors:
        print("ROUTING HYGIENE FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("routing hygiene OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
