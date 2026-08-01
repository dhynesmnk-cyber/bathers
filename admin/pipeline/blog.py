"""Blog authoring primitives (2026-07-21 addition, SCHEMA.md §7). Mirrors the
venue staging/published split in pipeline.staging as closely as possible:
drafts live in content-staging/_blog_staging until a deliberate Publish
action moves them into site/src/content/blog/_published.

Unlike venues, posts are hand-authored (no AI pipeline, no reject/undo), so
this module is a smaller subset: create/list/read/update/delete a draft,
and publish. "Update" works on a post wherever it currently lives (staging
or already-published), since the admin needs to edit posts after they go
live, not just before.

Body is Quill-authored HTML, stored directly as the MDX body (MDX renders
inline HTML fine).

Images inserted mid-draft are saved to a per-slug temp directory (gitignored,
mirrors pipeline.images' candidate-image staging) and served back to the
Quill editor from there; Publish is the point at which they're converted to
webp and moved into site/public/blog-images — mirroring how a venue's hero
image is only written into site/public/images on its own deliberate publish
action (UX.md §4). Images added while editing an *already-published* post
skip the temp step entirely and are converted straight to the public
directory, since there's no publish gate left to cross.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from PIL import Image

from admin.config import BLOG_IMAGES_TEMP_DIR, BLOG_PUBLISHED_DIR, BLOG_STAGING_DIR, SITE_BLOG_IMAGES_DIR

FRONTMATTER_FIELD_ORDER = (
    "title", "dateline", "summary", "cover_image",
    # Cover-image provenance (Gate E4b) — kept in frontmatter so a post's
    # generated/attributed header travels with the content, editable in admin.
    "cover_image_alt", "cover_image_ai", "cover_image_credit",
    "cover_image_license", "cover_image_source",
    "video_url",
)
MAX_DIMENSION = 1600

# Published posts that are site furniture — linked from the footer/nav (mission,
# about, methodology-style pages), not ordinary journal entries. Unpublishing one
# leaves a dead navigation link, so the admin warns (never blocks) first.
PROTECTED_SLUGS = frozenset(
    {
        "our-mission",
        "what-we-stand-for",
        "on-being-present",
        "why-we-love-to-bathe",
        "a-calm-directory-for-calm-experiences",
        "a-dream-of-bathing-in-switzerland",
    }
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# MDX parses the body as JSX, which requires void elements to be
# self-closing (`<img />`, not `<img>`) — Quill emits plain HTML, so every
# body write needs this normalisation or the Astro build fails.
_VOID_TAG_RE = re.compile(r"<(img|br|hr|input)((?:[^>]*[^/>])?)>", re.IGNORECASE)


def _mdx_safe_html(html: str) -> str:
    return _VOID_TAG_RE.sub(lambda m: f"<{m.group(1)}{m.group(2)} />", html)

Location = Literal["draft", "published"]


class ValidationFailed(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("blog post failed validation")


@dataclass
class BlogEntry:
    slug: str
    frontmatter: dict[str, Any]
    body: str
    saved_at: float


def slugify(title: str) -> str:
    base = _SLUG_RE.sub("-", title.strip().lower()).strip("-") or "post"
    slug = base
    n = 2
    while (BLOG_STAGING_DIR / f"{slug}.mdx").exists() or (BLOG_PUBLISHED_DIR / f"{slug}.mdx").exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError("missing frontmatter delimiter")
    _, fm_yaml, body = text.split("---", 2)
    data = yaml.safe_load(fm_yaml) or {}
    return data, body.strip("\n")


def _render_frontmatter(data: dict[str, Any]) -> str:
    ordered = {key: data[key] for key in FRONTMATTER_FIELD_ORDER if key in data and data[key] not in (None, "")}
    return yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _render_mdx(data: dict[str, Any], body: str) -> str:
    return f"---\n{_render_frontmatter(data)}---\n\n{body.strip()}\n"


def _entry_from_path(path: Path) -> BlogEntry:
    text = path.read_text(encoding="utf-8")
    data, body = _split_frontmatter(text)
    return BlogEntry(slug=path.stem, frontmatter=data, body=body, saved_at=path.stat().st_mtime)


def _location(slug: str) -> Location | None:
    if (BLOG_STAGING_DIR / f"{slug}.mdx").exists():
        return "draft"
    if (BLOG_PUBLISHED_DIR / f"{slug}.mdx").exists():
        return "published"
    return None


def _path_for(slug: str, location: Location) -> Path:
    return (BLOG_STAGING_DIR if location == "draft" else BLOG_PUBLISHED_DIR) / f"{slug}.mdx"


def list_all() -> list[tuple[BlogEntry, Location]]:
    BLOG_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    BLOG_PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[BlogEntry, Location]] = [
        (_entry_from_path(p), "draft")
        for p in sorted(BLOG_STAGING_DIR.glob("*.mdx"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]
    entries += [
        (_entry_from_path(p), "published")
        for p in sorted(BLOG_PUBLISHED_DIR.glob("*.mdx"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]
    return entries


def get(slug: str) -> tuple[BlogEntry, Location]:
    location = _location(slug)
    if location is None:
        raise FileNotFoundError(slug)
    return _entry_from_path(_path_for(slug, location)), location


def create_draft(title: str) -> BlogEntry:
    if not title.strip():
        raise ValidationFailed(["title is required"])
    BLOG_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    data = {"title": title.strip(), "dateline": date.today(), "summary": ""}
    path = BLOG_STAGING_DIR / f"{slug}.mdx"
    path.write_text(_render_mdx(data, ""), encoding="utf-8")
    return _entry_from_path(path)


def update(slug: str, patch: dict[str, Any]) -> tuple[BlogEntry, Location]:
    location = _location(slug)
    if location is None:
        raise FileNotFoundError(slug)
    path = _path_for(slug, location)
    data, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    if "body" in patch:
        body = _mdx_safe_html(patch.pop("body"))
    data.update(patch)
    path.write_text(_render_mdx(data, body), encoding="utf-8")
    return _entry_from_path(path), location


def _delete_draft_files(slug: str) -> None:
    """Remove a draft's staging MDX and its gitignored temp image directory."""
    (BLOG_STAGING_DIR / f"{slug}.mdx").unlink()
    image_dir = draft_image_dir(slug)
    if image_dir.exists():
        for f in image_dir.iterdir():
            f.unlink()
        image_dir.rmdir()


