# CLAUDE.md — Operating Instructions

You are building the project specified in TRD.md. Read TRD.md, SCHEMA.md, UX.md, and DESIGN.md before writing any code. This file governs *how* you work.

## Prime rules

1. **Gates are sequential and blocking.** Work happens inside the current gate only. When a gate's done-condition passes, stop, summarise what was built and how you verified it, and wait for explicit approval before starting the next gate. Never begin work from a later gate "while you're in there."
2. **Ask before adding any dependency** not already named in TRD.md — npm or pip, however small. State what it's for and what the no-dependency alternative would be.
3. **Never invent scope.** If the spec docs don't cover something, ask. If two docs conflict, the more specific document wins (SCHEMA.md > TRD.md for data; UX.md/DESIGN.md > TRD.md for interface); flag the conflict either way.
4. **File pathing:** all cross-cutting paths (content dirs, DB path, temp dirs) are defined once — `admin/config.py` for Python, `site/src/config.ts` for Astro — and imported everywhere else. No hardcoded relative paths in feature code. All Python file operations use `pathlib` and are safe to run from the repo root.
5. **Never touch:** `.env` (read-only, never commit, never print its values), anything in `temp_data/` manually, git history (no rebase/force-push), the `_published` directory by hand (only the approve action writes there).
6. **Honesty in generated content:** the pipeline's Architect agent writes documented profiles, never fabricated first-hand visits. If you write or edit prompts, preserve this rule.
7. **Locale follows the content's country** (amended 2026-09-15, Gate 16). Australian English for AU content, US English for US content — the Gatekeeper carries both variants and is told which one applies. Shared, country-neutral surfaces (the tagline, the glossary, the admin UI, the methodology page) stay Australian English: it is the house voice, and a page that belongs to no country has no reason to leave it. Until 2026-09-15 this rule was "Australian English in all user-facing copy"; it changed because the directory now publishes in a second country, not because the house voice moved.

## Stack constraints (recap — full detail in TRD.md §2)

Astro 5 SSG + Tailwind v4. FastAPI + Jinja2 + vanilla JS (no React/SPA in admin). SQLite via stdlib `sqlite3`. httpx + trafilatura (Playwright fallback only). Anthropic SDK; model IDs from `.env`. `gsap` (2026-07-30 exception, TRD.md §2) for in-page scroll effects only. Nothing else without asking (rule 2). *(No Leaflet — the map was added then removed 2026-07-26; TRD.md §2 has the full record.)*

## Commands

```bash
# site
cd site && npm run dev          # Astro dev server
cd site && npm run build        # static build — must pass with zero warnings for gate exits
# admin
uvicorn admin.app:app --reload --port 8787
# data
python -m admin.pipeline.data_store --rebuild   # rebuild DB + JSON + GeoJSON from _published
# validation (gate-exit test — see .claude/commands/validate.md)
/validate
```

## The Gates

### Gate 1 — Astro scaffold + content schema
Astro project initialised per TRD §3; Tailwind configured with DESIGN.md tokens as CSS custom properties; content collection `spas` with the full zod schema from SCHEMA.md; the sample MDX from SCHEMA.md §5 placed in `_published`; base layout with fonts, grain overlay, palette; `VenueEntry`, `Notation`, `Pull`, `TippedPhoto` components stubbed with real styles.
**Done when:** `npm run build` passes with the sample venue; deliberately corrupting one frontmatter field (wrong type, missing required) fails the build with a clear error; the rendered sample page passes the DESIGN.md §10 screenshot test; site renders correctly with JS disabled.

### Gate 2 — Data layer + data model
`data_store.py` per TRD §5: schema creation, rebuild-from-published, upsert-on-slug, `venues.json` + `venues.geojson` generation. CLI rebuild command works.
**Done when:** rebuild from the sample MDX produces correct DB rows and both derived files; running rebuild twice is byte-identical (idempotent); editing the sample's amenities and rebuilding updates rather than duplicates; deleting `directory.db` and rebuilding restores it exactly.

