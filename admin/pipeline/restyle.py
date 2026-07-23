"""One-shot batch restyle of published venue reviews (2026-07-24).

The reviews were written before the voice was tightened: they lean on em
dashes, "not X, but Y" contrast constructions, stiff attribution words
("documented", "has been built around"), and FAQ answers restated in the
body. This walks every venue with a staged draft or a published file, and for
each asks the Restyle agent to rewrite the body prose and FAQ wording in the
warmed voice WITHOUT touching a single fact. A pending staged draft is the
source when one exists (it holds the newest re-harvested facts); otherwise the
live published file is the source.

It is a style migration, not a re-harvest: no source URL is fetched. The
venue's own already-approved facts are the source of truth. To keep that
guarantee airtight the frontmatter scalars are frozen in code (only `faq` and
the body come from the agent), so no number, price, hour, or coordinate can
drift no matter what the model returns.

Fresh drafts land in `_staging/`. With `--approve` (the default) each draft
that passes the mechanical checks below is approved straight away via
`staging.approve()` — the only path into `_published` (CLAUDE.md rule 5). Use
`--no-approve` to stage-only and review by hand.

Usage:
    python -m admin.pipeline.restyle [--dry-run] [--slugs a,b,c] [--no-approve]

Do not run while an admin-UI harvest job is active — this CLI bypasses the
app's single-job lock.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from admin.config import MODEL_ARCHITECT, PUBLISHED_DIR, STAGING_DIR
from admin.pipeline import agents, staging
from admin.pipeline.staging import (
    _insert_tipped_photo,
    _strip_tipped_photo,
    _tipped_photo_tag,
    render_mdx,
    split_frontmatter,
)
from admin.schema import count_prose_words, validate_frontmatter

IMAGE_FIELDS = ("image", "image_source", "image_caption")
DEDASH_FIELDS = ("summary", "hours", "cost", "access", "image_caption")
EM_DASH = "—"

# Attribution / hedge vocabulary the new voice bans (lowercased substrings).
BANNED_ATTRIBUTION = (
    "documented",
    "undocumented",
    "has been described",
    "is described as",
    "has been built around",
    "given over to",
    "at the time of writing",
)


def _print(text: str, level: str) -> None:
    print(f"    [{level}] {text}")


def build_worklist(slugs: list[str] | None) -> list[tuple[str, Path]]:
    """[(slug, source path)] for every venue to restyle. A pending staged
    draft is the source of truth when one exists (it carries the newest,
    re-harvested facts); otherwise the live published file is the source.
    The restyled draft is always written to _staging and approved from there."""
    staged = {p.stem: p for p in STAGING_DIR.glob("*.mdx")} if STAGING_DIR.exists() else {}
    published = {p.stem: p for p in PUBLISHED_DIR.glob("*.mdx")}
    work: list[tuple[str, Path]] = []
    for slug in sorted(set(staged) | set(published)):
        if slugs is not None and slug not in slugs:
            continue
        work.append((slug, staged.get(slug) or published[slug]))
    return work


def _parse_agent_mdx(text: str) -> tuple[dict, str]:
    """Validator for the agent turn: the output must parse as an MDX file with
    a non-empty body. Raises ValueError so call_agent re-asks once on failure."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()
    if not text.startswith("---"):
        raise ValueError("output does not start with frontmatter delimiter")
    data, body = split_frontmatter(text, "restyle")
    if not body.strip():
        raise ValueError("empty body")
    # Banned attribution words can't be repaired deterministically (they need
    # rewording), so surface them as a validation failure to trigger the one
    # content re-ask. Em dashes are handled by a deterministic sweep instead.
    faq_text = " ".join(
        f"{i.get('question', '')} {i.get('answer', '')}"
        for i in (data.get("faq") or [])
        if isinstance(i, dict)
    )
    hits = [w for w in BANNED_ATTRIBUTION if w in (body + " " + faq_text).lower()]
    if hits:
        raise ValueError(f"remove banned attribution words: {', '.join(hits)}")
    return data, body


def _dedash_prose(text: str) -> str:
    """Deterministic em-dash removal for flowing prose. Every em dash in these
    entries sits between an opener and an aside ("Yes — massage...") or brackets
    an appositive, where a comma is the natural human replacement."""
    if not isinstance(text, str) or EM_DASH not in text:
        return text
    return re.sub(rf"\s*{EM_DASH}\s*", ", ", text)


def _dedash(value):
    """Deterministic em-dash removal for short display strings, where a
    punctuation swap is safe (the agent handles dashes in flowing prose)."""
    if not isinstance(value, str) or EM_DASH not in value:
        return value
    return re.sub(rf"\s*{EM_DASH}\s*", ", ", value).strip().rstrip(",")


def _valid_faq(faq) -> bool:
    return (
        isinstance(faq, list)
        and len(faq) <= 8
        and all(
            isinstance(item, dict)
            and isinstance(item.get("question"), str)
            and isinstance(item.get("answer"), str)
            for item in faq
        )
    )


def _build_draft(slug: str, orig: dict, new_faq, new_body: str) -> tuple[dict, str]:
    """Merge the agent's body + FAQ onto the frozen original frontmatter."""
    data = dict(orig)
    for field in DEDASH_FIELDS:
        if field in data:
            data[field] = _dedash(data[field])
    if _valid_faq(new_faq):
        data["faq"] = [
            {"question": _dedash_prose(i["question"]), "answer": _dedash_prose(i["answer"])}
            for i in new_faq
        ]

    new_body = _dedash_prose(new_body)
    has_full_image = all(orig.get(key) for key in IMAGE_FIELDS)
    if has_full_image:
        # caption from `data` (dedashed); image/source URLs from the original.
        fields = {key: (data[key] if key == "image_caption" else orig[key]) for key in IMAGE_FIELDS}
        body = _insert_tipped_photo(_strip_tipped_photo(new_body), _tipped_photo_tag(slug, fields))
    else:
        body = _strip_tipped_photo(new_body)
    return data, body