def delete_draft(slug: str) -> None:
    """Delete a draft (staging only). Kept for callers that specifically mean a
    draft; delete() handles a post in either location."""
    if not (BLOG_STAGING_DIR / f"{slug}.mdx").exists():
        raise FileNotFoundError(slug)
    _delete_draft_files(slug)


def delete(slug: str) -> Location:
    """Permanently delete a post from wherever it lives (2026-08-02). A draft's
    staging MDX (and its temp images) are removed; a published post's committed
    MDX is removed so the deletion rides the next deploy off the live site (its
    public /blog-images/ files are left in place, harmless, mirroring unpublish).
    Unlike unpublish this is NOT recoverable — the file is gone. Returns the
    location deleted from so the caller can decide whether to deploy."""
    location = _location(slug)
    if location is None:
        raise FileNotFoundError(slug)
    if location == "draft":
        _delete_draft_files(slug)
    else:
        (BLOG_PUBLISHED_DIR / f"{slug}.mdx").unlink()
    return location


# ---- Draft images (temp, gitignored — mirrors pipeline.images candidates) ----


def draft_image_dir(slug: str) -> Path:
    return BLOG_IMAGES_TEMP_DIR / slug


def draft_image_url(slug: str, index: int) -> str:
    return f"/api/blog/{slug}/images/{index}/file"


def draft_image_path(slug: str, index: int) -> Path | None:
    matches = list(draft_image_dir(slug).glob(f"{index}.*"))
    return matches[0] if matches else None


