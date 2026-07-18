"""Review-queue primitives: list/read/update staging entries, reject, approve
and undo. Frontmatter is the canonical source (CLAUDE.md); this module never
writes to `_published` except via `approve`, and never touches the DB/JSON
directly — it always goes through `data_store.rebuild()` so the derived
artefacts stay a full-rebuild-from-published (TRD.md §5), consistent with
how Gate 2 already guarantees idempotency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from admin.config import PUBLISHED_DIR, REJECTED_DIR, STAGING_DIR
from admin.pipeline import data_store, forewords, images
from admin.schema import FieldError, count_prose_words, staging_status, validate_frontmatter

FRONTMATTER_FIELD_ORDER = (
    "name", "state", "suburb", "address", "latitude", "longitude", "website",
    "amenities", "status", "summary", "drafted", "source_url",
    "image", "image_source", "image_caption",
)
AMENITY_FIELD_ORDER = (
    "magnesium_pool", "infrared_sauna", "traditional_sauna", "cold_plunge", "led_therapy",
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


def render_frontmatter(data: dict[str, Any]) -> str:
    ordered: dict[str, Any] = {}
    for key in FRONTMATTER_FIELD_ORDER:
        if key not in data:
            continue
        if key == "amenities" and isinstance(data[key], dict):
            ordered[key] = {ak: data[key].get(ak) for ak in AMENITY_FIELD_ORDER if ak in data[key]}
        else:
            ordered[key] = data[key]
    return yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False)


def render_mdx(data: dict[str, Any], body: str) -> str:
    return f"---\n{render_frontmatter(data)}---\n\n{body.strip()}\n"


def _entry_from_path(path: Path) -> StagingEntry:
    text = path.read_text(encoding="utf-8")
    slug = path.stem
    data, body = split_frontmatter(text, slug)
    errors = validate_frontmatter(data)
    word_count = count_prose_words(body)
    has_pending_images = bool(images.list_candidates(slug)) and not data.get("image")
    status = staging_status(errors, word_count, has_pending_images)
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


def get_staging(slug: str) -> StagingEntry:
    path = STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    return _entry_from_path(path)


def update_staging(slug: str, patch: dict[str, Any]) -> StagingEntry:
    path = STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    text = path.read_text(encoding="utf-8")
    data, body = split_frontmatter(text, slug)
    data.update(patch)
    path.write_text(render_mdx(data, body), encoding="utf-8")
    return _entry_from_path(path)


def remove_frontmatter_keys(slug: str, keys: list[str]) -> StagingEntry:
    """Delete keys entirely (rather than setting null) — used for the optional
    image/image_source/image_caption fields on `Remove image` (UX.md §4.4)."""
    path = STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    text = path.read_text(encoding="utf-8")
    data, body = split_frontmatter(text, slug)
    for key in keys:
        data.pop(key, None)
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
