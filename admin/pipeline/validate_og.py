"""Open Graph share-image integrity (Editorial Gate E4b, 2026-08-01). Check 22.

Two assertions:

- After ``npm run build``, every venue (``spa/*``) and article (``blog/*``) page
  emits a *page-specific* ``og:image`` — a real venue photo / blog cover, or its
  generated ``/og/<slug>.png`` card, never the generic sitewide default — that
  resolves to a built file, with a non-empty ``og:image:alt``. This is what makes
  a shared link show something real about that page rather than a stock banner.
- A blog post whose cover image is AI-generated (``cover_image_ai``) carries a
  ``cover_image_credit`` (also enforced by the zod schema; asserted here
  independently so the build gate proves it, and self-tested on a fixture).

``run(dist)`` returns failure strings; empty = pass. ``_selftest`` proves both
checks fire against corrupted fixtures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from admin.config import BLOG_PUBLISHED_DIR, ROOT

DIST = ROOT / "site" / "dist"
DEFAULT_OG = "/images/og-share.webp"  # BaseLayout's sitewide fallback share image

_OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]*)"')
_OG_ALT_RE = re.compile(r'<meta property="og:image:alt" content="([^"]*)"')


def og_meta(html: str) -> tuple[str | None, str | None]:
    img = _OG_IMAGE_RE.search(html)
    alt = _OG_ALT_RE.search(html)
    return (img.group(1) if img else None), (alt.group(1) if alt else None)


def _url_path(url: str) -> str:
    """The site-relative path of an og:image URL (drop scheme+host)."""
    return re.sub(r"^https?://[^/]+", "", url)


def evaluate_page(name: str, img: str | None, alt: str | None, resolves: bool) -> list[str]:
    """Testable core: the issues for one page's og:image/alt pair. `resolves` is
    whether the image path exists in the build."""
    issues: list[str] = []
    if not img:
        return [f"{name}: no og:image"]
    if _url_path(img) == DEFAULT_OG:
        issues.append(f"{name}: og:image is the generic default, not page-specific ({DEFAULT_OG})")
    elif not resolves:
        issues.append(f"{name}: og:image does not resolve to a built file ({img})")
    if not (alt and alt.strip()):
        issues.append(f"{name}: og:image:alt is empty")
    return issues


def check_pages(dist: Path = DIST) -> list[str]:
    errors: list[str] = []
    for kind in ("spa", "blog"):
        for page in sorted((dist / kind).glob("*/index.html")):
            img, alt = og_meta(page.read_text(encoding="utf-8"))
            resolves = bool(img) and (dist / _url_path(img).lstrip("/")).exists()
            errors += evaluate_page(f"{kind}/{page.parent.name}", img, alt, resolves)
    return errors


def ai_cover_issue(fm: dict) -> str | None:
    """A post flagged as an AI cover must attribute it (also a zod rule)."""
    if fm.get("cover_image_ai") and not fm.get("cover_image_credit"):
        return "cover_image_ai without cover_image_credit — AI imagery must be attributed"
    return None


def _split_frontmatter(text: str) -> dict:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            return fm if isinstance(fm, dict) else {}
    return {}


def check_ai_covers(blog_dir: Path = BLOG_PUBLISHED_DIR) -> list[str]:
    errors: list[str] = []
    for path in sorted(blog_dir.glob("*.mdx")):
        issue = ai_cover_issue(_split_frontmatter(path.read_text(encoding="utf-8")))
        if issue:
            errors.append(f"blog/{path.stem}: {issue}")
    return errors


def run(dist: Path = DIST) -> list[str]:
    if not dist.exists():
        return [f"{dist} missing — run `npm run build` first"]
    return check_pages(dist) + check_ai_covers()


def _selftest() -> list[str]:
    """Both checks must catch a corrupted fixture and pass a clean one."""
    failures: list[str] = []
    # page check: default og, unresolved card, and missing alt each fire
    if not evaluate_page("x", f"https://h{DEFAULT_OG}", "alt", True):
        failures.append("selftest: page check missed the generic-default og:image")
    if not evaluate_page("x", "/og/missing.png", "alt", False):
        failures.append("selftest: page check missed an unresolved og:image")
    if not evaluate_page("x", "/og/ok.png", "", True):
        failures.append("selftest: page check missed an empty og:image:alt")
    if evaluate_page("x", "/og/ok.png", "A real card", True):
        failures.append("selftest: page check false-positived on a valid page-specific card")
    # ai cover: flag without credit fires; with credit passes
    if not ai_cover_issue({"cover_image_ai": True}):
        failures.append("selftest: AI-cover check missed a flagged cover with no credit")
    if ai_cover_issue({"cover_image_ai": True, "cover_image_credit": "Generated with X"}):
        failures.append("selftest: AI-cover check false-positived on an attributed AI cover")
    return failures


def main() -> int:
    errors = _selftest() + run()
    if errors:
        print("OG IMAGE INTEGRITY FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OG image integrity OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