### Gate 3 — Admin UI shell + staging queue
FastAPI app serving the single-screen layout from UX.md §1: harvest panel (log pane wired, pipeline stubbed), review queue reading `content-staging/_staging/`, review pane with rendered preview (public CSS), frontmatter editor with amenity notation toggles + coordinate thumbnail + debounced autosave, approve/reject actions (move + upsert + regenerate + undo window), keyboard shortcuts, empty states.
**Done when:** with three hand-placed staging MDX files: full keyboard review session works end-to-end; approving lands the file in `_published`, updates DB/JSON/GeoJSON, and the site builds with it; rejecting moves to `_rejected` with reason sidecar; schema-invalid staging file is blocked from approval with field-level errors; undo within 3s fully reverses an approve.

### Gate 4 — AI pipeline integration
Harvester → Architect → Gatekeeper wired per TRD §7 and PROMPTS/, streaming each stage to the log; candidate-image download to `temp_data/images/<slug>/`; image thumbnail strip + separate publish-image action per UX.md §4; all failure states in UX.md §1.5.
**Done when:** each URL in SEED.md runs end-to-end producing a schema-valid staged draft; the drafts read per the Gatekeeper's rules (spot-check: no banned words, Australian spelling, no fabricated visit claims); a deliberately bad URL and a malformed-JSON simulation both fail per the failure table; token usage appears in the log.

### Gate 5 — Map + deploy trigger
Leaflet map chapter on the index per UX.md §2.1 (clustering, marker→list scroll, filter sync to URL, styled tiles, no-JS fallback); programmatic state/amenity pages with forewords.json; deploy strip per UX.md §1.4 with diff preview and tracked-file guard.
**Done when:** map renders all published venues and filters in sync with the list; URL-with-filters reloads to the same view; only legal paths appear in the deploy diff and the guard refuses a deliberately tracked `temp_data` file; `/validate` passes clean; full flow harvest→approve→deploy executes against a SEED.md venue.

*(2026-07-26: the map was removed — see TRD.md §2. Gate 5 shipped and closed before that revision; its done-condition stands as history, not a live requirement.)*

---

**2026-07-31: SEO/AI-citation remediation engagement approved.** Gates 1–5 are complete and the site is live at wherewebathe.com. Gates 6–11 below are new scope, sequenced and blocking per rule 1 exactly like Gates 1–5. Full context, rationale, risk flags, and cross-references for every item below live in the approved roadmap at `~/.claude/plans/where-we-bathe-bubbly-sunrise.md` — that document is the working reference; this section is the operational gate contract (scope + done-when) in the house style of Gates 1–5.

