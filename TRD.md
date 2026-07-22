# Technical Requirements Document
## Australian Spa & Bathhouse Directory + Local AI Publishing Pipeline

**This document is the authoritative build spec. It is accompanied by CLAUDE.md (process), DESIGN.md (visual), UX.md (behaviour), SCHEMA.md (data contract), PROMPTS/ (agent prompts), and SEED.md (test data). Where those files are more specific than this one, they win.**

---

## 1. Objective

A textured, editorial directory of Australian day spas and bathhouses. A local Python admin app orchestrates an AI pipeline (scrape → extract → draft → polish) into a staging queue; a human approves drafts; approved MDX files and a derived data file are committed and pushed, triggering a static Netlify build. No cloud database, no CMS, no runtime backend for the public site.

## 2. Core Stack (fixed — do not substitute)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Astro 5, SSG mode, MDX integration | Static output only. |
| Styling | Tailwind CSS v4 | Layout/utility only. All colour and type tokens come from DESIGN.md as CSS custom properties. Tailwind default grey palettes are banned. |
| Map | Leaflet + markercluster, free tile provider styled to palette | No Mapbox, no token. |
| Data | **Single local SQLite file** (`data/directory.db`) committed to the repo, plus generated `site/src/data/venues.json` and `site/public/venues.geojson` | Turso was considered and dropped. Frontmatter is canonical; the DB and JSON are derived artefacts regenerated on approve. |
| Admin app | Python 3.11+, FastAPI + Jinja2 templates + vanilla JS | No SPA framework, no React. Runs on localhost only. |
| Scraping | httpx + trafilatura; Playwright only as explicit user-triggered fallback for JS-heavy sites | Respect robots.txt; 20s timeout; one job at a time. |
| AI | Anthropic API | Harvester + Gatekeeper: `claude-haiku-4-5`. Architect: `claude-sonnet-4-6`. Model IDs configurable via .env; never hardcode. |
| Deploy | git push → Netlify build | Triggered from admin UI per UX.md §1.4. |

## 3. Repository Structure

One repo, two clearly separated applications sharing a content directory. No Python imports reach into `site/`; no Astro code reaches into `admin/`. All shared paths are defined once in `admin/config.py` and `site/src/config.ts` respectively.

```
/site                     # Astro project
  /src
    /content
      config.ts           # zod collection schema — MUST mirror SCHEMA.md exactly
      /spas
        /_published       # approved MDX (the only content Astro builds from)
      /blog
        /_published       # published posts (2026-07-21, SCHEMA.md §7)
    /components           # Map.astro, VenueEntry.astro, Features.astro, Icon.astro, Pull.astro, TippedPhoto.astro, CornerMenu.astro
    /icons/paths.ts        # hand-authored inline SVG icon set (DESIGN.md §6)
    /data/venues.json     # generated on approve — committed
    /pages
      index.astro
      /[state]/index.astro
      /[state]/[amenity].astro
      /category/[category]/index.astro  # 2026-07-22
      /glossary/index.astro              # 2026-07-22
      /glossary/[key]/index.astro        # 2026-07-22
      /spa/[slug].astro
      /blog/index.astro
      /blog/[slug].astro
  /public/venues.geojson  # generated on approve — committed
  /public/blog-images     # published blog images — committed
/admin                    # FastAPI app
  app.py  config.py  pipeline/  templates/  static/
/content-staging          # OUTSIDE site/src/content so Astro never builds drafts
  /_staging  /_rejected  /_blog_staging
/data/directory.db        # committed derived DB
/temp_data                # scrape output + candidate images — gitignored
/PROMPTS                  # agent prompt files, loaded at runtime by admin app
.env  .env.example  .gitignore
```

**Note the change from the original draft:** `_staging` and `_rejected` live in `/content-staging`, not inside `site/src/content`. Astro content collections glob everything in a collection directory; keeping drafts outside the tree is more robust than relying on underscore-prefix exclusion. The approve action moves files across into `site/src/content/spas/_published/`.

## 4. Frontend Requirements

