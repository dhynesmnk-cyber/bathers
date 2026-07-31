# /validate — gate-exit test suite

Run the full validation pass and report results as a pass/fail table. This command must pass clean before any gate is declared done (Gates 1–2: steps 1–4 only) and before any deploy.

1. **Schema validation.** For every MDX file in `site/src/content/spas/_published/` AND `content-staging/_staging/`: parse frontmatter, validate against the SCHEMA.md contract (required fields, types, enums, AU coordinate bounds, summary ≤160 chars, amenity object strict, image field co-requirements). Report per-file, per-field failures.
2. **Slug integrity.** No duplicate slugs across `_staging` + `_published`; all filenames kebab-case.
3. **Derived-data freshness.** Regenerate DB + `venues.json` + `venues.geojson` to a temp location and diff against the committed versions. Any drift = fail (someone edited published content without re-running approve/rebuild).
4. **Astro build.** `cd site && npm run build`. Zero errors, zero warnings.
5. **Link check.** Across the built output: every internal href resolves to a built page; every venue page exists for every slug in `venues.json` and vice versa; every state/amenity page has ≥1 venue; no page links to a draft.
6. **Register lint.** Grep `_published` bodies for the Gatekeeper banned list and for first-person visit tells ("we visited", "on arrival", "I found", "you'll find yourself"). Warnings, not failures — a human judges them — but list every hit with file and line.
7. **Repo hygiene.** `git status` must show no tracked files under `temp_data/`, `content-staging/`, or `.env`. Tracked = fail.

## Gate 6 checks (SEO/AI-citation remediation, 2026-07-31)

8. **Claim-page noindex.** Every built `claim/<slug>/index.html` must contain `<meta name="robots" content="noindex, follow">`; no other page type may. Missing on a claim page, or present anywhere else, = fail.
9. **National-route coverage.** For every amenity in `AMENITY_KEYS` with ≥1 published venue nationally, a `/[amenity-slug]/index.html` must be built AND appear in `sitemap.xml`; likewise every `CROSS_CUTTING_FACILITY_FILTERS` entry with ≥1 venue. An amenity/facility with ≥1 venue but no national route (or missing from the sitemap) = fail. (Pool-type national routes are deliberately excluded — their slugs collide with `/category/`; see `[scope]/index.astro`.)
10. **Region taxonomy lint** (`site/src/data/regions.ts`). Every state in `STATES` has ≥1 region; every published venue's `suburb` resolves via `regionForSuburb(state, suburb)` to exactly one region (zero = orphan = fail, >1 = ambiguous = fail); no region lists a suburb under the wrong state. Report any published suburb with no region as a fail.
11. **Abbreviation cleanup.** A grep of built HTML (and of `site/src/pages`, `site/src/layouts`, `site/src/components`) for the `AMENITY_NOTATION[*].short` codes rendered as a joined notation string (`Mg`, `IR`, `SA`, `CP`, `LED` separated by ` · `) must return zero hits. Full-word amenity labels and pool-type shorts (`Springs`/`Indoor`/`Outdoor`/`Other`) are fine — only the cryptic amenity-code notation is banned.

Output: a summary table (check / result / details), then the word **VALIDATE PASS** or **VALIDATE FAIL** on its own line. Do not fix anything during this command — report only.
