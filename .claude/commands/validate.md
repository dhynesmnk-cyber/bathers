# /validate — gate-exit test suite

Run the full validation pass and report results as a pass/fail table. This command must pass clean before any gate is declared done (Gates 1–2: steps 1–4 only) and before any deploy.

1. **Schema validation.** For every MDX file in `site/src/content/spas/_published/` AND `content-staging/_staging/`: parse frontmatter, validate against the SCHEMA.md contract (required fields, types, enums, AU coordinate bounds, summary ≤160 chars, amenity object strict, image field co-requirements). Report per-file, per-field failures.
2. **Slug integrity.** No duplicate slugs across `_staging` + `_published`; all filenames kebab-case.
3. **Derived-data freshness.** Regenerate DB + `venues.json` + `venues.geojson` to a temp location and diff against the committed versions. Any drift = fail (someone edited published content without re-running approve/rebuild).
4. **Astro build.** `cd site && npm run build`. Zero errors, zero warnings.
5. **Link check.** Across the built output: every internal href resolves to a built page; every venue page exists for every slug in `venues.json` and vice versa; every state/amenity page has ≥1 venue; no page links to a draft.
6. **Register lint.** Grep `_published` bodies for the Gatekeeper banned list and for first-person visit tells ("we visited", "on arrival", "I found", "you'll find yourself"). Warnings, not failures — a human judges them — but list every hit with file and line.
7. **Repo hygiene.** `git status` must show no tracked files under `temp_data/`, `content-staging/`, or `.env`. Tracked = fail.

Output: a summary table (check / result / details), then the word **VALIDATE PASS** or **VALIDATE FAIL** on its own line. Do not fix anything during this command — report only.
