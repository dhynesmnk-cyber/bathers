# CLAUDE.md — Operating Instructions

You are building the project specified in TRD.md. Read TRD.md, SCHEMA.md, UX.md, and DESIGN.md before writing any code. This file governs *how* you work.

## Prime rules

1. **Gates are sequential and blocking.** Work happens inside the current gate only. When a gate's done-condition passes, stop, summarise what was built and how you verified it, and wait for explicit approval before starting the next gate. Never begin work from a later gate "while you're in there."
2. **Ask before adding any dependency** not already named in TRD.md — npm or pip, however small. State what it's for and what the no-dependency alternative would be.
3. **Never invent scope.** If the spec docs don't cover something, ask. If two docs conflict, the more specific document wins (SCHEMA.md > TRD.md for data; UX.md/DESIGN.md > TRD.md for interface); flag the conflict either way.
4. **File pathing:** all cross-cutting paths (content dirs, DB path, temp dirs) are defined once — `admin/config.py` for Python, `site/src/config.ts` for Astro — and imported everywhere else. No hardcoded relative paths in feature code. All Python file operations use `pathlib` and are safe to run from the repo root.
5. **Never touch:** `.env` (read-only, never commit, never print its values), anything in `temp_data/` manually, git history (no rebase/force-push), the `_published` directory by hand (only the approve action writes there).
6. **Honesty in generated content:** the pipeline's Architect agent writes documented profiles, never fabricated first-hand visits. If you write or edit prompts, preserve this rule.
7. Australian English in all user-facing copy, including the admin UI.

## Stack constraints (recap — full detail in TRD.md §2)

Astro 5 SSG + Tailwind v4 + Leaflet. FastAPI + Jinja2 + vanilla JS (no React/SPA in admin). SQLite via stdlib `sqlite3`. httpx + trafilatura (Playwright fallback only). Anthropic SDK; model IDs from `.env`. Nothing else without asking (rule 2).

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

## Working style

Small commits per logical unit within a gate, imperative messages, no drive-by refactors. When a screenshot is possible, take one before claiming visual work is done. When you are unsure whether something meets DESIGN.md, it doesn't — ask.
