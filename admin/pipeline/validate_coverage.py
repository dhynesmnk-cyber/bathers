"""Coverage floor and concentration ceiling (Gate 14, 2026-09-10).

Gate 14's done-condition is a shape for the catalogue, not a feature: every
state and territory carries at least `COVERAGE_FLOOR` published venues, or a
logged and dated reason why it cannot, and no single subdivision holds more than
`CONCENTRATION_CEILING` of the whole. A directory claiming national scope with
two thirds of its venues in one state cannot honestly answer a national
question, and every comparison page it generates is quality-capped by that.

**What fails here and what only reports.** Coverage below the floor is a content
backlog, not a defect: it is reported with a per-subdivision countdown and does
not fail, because failing it would put CI red for as long as the backlog takes
to clear, and a permanently red suite is one nobody reads. The one thing that
fails today is a malformed entry in the reasons file — that is the escape hatch
being used without saying why, which is a defect.

So this module's job right now is to be the authoritative number: how far off
the floor each subdivision is, and how many venues elsewhere the concentration
ceiling needs. Flipping the floor and ceiling to hard failures is a one-line
change (`FLOOR_IS_BLOCKING`), and is what closing Gate 14 should do.

**The reasons file.** `data/coverage-reasons.json` records, per subdivision, a
dated reason the floor is genuinely unreachable — a territory with no qualifying
venues in it, say. It is the escape the gate contract allows, and it is
deliberately narrow: it excuses a subdivision from the *floor*, never from being
counted, and an undated or unexplained entry fails. It is not a place to record
that the work has not been done yet.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

from admin.config import (
    COUNTRIES,
    ROOT,
    SUBDIVISION_NAMES,
    PUBLISHED_DIR,
)
from admin.pipeline.staging import split_frontmatter

COVERAGE_FLOOR = 5
CONCENTRATION_CEILING = 0.40

# Flip to True when Gate 14 closes: from then on, a subdivision below the floor
# without a logged reason is a build failure rather than a reported backlog.
FLOOR_IS_BLOCKING = False

REASONS_PATH = ROOT / "data" / "coverage-reasons.json"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def counts() -> dict[tuple[str, str], int]:
    """(country, subdivision) -> published venue count."""
    tally: dict[tuple[str, str], int] = {}
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"), path.stem)
        key = (frontmatter.get("country", "AU"), frontmatter.get("state_province"))
        tally[key] = tally.get(key, 0) + 1
    return tally


def load_reasons() -> tuple[dict[str, dict], list[str]]:
    """Parsed reasons plus any failures in the file itself."""
    if not REASONS_PATH.exists():
        return {}, []
    try:
        raw = json.loads(REASONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{REASONS_PATH.name} is not valid JSON: {exc}"]

    failures: list[str] = []
    parsed: dict[str, dict] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            failures.append(f"{REASONS_PATH.name}: {key} must be an object with `reason` and `dated`")
            continue
        reason = str(entry.get("reason") or "").strip()
        dated = str(entry.get("dated") or "").strip()
        if len(reason) < 20:
            failures.append(
                f"{REASONS_PATH.name}: {key} needs a real reason the floor is unreachable, "
                "not a placeholder — this excuses a subdivision from the coverage floor"
            )
        if not _DATE_RE.match(dated):
            failures.append(f"{REASONS_PATH.name}: {key} needs a `dated` of YYYY-MM-DD")
        parsed[key] = {"reason": reason, "dated": dated}
    return parsed, failures


def report() -> tuple[list[str], list[str]]:
    """(failures, lines) — `lines` is the human-readable coverage table."""
    tally = counts()
    total = sum(tally.values())
    reasons, failures = load_reasons()
    lines: list[str] = []

    if total == 0:
        return ["no published venues found"], lines

    # Concentration.
    largest_key, largest = max(tally.items(), key=lambda kv: kv[1])
    share = largest / total
    marker = "" if share <= CONCENTRATION_CEILING else (
        f"  <- over the {CONCENTRATION_CEILING:.0%} ceiling; "
        f"needs {_needed_for_ceiling(largest, total)} more venues elsewhere"
    )
    lines.append(
        f"{total} venues; largest is {largest_key[0]}/{largest_key[1]} at "
        f"{largest} ({share:.0%}){marker}"
    )

    # Per-subdivision floor.
    shortfalls: list[str] = []
    for country in COUNTRIES:
        for code in SUBDIVISION_NAMES[country]:
            count = tally.get((country, code), 0)
            # Only subdivisions the directory actually claims are held to the
            # floor: every AU state and territory, and any non-AU subdivision
            # that already has a venue. Holding all 51 US states to the floor
            # before a single US venue exists would be noise, not a signal.
            claimed = country == "AU" or count > 0
            if not claimed:
                continue
            key = f"{country}/{code}"
            if count >= COVERAGE_FLOOR:
                continue
            if key in reasons:
                lines.append(
                    f"  {key}: {count} — excused {reasons[key]['dated']}: {reasons[key]['reason']}"
                )
                continue
            shortfalls.append(f"  {key}: {count} of {COVERAGE_FLOOR} (needs {COVERAGE_FLOOR - count} more)")

    if shortfalls:
        lines.append(f"below the floor of {COVERAGE_FLOOR} ({len(shortfalls)} subdivision(s)):")
        lines.extend(shortfalls)
        if FLOOR_IS_BLOCKING:
            failures.extend(s.strip() + " — below the coverage floor" for s in shortfalls)
    else:
        lines.append(f"every claimed subdivision is at or above the floor of {COVERAGE_FLOOR}")

    if share > CONCENTRATION_CEILING and FLOOR_IS_BLOCKING:
        failures.append(
            f"{largest_key[0]}/{largest_key[1]} holds {share:.0%} of the catalogue, "
            f"over the {CONCENTRATION_CEILING:.0%} ceiling"
        )
    return failures, lines


def _needed_for_ceiling(largest: int, total: int) -> int:
    """How many venues elsewhere would bring the largest subdivision's share to
    the ceiling. Solves largest / (total + n) <= ceiling for n."""
    required_total = math.ceil(largest / CONCENTRATION_CEILING)
    return max(0, required_total - total)


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    failures, lines = report()
    for line in lines:
        print(line)
    if failures:
        print(f"COVERAGE FAIL — {len(failures)} issue(s):")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print("coverage: pass" + ("" if FLOOR_IS_BLOCKING else " (floor reported, not blocking — see module docstring)"))


def _self_test() -> int:
    """Proves the reasons-file validation and the ceiling arithmetic, and that a
    clean input passes — a check that only ever says "no" proves nothing."""
    module = sys.modules[__name__]
    results: list[tuple[str, bool]] = []

    import tempfile

    original_path = module.REASONS_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            module.REASONS_PATH = Path(tmp) / "coverage-reasons.json"

            module.REASONS_PATH.write_text('{"AU/NT": {"reason": "x", "dated": "2026-09-10"}}', encoding="utf-8")
            _, failures = module.load_reasons()
            results.append(("a placeholder reason is rejected", any("placeholder" in f for f in failures)))

            module.REASONS_PATH.write_text(
                '{"AU/NT": {"reason": "No qualifying pool or sauna venue exists in the territory.", "dated": "not-a-date"}}',
                encoding="utf-8",
            )
            _, failures = module.load_reasons()
            results.append(("an undated reason is rejected", any("dated" in f for f in failures)))

            module.REASONS_PATH.write_text("{not json", encoding="utf-8")
            _, failures = module.load_reasons()
            results.append(("malformed JSON is rejected", any("not valid JSON" in f for f in failures)))

            module.REASONS_PATH.write_text(
                '{"AU/NT": {"reason": "No qualifying pool or sauna venue exists in the territory.", "dated": "2026-09-10"}}',
                encoding="utf-8",
            )
            parsed, failures = module.load_reasons()
            results.append(("a proper reason passes", not failures and "AU/NT" in parsed))
    finally:
        module.REASONS_PATH = original_path

    # 26 of 39 is 67%; reaching 40% needs a catalogue of 65, so 26 more.
    results.append(("ceiling arithmetic", module._needed_for_ceiling(26, 39) == 26))
    # Already under the ceiling: nothing needed.
    results.append(("no shortfall when under the ceiling", module._needed_for_ceiling(10, 100) == 0))

    for label, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    main()
