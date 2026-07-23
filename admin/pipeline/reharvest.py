"""One-shot batch re-harvest for under-captured published venues (2026-07-23).

An audit found most early venues were harvested before the pipeline was
hardened (nullable optional fields, geocoder, Places check, dup detection),
leaving honest gaps: missing `cost`, missing `hours`, or all five amenities
false. This walks `_published`, selects venues with any of those gaps, and
re-runs the full Harvester→Architect→Gatekeeper pipeline against each
venue's original `source_url` via `run_harvest_pipeline`'s
`allow_existing_slug` escape hatch. Fresh drafts land in `_staging/` for
normal human review — this module never writes to `_published`
(CLAUDE.md rule 5); `approve()` remains the only path there.

Each produced draft is fixed up so approving it is a clean update of the
existing venue rather than a regression:
  - renamed to the original slug if the Harvester extracted a drifted name
    (a drifted filename would make approve() ADD a venue, not update it);
  - original `drafted` date restored (SCHEMA.md §2 — only `verified` moves
    on re-harvest);
  - the published photo's frontmatter fields and <TippedPhoto> body tag
    carried forward (a fresh draft has neither, so approving it as-is
    would silently wipe the venue's photo).

Usage:
    python -m admin.pipeline.reharvest [--dry-run] [--slugs a,b,c]
        [--no-playwright-fallback]

Do not run while an admin-UI harvest job is active — this CLI bypasses the
app's single-job harvest lock.
"""

from __future__ import annotations

import argparse
import datetime

from admin.config import AMENITY_KEYS, PUBLISHED_DIR, STAGING_DIR
from admin.pipeline import images, places
from admin.pipeline.orchestrator import run_harvest_pipeline
from admin.pipeline.staging import (
    _insert_tipped_photo,
    _strip_tipped_photo,
    _tipped_photo_tag,
    render_mdx,
    split_frontmatter,
)

IMAGE_FIELDS = ("image", "image_source", "image_caption")


def gap_reasons(data: dict) -> list[str]:
    """Why a published venue needs a re-harvest; empty list means it doesn't."""
    reasons = []
    if data.get("cost") in (None, ""):
        reasons.append("no cost")
    if data.get("hours") in (None, ""):
        reasons.append("no hours")
    amenities = data.get("amenities") or {}
    if not any(amenities.get(key) for key in AMENITY_KEYS):
        reasons.append("amenities all false")
    return reasons


def select_venues(slugs: list[str] | None) -> list[tuple[str, dict, str]]:
    """[(slug, published frontmatter, reason string)] for venues to re-harvest."""
    selected = []
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        slug = path.stem
        if slugs is not None and slug not in slugs:
            continue
        data, _body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        reasons = gap_reasons(data)
        if slugs is None and not reasons:
            continue
        selected.append((slug, data, ", ".join(reasons) or "explicitly requested"))
    return selected


def _drain(url: str, use_playwright: bool) -> list:
    log_lines = []
    for line in run_harvest_pipeline(url, use_playwright=use_playwright, allow_existing_slug=True):
        print(f"    [{line.level}] {line.text}")
        log_lines.append(line)
    return log_lines


def _staging_state() -> dict[str, float]:
    return {p.name: p.stat().st_mtime for p in STAGING_DIR.glob("*.mdx")} if STAGING_DIR.exists() else {}


def _fix_up_draft(orig_slug: str, produced_slug: str, published: dict) -> list[str]:
    """Post-stage fix-up; returns human-readable notes of what was adjusted."""
    notes = []
    path = STAGING_DIR / f"{produced_slug}.mdx"
    if produced_slug != orig_slug:
        target = STAGING_DIR / f"{orig_slug}.mdx"
        path.rename(target)
        path = target
        # Mirror the temp_data slug→key registrations so the admin UI still
        # finds this run's Places check and image candidates under the slug
        # the draft now lives at.
        images.record_slug_key(orig_slug, images.resolve_key(produced_slug))
        places.record_slug_key(orig_slug, places.resolve_key(produced_slug))
        notes.append(f"slug drifted ('{produced_slug}') — renamed to '{orig_slug}'")

    data, body = split_frontmatter(path.read_text(encoding="utf-8"), orig_slug)

    if published.get("drafted") and data.get("drafted") != published["drafted"]:
        data["drafted"] = published["drafted"]
        notes.append(f"restored drafted: {published['drafted']}")

    if published.get("image"):
        fields = {key: published[key] for key in IMAGE_FIELDS if published.get(key)}
        data.update(fields)
        if all(key in fields for key in IMAGE_FIELDS):
            body = _insert_tipped_photo(_strip_tipped_photo(body), _tipped_photo_tag(orig_slug, fields))
            notes.append("carried published photo forward (fields + <TippedPhoto>)")
        else:
            notes.append("carried partial image fields forward (no <TippedPhoto> — incomplete set)")

    path.write_text(render_mdx(data, body), encoding="utf-8")
    return notes


