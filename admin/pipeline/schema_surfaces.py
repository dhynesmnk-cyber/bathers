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
"""

from __future__ import annotations

import re

from admin.config import ROOT
from admin.pipeline import data_store
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


def run() -> list[str]:
    failures: list[str] = []

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
