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
9. **National-route coverage.** For every amenity in `AMENITY_KEYS` with ≥1 published venue nationally, a `/[amenity-slug]/index.html` must be built AND appear in `sitemap.xml`; likewise every `CROSS_CUTTING_FACILITY_FILTERS` entry and every `POOL_NATIONAL_FILTERS` entry with ≥1 venue. An amenity/facility/pool-setting with ≥1 venue but no national route (or missing from the sitemap) = fail. (Gate E3, 2026-08-01, added national pool-setting routes `/indoor-pool/`, `/outdoor-pool/`, `/natural-spring/` — descriptive slugs that don't shadow `/category/` or `/[state]/[pooltype]/`; the residual `other` pool setting has no national page. See `[scope]/index.astro`.)
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

## Editorial Gate E3 checks (SEO/GEO routing cleanup, 2026-08-01)

20. **Routing hygiene.** `python3 -m admin.pipeline.validate_routing` must exit 0 — after `npm run build`, no internal `<a href>` in the built site emits a query-param URL (Gate E3 pointed the homepage + corner-menu chooser links at static national routes — amenity pages and the new `/indoor-pool/`·`/outdoor-pool/`·`/natural-spring/` pool pages — so crawlers never index the client-only `/?amenities=`/`/?pooltype=` filter space), and the homepage `<link rel="canonical">` is the apex root `/` with no query/fragment. External links carrying query strings are ignored. The module self-tests both checks against corrupted fixtures.

## Editorial Gate E4a checks (opportunity queue + brief gate, 2026-08-01)

21. **Article intent-uniqueness.** `python3 -m admin.pipeline.validate_intents` must exit 0 — no `query_key` in `site/src/content/blog/_published/` is carried by more than one post. One search intent, one comparison article: this is the invariant the opportunity queue's dedupe and the `/compare/<key>/ → /blog/<slug>/` 301 both rely on (two articles for one intent is the self-competition the model exists to avoid). Essays (no `query_key`) are ignored. A deliberately corrupted fixture (two files sharing a `query_key`) must fail; the module self-tests both the catch and a clean pass. *(The opportunity queue and brief gate themselves live in the admin-only, gitignored `articles.db` and so aren't build-gate-checkable; this asserts their published-layer invariant.)*

## Editorial Gate E4b checks (OG cards + AI header images, 2026-08-01)

22. **OG image integrity.** `python3 -m admin.pipeline.validate_og` must exit 0 — after `npm run build`, every venue (`spa/*`) and article (`blog/*`) page emits a *page-specific* `og:image` (a real venue photo / blog cover, or its generated `/og/<slug>.png` card via `admin.pipeline.og_cards`, never the sitewide default `/images/og-share.webp`) that resolves to a built file, with a non-empty `og:image:alt`; and any blog post flagged `cover_image_ai` carries a `cover_image_credit` (AI imagery must be attributed — also a zod rule, asserted here independently). Deliberately corrupted fixtures (default og:image, unresolved card, empty alt, AI cover with no credit) must each fail; the module self-tests every case plus a clean pass. *(Cards render via the existing Playwright/chromium, not Pillow — the brand fonts are woff2-only; see `og_cards.py`.)*

## Gate 12 checks (admin hardening & operational safety, 2026-09-08)

23. **Admin security self-test.** `python3 -m admin.security` must exit 0 — blank credentials must refuse to start (the fail-open hole this gate closed), an explicit `ADMIN_ALLOW_INSECURE_AUTH` must still permit a local unauthenticated run, Basic Auth must accept only the configured pair, an uploaded photo must be identified by its magic bytes rather than its declared Content-Type (a PDF or HTML payload labelled `image/png` fails; a PNG mislabelled `image/jpeg` is stored as `.png`), oversized and undeclared public bodies must be refused, the throttle must lock out and release, and a caller-supplied `X-Forwarded-For` must never win over the Fly-set peer address. Each check asserts both the rejection and the matching clean pass.

24. **Backup integrity.** `python3 -m admin.pipeline.backup --self-test` must exit 0 — a snapshot taken while a writer holds the database open must restore with every committed row intact, a deliberately corrupted archive must fail verification (sha256 or `PRAGMA integrity_check`), an unknown snapshot name must be refused, and retention must prune to the newest N. Separately, **run the restore drill quarterly** per SECURITY.md §4: restore into a scratch directory, point the admin at it, confirm claims list unchanged. A backup nobody has restored is a hypothesis.

25. **Repo hygiene, extended** (folded into check 7). `git ls-files` must return nothing under `temp_data/`, `content-staging/`, `.env*` (except `.env.example`), `data/claims.db` or `data/articles.db`. The last two were asserted as gitignored by four separate code comments while `.gitignore` did not in fact list them; `claims.db` holds requester PII.

## Place-hierarchy checks (global URL structure, 2026-09-08)

26. **Place hierarchy.** `python3 -m admin.pipeline.validate_places` must exit 0 — area slugs and feature-filter slugs must not collide within a subdivision (they share one URL slot, and a collision silently drops one page with no build error); every published venue's `country` must belong to a declared world region and its `state_province` to that country; and in the built output every level of `/places/` must link the one below it (hub → world region → country → subdivision → leaf). `--self-test` proves the collision check catches a deliberately colliding fixture and passes a normal one.

## Gate 13 checks (operator outreach, 2026-09-08)

27. **Outreach & provenance integrity.** `python3 -m admin.pipeline.validate_outreach` must exit 0 — the `OUTREACH_TRANSITIONS` graph must name only known states and leave none unreachable from `not_contacted` (a typo making `operator_confirmed` unreachable breaks no test, it just silently means no venue is ever confirmed); and every published `operator_confirmed` record must name who confirmed it and when, since that tier is the strongest claim the site makes and an unattributable one is worse than none. The cross-check against `data/outreach.db` runs only where that file exists — it is gitignored (operator names, addresses, correspondence notes), so CI skips it and says so. `--self-test` proves each check catches its own failure and passes a clean input.

**CI.** `.github/workflows/validate.yml` runs the mechanisable subset of this file on every push. The checks it does not cover — 1/2 (subsumed by the build), 5, 6 (advisory by design), and 8–11 (still prose, not modules) — are listed at the bottom of that workflow so the gap stays written down.

Output: a summary table (check / result / details), then the word **VALIDATE PASS** or **VALIDATE FAIL** on its own line. Do not fix anything during this command — report only.
