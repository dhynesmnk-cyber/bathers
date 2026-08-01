"""Open Graph share cards (Editorial Gate E4b, 2026-08-01).

Programmatic 1200x630 share images so every venue/article page has a controlled,
on-brand preview instead of a generic default. Rendered by screenshotting a small
HTML/CSS template through the existing Playwright/chromium (the harvest fallback,
TRD.md §2) — chosen over Pillow because the brand fonts ship only as woff2, which
Pillow can't load; a browser renders them natively at full fidelity, with the
exact DESIGN.md palette and no new dependency.

Cards are a *fallback*: a venue with a published photo, or a blog post with a
cover image, keeps that real image as its og:image; only pages that would
otherwise fall back to the generic default get a card. Output lands in
site/public/og/<slug>.png (committed, served by Netlify, deployed via the
deploy.py allow-list). Regeneration is idempotent for a given content state.

Run: python3 -m admin.pipeline.og_cards --all   (or --venue SLUG / --article SLUG)
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

from admin.config import (
    BLOG_PUBLISHED_DIR,
    OG_CARDS_DIR,
    SITE_FONTS_DIR,
    VENUES_JSON_PATH,
)

# DESIGN.md light palette (OG cards read as the warm paper card in a feed).
PAPER = "#f2ece0"
PAPER_RAISED = "#e9e1d1"
INK = "#2a241e"
INK_FADED = "#6b6255"
THERMAL = "#3f6b5b"

WIDTH, HEIGHT = 1200, 630

# Human-facing category labels (kebab slug -> words). Unknown slugs fall back to
# a title-cased form so a new category never renders as a raw slug.
_CATEGORY_LABELS = {
    "bathhouse": "Bathhouse",
    "day_spa": "Day spa",
    "hot_springs": "Hot springs",
    "thermal_springs": "Thermal springs",
    "sauna": "Sauna",
    "hotel_spa": "Hotel spa",
    "float_centre": "Float centre",
}


def _font_face(family: str, filename: str, weight: str) -> str:
    data = (SITE_FONTS_DIR / filename).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return (
        f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
    )


def _fonts_css() -> str:
    # Fraunces (variable) for the display title; IBM Plex Mono for eyebrow/meta.
    return (
        _font_face("Fraunces", "fraunces-variable.woff2", "100 900")
        + _font_face("IBM Plex Mono", "ibm-plex-mono-500.woff2", "500")
    )


def _card_html(eyebrow: str, title: str, meta: str) -> str:
    e, t, m = html.escape(eyebrow), html.escape(title), html.escape(meta)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{_fonts_css()}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;}}
body{{background:{PAPER};color:{INK};
  font-family:'IBM Plex Mono',monospace;-webkit-font-smoothing:antialiased;}}
.frame{{position:absolute;inset:28px;border:1px solid {INK_FADED};}}
.pad{{position:absolute;inset:80px;display:flex;flex-direction:column;justify-content:space-between;}}
.eyebrow{{font-family:'IBM Plex Mono',monospace;font-weight:500;font-size:24px;
  letter-spacing:0.22em;text-transform:uppercase;color:{INK_FADED};display:flex;align-items:center;gap:18px;}}
.tick{{width:16px;height:16px;background:{THERMAL};display:inline-block;}}
.title{{font-family:'Fraunces',serif;font-weight:560;font-size:82px;line-height:1.04;
  letter-spacing:-0.01em;max-width:1000px;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}}
.meta{{font-family:'IBM Plex Mono',monospace;font-weight:500;font-size:26px;
  letter-spacing:0.08em;text-transform:uppercase;color:{INK_FADED};
  border-top:1px solid {INK_FADED};padding-top:22px;}}
</style></head><body>
<div class="frame"></div>
<div class="pad">
  <div class="eyebrow"><span class="tick"></span> {e}</div>
  <div class="title">{t}</div>
  <div class="meta">{m}</div>
</div></body></html>"""


def _category_label(slug: str | None) -> str:
    if not slug:
        return "Bathing"
    return _CATEGORY_LABELS.get(slug, slug.replace("_", " ").title())


# ---- Card specs (what each page's card says) --------------------------------

