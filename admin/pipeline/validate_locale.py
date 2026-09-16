"""Locale check (Gate 16, 2026-09-15 — CLAUDE.md rule 7).

Until this module existed, the Australian-English rule was enforced entirely by
prompt and by eye: the Gatekeeper was told to apply it, `/validate` check 6
greps only for banned *marketing* words, and nothing anywhere compared a venue's
prose against the spelling its own country implies. That was survivable while
every venue was Australian. With two locales in the catalogue it is not — a US
entry written in Australian English, or an Australian one drifting into -ize,
reads plausibly and is wrong, and nothing would have said so.

What it does NOT do: judge register, vocabulary or quality. It looks for a
handful of unambiguous orthographic and lexical markers that belong to one
locale and not the other, in the venue's own body prose. Frontmatter is exempt —
`cost`, `hours` and `address` quote the venue's own wording, and a US venue's
address really does say "Center".

Markers are deliberately few and deliberately certain. A word that is correct in
both (program/programme both exist in AU usage; "meter" is a measuring device
everywhere) earns its place only where the surrounding pattern makes it
unambiguous, or it is left out. A false positive here fails a build over a
correctly spelled word, which is worse than a missed one.
"""

from __future__ import annotations

import re
import sys

from admin.config import COUNTRY_LOCALE, DEFAULT_COUNTRY, PUBLISHED_DIR
from admin.pipeline.staging import split_frontmatter

# (pattern, the locale it belongs to, a human name for the report)
MARKERS: list[tuple[str, str, str]] = [
    # -ise / -ize on the verbs this directory actually uses
    (r"\b(?:special|organ|real|minim|maxim|recogn|emphas|prior)ise[sd]?\b", "en-AU", "-ise spelling"),
    (r"\b(?:special|organ|real|minim|maxim|recogn|emphas|prior)ize[sd]?\b", "en-US", "-ize spelling"),
    # -our / -or
    (r"\b(?:colour|harbour|favour|flavour|neighbour|odour|vapour)(?:s|ed|ing)?\b", "en-AU", "-our spelling"),
    (r"\b(?:color|harbor|favor|flavor|neighbor|odor|vapor)(?:s|ed|ing)?\b", "en-US", "-or spelling"),
    # -re / -er, only where the -er form is not also a common noun
    (r"\b(?:centre|litre|fibre|theatre)s?\b", "en-AU", "-re spelling"),
    (r"\b(?:center|liter|fiber|theater)s?\b", "en-US", "-er spelling"),
    # everyday nouns that differ outright
    (r"\bbathers\b", "en-AU", "'bathers' for swimwear"),
    (r"\b(?:swimsuit|bathing suit|faucet|vacation)s?\b", "en-US", "US vocabulary"),
    # units in prose
    (r"\b\d+\s*(?:°\s*)?C\b|\bdegrees Celsius\b|\bkilometres?\b", "en-AU", "metric units"),
    (r"\b\d+\s*(?:°\s*)?F\b|\bdegrees Fahrenheit\b|\bmiles\b", "en-US", "US customary units"),
]


def check_body(slug: str, country: str, body: str) -> list[str]:
    """Markers from the locale this venue does NOT use."""
    want = COUNTRY_LOCALE.get(country, COUNTRY_LOCALE[DEFAULT_COUNTRY])
    out: list[str] = []
    for pattern, locale, label in MARKERS:
        if locale == want:
            continue
        hits = sorted({m.group(0) for m in re.finditer(pattern, body, re.IGNORECASE)})
        if hits:
            out.append(
                f"{slug} ({country}, expects {want}): {label} from {locale} — {', '.join(hits[:5])}"
            )
    return out


def run() -> list[str]:
    failures: list[str] = []
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        try:
            data, body = split_frontmatter(path.read_text(encoding="utf-8"), path.stem)
        except ValueError as exc:
            failures.append(f"{path.stem}: unreadable frontmatter — {exc}")
            continue
        failures.extend(check_body(path.stem, data.get("country", DEFAULT_COUNTRY), body))
    return failures


def self_test() -> int:
    """A check that only ever passes is indistinguishable from one that checks
    nothing, so each direction is asserted against a fixture, both ways."""
    problems: list[str] = []

    au_in_us = check_body(
        "fixture", "US",
        "The centre has a magnesium pool at 39°C. Bring your bathers; the colour surprises people.",
    )
    if not au_in_us:
        problems.append("a US venue written in Australian English was not caught")

    us_in_au = check_body(
        "fixture", "AU",
        "The center offers a specialized program. The water is 102°F and the color is striking.",
    )
    if not us_in_au:
        problems.append("an AU venue drifting into US English was not caught")

    if check_body("fixture", "US", "The center has a mineral pool at 102°F. Bring a swimsuit."):
        problems.append("a correctly US-spelled US venue was flagged")
    if check_body("fixture", "AU", "The centre has a magnesium pool at 39°C. Bring your bathers."):
        problems.append("a correctly AU-spelled AU venue was flagged")

    for line in problems:
        print(f"FAIL self-test: {line}")
    print(f"locale self-test: {len(problems)} problem(s)")
    return 1 if problems else 0


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    failures = run()
    for line in failures:
        print(f"FAIL {line}")
    print(f"locale: {len(failures)} problem(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
