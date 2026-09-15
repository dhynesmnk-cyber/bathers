"""Six-surface schema diff (Gate 7, 2026-07-31) — the concrete guard against
the drift risk SCHEMA.md's "one contract, propagate to all in the same commit"
rule warns about. A frontmatter field that lands in the zod schema but not the
admin validator (or the SCHEMA.md table) validates in one layer and silently
fails in another; this check makes that a hard failure.

Compares the three machine-readable *field-set* surfaces for exact agreement:
  1. SCHEMA.md §2/§2a frontmatter table
  2. the zod content schema (site/src/content/config.ts)
  3. admin/schema.py's KNOWN_FIELDS
and checks the SQLite DDL columns match data_store's VENUE_SCALAR_COLUMNS, and
that the two prose surfaces (prompts, mdx_preview) mention the new structured
fields. Run via /validate; `run()` returns failure strings.

The *Harvester's* JSON contract (2026-09-10) is diffed the same way, across its
own three surfaces: the object literal in PROMPTS/harvester.md, the one in
SCHEMA.md §4, and orchestrator.HARVESTER_REQUIRED_KEYS. Both literals are real
JSON, so this is an exact key diff rather than a grep. It exists because that
contract had drifted twice over: SCHEMA.md §4 still described the retired
`state`/`suburb` fields three weeks after the migration renamed them, and
`zipcode` was asked for by the prompt while nothing validated that it came
back — the same silence that left `contact_email` uncollected on all 39 venues.
"""

from __future__ import annotations

import json
import re

from admin.config import ROOT
from admin.pipeline import data_store, orchestrator, staging
from admin.schema import KNOWN_FIELDS


def _schema_md_fields() -> set[str]:
    text = (ROOT / "SCHEMA.md").read_text(encoding="utf-8")
    section = text.split("## 2. MDX Frontmatter", 1)[-1].split("## 3.", 1)[0]
    return set(re.findall(r"^\| `(\w+)`", section, re.MULTILINE))


def _zod_fields() -> set[str]:
    text = (ROOT / "site/src/content/config.ts").read_text(encoding="utf-8")
    block = text.split("const spasCollection", 1)[-1].split("const blogCollection", 1)[0]
    # Top-level venue keys are 6-space indented and their value is a zod
    # expression (`z.` inline, or `z` then a line-broken `.method()`) or a
    # *Schema helper — excludes refine()'s message:/path: string/array values.
    return set(re.findall(r"^      (\w+):\s*(?:z\b|\w+Schema)", block, re.MULTILINE))


def _ddl_columns() -> set[str]:
    return set(re.findall(r"^\s*(\w+)\s+(?:TEXT|REAL|INTEGER)", data_store.SCHEMA_SQL, re.MULTILINE))


def _json_object(text: str, label: str) -> tuple[set[str], str | None]:
    """Top-level keys of the first `{...}` object literal in `text`."""
    match = re.search(r"^\{$.*?^\}$", text, re.MULTILINE | re.DOTALL)
    if not match:
        return set(), f"{label} contains no JSON object literal for the Harvester contract"
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return set(), f"{label}'s Harvester JSON literal does not parse: {exc}"
    if not isinstance(parsed, dict):
        return set(), f"{label}'s Harvester JSON literal is not an object"
    return set(parsed), None


def _harvester_contract_failures() -> list[str]:
    failures: list[str] = []
    surfaces: dict[str, set[str]] = {}

    prompt_keys, error = _json_object(
        (ROOT / "PROMPTS/harvester.md").read_text(encoding="utf-8"), "PROMPTS/harvester.md"
    )
    if error:
        failures.append(error)
    else:
        surfaces["PROMPTS/harvester.md"] = prompt_keys

    schema_section = (
        (ROOT / "SCHEMA.md").read_text(encoding="utf-8")
        .split("## 4. Harvester JSON output", 1)[-1]
        .split("## 5.", 1)[0]
    )
    schema_keys, error = _json_object(schema_section, "SCHEMA.md §4")
    if error:
        failures.append(error)
    else:
        surfaces["SCHEMA.md §4"] = schema_keys

    required = set(orchestrator.HARVESTER_REQUIRED_KEYS)
    for label, keys in surfaces.items():
        only_prompt = keys - required
        only_code = required - keys
        if only_prompt:
            failures.append(
                f"{label} asks the Harvester for key(s) that HARVESTER_REQUIRED_KEYS does not "
                f"validate, so a missing one would pass silently: {', '.join(sorted(only_prompt))}"
            )
        if only_code:
            failures.append(
                f"HARVESTER_REQUIRED_KEYS requires key(s) {label} never asks for, so every "
                f"harvest would fail validation: {', '.join(sorted(only_code))}"
            )

    return failures


