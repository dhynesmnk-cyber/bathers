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

from admin.config import ARTICLES_META_JSON_PATH, BLOG_PUBLISHED_DIR

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
        if query_key not in meta:
            errors.append(
                f"{path.name}: query_key '{query_key}' is not in articles-meta.json — "
                f"unknown comparison or below the >=5-venue threshold (run article_store --rebuild)"
            )
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