def _save_draft_image(slug: str, data: bytes, ext: str) -> dict[str, Any]:
    image_dir = draft_image_dir(slug)
    image_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(int(p.stem) for p in image_dir.glob("*.*") if p.stem.isdigit())
    index = (existing[-1] + 1) if existing else 0
    (image_dir / f"{index}.{ext}").write_bytes(data)
    return {"url": draft_image_url(slug, index)}


def _save_published_image(slug: str, data: bytes) -> dict[str, Any]:
    SITE_BLOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(
        int(p.stem.rsplit("-", 1)[-1])
        for p in SITE_BLOG_IMAGES_DIR.glob(f"{slug}-*.webp")
        if p.stem.rsplit("-", 1)[-1].isdigit()
    )
    index = (existing[-1] + 1) if existing else 0
    dest = SITE_BLOG_IMAGES_DIR / f"{slug}-{index}.webp"
    _write_webp(data, dest)
    return {"url": f"/blog-images/{slug}-{index}.webp"}


def _write_webp(data: bytes, dest: Path) -> None:
    import io

    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        im.save(dest, "WEBP", quality=82)


def save_image(slug: str, data: bytes, content_type: str) -> dict[str, Any]:
    ext = content_type.split("/")[-1].split(";")[0] or "jpg"
    if ext not in ("jpeg", "jpg", "png", "webp", "gif"):
        raise ValidationFailed([f"unsupported image type '{content_type}'"])
    location = _location(slug)
    if location is None:
        raise FileNotFoundError(slug)
    if location == "published":
        return _save_published_image(slug, data)
    return _save_draft_image(slug, data, ext)


# ---- Publish (drafts only) ----

_DRAFT_IMG_SRC_RE = re.compile(r"/api/blog/([a-z0-9-]+)/images/(\d+)/file")


def _publish_images(slug: str, text: str) -> str:
    """Replace every draft-image URL reference in `text` (body HTML or a
    single frontmatter string like cover_image) with its published webp
    URL, converting+moving each referenced file exactly once."""
    converted: dict[int, str] = {}

    def _replace(match: re.Match) -> str:
        index = int(match.group(2))
        if index not in converted:
            source_path = draft_image_path(slug, index)
            if source_path is None:
                return match.group(0)
            SITE_BLOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            dest_path = SITE_BLOG_IMAGES_DIR / f"{slug}-{index}.webp"
            _write_webp(source_path.read_bytes(), dest_path)
            converted[index] = f"/blog-images/{slug}-{index}.webp"
        return converted[index]

    return _DRAFT_IMG_SRC_RE.sub(_replace, text)


def publish(slug: str) -> None:
    path = BLOG_STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    data, body = _split_frontmatter(path.read_text(encoding="utf-8"))

    errors = []
    if not data.get("title"):
        errors.append("title is required")
    if not data.get("summary"):
        errors.append("summary is required")
    if not data.get("dateline"):
        errors.append("dateline is required")
    if errors:
        raise ValidationFailed(errors)

    body = _publish_images(slug, body)
    if data.get("cover_image"):
        data["cover_image"] = _publish_images(slug, data["cover_image"])

    BLOG_PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    dest = BLOG_PUBLISHED_DIR / f"{slug}.mdx"
    dest.write_text(_render_mdx(data, body), encoding="utf-8")
    path.unlink()

    image_dir = draft_image_dir(slug)
    if image_dir.exists():
        for f in image_dir.iterdir():
            f.unlink()
        image_dir.rmdir()


def unpublish(slug: str) -> None:
    """Take a published post off the live site, recoverably (2026-08-01 admin-UX
    change). The MDX moves back to _blog_staging so it can be fixed and
    re-published; the deploy strip carries the _published deletion to Netlify on
    the next push. Public images under site/public/blog-images/ are left in place
    — harmless while unpublished and re-used verbatim on re-publish, since the
    body already references their /blog-images/ URLs (a re-publish only rewrites
    fresh /api/blog/ draft refs)."""
    path = BLOG_PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    BLOG_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    dest = BLOG_STAGING_DIR / f"{slug}.mdx"
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.unlink()