def run() -> list[str]:
    failures: list[str] = _harvester_contract_failures()

    # 2026-09-08: render_frontmatter() writes ONLY the keys listed in
    # FRONTMATTER_FIELD_ORDER, so a known field missing from it is silently
    # dropped on every admin re-save. That is exactly what happened to
    # country/state_province/city in the international migration, and it is
    # invisible until a rebuild or a build fails afterwards. Asserted here
    # because this tuple is a schema surface like the other three.
    missing_from_order = KNOWN_FIELDS - set(staging.FRONTMATTER_FIELD_ORDER)
    if missing_from_order:
        failures.append(
            "fields in admin KNOWN_FIELDS but not staging.FRONTMATTER_FIELD_ORDER "
            f"(render_frontmatter would DROP these on any re-save): {', '.join(sorted(missing_from_order))}"
        )

    schema_md = _schema_md_fields()
    zod = _zod_fields()
    admin = KNOWN_FIELDS

    for label_a, a, label_b, b in (
        ("zod", zod, "admin KNOWN_FIELDS", admin),
        ("zod", zod, "SCHEMA.md §2 table", schema_md),
    ):
        only_a = a - b
        only_b = b - a
        if only_a:
            failures.append(f"fields in {label_a} but not {label_b}: {', '.join(sorted(only_a))}")
        if only_b:
            failures.append(f"fields in {label_b} but not {label_a}: {', '.join(sorted(only_b))}")

    # SQLite DDL must carry every scalar column data_store's upsert writes.
    ddl_cols = _ddl_columns()
    for col in data_store.VENUE_SCALAR_COLUMNS:
        if col not in ddl_cols:
            failures.append(f"SQLite DDL is missing column '{col}' that upsert writes")

    # Prose surfaces: the structured price field must be described where the
    # Architect/Gatekeeper and the review preview reference pricing.
    for rel in ("PROMPTS/architect.md", "PROMPTS/gatekeeper.md", "admin/mdx_preview.py"):
        if "price" not in (ROOT / rel).read_text(encoding="utf-8"):
            failures.append(f"{rel} does not mention the structured 'price' field")

    # The Harvester's key list is diffed above, but a key can be present in the
    # literal with no rule governing it. `contact_email` is the one field here
    # used to write to a real business, so its honesty rule (published or null,
    # never pattern-built) must stay in the prompt's prose too.
    harvester = (ROOT / "PROMPTS/harvester.md").read_text(encoding="utf-8")
    if "never build one from the domain" not in harvester.lower():
        failures.append(
            "PROMPTS/harvester.md no longer forbids pattern-building contact_email from the "
            "domain — see SCHEMA.md §4's note and harvester rule 9"
        )

    # Collected, never published (owner decision, 2026-09-15). `contact_email`
    # is the one field that must appear in the Harvester's contract and in none
    # of the frontmatter surfaces, so the usual "all surfaces agree" diff would
    # not catch it being re-added — this asserts the asymmetry directly.
    # `_published/` is committed to a public repository; an operator's address
    # reaching it would be a disclosure, not a bug to fix next release.
    for label, names in (
        ("admin KNOWN_FIELDS", admin),
        ("SCHEMA.md §2 table", schema_md),
        ("the zod content schema", zod),
        ("staging.FRONTMATTER_FIELD_ORDER", set(staging.FRONTMATTER_FIELD_ORDER)),
    ):
        if "contact_email" in names:
            failures.append(
                f"contact_email is back in {label} — it is collected for outreach and stored in "
                "the gitignored outreach.db (outreach.published_email), and must never become "
                "published frontmatter. See SCHEMA.md §4's note."
            )

    return failures


def main() -> None:
    failures = run()
    if failures:
        print(f"SCHEMA SURFACE DIFF FAIL — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("schema surface diff: pass")


if __name__ == "__main__":
    main()
