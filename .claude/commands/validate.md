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

## Gate 7 checks (verification metadata / fact model, 2026-07-31)

12. **Fact plausibility.** `python3 -m admin.pipeline.validate_facts` must exit 0. These FAIL (not warn) on *implausible* data only, never on absence: verification completeness (every populated verifiable field carries a source+tier), structured-price cross-validation against the `cost` string, drive-time sanity, coords inside the state bounding box, temperature plausibility, amenity/plunge-temperature consistency, glossary coverage both directions. A deliberately corrupted fixture must fail its matching check (see the module's own fixture test).
13. **Six-surface schema diff.** `python3 -m admin.pipeline.schema_surfaces` must exit 0 — the SCHEMA.md §2 table, the zod schema, and `admin/schema.py`'s `KNOWN_FIELDS` must name exactly the same fields; the SQLite DDL must carry every column the upsert writes; the prompts + preview must describe the structured `price` field. A field added to one surface but not the others = fail.

## Gate 10 checks (comparison & region pages, 2026-07-31)

14. **Internal-linking graph.** After `npm run build`, `python3 -m admin.pipeline.link_graph` must exit 0 — every published venue is linked from ≥3 aggregation pages (comparison, region roll-up, state, or national list), and every comparison/region page is reachable from its `/compare/` or `/region/` hub. Any orphan = fail. Comparison pages below the ≥5-venue threshold must skip-and-log (visible in the build output), never fail.
15. **Comparison-copy audit.** `python3 -m admin.pipeline.comparison_copy` self-test must exit 0 — the Gatekeeper-style audit must drop a deliberately inserted false price/count claim from a lead paragraph while keeping the supported sentences. Comparison-page ItemList JSON-LD and semantic `<table>`/`<caption>`/`<th scope>` markup are asserted by the JSON-LD structural validator (check 16) and the build.

## Gate 11 checks (structured data & E-E-A-T, 2026-07-31)

16. **JSON-LD structural validation.** After `npm run build`, `python3 -m admin.pipeline.jsonld_validator` must exit 0 — every `application/ld+json` block in the built site is valid JSON with `@context`/`@type`, each `@type` is one the site is meant to emit, and required properties (and nested item shapes) are present. Covers `Organization`, `WebSite`, `LocalBusiness` (+`amenityFeature`, `PostalAddress`), `FAQPage`, `BlogPosting`, `ItemList`, `BreadcrumbList`, `DefinedTermSet`, `DefinedTerm`. A missing required property or an unexpected type = fail. (No public Rich Results Test API exists; manual spot-checks with Google's Rich Results Test continue before major pushes.)
17. **llms.txt integrity.** `site/public/llms.txt` must reference only live routes — grep it for `/category/day-spa/` (retired) and any other dead path; every path it lists must resolve in the build.

## Editorial Gate E1 checks (hybrid comparison articles, 2026-08-01)

18. **Article-metadata freshness.** `cd site && node --import ./scripts/ts-register.mjs scripts/refresh-articles.ts --check` must exit 0 — the committed `site/src/data/articles-meta.json` must match what the current `venues.json` + comparison registry produce (report-only; writes nothing). Drift means venue data changed without an article refresh: run `python3 -m admin.pipeline.article_store --rebuild` and commit the result. (This is the article analogue of check 3's venue-data freshness.)
19. **Article data-binding integrity.** `python3 -m admin.pipeline.validate_articles` must exit 0 — every published comparison article (a `site/src/content/blog/_published/` post carrying a `query_key`) must contain no hardcoded numeric/currency/temperature figure in its body (every figure is a `<Figure>`/`<ComparisonTable>`/`<ExtractiveAnswer>`/`<Superlative>` data component, never a literal), and its `query_key` must resolve to a comparison present in `articles-meta.json` (i.e. known and clearing the ≥5-venue threshold). A deliberately corrupted body (a bare `$`/`°C`/count typed into prose) must fail; the module self-tests both the catch and a clean pass.

Output: a summary table (check / result / details), then the word **VALIDATE PASS** or **VALIDATE FAIL** on its own line. Do not fix anything during this command — report only.