def _venue_card_spec(v: dict[str, Any]) -> dict[str, str]:
    where = " · ".join(x for x in (v.get("suburb"), (v.get("state") or "").upper()) if x)
    return {
        "eyebrow": "WHERE WE BATHE",
        "title": v.get("name") or v.get("slug", ""),
        "meta": " · ".join(x for x in (where, _category_label(v.get("category")).upper()) if x),
    }


def _article_card_spec(fm: dict[str, Any], meta_entry: dict[str, Any] | None) -> dict[str, str]:
    if meta_entry:  # comparison article — say what it compares and how many
        count = meta_entry.get("venue_count")
        tail = f"{count} VENUES COMPARED" if count else "COMPARISON"
        sub = f"COMPARISON · {tail}"
    else:  # essay
        sub = "FROM THE BLOG"
    return {"eyebrow": "WHERE WE BATHE", "title": fm.get("title", ""), "meta": sub}


# ---- Rendering --------------------------------------------------------------

def _split_frontmatter(text: str) -> dict[str, Any]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            return fm if isinstance(fm, dict) else {}
    return {}


def _load_venues() -> list[dict[str, Any]]:
    try:
        return json.loads(VENUES_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def _load_article_meta() -> dict[str, Any]:
    from admin.config import ARTICLES_META_JSON_PATH
    try:
        return json.loads(ARTICLES_META_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def needed_cards() -> list[tuple[str, dict[str, str]]]:
    """(slug, spec) for every page that lacks a real image and so needs a card:
    venues with no published `image`, and blog posts with no `cover_image`."""
    out: list[tuple[str, dict[str, str]]] = []
    for v in _load_venues():
        # venues.json carries `has_image` (bool), not the image path — a card is
        # the fallback only where the venue has no published photo.
        if not v.get("has_image"):
            out.append((v["slug"], _venue_card_spec(v)))
    meta = _load_article_meta()
    for path in sorted(BLOG_PUBLISHED_DIR.glob("*.mdx")):
        fm = _split_frontmatter(path.read_text(encoding="utf-8"))
        if fm.get("cover_image"):
            continue
        out.append((path.stem, _article_card_spec(fm, meta.get(fm.get("query_key")))))
    return out


def _render_many(specs: Iterable[tuple[str, dict[str, str]]]) -> list[str]:
    """Render each (slug, spec) to site/public/og/<slug>.png. One browser for the
    batch. Returns the slugs written."""
    from playwright.sync_api import sync_playwright

    OG_CARDS_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    specs = list(specs)
    if not specs:
        return written
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        try:
            for slug, spec in specs:
                page.set_content(_card_html(**spec), wait_until="networkidle")
                page.evaluate("document.fonts.ready")
                (OG_CARDS_DIR / f"{slug}.png").write_bytes(page.screenshot(type="png"))
                written.append(slug)
        finally:
            browser.close()
    return written


def generate_all() -> list[str]:
    """Regenerate every needed card and prune cards for slugs that no longer need
    one (a venue that gained a photo). Returns the slugs written."""
    needed = needed_cards()
    written = _render_many(needed)
    keep = {f"{slug}.png" for slug, _ in needed}
    if OG_CARDS_DIR.exists():
        for stale in OG_CARDS_DIR.glob("*.png"):
            if stale.name not in keep:
                stale.unlink()
    return written


def generate_slugs(slugs: list[str]) -> list[str]:
    lookup = dict(needed_cards())
    specs = [(s, lookup[s]) for s in slugs if s in lookup]
    return _render_many(specs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Open Graph share cards (Gate E4b).")
    parser.add_argument("--all", action="store_true", help="regenerate every needed card (and prune stale)")
    parser.add_argument("--slug", action="append", default=[], help="regenerate a specific slug (repeatable)")
    args = parser.parse_args()
    if args.slug:
        written = generate_slugs(args.slug)
    elif args.all:
        written = generate_all()
    else:
        needed = needed_cards()
        print(f"{len(needed)} card(s) needed: {', '.join(s for s, _ in needed)}")
        return 0
    print(f"wrote {len(written)} card(s) to {OG_CARDS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