def _checks(slug: str, orig: dict, draft: dict, body: str, orig_body: str) -> list[str]:
    """Mechanical guards. Empty list means the draft is safe to auto-approve."""
    problems: list[str] = []

    faq = draft.get("faq") or []
    faq_text = " ".join(f"{i.get('question', '')} {i.get('answer', '')}" for i in faq)
    if EM_DASH in body or EM_DASH in faq_text:
        problems.append("em dash left in body/FAQ")
    for field in DEDASH_FIELDS:
        if EM_DASH in str(draft.get(field) or ""):
            problems.append(f"em dash left in {field}")

    haystack = (body + " " + faq_text).lower()
    hits = [w for w in BANNED_ATTRIBUTION if w in haystack]
    if hits:
        problems.append(f"banned attribution words: {', '.join(hits)}")

    # Frozen-fact guard: every non-faq frontmatter field must equal the
    # original (display fields compared after the same dedash we applied).
    for key, value in orig.items():
        if key == "faq":
            continue
        expected = _dedash(value) if key in DEDASH_FIELDS else value
        if draft.get(key) != expected:
            problems.append(f"frontmatter drift on '{key}'")
    if not _valid_faq(draft.get("faq") or []):
        problems.append("faq malformed or >8 entries")

    orig_words = count_prose_words(orig_body)
    new_words = count_prose_words(body)
    low, high = max(50, round(orig_words * 0.55)), round(orig_words * 1.5) + 40
    if not (low <= new_words <= high):
        problems.append(f"word count {new_words} outside {low}-{high} (was {orig_words})")

    orig_has_photo = "<TippedPhoto" in orig_body
    new_has_photo = "<TippedPhoto" in body
    if orig_has_photo != new_has_photo:
        problems.append(f"TippedPhoto presence changed ({orig_has_photo}->{new_has_photo})")

    errors = validate_frontmatter(draft)
    if errors:
        problems.append(f"schema invalid: {', '.join(e.field for e in errors)}")

    return problems


def restyle_one(slug: str, orig: dict, orig_body: str) -> tuple[dict, str, list[str]]:
    """Returns (draft frontmatter, draft body, check problems)."""
    original_mdx = render_mdx(orig, orig_body)
    (new_data, new_body), _usage = agents.call_agent(
        model=MODEL_ARCHITECT,
        system=agents.load_prompt("restyle.md"),
        user_content=original_mdx,
        max_tokens=4096,
        validate=_parse_agent_mdx,
        log=_print,
    )
    draft, body = _build_draft(slug, orig, new_data.get("faq"), new_body)
    problems = _checks(slug, orig, draft, body, orig_body)
    return draft, body, problems


def restyle(
    slugs: list[str] | None,
    dry_run: bool,
    do_approve: bool,
) -> dict[str, list[str]]:
    work = build_worklist(slugs)
    outcomes: dict[str, list[str]] = {"approved": [], "staged": [], "failed": []}
    print(f"{len(work)} venue(s) selected for restyle")
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    for slug, source in work:
        origin = "staged" if source.parent == STAGING_DIR else "published"
        print(f"\n== {slug}  (source: {origin})")
        orig, orig_body = split_frontmatter(source.read_text(encoding="utf-8"), slug)
        if dry_run:
            print(f"    would restyle ({count_prose_words(orig_body)} words)")
            continue

        try:
            draft, body, problems = restyle_one(slug, orig, orig_body)
        except Exception as exc:  # keep the batch going; one venue's crash isn't the run's
            print(f"    [error] restyle crashed — {exc}")
            outcomes["failed"].append(f"{slug} ({exc})")
            continue

        (STAGING_DIR / f"{slug}.mdx").write_text(render_mdx(draft, body), encoding="utf-8")

        if problems:
            for problem in problems:
                print(f"    [error] check failed: {problem}")
            print("    staged for manual review, not approved")
            outcomes["failed"].append(f"{slug} ({'; '.join(problems)})")
            continue

        print("    checks passed")
        if not do_approve:
            outcomes["staged"].append(slug)
            continue
        try:
            staging.approve(slug)
            print("    approved -> _published, rebuilt")
            outcomes["approved"].append(slug)
        except staging.ValidationFailed as exc:
            print(f"    [error] approve rejected: {', '.join(e.field for e in exc.errors)}")
            outcomes["failed"].append(f"{slug} (approve: schema)")
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch restyle published venue reviews into the warmed voice.")
    parser.add_argument("--dry-run", action="store_true", help="list selected venues, restyle nothing")
    parser.add_argument("--slugs", help="comma-separated slugs to restyle (default: all staged + published)")
    parser.add_argument("--no-approve", action="store_true", help="stage drafts only; do not auto-approve")
    args = parser.parse_args()
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()] if args.slugs else None

    outcomes = restyle(
        slugs,
        dry_run=args.dry_run,
        do_approve=not args.no_approve,
    )
    if args.dry_run:
        print("\ndry run — nothing restyled")
        return
    print(
        f"\ndone — {len(outcomes['approved'])} approved, {len(outcomes['staged'])} staged, "
        f"{len(outcomes['failed'])} failed"
    )
    for item in outcomes["failed"]:
        print(f"  failed: {item}")


if __name__ == "__main__":
    main()
