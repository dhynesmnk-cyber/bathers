"""Article data-binding integrity checks (Editorial Gate E1, 2026-08-01).

A hybrid comparison article's whole point is that its figures resolve live from
the venue data, never typed into prose. This validator enforces that at build:

  * no hardcoded numeric/currency/temperature claim in a comparison article's
    body (every figure must be a data component/token);
  * the post's `query_key` resolves to a comparison that cleared the >=5-venue
    threshold — proxied by its presence in articles-meta.json, which the runner
    only writes for eligible comparisons.

Run: ``python3 -m admin.pipeline.validate_articles`` (exit 0 = pass). Fails, not
warns, and fails against its own deliberately corrupted fixture (see _selftest).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from admin.config import ARTICLES_META_JSON_PATH, BLOG_PUBLISHED_DIR, FACTCHECKS_DIR

# MDX tags (data components like <Figure .../> and paired wrappers like <Pull>)
# are stripped before scanning: a self-closing data component carries no literal
# figure, and stripping the paired tags leaves their inner *prose* to be scanned
# (so a number typed inside a <Pull> is still caught).
_TAG_RE = re.compile(r"<[^>]+>")
# A markdown-link target — /compare/, /methodology/ etc. — is a route, not a
# claim; its slug is dropped so a future dated path can't false-positive.
_LINK_TARGET_RE = re.compile(r"\]\(([^)]*)\)")
# What counts as a hardcoded figure in prose: a currency amount, a temperature,
# or any bare number token (a count like "7 venues" goes stale too).
_CURRENCY_RE = re.compile(r"\$\s?\d")
_TEMPERATURE_RE = re.compile(r"\d\s*°")
_BARE_NUMBER_RE = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?(?![\w-])")


# House-register violations the drafting model controls and the Gatekeeper bans
# (PROMPTS/gatekeeper.md): em dashes and their `--` substitute, "not X but Y" /
# "rather than" contrast constructions, and first-person visit tells. Scoped to
# structural tells (not the spa-vocabulary word list, which risks false hits on a
# venue's own name) so it is safe to fail the build on.
_REGISTER_PATTERNS = [
    (re.compile(r"—"), "em dash (—) — the house uses commas/full stops"),
    (re.compile(r"(?<=\w)\s*--\s*(?=\w)"), "'--' used as an em dash"),
    (re.compile(r"\brather than\b", re.I), "'rather than' contrast construction"),
    (re.compile(r"\bnot just\b|\bisn't just\b", re.I), "'not just' contrast construction"),
    (re.compile(r"\bwe visited\b|\bon arrival\b|\bI found\b|you'll find yourself", re.I), "first-person visit claim"),
]


def register_issues(body: str) -> list[str]:
    """House-register violations in the prose (tags/link targets stripped)."""
    prose = _LINK_TARGET_RE.sub("]( )", _TAG_RE.sub(" ", body))
    issues: list[str] = []
    for line in prose.splitlines():
        line = line.strip()
        for pattern, label in _REGISTER_PATTERNS:
            if pattern.search(line):
                issues.append(f"{label}: {line[:90]}")
    return issues


def find_hardcoded_numbers(body: str) -> list[str]:
    """Return the offending prose fragments (empty = clean). Scans the body with
    component tags and link targets removed."""
    prose = _TAG_RE.sub(" ", body)
    prose = _LINK_TARGET_RE.sub("]( )", prose)
    hits: list[str] = []
    for line in prose.splitlines():
        line = line.strip()
        if not line:
            continue
        if _CURRENCY_RE.search(line) or _TEMPERATURE_RE.search(line) or _BARE_NUMBER_RE.search(line):
            hits.append(line)
    return hits


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = yaml.safe_load(text[3:end]) or {}
            body = text[end + 4 :]
            return (fm if isinstance(fm, dict) else {}), body
    return {}, text


def check_articles(blog_dir: Path = BLOG_PUBLISHED_DIR, meta_path: Path = ARTICLES_META_JSON_PATH) -> list[str]:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        meta = {}
    errors: list[str] = []
    for path in sorted(blog_dir.glob("*.mdx")):
        fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        query_key = fm.get("query_key")
        if not query_key:
            continue  # an essay, not a comparison article
        for hit in find_hardcoded_numbers(body):
            errors.append(f"{path.name}: hardcoded figure in prose (use a data component): {hit!r}")
        for issue in register_issues(body):
            errors.append(f"{path.name}: register — {issue}")
        if query_key not in meta:
            errors.append(
                f"{path.name}: query_key '{query_key}' is not in articles-meta.json — "
                f"unknown comparison or below the >=5-venue threshold (run article_store --rebuild)"
            )
        # Every published comparison article must carry a stored fact-check
        # report, and it must be clean (no unsupported claims): the article's
        # claims must have been checked against the data (Editorial Gate E2).
        report_path = FACTCHECKS_DIR / f"{path.stem}.json"
        if not report_path.exists():
            errors.append(f"{path.name}: no fact-check report (data/factchecks/{path.stem}.json) — run the pipeline or factcheck_existing")
        else:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            # A deliberate operator force-publish (2026-08-03, TRD.md) carries an
            # `override` record; its unsupported claims stay visible in the report
            # but no longer fail the build. Without an override the block stands.
            if not report.get("override") and (
                report.get("status") == "blocked" or report.get("unsupported_count", 0) > 0
            ):
                errors.append(f"{path.name}: fact-check report has {report.get('unsupported_count', 0)} unsupported claim(s) — must be resolved")
    return errors


def _selftest() -> list[str]:
    """The check must catch a deliberately corrupted body and pass a clean one."""
    failures: list[str] = []
    corrupted = "The cheapest is Bitter Springs at $10, a steal.\nCold plunge sits at 8°C.\nThere are 7 venues."
    if not find_hardcoded_numbers(corrupted):
        failures.append("selftest: scanner failed to catch a hardcoded $/°C/count claim")
    clean = (
        "The cheapest is <Superlative queryKey=\"cheapest\" />, straight from the data.\n"
        "<ComparisonTable queryKey=\"cheapest\" />\n"
        "See the [compare](/compare/) hub for more."
    )
    if find_hardcoded_numbers(clean):
        failures.append(f"selftest: scanner false-positived on clean prose: {find_hardcoded_numbers(clean)}")
    return failures


def main() -> int:
    errors = _selftest() + check_articles()
    if errors:
        print("ARTICLE VALIDATION FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("article data-binding OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
