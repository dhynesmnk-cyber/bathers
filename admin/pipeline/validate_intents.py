"""Article intent-uniqueness check (Editorial Gate E4a, 2026-08-01). Folded into
/validate as check 21.

A hybrid comparison article owns one search *intent* (its `query_key`). The
whole editorial model — the opportunity queue's dedupe, the `/compare/<key>/ ->
/blog/<slug>/` 301, the "one intent, one article" contract — assumes no two
published articles compete for the same intent (the self-competition the brief
warns against). This asserts it at build: no `query_key` in
`site/src/content/blog/_published/` is carried by more than one post.

The opportunity queue enforces this going forward (a written intent is never
re-offered, and the brief gate sits in front of drafting), but a hand-placed or
mis-migrated file could still collide, so the build gate proves it.

`duplicate_intents(pairs)` is the testable core; `_selftest` proves it fires on a
deliberately corrupted fixture and passes a clean one.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

from admin.config import BLOG_PUBLISHED_DIR


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            return (fm if isinstance(fm, dict) else {}), text[end + 4:]
    return {}, text


def duplicate_intents(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Given (filename, query_key) pairs, return {query_key: [files]} for every
    intent claimed by more than one file. Empty = every intent is unique."""
    by_key: dict[str, list[str]] = defaultdict(list)
    for name, key in pairs:
        if key:
            by_key[key].append(name)
    return {key: sorted(names) for key, names in by_key.items() if len(names) > 1}


def _published_pairs(blog_dir: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for path in sorted(blog_dir.glob("*.mdx")):
        fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        pairs.append((path.name, fm.get("query_key")))
    return pairs


def check_intents(blog_dir: Path = BLOG_PUBLISHED_DIR) -> list[str]:
    dupes = duplicate_intents(_published_pairs(blog_dir))
    return [
        f"query_key {key!r} is claimed by {len(names)} articles ({', '.join(names)}) — "
        "one intent, one article (drop or merge the duplicates)"
        for key, names in sorted(dupes.items())
    ]


def _selftest() -> list[str]:
    """Must catch two articles sharing an intent and pass distinct intents."""
    failures: list[str] = []
    corrupted = [("cheapest-a.mdx", "cheapest"), ("cheapest-b.mdx", "cheapest"), ("hot.mdx", "hottest")]
    if "cheapest" not in duplicate_intents(corrupted):
        failures.append("selftest: duplicate-intent scanner missed two articles sharing a query_key")
    clean = [("cheapest.mdx", "cheapest"), ("hottest.mdx", "hottest"), ("essay.mdx", None)]
    if duplicate_intents(clean):
        failures.append(f"selftest: duplicate-intent scanner false-positived on unique intents: {duplicate_intents(clean)}")
    return failures


def main() -> int:
    errors = _selftest() + check_intents()
    if errors:
        print("ARTICLE INTENT-UNIQUENESS FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("article intent-uniqueness OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
