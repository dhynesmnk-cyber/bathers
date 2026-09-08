"""Outreach and provenance integrity (Gate 13, 2026-09-08).

Three things are checked, and they are deliberately different in kind.

**The state machine** (always checkable): `OUTREACH_TRANSITIONS` must describe a
coherent graph — no unknown states, and every state reachable from
`not_contacted`. A typo that quietly made `operator_confirmed` unreachable would
break no test; it would just mean no venue ever gets confirmed, silently.

**Published provenance** (always checkable): `operator_confirmed` is the
strongest claim this site makes about a fact, so every record carrying that tier
must name who confirmed it and when. A tier with an empty or generic source is
an unattributable claim, which is worse than making no claim at all.

**The cross-check against `data/outreach.db`** runs only where that file exists.
It is gitignored by design (operator names, addresses, correspondence notes), so
CI has no copy — the check skips there and says so, rather than failing on an
absence that is correct.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from admin.config import (
    OUTREACH_DB_PATH,
    OUTREACH_STATES,
    OUTREACH_TRANSITIONS,
    PUBLISHED_DIR,
)
from admin.pipeline.staging import split_frontmatter

# A source that only repeats the tier tells a reader nothing. Real ones name a
# person or an address, which is what makes the claim checkable later.
_UNATTRIBUTED = {"", "operator", "the operator", "operator_confirmed", "confirmed"}


def _state_machine_failures() -> list[str]:
    failures: list[str] = []
    known = set(OUTREACH_STATES)

    for origin, destinations in OUTREACH_TRANSITIONS.items():
        if origin not in known:
            failures.append(f"OUTREACH_TRANSITIONS has unknown origin state {origin!r}")
        for destination in destinations:
            if destination not in known:
                failures.append(f"{origin} -> unknown state {destination!r}")

    seen = {"not_contacted"}
    frontier = ["not_contacted"]
    while frontier:
        current = frontier.pop()
        for destination in OUTREACH_TRANSITIONS.get(current, ()):
            if destination not in seen:
                seen.add(destination)
                frontier.append(destination)
    unreachable = sorted(known - seen)
    if unreachable:
        failures.append(
            "state(s) unreachable from not_contacted — no venue could ever reach them: "
            + ", ".join(unreachable)
        )
    return failures


def _provenance_failures() -> list[str]:
    failures: list[str] = []
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"), path.stem)
        for field, record in (frontmatter.get("verification") or {}).items():
            if not isinstance(record, dict) or record.get("tier") != "operator_confirmed":
                continue
            source = str(record.get("source") or "").strip()
            if source.lower() in _UNATTRIBUTED:
                failures.append(
                    f"{path.stem}: verification.{field} claims operator_confirmed with an "
                    f"unattributable source ({source!r}) — the strongest tier must name who "
                    "confirmed it"
                )
            if not record.get("date"):
                failures.append(
                    f"{path.stem}: verification.{field} claims operator_confirmed with no date"
                )
    return failures


def _store_cross_check() -> tuple[list[str], bool]:
    """Confirmed fields in published content should match the outreach record.

    Returns (failures, ran) — `ran` is False where the gitignored DB is absent.
    """
    if not OUTREACH_DB_PATH.exists():
        return [], False
    from admin.pipeline import outreach_store

    rows = {r.slug: r for r in outreach_store.list_rows()}
    failures: list[str] = []
    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"), path.stem)
        confirmed = {
            field
            for field, record in (frontmatter.get("verification") or {}).items()
            if isinstance(record, dict) and record.get("tier") == "operator_confirmed"
        }
        if not confirmed:
            continue
        row = rows.get(path.stem)
        if row is None:
            failures.append(
                f"{path.stem}: publishes operator_confirmed fields but has no outreach record"
            )
            continue
        missing = sorted(confirmed - set(row.confirmed_fields))
        if missing:
            failures.append(
                f"{path.stem}: publishes operator_confirmed for {', '.join(missing)} but the "
                "outreach record does not list them as confirmed"
            )
    return failures, True


def run() -> list[str]:
    failures = _state_machine_failures() + _provenance_failures()
    store_failures, ran = _store_cross_check()
    failures += store_failures
    if not ran:
        print("  (outreach.db absent — store cross-check skipped, as expected in CI)")
    return failures


def _self_test() -> int:
    """Proves each check catches the failure it exists for, and passes a clean
    input — a check that only ever says "no" is not evidence of anything."""
    module = sys.modules[__name__]
    results: list[tuple[str, bool]] = []

    original_transitions = module.OUTREACH_TRANSITIONS
    try:
        module.OUTREACH_TRANSITIONS = {
            "not_contacted": ("contacted",),
            "contacted": ("responded",),
            "responded": (),
        }
        results.append(
            ("an unreachable outcome is caught",
             any("unreachable" in f for f in module._state_machine_failures()))
        )
        module.OUTREACH_TRANSITIONS = {"not_contacted": ("teleported",)}
        results.append(
            ("an unknown destination state is caught",
             any("unknown state" in f for f in module._state_machine_failures()))
        )
    finally:
        module.OUTREACH_TRANSITIONS = original_transitions
    results.append(("the real state machine passes", not module._state_machine_failures()))

    original_dir = module.PUBLISHED_DIR
    try:
        with tempfile.TemporaryDirectory() as tmp:
            module.PUBLISHED_DIR = Path(tmp)
            (module.PUBLISHED_DIR / "good.mdx").write_text(
                "---\nname: Good\nverification:\n  hours:\n"
                "    source: Confirmed by Jo Smith (jo@example.com), 2026-09-08\n"
                "    tier: operator_confirmed\n    date: '2026-09-08'\n---\n\nbody\n",
                encoding="utf-8",
            )
            results.append(
                ("an attributed confirmation passes", not module._provenance_failures())
            )
            (module.PUBLISHED_DIR / "bad.mdx").write_text(
                "---\nname: Bad\nverification:\n  hours:\n    source: operator\n"
                "    tier: operator_confirmed\n    date: '2026-09-08'\n---\n\nbody\n",
                encoding="utf-8",
            )
            results.append(
                ("an unattributable confirmation is caught",
                 any("unattributable" in f for f in module._provenance_failures()))
            )
    finally:
        module.PUBLISHED_DIR = original_dir

    for label, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    return 0 if all(ok for _, ok in results) else 1


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    failures = run()
    if failures:
        print(f"OUTREACH INTEGRITY FAIL — {len(failures)} issue(s):")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print("outreach integrity: pass")


if __name__ == "__main__":
    main()