1. Content collection `spas` with a strict zod schema per SCHEMA.md. Build must fail on any schema violation.
2. Routes: `/` (index), `/spa/[slug]` (venue), `/[state]/`, `/[state]/[amenity]/`, `/category/[category]/` *(2026-07-22)* — programmatic pages generated **only** for combinations with ≥1 venue.
3. All layout, ordering, interaction, and no-JS behaviour per UX.md §2–3. All visual decisions per DESIGN.md — including the venue-feature icon system (DESIGN.md §6, superseding the earlier field-notation system as a 2026-07-21 user-approved exception), which is a build requirement, not a suggestion.
4. Map data comes from the generated GeoJSON; venue lists and filters from `venues.json`/frontmatter at build time. The public site performs zero runtime data fetching except map tiles.
5. `<Pull>` MDX component for pull-quotes; `<TippedPhoto>` for the single optional image, implementing the treatment in DESIGN.md §4.

## 5. Data Layer Requirements

- `data/directory.db` tables exactly as SCHEMA.md §3 (venues, amenities). 
- **Upsert on slug, never insert.** Re-approving an edited venue must update in place. Deleting/unpublishing a venue removes its rows.
- A single Python module `admin/pipeline/data_store.py` owns all DB and JSON/GeoJSON generation. Regeneration is full-rebuild-from-published-frontmatter (idempotent), not incremental patching — the published MDX directory is always the source of truth and the DB can be deleted and rebuilt from it at any time. Provide `python -m admin.pipeline.data_store --rebuild` for exactly that.

## 6. Admin App Requirements

Implement UX.md §1 in full: harvest panel with streaming log, review queue with status chips, review pane (rendered preview using the public site's actual CSS, frontmatter editor, amenity toggle chips, debounced autosave), approve/reject with keyboard shortcuts and 3-second undo, deploy strip with diff preview and tracked-file guard, and **every failure state in the UX.md §1.5 table**. The image pipeline is UX.md §4 verbatim: candidate images are staging-only, publishing an image is a separate action, max one image per venue, attribution mandatory, one-click removal.

Also implement UX.md §6 (2026-07-21) — the `/blog` authoring screen and its own create/update/publish/image-upload flow.

## 7. AI Pipeline Requirements

- Three agents, prompts loaded from `/PROMPTS/*.md` at call time (never embedded in Python source): Harvester (facts → JSON per SCHEMA.md §4), Architect (JSON → MDX draft), Gatekeeper (draft → polished Australian-English MDX).
- Malformed-output handling per UX.md §1.5: one automatic re-ask with the parse error appended; then fail to `temp_data/failed/` with a log line.
- **Integrity rule:** the Architect writes a documented profile from the harvested record. It must never claim a first-hand visit, invent amenities, temperatures, prices, or history not present in the JSON. Anything uncertain is omitted, not guessed. This rule appears again inside the prompts; enforce it there and honour it here.
- API key from `.env` only. Log token usage per call in the harvest log.

## 8. Out of Scope (v1)

Accounts/auth, venue claiming beyond a mailto line, reviews by users, search, analytics, image galleries (one image max), any hosted database, any serverless functions.

**Exception (user-approved, 2026-07-20):** a minimal, single-purpose exception to the "analytics" exclusion above — GoatCounter click tracking on the Book Now button only (no page-view analytics, no dashboards beyond a simple admin read-back of per-venue click counts). See `admin/pipeline/goatcounter.py`. Nothing else in this list is affected; general site analytics remains out of scope.

**Exception (user-approved, 2026-07-20):** admin-side venue *discovery* (finding candidate URLs via Google Places Text Search, reviewed by a human before harvesting) is in scope. Public-facing site search remains out of scope — this exception does not add a search feature to the published site. See `admin/pipeline/discovery.py`.

**Exception (user-approved, 2026-07-21):** a hand-authored blog/journal is in scope — a new Astro content collection (`site/src/content/blog/`, SCHEMA.md §7) with list/post pages, and an admin authoring screen (`/blog`) with a Quill.js rich-text editor (vendored locally, `admin/static/vendor/quill/` — no CDN, no build step; see UX.md §6), inline image upload, and external YouTube/Vimeo video embeds (no self-hosted video, no new backend dependency). Unlike venues, posts are not part of the AI pipeline — no Harvester/Architect/Gatekeeper, no SQLite table.

## 9. Execution

Build proceeds through the five gates defined in CLAUDE.md, in order, stopping at each gate for verification. Do not begin a gate before the previous gate's done-condition passes. Read CLAUDE.md, DESIGN.md, UX.md, and SCHEMA.md before writing any code.
