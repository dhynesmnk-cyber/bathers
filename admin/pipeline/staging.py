"""Review-queue primitives: list/read/update staging entries, reject, approve
and undo. Frontmatter is the canonical source (CLAUDE.md); this module never
writes to `_published` except via `approve`, and never touches the DB/JSON
directly — it always goes through `data_store.rebuild()` so the derived
artefacts stay a full-rebuild-from-published (TRD.md §5), consistent with
how Gate 2 already guarantees idempotency.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from admin.config import DELETED_DIR, PUBLISHED_DIR, REJECTED_DIR, SITE_IMAGES_DIR, STAGING_DIR
from admin.pipeline import data_store, forewords, images, places
from admin.schema import FieldError, count_prose_words, staging_status, validate_frontmatter

FRONTMATTER_FIELD_ORDER = (
    "name", "state", "category", "suburb", "address", "latitude", "longitude", "website",
    "amenities", "facilities", "hours", "cost", "access", "status", "summary", "drafted", "verified", "source_url",
    "image", "image_source", "image_caption", "faq",
)
AMENITY_FIELD_ORDER = (
    "magnesium_pool", "infrared_sauna", "traditional_sauna", "cold_plunge", "led_therapy",
)
FACILITY_FIELD_ORDER = (
    "parking", "towels_provided", "changerooms", "bookings_required", "wheelchair_access",
    "outdoor_pool", "indoor_pool", "natural_spring",
)

UNDO_WINDOW_SECONDS = 10  # client shows a 3s undo affordance; server keeps a wider grace window


class ValidationFailed(Exception):
    def __init__(self, errors: list[FieldError]):
        self.errors = errors
        super().__init__("frontmatter failed schema validation")


class UndoExpired(Exception):
    pass


@dataclass
class StagingEntry:
    slug: str
    frontmatter: dict[str, Any]
    body: str
    errors: list[FieldError]
    word_count: int
    status: str
    saved_at: float


@dataclass
class _UndoRecord:
    staged_text: str
    previous_published_text: str | None
    timestamp: float = field(default_factory=time.time)


_UNDO_STORE: dict[str, _UndoRecord] = {}


def split_frontmatter(text: str, slug: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError(f"{slug}: missing frontmatter delimiter")
    _, fm_yaml, body = text.split("---", 2)
    data = yaml.safe_load(fm_yaml) or {}
    return data, body.strip("\n")


def _coerce_date(value: Any) -> Any:
    """Date fields arriving through the JSON PATCH API are strings; safe_dump
    would quote them ('2026-07-23') to preserve the string type, and Astro's
    frontmatter parser then reads a string where the zod schema demands
    z.date() — breaking the site build. Coerce so dates always dump unquoted."""
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return value
    return value


def render_frontmatter(data: dict[str, Any]) -> str:
    ordered: dict[str, Any] = {}
    for key in FRONTMATTER_FIELD_ORDER:
        if key not in data:
            continue
        if key == "amenities" and isinstance(data[key], dict):
            ordered[key] = {ak: data[key].get(ak) for ak in AMENITY_FIELD_ORDER if ak in data[key]}
        elif key == "facilities" and isinstance(data[key], dict):
            ordered[key] = {fk: data[key].get(fk) for fk in FACILITY_FIELD_ORDER if fk in data[key]}
        elif key in ("drafted", "verified"):
            ordered[key] = _coerce_date(data[key])
        else:
            ordered[key] = data[key]
    return yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False)


def render_mdx(data: dict[str, Any], body: str) -> str:
    return f"---\n{render_frontmatter(data)}---\n\n{body.strip()}\n"


# ---- TippedPhoto body tag (UX.md §4.3) ----
#
# publish_image() (images.py) only ever computes frontmatter fields — the
# venue page renders a photo exclusively via a literal <TippedPhoto> tag in
# the MDX body ([slug].astro: `<Content components={{ Pull, TippedPhoto }} />`).
# Setting image/image_source/image_caption alone has no visible effect on the
# built page. These helpers are the other half of "publish": inserting (and,
# on removal, stripping) that tag so the frontmatter and the body never
# disagree about whether a photo exists.

_TIPPED_PHOTO_TAG_RE = re.compile(r"<TippedPhoto\b[^>]*/>")


def _jsx_attr(name: str, value: str) -> str:
    # {} + json.dumps rather than a bare "..." attribute — MDX/JSX string
    # attributes don't support backslash-escaping, so a caption containing a
    # literal `"` would otherwise break the tag. json.dumps produces a valid
    # JS string literal for the {} expression form regardless of content.
    return f"{name}={{{json.dumps(value)}}}"


def _tipped_photo_tag(slug: str, fields: dict[str, Any]) -> str:
    caption = fields["image_caption"]
    attrs = " ".join(
        [
            _jsx_attr("slug", slug),
            _jsx_attr("src", fields["image"]),
            _jsx_attr("alt", caption),
            _jsx_attr("caption", caption),
            _jsx_attr("sourceUrl", fields["image_source"]),
        ]
    )
    return f"<TippedPhoto {attrs} />"


def _strip_tipped_photo(body: str) -> str:
    stripped = _TIPPED_PHOTO_TAG_RE.sub("", body)
    return re.sub(r"\n{3,}", "\n\n", stripped).strip()


def _insert_tipped_photo(body: str, tag: str) -> str:
    """DESIGN.md §7 — "mid-article, never top." Inserts around the middle
    block of the body's paragraphs, never before the first."""
    blocks = [b for b in re.split(r"\n\s*\n", body.strip()) if b.strip()]
    insert_at = max(1, len(blocks) // 2) if len(blocks) > 1 else len(blocks)
    blocks.insert(insert_at, tag)
    return "\n\n".join(blocks)


def _entry_from_path(path: Path) -> StagingEntry:
    text = path.read_text(encoding="utf-8")
    slug = path.stem
    data, body = split_frontmatter(text, slug)
    errors = validate_frontmatter(data)
    word_count = count_prose_words(body)
    has_pending_images = bool(images.list_candidates(slug)) and not data.get("image")
    places_check = places.load_check(slug)
    places_flagged = (
        places_check is not None
        and not places_check.skipped
        and not places_check.found
        and places_check.error is None
    )
    status = staging_status(errors, word_count, has_pending_images, places_flagged)
    return StagingEntry(
        slug=slug,
        frontmatter=data,
        body=body,
        errors=errors,
        word_count=word_count,
        status=status,
        saved_at=path.stat().st_mtime,
    )


def list_staging() -> list[StagingEntry]:
    paths = sorted(STAGING_DIR.glob("*.mdx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [_entry_from_path(p) for p in paths]


# ---- Duplicate detection (2026-07-23) ----
#
# The same venue harvested twice under different slugs produces a second
# listing (it happened: mornington-peninsula-hot-springs duplicated
# peninsula-hot-springs). Matching is on normalised website domain+path and
# normalised name across published venues and other staged drafts. Warn-only
# by design — the reviewer decides; approve is never blocked.


def _normalise_website(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    url = url.strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.rstrip("/")


def _normalise_name(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def find_duplicates(slug: str, frontmatter: dict[str, Any]) -> list[dict[str, str]]:
    """Possible duplicates of the given entry among published venues and
    other staged drafts. Returns [{slug, name, location, reason}]."""
    website = _normalise_website(frontmatter.get("website"))
    name = _normalise_name(frontmatter.get("name"))
    duplicates: list[dict[str, str]] = []
    for location, directory in (("published", PUBLISHED_DIR), ("staged", STAGING_DIR)):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.mdx")):
            if location == "staged" and path.stem == slug:
                continue  # not a duplicate of itself
            if location == "published" and path.stem == slug:
                continue  # re-harvest of the same slug is an update, not a dupe
            try:
                other, _ = split_frontmatter(path.read_text(encoding="utf-8"), path.stem)
            except ValueError:
                continue
            reasons = []
            if website and _normalise_website(other.get("website")) == website:
                reasons.append("same website")
            if name and _normalise_name(other.get("name")) == name:
                reasons.append("same name")
            if reasons:
                duplicates.append(
                    {
                        "slug": path.stem,
                        "name": other.get("name") or path.stem,
                        "location": location,
                        "reason": ", ".join(reasons),
                    }
                )
    return duplicates


def get_staging(slug: str) -> StagingEntry:
    path = STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    return _entry_from_path(path)


def _apply_patch(dir_path: Path, slug: str, patch: dict[str, Any], *, validate: bool) -> StagingEntry:
    path = dir_path / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    data, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
    patch = dict(patch)
    if "body" in patch:
        body = patch.pop("body")
    data.update(patch)
    if validate:
        errors = validate_frontmatter(data)
        if errors:
            raise ValidationFailed(errors)
    path.write_text(render_mdx(data, body), encoding="utf-8")
    return _entry_from_path(path)


def update_staging(slug: str, patch: dict[str, Any]) -> StagingEntry:
    return _apply_patch(STAGING_DIR, slug, patch, validate=False)


def get_published(slug: str) -> StagingEntry:
    path = PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    return _entry_from_path(path)


def update_published(slug: str, patch: dict[str, Any]) -> StagingEntry:
    """General published-venue editing (as opposed to `remove_published_image`'s
    narrow field-removal): validated on every save, unlike staging drafts,
    so `_published/` never holds a file that would fail the schema check
    `approve()` already guarantees on the way in."""
    entry = _apply_patch(PUBLISHED_DIR, slug, patch, validate=True)
    data_store.rebuild()
    return entry


def publish_image_fields(slug: str, fields: dict[str, str]) -> StagingEntry:
    """UX.md §4.3's "publish image" action: merges the image/image_source/
    image_caption frontmatter fields AND inserts the corresponding
    <TippedPhoto> body tag in the same write — frontmatter alone renders
    nothing (see the TippedPhoto note above `render_mdx`)."""
    path = STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    text = path.read_text(encoding="utf-8")
    data, body = split_frontmatter(text, slug)
    data.update(fields)
    body = _insert_tipped_photo(_strip_tipped_photo(body), _tipped_photo_tag(slug, fields))
    path.write_text(render_mdx(data, body), encoding="utf-8")
    return _entry_from_path(path)


def remove_image_fields(slug: str) -> StagingEntry:
    """UX.md §4.4's "Remove image" action on a staged draft — reverse of
    publish_image_fields: drops the frontmatter fields and strips the
    <TippedPhoto> tag back out of the body."""
    path = STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    text = path.read_text(encoding="utf-8")
    data, body = split_frontmatter(text, slug)
    for key in ("image", "image_source", "image_caption"):
        data.pop(key, None)
    body = _strip_tipped_photo(body)
    path.write_text(render_mdx(data, body), encoding="utf-8")
    return _entry_from_path(path)


def reject(slug: str, reason: str) -> None:
    src = STAGING_DIR / f"{slug}.mdx"
    if not src.exists():
        raise FileNotFoundError(slug)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = REJECTED_DIR / f"{slug}.mdx"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (REJECTED_DIR / f"{slug}.reason.txt").write_text(reason.strip() + "\n", encoding="utf-8")
    src.unlink()


def approve(slug: str) -> int:
    src = STAGING_DIR / f"{slug}.mdx"
    if not src.exists():
        raise FileNotFoundError(slug)
    staged_text = src.read_text(encoding="utf-8")
    data, body = split_frontmatter(staged_text, slug)
    if not data.get("verified"):
        # Backstop for drafts that never passed through orchestrator.py's
        # finalize step (hand-placed staging files, or ones drafted before
        # `verified` existed, SCHEMA.md §2 2026-07-22) — re-harvest updates
        # get their own re-verify date from the reviewer instead (the
        # "Verify with today's date" editor action), so this only fires once.
        data["verified"] = datetime.date.today()
        staged_text = render_mdx(data, body)
    errors = validate_frontmatter(data)
    if errors:
        raise ValidationFailed(errors)

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PUBLISHED_DIR / f"{slug}.mdx"
    previous_published_text = dest.read_text(encoding="utf-8") if dest.exists() else None

    dest.write_text(staged_text, encoding="utf-8")
    src.unlink()
    count = data_store.rebuild()
    forewords.ensure_forewords()  # UX.md §2.3 — generated once, on first venue in a new state/amenity combo

    _UNDO_STORE[slug] = _UndoRecord(
        staged_text=staged_text,
        previous_published_text=previous_published_text,
    )
    return count


def delete_published(slug: str) -> None:
    """Delete-listing action (2026-07-23): parks the MDX in
    content-staging/_deleted/ (timestamped, never destroyed) rather than
    unlinking, removes the venue's published image file if it has one, and
    rebuilds the derived data. The deploy strip then carries the removal to
    the site as a normal content change."""
    path = PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    text = path.read_text(encoding="utf-8")
    data, _body = split_frontmatter(text, slug)

    DELETED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    (DELETED_DIR / f"{slug}.{stamp}.mdx").write_text(text, encoding="utf-8")
    path.unlink()

    image = data.get("image")
    if isinstance(image, str) and image.startswith("/images/"):
        image_path = SITE_IMAGES_DIR / Path(image).name
        image_path.unlink(missing_ok=True)

    data_store.rebuild()


def remove_published_image(slug: str) -> None:
    """UX.md §4.4 — takedown/claim action on an already-published venue: strip
    the image fields and redeploy the derived data. No staging UI surfaces
    this in Gate 4 (claim workflow itself is out of scope per TRD.md §8); the
    capability exists as an admin action regardless."""
    path = PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    text = path.read_text(encoding="utf-8")
    data, body = split_frontmatter(text, slug)
    for key in ("image", "image_source", "image_caption"):
        data.pop(key, None)
    body = _strip_tipped_photo(body)
    path.write_text(render_mdx(data, body), encoding="utf-8")
    data_store.rebuild()


def undo_approve(slug: str) -> None:
    record = _UNDO_STORE.get(slug)
    if record is None:
        raise UndoExpired(slug)
    if time.time() - record.timestamp > UNDO_WINDOW_SECONDS:
        del _UNDO_STORE[slug]
        raise UndoExpired(slug)

    dest = PUBLISHED_DIR / f"{slug}.mdx"
    if record.previous_published_text is None:
        dest.unlink(missing_ok=True)
    else:
        dest.write_text(record.previous_published_text, encoding="utf-8")

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (STAGING_DIR / f"{slug}.mdx").write_text(record.staged_text, encoding="utf-8")

    data_store.rebuild()
    del _UNDO_STORE[slug]
