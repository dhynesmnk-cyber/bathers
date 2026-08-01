"""Staleness engine for hybrid comparison articles (Editorial Gate E1, 2026-08-01).

The venue-selection logic that decides "who wins" a comparison lives in
TypeScript (site/src/data/comparisons.ts) and drives the public build. To avoid
maintaining a second, drifting copy of that logic in Python, this module shells
out to the site's own refresh runner (site/scripts/refresh-articles.ts, run
under native Node type-stripping) and reads back the derived, committed artifact
articles-meta.json.

Same source-of-truth posture as data_store: venues.json / directory.db are
derived from _published; articles-meta.json is derived from venues.json + the
comparison registry. The runner reads the *current* venues.json, so callers must
rebuild venue data first (staging._rebuild_derived does exactly this).
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from typing import Any

import yaml

from admin.config import ARTICLES_META_JSON_PATH, BLOG_PUBLISHED_DIR, FACTCHECKS_DIR, SITE_DIR

_logger = logging.getLogger("admin.article_store")

# Native Node (>=22.18) strips types; the register bootstrap adds a resolve hook
# so the runner can import the project's extensionless relative TS. Run from
# SITE_DIR so the relative loader/script paths resolve.
_REFRESH_CMD = ["node", "--import", "./scripts/ts-register.mjs", "scripts/refresh-articles.ts"]


def rebuild(*extra: str) -> dict[str, Any]:
    """Re-resolve every comparison against the current venues.json and rewrite
    articles-meta.json. Pass ``--accept <key>`` / ``--accept-all`` to re-baseline
    an article (record a human re-review, clearing its staleness). Returns the
    parsed metadata. Raises RuntimeError on a runner failure so callers can log
    it (staging treats it as non-fatal)."""
    proc = subprocess.run(
        [*_REFRESH_CMD, *extra], cwd=SITE_DIR, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"article refresh failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    if proc.stdout.strip():
        _logger.info(proc.stdout.strip())
    return read_meta()


def read_meta() -> dict[str, Any]:
    try:
        return json.loads(ARTICLES_META_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def stale_keys() -> list[str]:
    """Comparison query_keys whose live ranking/headline has drifted from the
    last human-reviewed baseline — surfaced in the admin for re-review."""
    return sorted(k for k, e in read_meta().items() if isinstance(e, dict) and e.get("stale"))


def accept(key: str) -> dict[str, Any]:
    """Record a human re-review of one article: re-baseline it to the current
    figures, clearing its stale flag."""
    return rebuild("--accept", key)


def _published_comparisons() -> dict[str, dict[str, Any]]:
    """query_key -> {slug, reviewed_at} for every published comparison article."""
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(BLOG_PUBLISHED_DIR.glob("*.mdx")):
        text = p.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        fm = yaml.safe_load(text[3:end]) if end != -1 else {}
        if isinstance(fm, dict) and fm.get("query_key"):
            ra = fm.get("reviewed_at") or fm.get("dateline")
            out[fm["query_key"]] = {"slug": p.stem, "reviewed_at": str(ra) if ra else None}
    return out


def _factcheck_status(slug: str) -> str | None:
    path = FACTCHECKS_DIR / f"{slug}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("status")
    except (json.JSONDecodeError, OSError):
        return None


def published_staleness() -> list[dict[str, Any]]:
    """Post-publish staleness dashboard rows (Editorial Gate E4c): every published
    comparison article with its two dates (prose reviewed_at + figures
    data_updated_at), its stale flag, what has moved since the last human
    baseline (winner / headline figure / ranking order), its stored fact-check
    status, and whether the comparison is still eligible (>=5 venues). Sorted
    stale-first so the ones needing a human sit at the top."""
    meta = read_meta()
    rows: list[dict[str, Any]] = []
    for key, info in _published_comparisons().items():
        e = meta.get(key) or {}
        reviewed = e.get("reviewed") or {}
        current = e.get("current") or {}
        rows.append({
            "query_key": key,
            "slug": info["slug"],
            "title": e.get("title", info["slug"]),
            "stale": bool(e.get("stale")),
            "reviewed_at": info["reviewed_at"],
            "data_updated_at": e.get("data_updated_at"),
            "moved": {
                "winner": reviewed.get("winner") != current.get("winner"),
                "headline": reviewed.get("headline") != current.get("headline"),
                "order": reviewed.get("order") != current.get("order"),
            },
            "report_status": _factcheck_status(info["slug"]),
            "eligible": key in meta,
        })
    return sorted(rows, key=lambda r: (not r["stale"], r["slug"]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh articles-meta.json (hybrid-article staleness) from venues.json + comparisons.ts."
    )
    parser.add_argument("--rebuild", action="store_true", help="re-resolve and rewrite the metadata")
    parser.add_argument("--accept", metavar="QUERY_KEY", help="re-baseline one article (clear its staleness)")
    parser.add_argument("--accept-all", action="store_true", help="re-baseline every article")
    args = parser.parse_args()

    extra: list[str] = []
    if args.accept:
        extra += ["--accept", args.accept]
    if args.accept_all:
        extra += ["--accept-all"]

    meta = rebuild(*extra) if (args.rebuild or extra) else read_meta()
    stale = [k for k, e in meta.items() if isinstance(e, dict) and e.get("stale")]
    print(
        f"{len(meta)} comparison(s); {len(stale)} stale"
        + (f": {', '.join(stale)}" if stale else "")
    )


if __name__ == "__main__":
    main()
