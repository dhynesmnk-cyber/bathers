"""Candidate image harvesting + the separate publish/remove actions (UX.md §4).

Candidates are staging-only: downloaded to temp_data/images/<slug>/ (gitignored)
with a manifest.json of source URLs. Publishing is a distinct reviewer action
that resizes/re-encodes to webp into site/public/images/ and writes the
image/image_source/image_caption frontmatter fields — never automatic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image

from admin.config import IMAGES_DIR, SITE_IMAGES_DIR

MAX_CANDIDATES = 5
MAX_DIMENSION = 1600
FETCH_TIMEOUT = 20.0
USER_AGENT = "BathersDirectoryBot/1.0 (local admin tool; contact via venue's own listing)"

_SKIP_HINTS = ("logo", "icon", "sprite", "favicon", "avatar", "pixel.gif", "1x1")


class _ImgTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attr_map = dict(attrs)
        src = attr_map.get("src")
        if src:
            self.srcs.append(src)


@dataclass
class Candidate:
    index: int
    filename: str
    source_url: str


def discover_image_urls(html: str, base_url: str) -> list[str]:
    parser = _ImgTagParser()
    parser.feed(html)
    seen: set[str] = set()
    urls: list[str] = []
    for src in parser.srcs:
        if any(hint in src.lower() for hint in _SKIP_HINTS):
            continue
        absolute = urljoin(base_url, src)
        if absolute in seen:
            continue
        seen.add(absolute)
        urls.append(absolute)
    return urls


def download_candidates(urls: list[str], slug: str) -> list[Candidate]:
    slug_dir = IMAGES_DIR / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[Candidate] = []
    for url in urls:
        if len(candidates) >= MAX_CANDIDATES:
            break
        try:
            response = httpx.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                continue
            ext = content_type.split("/")[-1].split(";")[0] or "jpg"
            index = len(candidates)
            filename = f"{index}.{ext}"
            (slug_dir / filename).write_bytes(response.content)
            candidates.append(Candidate(index=index, filename=filename, source_url=url))
        except httpx.HTTPError:
            continue
    manifest = {"slug": slug, "candidates": [c.__dict__ for c in candidates]}
    (slug_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return candidates


def list_candidates(slug: str) -> list[Candidate]:
    manifest_path = IMAGES_DIR / slug / "manifest.json"
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [Candidate(**c) for c in data.get("candidates", [])]


def publish_image(slug: str, candidate_index: int, caption: str) -> dict[str, str]:
    """Resize/re-encode the chosen candidate to webp in site/public/images/,
    return the frontmatter fields to merge in (UX.md §4.3)."""
    candidates = {c.index: c for c in list_candidates(slug)}
    candidate = candidates.get(candidate_index)
    if candidate is None:
        raise FileNotFoundError(f"no candidate {candidate_index} for {slug}")

    source_path = IMAGES_DIR / slug / candidate.filename
    SITE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = SITE_IMAGES_DIR / f"{slug}.webp"

    with Image.open(source_path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        im.save(dest_path, "WEBP", quality=82)

    return {
        "image": f"/images/{slug}.webp",
        "image_source": candidate.source_url,
        "image_caption": caption,
    }


def remove_image(slug: str) -> None:
    dest_path = SITE_IMAGES_DIR / f"{slug}.webp"
    dest_path.unlink(missing_ok=True)
