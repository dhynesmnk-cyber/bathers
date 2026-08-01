"""Comparison-article staging (Editorial Gate E2, 2026-08-01). Mirrors the venue
and blog staging split: drafts + their fact-check reports live in
content-staging/_article_staging until a deliberate approve moves the MDX into
site/src/content/blog/_published (comparison articles are canonical under /blog/,
Gate E1) and the report into data/factchecks/ as the committed editorial record.

Approve is gated on the fact-check: an article whose report is `blocked`
(unsupported claims) cannot be approved — the claims must be resolved and the
article re-run or hand-corrected first. Unsupported claims are never silently
stripped; they surface for a human to resolve (the editorial brief, Stage 4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from admin.config import (
    ARTICLE_REJECTED_DIR,
    ARTICLE_STAGING_DIR,
    BLOG_PUBLISHED_DIR,
    FACTCHECKS_DIR,
)
from admin.pipeline import article_store
from admin.pipeline.article_factcheck import deterministic_findings, register_findings, report_status
from admin.pipeline.validate_articles import find_hardcoded_numbers, register_issues

_FIELD_ORDER = ("title", "dateline", "summary", "author", "query_key", "reviewed_at")


class ValidationFailed(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("article failed validation")


class PublishBlocked(Exception):
    """Approve refused because the fact-check report is not clean."""


@dataclass
class ArticleEntry:
    slug: str
    frontmatter: dict[str, Any]
    body: str
    report: dict[str, Any] | None
    saved_at: float


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError("missing frontmatter delimiter")
    _, fm_yaml, body = text.split("---", 2)
    data = yaml.safe_load(fm_yaml) or {}
    return (data if isinstance(data, dict) else {}), body.strip("\n")


def _render_mdx(data: dict[str, Any], body: str) -> str:
    ordered = {k: data[k] for k in _FIELD_ORDER if k in data and data[k] not in (None, "")}
    front = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{front}---\n\n{body.strip()}\n"


def _report_path(slug: str) -> Path:
    return ARTICLE_STAGING_DIR / f"{slug}.factcheck.json"


def _read_report(slug: str) -> dict[str, Any] | None:
    path = _report_path(slug)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(path: Path) -> ArticleEntry:
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    return ArticleEntry(
        slug=path.stem,
        frontmatter=fm,
        body=body,
        report=_read_report(path.stem),
        saved_at=path.stat().st_mtime,
    )


def existing_query_keys() -> set[str]:
    """Comparison query_keys already used by a published or staged article — so
    the opportunity list only offers intents not yet written."""
    keys: set[str] = set()
    for p in BLOG_PUBLISHED_DIR.glob("*.mdx"):
        fm, _ = _split_frontmatter(p.read_text(encoding="utf-8"))
        if fm.get("query_key"):
            keys.add(fm["query_key"])
    for entry in list_staging():
        if entry.frontmatter.get("query_key"):
            keys.add(entry.frontmatter["query_key"])
    return keys


def list_staging() -> list[ArticleEntry]:
    ARTICLE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return [
        _entry(p)
        for p in sorted(ARTICLE_STAGING_DIR.glob("*.mdx"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


def get_staging(slug: str) -> ArticleEntry:
    path = ARTICLE_STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    return _entry(path)


def update_staging(slug: str, patch: dict[str, Any]) -> ArticleEntry:
    """Edit a staged article or essay (frontmatter fields and/or body) before
    approval — e.g. after a human resolves a flagged claim. A body edit re-runs the
    deterministic layer into the report so the block clears only when the prose is
    actually clean; the LLM claim rows are preserved."""
    path = ARTICLE_STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    if "body" in patch:
        body = patch.pop("body")
    fm.update(patch)
    path.write_text(_render_mdx(fm, body), encoding="utf-8")
    _resync_report(slug, body, is_essay=not fm.get("query_key"))
    return _entry(path)


def _resync_report(slug: str, body: str, is_essay: bool = False) -> None:
    """Recompute the deterministic layer of the report against the current body (an
    edit may have removed a hardcoded figure, or fixed a register/visit tell). LLM
    findings are kept. Essays use the register/visit layer; comparison articles use
    the hardcoded-figure layer — the same split as generation."""
    report = _read_report(slug)
    if report is None:
        return
    kept = [c for c in report.get("claims", []) if c.get("source") != "deterministic"]
    kept += register_findings(body) if is_essay else deterministic_findings(body)
    status, unsupported = report_status(kept)
    report["claims"] = kept
    report["status"] = status
    report["unsupported_count"] = unsupported
    _report_path(slug).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_for_publish(entry: ArticleEntry) -> list[str]:
    errors: list[str] = []
    fm = entry.frontmatter
    if not fm.get("title"):
        errors.append("title is required")
    summary = fm.get("summary")
    if not summary:
        errors.append("summary is required")
    elif len(str(summary)) > 160:
        errors.append(f"summary is {len(str(summary))} chars (max 160)")
    query_key = fm.get("query_key")
    if not query_key:
        # Essay: no live comparison, so no query_key or data-token discipline. The
        # house register (no em dashes / banned constructions / first-person visit)
        # still applies to every published word.
        for issue in register_issues(entry.body):
            errors.append(f"register — {issue}")
        return errors
    if query_key not in article_store.read_meta():
        errors.append(f"query_key '{query_key}' is not eligible (unknown or below the 5-venue threshold)")
    if find_hardcoded_numbers(entry.body):
        errors.append("body contains a hardcoded figure — every figure must be a data component")
    for issue in register_issues(entry.body):
        errors.append(f"register — {issue}")
    return errors


def approve(slug: str) -> str | None:
    """Publish a staged article or essay. Refuses if the report is missing or
    blocked, or if the frontmatter/body fails validation. On success the MDX moves
    into the blog _published collection and staging is cleared.

    A comparison article (has query_key) also writes its report to the committed
    factchecks record and re-baselines the comparison (records this review as the
    fresh baseline, so it isn't immediately flagged stale), and returns the netlify
    301 line for the superseded /compare/ page. An essay (no query_key) is a plain
    blog post: no committed report, no 301, no re-baseline — returns None."""
    entry = get_staging(slug)
    report = entry.report
    if report is None:
        raise PublishBlocked("no fact-check report — re-run the pipeline before approving")
    if report.get("status") == "blocked":
        raise PublishBlocked(
            f"{report.get('unsupported_count', 0)} unsupported claim(s) must be resolved before approval"
        )
    errors = _validate_for_publish(entry)
    if errors:
        raise ValidationFailed(errors)

    BLOG_PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    (BLOG_PUBLISHED_DIR / f"{slug}.mdx").write_text(
        _render_mdx(entry.frontmatter, entry.body), encoding="utf-8"
    )
    (ARTICLE_STAGING_DIR / f"{slug}.mdx").unlink()
    _report_path(slug).unlink(missing_ok=True)

    query_key = entry.frontmatter.get("query_key")
    if not query_key:
        # Essay: a plain blog post. The build validators (validate_articles) only
        # audit posts carrying a query_key, so nothing further is needed to publish.
        return None

    FACTCHECKS_DIR.mkdir(parents=True, exist_ok=True)
    FACTCHECKS_DIR.joinpath(f"{slug}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # Publishing after a fresh fact-check is a review — baseline the comparison so
    # it isn't reported stale against its own just-approved state.
    try:
        article_store.accept(query_key)
    except Exception:  # noqa: BLE001 — meta refresh is best-effort
        pass
    return f'[[redirects]]\n  from = "/compare/{query_key}/"\n  to = "/blog/{slug}/"\n  status = 301'


def reject(slug: str, reason: str) -> None:
    path = ARTICLE_STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    ARTICLE_REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = ARTICLE_REJECTED_DIR / f"{slug}.mdx"
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (ARTICLE_REJECTED_DIR / f"{slug}.reason.txt").write_text(
        f"{date.today().isoformat()}\n{reason.strip()}\n", encoding="utf-8"
    )
    report = _read_report(slug)
    if report is not None:
        (ARTICLE_REJECTED_DIR / f"{slug}.factcheck.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    path.unlink()
    _report_path(slug).unlink(missing_ok=True)


def unpublish(slug: str) -> None:
    """Take a published comparison article off the live site, recoverably
    (2026-08-01 admin-UX change). The MDX moves back to _article_staging and its
    committed fact-check record moves back beside it as <slug>.factcheck.json, so
    re-review keeps its report (mirror of approve/reject). articles-meta.json is
    rebuilt so the intent drops out of the published set and reappears as an
    opportunity. The /compare/<query_key>/ redirect in netlify.toml is left in
    place — the article is coming back, and netlify.toml is outside the deploy
    set anyway. The _published deletion rides the next deploy to Netlify."""
    path = BLOG_PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        raise FileNotFoundError(slug)
    ARTICLE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (ARTICLE_STAGING_DIR / f"{slug}.mdx").write_text(
        path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    committed_report = FACTCHECKS_DIR / f"{slug}.json"
    if committed_report.exists():
        _report_path(slug).write_text(
            committed_report.read_text(encoding="utf-8"), encoding="utf-8"
        )
        committed_report.unlink()
    path.unlink()

    # Refresh the derived staleness metadata so the now-unpublished intent leaves
    # the published set (best-effort — a meta hiccup must not strand the file).
    try:
        article_store.rebuild()
    except Exception:  # noqa: BLE001
        pass
