"""One-time backfill of the new `category` and `verified` fields (SCHEMA.md
§2, 2026-07-22) onto venues published before either field existed. This is a
deliberate, narrow exception to CLAUDE.md rule 5 ("never touch `_published`
by hand") — it goes through the same `staging.split_frontmatter`/`render_mdx`
helpers a normal approve would use, so field ordering stays canonical, and it
only ever sets keys that are currently absent.

`verified` backfills to the existing `drafted` date — these venues were
never re-harvested, so "last verified" and "first drafted" are the same
point in time for them; every venue drafted from here on gets a real
`verified` date from the pipeline itself (orchestrator._finalize_frontmatter).

Dry-run by default; pass --apply to actually write. Usage:

    python -m admin.pipeline.migrate_category            # preview only
    python -m admin.pipeline.migrate_category --apply    # write + rebuild
"""

from __future__ import annotations

import argparse
import datetime

from admin.config import CATEGORY_KEYS, PUBLISHED_DIR
from admin.pipeline import data_store
from admin.pipeline.staging import render_mdx, split_frontmatter

# Editorial call, confirmed with the site owner (2026-07-22) — see the three
# published venues' summaries: Aurora is a subterranean bathhouse built
# around an 11-step thermal ritual; Chuan Spa is a hotel treatment spa;
# Sense of Self is a mineral bath/sauna/plunge/hammam venue.
CATEGORY_ASSIGNMENTS = {
    "aurora-spa-bathhouse": "bathhouse",
    "chuan-spa": "day_spa",
    "sense-of-self": "bathhouse",
}


def migrate(apply: bool) -> None:
    for slug, category in CATEGORY_ASSIGNMENTS.items():
        if category not in CATEGORY_KEYS:
            raise ValueError(f"{slug}: '{category}' is not a valid category")
        path = PUBLISHED_DIR / f"{slug}.mdx"
        if not path.exists():
            print(f"skip {slug} — not found in _published")
            continue
        data, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        changes = []
        if "category" not in data:
            data["category"] = category
            changes.append(f"category={category}")
        if "verified" not in data:
            drafted = data.get("drafted")
            # A fresh date object, not the same one stored under `drafted` —
            # otherwise PyYAML emits an anchor/alias pair (&id001/*id001)
            # for the repeated reference, which is valid but not how any
            # other file in this repo is formatted.
            data["verified"] = datetime.date(drafted.year, drafted.month, drafted.day)
            changes.append(f"verified={data['verified']}")
        if not changes:
            print(f"skip {slug} — already has category and verified")
            continue
        print(f"{'write' if apply else 'would write'} {slug} — {', '.join(changes)}")
        if apply:
            path.write_text(render_mdx(data, body), encoding="utf-8")

    if apply:
        count = data_store.rebuild()
        print(f"rebuilt {count} venue(s)")
    else:
        print("dry run — pass --apply to write and rebuild")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually write the files and rebuild the DB")
    args = parser.parse_args()
    migrate(apply=args.apply)


if __name__ == "__main__":
    main()