### Gate 6 — Technical & discoverability foundation + abbreviation cleanup
Netlify apex 301 (`.netlify.app` → `wherewebathe.com`); GSC + Bing Webmaster Tools verification against the apex; sitemap/robots confirm-pass; `noindex, follow` on `/claim/[slug]/`; IndexNow key file + ping wired into `admin/pipeline/deploy.py`'s post-push flow; national (cross-state) amenity routes (`/magnesium-pool/` etc.) mirroring `[state]/[filter].astro`'s pattern; region-taxonomy **data file** only (route generation deferred to Gate 10); the two remaining `Mg · IR · SA · CP · LED` spots (`[state]/index.astro:24-25`, `[state]/[filter].astro:82,92`) rewritten to natural-language titles + hand-written 140–155-char meta descriptions.
**Done when:** `.netlify.app` 301s to the apex on homepage + one deep path; GSC and Bing both show verified on `wherewebathe.com` with the sitemap submitted; every claim page emits `noindex, follow`, asserted in `/validate`; a national amenity route resolves for every amenity with ≥1 venue nationally and appears in `sitemap.xml`; the region data file lints clean (every state ≥1 region, every published venue's suburb resolves to exactly one region, no orphans); a sitewide grep for the notation pattern returns zero hits; `npm run build` passes with zero warnings.

### Gate 7 — Full verification metadata, structured pricing & fact-model data layer
Per-field `{source, confidence tier, date}` + change log; structured numeric pricing fields alongside the existing freeform `cost`; promotion of `temperatures`/`dress_code`/`session_gender`/`silence_policy`/`phone_policy`/`minimum_age` into SQLite; drive-time field (OSRM public routing demo, per the dated TRD.md §2 exception — no new package); backfill of all 25 published venues; new build-time validators that fail, not warn, on implausible (never merely absent) data; an automated diff across all six schema surfaces added to `/validate`.
**Done when:** the six-surface schema diff passes for every new field; all 25 venues carry at least a source + confidence tier for every currently-populated field; structured price cross-validates against `priceRange()`; drive-time is populated for every venue with non-null coordinates, cleanly absent otherwise; each new validator demonstrably fails the build against a deliberately corrupted fixture.

### Gate 8 — Operator outreach & verification flow
Outreach state machine (not-contacted → contacted → responded → operator-confirmed / no-response / declined) feeding Gate 7's confidence tiers; email via the existing `admin/pipeline/notify.py` pattern (zero new dependency); manual-entry admin screen as the single source of truth for outcomes regardless of channel (email or phone); new outreach-state table kept separate from public git-committed frontmatter, same reasoning as `claims.db`.
**Done when:** the state machine exists and is visible in a new admin screen; a test outreach email sends via existing SMTP config; a manually recorded response correctly upgrades a venue's confidence tier, visible on next build; a first real batch (e.g. all VIC venues) has gone out with responses reflected in confidence tiers.

### Gate 9 — Coverage-gap venue research
SA/WA/NT/ACT (currently zero venues each), additional NSW, named missing venues (Moree, Yarrangobilly, Innot, Mataranka, Bitter Springs, Dalhousie, Zebedee, Soak's second South Melbourne site) — harvested under Gate 7's full fact-model shape from day one, not backfilled after.
**Done when:** at least one venue published in each of SA/WA/NT/ACT, or an explicitly logged reason for any state still at zero; every newly published venue carries complete Gate-7-shape data at publish time; the full `/validate` suite passes against the expanded set; state/region/national pages regenerate correctly for newly-populated states with no manual intervention beyond the normal approve action.

### Gate 10 — Comparison & region pages
Superlative, constraint, head-to-head (heuristic-proposed pairs, user-approved), occasion, and geographic roll-up pages, generated entirely from Gate 7's dataset; region-taxonomy route generation; new LLM-assisted + Gatekeeper-style copy stage for lead paragraphs; semantic `<table>`/`<caption>`/`<th scope>` + `ItemList` schema; internal-linking rules (every venue in ≥3 comparison pages, every comparison page reachable from ≥1 hub) enforced as a `/validate` graph check.
**Done when:** a page exists for every category clearing the ≥5-venue threshold; the threshold check demonstrably skips-and-logs (not fails) a deliberately thinned 4-venue fixture; every generated page has valid table/caption/scope markup and a structurally valid `ItemList` block; head-to-head pages generate only from approved pairs; the comparison-copy audit demonstrably deletes/softens a deliberately inserted false claim in a test fixture; the internal-linking graph check passes with zero orphans.

### Gate 11 — Structured data, E-E-A-T & content expansion
`amenityFeature` arrays, `BreadcrumbList`, `DefinedTermSet`/`DefinedTerm` on the glossary, `WebSite` schema, `Article` on blog posts, the methodology/about page (describing only verification activity that has actually occurred by this point), `llms.txt` audit + fix (the dead `/category/day-spa/` reference), offline JSON-LD structural validator folded into `/validate`. The `LocalBusiness` schema.org type decision and the blog `author` field addition are schema changes — explicit user sign-off required per rule 3 before either lands.
**Done when:** JSON-LD passes the offline validator on 100% of page types; the venue schema.org type decision is recorded as a dated TRD.md exception with explicit sign-off; the blog author-field decision is explicitly recorded either way; `llms.txt`'s dead route is fixed and Gate 6/10's new route types are added; the methodology page is live and linked from footer/nav.

---

**2026-09-08: expansion/security engagement approved.** `ROADMAP.md` reviewed the project and proposed Gates 12–15; the owner approved them by starting them in sequence. They are new scope, sequenced and blocking per rule 1 exactly like Gates 1–11. `ROADMAP.md` remains the reasoning; the contracts below are operational.

### Gate 12 — Admin hardening & operational safety *(complete, 2026-09-08)*
Fail-open auth replaced with an explicit local-dev opt-in plus a startup assertion; byte cap, content-type allowlist and magic-byte sniff on the claim photo path; global and per-client rate limits alongside the per-slug one; auth-attempt throttling; an append-only audit log; verified off-host backups of `claims.db`/`articles.db` with a documented restore procedure; security headers; CI running `/validate` on every push; documented secret-rotation cadence and revocation order (`SECURITY.md`).

### Gate 13 — Operator outreach & verification flow *(the deferred Gate 8)*
The outreach state machine (not-contacted → contacted → responded → operator-confirmed / no-response / declined) feeding Gate 7's confidence tiers, in its own gitignored SQLite file for the same reason `claims.db` is separate; email via the existing `notify.py` SMTP pattern, zero new dependency; a manual-entry admin screen as the single source of truth for outcomes whatever the channel; tier upgrades flowing into the existing `verification` block, upgrade-only and field-by-field, never a silent sweep; the claim offer introduced in the same conversation.

**Done when:** the state machine is visible in a new admin screen and every transition is exercised; a test outreach email sends via existing SMTP config; a manually recorded response upgrades a venue's confidence tier, visible on the next build and asserted by `validate_facts`; the first real batch (all VIC venues) has gone out with outcomes recorded; at least one venue carries an `operator_confirmed` field in published frontmatter.

### Gate 14 — Coverage to a national floor
WA first, then SA/NT/ACT to the floor, then the named remote thermal springs from Gate 9's list; every new venue harvested at full Gate-7 fact-model shape at publish time, never backfilled; outreach opened for each new venue as part of publishing it.

**Done when:** every state and territory carries ≥5 published venues, or a logged, dated reason for any that cannot; `/validate` passes against the expanded set; every newly published venue is in the outreach state machine.

*(Amended 2026-09-10, owner decision: the proposed "no state exceeds 40% of the catalogue" ceiling is dropped. With Victoria at 26 of 39 it would have required 26 new venues elsewhere purely to move a ratio, and if Victoria genuinely holds most of Australia's bathhouses a ceiling fights the territory rather than measuring it. The floor is the criterion; `admin/pipeline/validate_coverage.py` still prints the distribution as context.)*

### Gate 15 — Measurement, distribution & first revenue
`gsc.py` replaced with a real Search Console integration feeding the opportunity queue as a ranked prompt only, never auto-creating articles; a tracked monthly AI-citation audit; a published commercial-relationships policy; whichever revenue lines the owner rules in; one chosen distribution channel actually running.

**Done when:** the opportunity queue shows demand-derived candidates and the brief gate still governs each; the citation audit has three months of recorded results; the policy is live and linked from the methodology page; first revenue is recorded; the distribution channel has run a full cycle.

---

**2026-09-15: United States expansion approved.** Gates 1–15 established an Australian directory. The
country-aware data model, the `/places/<world>/<country>/<subdivision>/` URL tree and the `US` country
registry all landed on 2026-09-08 (TRD.md §1) in anticipation of this, but no US venue was ever published
and three layers of Australia-only residue remain. Gate 16 is new scope, sequenced and blocking per rule 1
exactly like the gates before it. The approved plan is the working reference; the contract below is
operational.

### Gate 16 — United States, beginning with Florida
Country-scoped page sets (amenity, category, comparison), so an existing AU URL keeps its meaning and its
indexing rather than being widened or redirected; per-country locale for copy, units and currency —
metric stays the storage form, °F/miles the US display form; country-aware geocoding, venue discovery,
Places verification, drive-time origins and forewords; a unified place gazetteer and a Florida region
taxonomy; the admin editor able to stage a non-AU venue at all; and Florida published to Gate 14's
coverage floor at full Gate-7 fact-model shape at publish time, with outreach opened per venue.

**Done when:** `/validate` passes with US venues present; no `STATE_NAMES[...]` lookup remains unguarded by
country anywhere; a Florida venue geocodes, drive-times from a US origin, and renders correct JSON-LD
(`addressRegion` a real subdivision name, `addressCountry: "US"`, breadcrumbs resolving at every level);
`/places/north-america/united-states/florida/` and its leaf filters appear in `sitemap.xml`; a deliberately
AU-spelled US draft fails the new locale check and a `state_province: "WA"` under `country: "US"` resolves
to Washington, never Western Australia; Florida carries ≥5 published venues with the full Florida set
published; every published US venue is in the outreach state machine; `npm run build` passes with zero
warnings.

## Working style

Small commits per logical unit within a gate, imperative messages, no drive-by refactors. When a screenshot is possible, take one before claiming visual work is done. When you are unsure whether something meets DESIGN.md, it doesn't — ask.
