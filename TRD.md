# Technical Requirements Document
## Australian Spa & Bathhouse Directory + Local AI Publishing Pipeline

**This document is the authoritative build spec. It is accompanied by CLAUDE.md (process), DESIGN.md (visual), UX.md (behaviour), SCHEMA.md (data contract), PROMPTS/ (agent prompts), and SEED.md (test data). Where those files are more specific than this one, they win.**

---

## 1. Objective

A textured, editorial directory of Australian bathhouses, thermal springs, and hotel spas — anywhere with a pool or a sauna as a central offering (2026-07-26: narrowed from "day spas and bathhouses"; see §8's scope note). A local Python admin app orchestrates an AI pipeline (scrape → extract → draft → polish) into a staging queue; a human approves drafts; approved MDX files and a derived data file are committed and pushed, triggering a static Netlify build. No cloud database, no CMS, no runtime backend for the public site.

## 2. Core Stack (fixed — do not substitute)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Astro 5, SSG mode, MDX integration | Static output only. |
| Styling | Tailwind CSS v4 | Layout/utility only. All colour and type tokens come from DESIGN.md as CSS custom properties. Tailwind default grey palettes are banned. |
| ~~Map~~ | ~~Leaflet + markercluster, free tile provider styled to palette~~ | **2026-07-26: removed.** The homepage no longer carries a map; superseded by the manual-postcode 50km radius list (UX.md §2.1, DESIGN.md §5). No remaining call site for Leaflet. |
| Data | **Single local SQLite file** (`data/directory.db`) committed to the repo, plus generated `site/src/data/venues.json` and `site/public/venues.geojson` | Turso was considered and dropped. Frontmatter is canonical; the DB and JSON are derived artefacts regenerated on approve. |
| Admin app | Python 3.11+, FastAPI + Jinja2 templates + vanilla JS | No SPA framework, no React. Runs on localhost only. |
| Scraping | httpx + trafilatura; Playwright only as explicit user-triggered fallback for JS-heavy sites | Respect robots.txt; 20s timeout; one job at a time. |
| AI | Anthropic API | Harvester + Gatekeeper: `claude-haiku-4-5`. Architect: `claude-sonnet-4-6`. Model IDs configurable via .env; never hardcode. |
| Deploy | git push → Netlify build | Triggered from admin UI per UX.md §1.4. |
| Motion | `gsap` (core + `ScrollTrigger` + `SplitText` submodules) for in-page scroll effects; Astro's built-in `<ClientRouter />` for page-to-page hero-photo persistence | **2026-07-30 exception** — see below. |

**Exception (user-approved, 2026-07-30) — a new frontend dependency, `gsap`.** CLAUDE.md rule 2 ("ask before adding any dependency … state what it's for and what the no-dependency alternative would be") applies; this is that ask, documented as approved. Added for DESIGN.md §9's 2026-07-30 "Notebook Depth" motion — restrained parallax on the tipped-in photograph (§4) and margin animals (§6a), sitewide hairline self-draw on enter-view, and ~60ms-per-line staggered text reveal on enter-view.

*No-dependency alternative considered:* native CSS `animation-timeline: scroll()`/`view()`. Rejected — Firefox has not shipped scroll-driven animations as of early 2026, and the specific combination this vocabulary needs (per-line stagger measured against actual rendered line breaks, which reflow with viewport width and this project's `font-display: swap` variable fonts, plus a tunable custom-eased parallax) is materially harder to hand-roll robustly than with a mature scroll-animation library.

*Why `gsap` specifically:* one npm package, no separate packages to track; "Standard no-charge license" (gsap.com/standard-license, verified against the published npm package, `gsap@3.15.0`), free for this project's use including `ScrollTrigger`/`SplitText`, both free only since Webflow's 2024 GreenSock acquisition. `SplitText` specifically solves "split into actual rendered lines, not just words," which a hand-rolled measurement approach would otherwise reimplement. Bundle cost: ~27KB gzipped for core (measured at `gsap@3.15.0`, 2026-07-30) plus roughly 10–15KB combined for the two submodules actually imported — confirm the exact tree-shaken figure at implementation time.

*Page-to-page hero-photo persistence uses Astro's own `<ClientRouter />` instead — zero new dependency, ships inside the already-installed `astro` package.* `gsap` is scoped to in-page scroll-linked effects only.

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
    /components           # VenueEntry.astro, Features.astro, Icon.astro, MarginAnimal.astro, Pull.astro, TippedPhoto.astro, CornerMenu.astro (2026-07-26: Map.astro removed, see §2)
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
  /public/animals         # 2026-07-26 — downscaled margin-decoration artwork (DESIGN.md §6a), sourced from /Icons and logos below
/admin                    # FastAPI app
  app.py  config.py  pipeline/  templates/  static/
/content-staging          # OUTSIDE site/src/content so Astro never builds drafts
  /_staging  /_rejected  /_blog_staging
/data/directory.db        # committed derived DB
/temp_data                # scrape output + candidate images — gitignored
/PROMPTS                  # agent prompt files, loaded at runtime by admin app
/Icons and logos          # 2026-07-26 addition — committed source design assets (user-supplied), not built; downscaled derivatives served from site/public/animals
.env  .env.example  .gitignore
```

**Note the change from the original draft:** `_staging` and `_rejected` live in `/content-staging`, not inside `site/src/content`. Astro content collections glob everything in a collection directory; keeping drafts outside the tree is more robust than relying on underscore-prefix exclusion. The approve action moves files across into `site/src/content/spas/_published/`.

## 4. Frontend Requirements

1. Content collection `spas` with a strict zod schema per SCHEMA.md. Build must fail on any schema violation.
2. Routes: `/` (index), `/spa/[slug]` (venue), `/[state]/`, `/[state]/[amenity]/`, `/category/[category]/` *(2026-07-22)* — programmatic pages generated **only** for combinations with ≥1 venue.
3. All layout, ordering, interaction, and no-JS behaviour per UX.md §2–3. All visual decisions per DESIGN.md — including the venue-feature icon system (DESIGN.md §6, superseding the earlier field-notation system as a 2026-07-21 user-approved exception) and the homepage chooser section plus repositioned corner menu (DESIGN.md §5/§6/§7/§5b, UX.md §2.1/§3, 2026-07-23 user-approved exception) — which are build requirements, not suggestions.
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

Accounts/auth, reviews by users, search, analytics, image galleries (one image max), any hosted database, any serverless functions.

**Scope note (user-approved, 2026-07-26):** pure treatment/wellness spas, head spas, and dental spas are out of scope — a venue must have a pool or a sauna as a central offering, not a menu add-on inside an otherwise massage/facial-led business. This retires `day_spa` as a category (SCHEMA.md §2) in favour of `hotel_spa` for hotel/lodge venues that do have a real bathing circuit; see `admin/pipeline/discovery.py` (discovery keywords), `PROMPTS/harvester.md` and `admin/pipeline/orchestrator.py` (the automated pool-or-sauna eligibility check) for enforcement. Eight previously published venues with no qualifying pool/sauna were removed under this rule (parked in `content-staging/_deleted/`, never destroyed).

**Exception (user-approved, 2026-07-20):** a minimal, single-purpose exception to the "analytics" exclusion above — GoatCounter click tracking on the Book Now button only (no page-view analytics, no dashboards beyond a simple admin read-back of per-venue click counts). See `admin/pipeline/goatcounter.py`. Nothing else in this list is affected; general site analytics remains out of scope.

**Exception (user-approved, 2026-07-20):** admin-side venue *discovery* (finding candidate URLs via Google Places Text Search, reviewed by a human before harvesting) is in scope. Public-facing site search remains out of scope — this exception does not add a search feature to the published site. See `admin/pipeline/discovery.py`.

**Exception (user-approved, 2026-07-21):** a hand-authored blog/journal is in scope — a new Astro content collection (`site/src/content/blog/`, SCHEMA.md §7) with list/post pages, and an admin authoring screen (`/blog`) with a Quill.js rich-text editor (vendored locally, `admin/static/vendor/quill/` — no CDN, no build step; see UX.md §6), inline image upload, and external YouTube/Vimeo video embeds (no self-hosted video, no new backend dependency). Unlike venues, posts are not part of the AI pipeline — no Harvester/Architect/Gatekeeper, no SQLite table.

**Exception (user-approved, 2026-07-25, supersedes the 2026-07-23 exception below):** the claim page now carries a real structured request form and an automated payment/publish path, not a mailto-only line. `/claim/[slug]` (UX.md §2.5) presents a structured request form mirroring the admin frontmatter editor's fields (name, address, suburb, hours, cost, access, the five amenity toggles, the eight facility toggles, summary), plus one optional photo upload, and submits it as a JSON POST to the admin app (`admin/app.py`) rather than a `mailto:` link. Submitting emails the site owner only (never a public inbox), via stdlib `smtplib` — no new dependency. There is still no visitor login or local account of any kind; a submission is a one-off, unauthenticated write identified only by the email address the requester types in.

The owner reviews each request by hand in a new admin screen (UX.md §1.6, `/claims`) and approves or denies it. Approval sends the requester a Stripe Checkout link — built from raw httpx REST calls against the Stripe API, explicitly not the `stripe` pip package, consistent with this project's existing no-SDK pattern (see also: no `python-dotenv`, no `python-multipart`) — for the one-off $25 fee or the $5/month subscription, whichever the requester selected. A returning subscriber is recognised by a live Stripe API lookup matching their submission email against active subscriptions at approval time — no locally cached account/session table. Every request, subscriber or not, still requires the owner's manual approve/deny; a subscriber's approved request skips the fee but still needs a separate deliberate "Publish" click in the admin UI, not an instant publish the moment Approve is clicked.

On successful payment, Stripe's webhook (signature verified with stdlib `hmac`/`hashlib`, no new dependency) writes the approved changes straight to the published MDX, `data/directory.db`, and `venues.json`/`venues.geojson`, reusing `admin/pipeline/staging.update_published`, with no further human step. **This webhook — and the subscriber's manual Publish click — also trigger this project's existing deploy pipeline (`admin/pipeline/deploy.py`) automatically, as a background task:** the one write path in this system that commits and pushes to git, and therefore reaches the live Netlify site, without a human clicking the Deploy strip's button. Every other write in this system (venue approvals, image publishes, manual edits) stops at "updated on disk" and waits for that manual step; this is a deliberate, narrow exception to that posture, scoped to paid/approved claim requests only.

Claim-request records (pending/approved/denied/awaiting_payment/paid/published state, requester contact, the submitted change patch, Stripe session/customer ids) live in their own `data/claims.db` file, gitignored and never committed — kept separate from `directory.db` because `data_store.rebuild()` deletes and fully recreates `directory.db` on every venue write, which would destroy anything stored there.

This does not reopen the "Out of scope" line below: no user accounts, no reviews, no search, no hosted database beyond the two local SQLite files this project already uses this way — only the claim-request/payment/publish/deploy path described here is added.

**Exception (superseded above, 2026-07-23, kept for record):** venue claiming beyond a mailto line is in scope, specifically — a per-venue `/claim/[slug]` detail page (UX.md §2.5) explaining two paid options for a venue owner to request content updates (a one-off processing fee, or a monthly subscription for ongoing access), ending in a `mailto:` CTA. This remains a static page with a mailto link only: no accounts, no forms, no payment gateway, no hosted database. Fee collection and request review happen manually over email, not through the site.

**Exception (user-approved, 2026-07-25):** public-facing search, and a manual "near me" distance sort, are in scope for the published site — narrowly reversing the "search" line in the out-of-scope list above and the 2026-07-20 exception's note that "this does not add a search feature to the published site." Both are client-side only: no backend, no serverless function, no new npm dependency, and no runtime data fetching beyond the site's existing zero-fetch build (§4.4).

- **Search:** a build-time-embedded JSON index of every published venue's name, suburb, state, category and amenities — the same embedded-JSON-at-build-time pattern the map already uses (`Map.astro`) — matched in the browser with plain case- and accent-insensitive substring matching (no fuzzy-search library). Reachable sitewide from the corner menu (DESIGN.md §5b) and from a prominent entry point in the homepage chooser (DESIGN.md §5/§7). See `site/src/components/SearchBox.astro`, `site/src/layouts/BaseLayout.astro`.
- **Near me:** resolves a manually typed suburb name or postcode (never browser geolocation, which the user explicitly declined, reconfirmed 2026-07-26) against a small, hand-curated, committed gazetteer of Australian place names/postcodes and centroid coordinates (`site/src/data/au-places.ts` — hand-authored from public place-name/coordinate facts, not a bulk-imported postcode database). **2026-07-26 revision:** rather than re-sorting the full list and reframing a map (the map is removed, see §2), near-me now filters to a hard 50km straight-line cutoff and renders the matches in the homepage's results area (UX.md §2.1), sorted nearest-first. See `site/src/config.ts` (`haversineDistanceKm`, `nearestByDistance`).
- The venue page also gains a "Nearby" block listing the nearest three other published venues (any category) by straight-line distance, computed once at build time over `getCollection("spas")` coordinates. This isn't itself a new capability requiring an exception — the whole site already rebuilds from `_published` on every deploy (§1) — but is documented here since it ships alongside the above.

Nothing else in this list is affected: accounts, user reviews, hosted databases and serverless functions remain out of scope.

## 9. Execution

Build proceeds through the gates defined in CLAUDE.md, in order, stopping at each gate for verification. Do not begin a gate before the previous gate's done-condition passes. Read CLAUDE.md, DESIGN.md, UX.md, and SCHEMA.md before writing any code.

**2026-07-31:** Gates 1–5 (the original build) are complete; the site is live at wherewebathe.com. Gates 6–11, covering the SEO/AI-citation remediation engagement, are appended in CLAUDE.md. The approved roadmap with full context and rationale for that engagement is `~/.claude/plans/where-we-bathe-bubbly-sunrise.md`.