def _short(value, width: int = 60) -> str:
    if value in (None, ""):
        return "—"
    text = str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_diff(old: dict, new_path) -> None:
    new, _ = split_frontmatter(new_path.read_text(encoding="utf-8"), new_path.stem)
    old_amenities = old.get("amenities") or {}
    new_amenities = new.get("amenities") or {}
    flipped = [key for key in AMENITY_KEYS if bool(old_amenities.get(key)) != bool(new_amenities.get(key))]
    old_true = sum(bool(old_amenities.get(key)) for key in AMENITY_KEYS)
    new_true = sum(bool(new_amenities.get(key)) for key in AMENITY_KEYS)
    print(f"    diff amenities: {old_true}→{new_true} true" + (f" (changed: {', '.join(flipped)})" if flipped else ""))
    for field in ("cost", "hours"):
        if _short(old.get(field)) != _short(new.get(field)):
            print(f"    diff {field}: {_short(old.get(field))} → {_short(new.get(field))}")


def reharvest(
    slugs: list[str] | None,
    dry_run: bool,
    playwright_fallback: bool,
    overwrite_staged: bool = False,
    playwright: bool = False,
) -> dict[str, list[str]]:
    selected = select_venues(slugs)
    outcomes: dict[str, list[str]] = {"staged": [], "skipped": [], "failed": []}
    print(f"{len(selected)} venue(s) selected for re-harvest")
    for slug, data, reason in selected:
        print(f"\n== {slug}  ({reason})")
        source_url = data.get("source_url")
        if not source_url:
            print("    [error] no source_url — cannot re-harvest")
            outcomes["failed"].append(f"{slug} (no source_url)")
            continue
        if dry_run:
            print(f"    would re-harvest {source_url}")
            continue
        if (STAGING_DIR / f"{slug}.mdx").exists() and not overwrite_staged:
            print("    [warn] already has an unreviewed staged draft — skipping")
            outcomes["skipped"].append(slug)
            continue

        before = _staging_state()
        try:
            log_lines = _drain(source_url, use_playwright=playwright)
            thin = any("thin extraction" in line.text for line in log_lines)
            if thin and playwright_fallback and not playwright:
                print("    [info] retrying with Playwright fallback")
                log_lines = _drain(source_url, use_playwright=True)
        except Exception as exc:  # keep the batch going; one venue's crash isn't the run's
            print(f"    [error] pipeline crashed — {exc}")
            outcomes["failed"].append(f"{slug} ({exc})")
            continue
        after = _staging_state()

        produced = [name for name, mtime in after.items() if before.get(name) != mtime]
        if not produced:
            last_problem = next(
                (line.text for line in reversed(log_lines) if line.level in ("error", "warn")),
                "no error logged",
            )
            print(f"    [error] no draft produced — {last_problem}")
            outcomes["failed"].append(f"{slug} ({last_problem})")
            continue
        produced_slug = produced[0].removesuffix(".mdx")
        clobbered = [name for name in produced if name in before]
        if clobbered:
            print(f"    [warn] overwrote pre-existing staged draft(s): {', '.join(clobbered)}")

        for note in _fix_up_draft(slug, produced_slug, data):
            print(f"    [info] {note}")
        _print_diff(data, STAGING_DIR / f"{slug}.mdx")
        outcomes["staged"].append(slug)
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch re-harvest under-captured published venues into _staging/.")
    parser.add_argument("--dry-run", action="store_true", help="list selected venues and URLs, harvest nothing")
    parser.add_argument("--slugs", help="comma-separated slugs to re-harvest (default: all venues with gaps)")
    parser.add_argument(
        "--no-playwright-fallback",
        action="store_true",
        help="do not retry thin extractions with Playwright",
    )
    parser.add_argument(
        "--overwrite-staged",
        action="store_true",
        help="regenerate over an existing unreviewed staged draft instead of skipping it",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="fetch with Playwright from the start (also lets thin pricing pages retry in-browser)",
    )
    args = parser.parse_args()
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()] if args.slugs else None

    started = datetime.datetime.now()
    outcomes = reharvest(
        slugs,
        dry_run=args.dry_run,
        playwright_fallback=not args.no_playwright_fallback,
        overwrite_staged=args.overwrite_staged,
        playwright=args.playwright,
    )
    if args.dry_run:
        print("\ndry run — nothing harvested")
        return
    elapsed = (datetime.datetime.now() - started).seconds
    print(f"\ndone in {elapsed}s — {len(outcomes['staged'])} staged, {len(outcomes['skipped'])} skipped, {len(outcomes['failed'])} failed")
    for label in ("skipped", "failed"):
        for item in outcomes[label]:
            print(f"  {label}: {item}")
    if outcomes["staged"]:
        print("drafts await review in the admin queue — approve/reject as normal")


if __name__ == "__main__":
    main()
