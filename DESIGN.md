# DESIGN.md — Visual Specification

**Read this before touching any UI code. Every visual decision derives from this file. If a choice is not covered here, ask — do not default.**

---

## 1. Direction

**A naturalist's field diary meets a European bathhouse pamphlet. Ink on warm paper, inverted for dark mode.**

The site should feel like a privately printed guide — something set in metal type, annotated by hand, carried damp into a bathhouse. Restrained, textured, editorial. It records places the way a field guide records species: with a notation system, a dateline, and prose that takes its time.

It should **never** feel like: a SaaS product, an Airbnb listing, a Google Maps sidebar, a wellness startup, a link directory. If a screen could belong to any of those, it is wrong.

---

## 2. Colour

**Two modes, 2026-07-21 addition.** The site now supports both a light and a dark mode — auto-detected from the visitor's OS preference (`prefers-color-scheme`), with a manual override (see §5a, Theme Toggle). Dark mode keeps its original six values unchanged. Light mode is not a separate palette invented from scratch — it's the "ink on warm paper" register §1 always described, with dark mode as the inversion of it. One mineral accent, one oxide secondary, in both modes. Nothing else.

**Dark mode:**

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#191614` | Page background. Warm near-black — charcoal with brown, never blue-black. |
| `--paper-raised` | `#211d1a` | Slightly lifted surfaces (review appendix block, admin panes). Difference should be barely perceptible. |
| `--ink` | `#e8e2d6` | Primary text. Warm off-white, like aged paper made luminous. |
| `--ink-faded` | `#a89f8f` | Secondary text, datelines, captions. Ink that has sat in sun. |
| `--thermal` | `#7fb5a4` | The mineral accent. Thermal-pool green — links, active states, the current map marker. Used sparingly: if more than ~5% of a screen is thermal, it's overused. |
| `--oxide` | `#b4633a` | Secondary accent. Rust/iron-oxide — reject actions, warnings, the occasional annotation. Rarer than thermal. |

**Light mode:**

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#f2ece0` | Page background. Warm off-white — handmade paper, never clinical white. Carries the grain texture (§4). |
| `--paper-raised` | `#e9e1d1` | Slightly lifted surfaces. Difference should be barely perceptible, as in dark mode. |
| `--ink` | `#2a241e` | Primary text. Warm charcoal, never pure black. |
| `--ink-faded` | `#6b6255` | Secondary text, datelines, captions. |
| `--thermal` | `#3f6b5b` | The mineral accent, deepened from the dark-mode value to hold ≥4.5:1 contrast against `--paper` at text weight. Same role: links, active states, current map marker. |
| `--oxide` | `#96502e` | Secondary accent, deepened for the same contrast reason. Same role: reject actions, warnings, occasional annotation. |

**Banned in both modes:** the Tailwind default grey scale (`slate`, `gray`, `zinc`, `neutral`, `stone` utilities for colour), pure `#000`/`#fff`, any blue that reads "tech", any purple, gradients of any kind, coloured glows/shadows.

**2026-07-26 amendment — olive `--ink`/`--ink-faded`.** Body copy and hairlines move from the previous warm-neutral ink to an olive family, user-requested. New values, replacing the ones in the tables above:

| Token | Mode | Hex |
|---|---|---|
| `--ink` | Dark | `#d9dcb0` (pale khaki-olive) |
| `--ink-faded` | Dark | `#9aa06e` (muted olive) |
| `--ink` | Light | `#3d4423` (deep olive) |
| `--ink-faded` | Light | `#6f7a4a` (muted olive) |

`--paper`/`--paper-raised`/`--oxide` are unchanged. Because `--ink` is now itself green, `--thermal` moves cooler/tealer so the "one mineral accent" (see role description above) still reads as a distinct colour rather than a shade of the body text — `#2f6e78` (light) / `#6fb8bd` (dark), replacing the values in the tables above. The "~5% of a screen" thermal budget still applies unchanged. Verify actual contrast on screen before treating these hexes as final (§10).

**2026-07-26 amendment (later, superseding the thermal values above) — `#496459` accent.** `--thermal` moves again, user-requested, to `#496459` for light mode (still ≥4.5:1 against light `--paper`, ≈5.1:1). Used verbatim, `#496459` only holds ≈3:1 against near-black dark `--paper` — both colours are dark — so dark mode gets a same-hue, lightened derivative instead: `#74b49a` (≈7.5:1 against dark `--paper`, matching the outgoing dark thermal's ≈7.9:1). Same deepen-for-light/lighten-for-dark method as the amendment above. `--ink`/`--ink-faded`/`--oxide` are unchanged.

---

## 3. Typography

Type carries the entire personality of this site. Three faces, three jobs, no substitutions.

| Role | Face | Usage |
|---|---|---|
| **Display** | Fraunces (variable; use high optical size, weight 300–600, `SOFT` axis up for ink-spread character) | Venue names, page mastheads, pull-quotes. Large, unhurried, generous. |
| **Body** | Newsreader (400/400i/600) | All editorial prose. Set at 17–19px, line-height 1.65, **measure capped at 65ch**. Italic for asides and pull-quote attribution. |
| **Utility** | IBM Plex Mono (400/500) | Datelines, coordinates, amenity notation, admin UI chrome, frontmatter display, log output. Always small (12–13px), often letterspaced 0.05em, often uppercase. |

Rules:
- Display sizes step big: venue names at clamp(2.5rem, 6vw, 4.5rem). Don't be timid.
- No font-weight 700+ anywhere. Emphasis comes from size, italics, and the mono/serif contrast, not boldness.
- **Never** Inter, system-ui stacks, Roboto, or any grotesque sans. There is no sans-serif on this site.
- Real underlines on links: `text-underline-offset: 3px`, 1px thickness, `--ink-faded` underline that turns `--thermal` on hover. No hover colour-flip of the text itself.

---

## 4. Texture & Material

This is what separates "dark editorial" from "dark dashboard":

- **Grain:** a full-page noise overlay — SVG `feTurbulence` fractal noise, ~3% opacity, `mix-blend-mode: overlay`, fixed position, pointer-events none. Subtle enough that you only notice it when it's gone. **Light mode (2026-07-21):** the same technique, but `overlay` blend against a light `--paper` reads differently than against a near-black one — tune opacity/blend-mode independently per mode rather than assuming the dark-mode values carry over; verify visually before locking in.
- **Rules, not borders:** dividers are 1px hairlines in `--ink-faded` at 25% opacity. No boxed borders around content blocks. No border-radius above 2px anywhere on the public site. No box-shadows on the public site, ever. **Exception (user-approved, 2026-07-22):** a single hairline frame now runs around the whole page at the layout level — see §5b. This is page-level chrome, not a "boxed border around a content block" in the sense this rule bans; individual sections/cards remain unbordered.
- **The tipped-in photograph** (see §6, Signature): when a venue has an image, it is treated as a physical photo tipped into a diary — inset, not full-bleed; 2–4px `--paper-raised` mount border; mono caption beneath, e.g. `PLATE I. — THE MAGNESIUM POOL, LOOKING SOUTH.` **2026-07-22 removal:** the photo previously rotated −1.2°…+1.2° (deterministic per venue, derived from the slug hash) — this has been removed at the user's request; the photo now sits flat. Mount border/padding/caption treatment is unchanged.
- **Section openers:** small-caps mono eyebrow + hairline, in the manner of a pamphlet chapter head. No icons.

---

## 5. Layout Grammar

- **Single reading spine.** One column of prose, max 65ch, asymmetrically placed (offset left of centre on wide screens, with the wide right margin used for occasional mono margin-notes). Never centred symmetric hero layouts.
- **No cards.** Venue listings on the index are typographic entries — name, dateline, one-line notation — separated by hairlines, like a table of contents. ~~No thumbnails in lists.~~ *(Narrowly superseded 2026-07-30 — see below.)*
- **Whitespace is structural.** Section spacing at 6–10rem on desktop. When in doubt, add space, not decoration.
- **Filters are text.** Feature filters (2026-07-26: user-facing copy renamed from "amenity" — schema/field names unchanged, SCHEMA.md) render as inline mono toggles (`magnesium pool · infrared · cold plunge`); active state = thermal underline. No sidebar, no checkboxes, no pills.
- **2026-07-26 — map removed.** The map (Leaflet) chapter described in earlier revisions of this section is superseded: the homepage no longer carries a map. It's replaced by a manual-postcode "facilities around me" 50km radius list (UX.md §2.1) rendered in the same results slot as search. Kept here, struck through for the record: ~~The map (Leaflet) is a chapter within the index page, not the hero. Tiles must be styled/filtered to sit in the palette (CSS filter to warm-dark, or a dark tile theme with a warm overlay). Default markers replaced with a small thermal ring; active marker fills.~~

**Exception (user-approved, 2026-07-23).** The homepage carries one icon-based chooser section (§6, §7) between the foreword and the results area — a narrow, scoped departure from "never centred symmetric hero layouts" and "filters are text... no pills" above. It stays inside the reading-spine rhythm (asymmetric, not full-bleed, not centred) so it reads as the next section of the pamphlet rather than a hero banner, and it fronts the site's existing plain-text amenity filter and state pages rather than replacing either. Everything else covered by these two rules — the inline amenity-filter toggle bar, state/amenity page nav, and all venue listings — is unaffected and stays plain mono text and card-free.

**Exception (user-approved, 2026-07-31).** The homepage's masthead moment (§5c, §7) — the large site logo's seal growing to hero scale and centred horizontally for its one-time on-load appear-then-settle sequence — is a second, narrowly-scoped departure from "never centred symmetric hero layouts" above, alongside the 2026-07-23 chooser exception. Scoped strictly to `SiteLogo`'s `large` variant, index-only: nothing else on the homepage becomes centred (the foreword, chooser, and results sections keep their existing asymmetric reading-spine placement, unchanged), and no other page adopts a centred layout of any kind — every other page keeps the smaller, left-aligned, `inline-flex` default `SiteLogo` treatment exactly as before. This does not reopen centred or hero-style layouts generally.

**2026-07-25 extension.** The same chooser section also fronts a plain mono-text search field and a "near you" suburb/postcode field (TRD.md §8 exception), sitting above the existing by-state/by-amenity grid. Same idiom as everything else in §5 — text inputs and text buttons, underline-on-focus, no pill/card treatment, not a third icon grid or hero element. The search field also appears inside the corner menu panel (§5b) so it's reachable from every page, not just the homepage.

**2026-07-26 extension.** Below the chooser, a results area (also §7) replaces the former map-plus-contents-list pairing: empty by default with a direction line, populated by the feature filter and/or the near-me 50km radius list (search keeps its own dropdown under the search field, unchanged), each row the existing `VenueEntry` typographic-entry treatment (§5, "no cards"). ~~The pool-type grouping (thermal springs/indoor/outdoor/other) that the removed default contents list used to sort by no longer has a homepage entry point — it remains reachable via each state's `/[state]/[pooltype]/` pages (UX.md §2.3, unchanged) and is otherwise surfaced per-venue via promoted feature badges (§6, DESIGN.md's Features.astro ordering) rather than a new sitewide browse column, since no sitewide pool-type route exists to link to.~~ (superseded below, same day.)

**2026-07-26 revision (later, reversing the note above).** The pool-type grouping is reinstated with a homepage entry point after all — a "By pool setting" column sits alongside "By state" in the chooser grid (indoor/outdoor/springs/other, present-only), reusing the same `POOL_TYPES.match()` rule already shared by the corner menu and the `/[state]/[pooltype]/` pages rather than reimplementing it a third time. The corner menu's per-state pool-type sub-rows (§5b) are also promoted to primary-tier status, not an afterthought under "More." The amenity/feature icon grid (§6, §7) moves below this row as a secondary, demoted block — see §7.

**Exception (user-approved, 2026-07-30) — a small thumbnail on venues with a published photo, narrowly superseding "No thumbnails in lists" above.** `VenueEntry` shows a small (~56–72px), unbordered, unrotated thumbnail of the venue's own tipped-in photograph (§4) when one exists, beside the existing name/dateline/notation text — no card, no shadow, no mount border, no change to the hairline-separated "table of contents" rhythm otherwise. Venues with the zero-image default (§7) show nothing extra, exactly as before. This exists solely to give §9's sitewide hero-photo page transition a shared element to carry between a venue's listing row and its own page — it is not a general reintroduction of thumbnails/cards to list views, and nothing else about "No cards" above is affected.

---

## 5a. Theme Toggle (2026-07-21 addition, moved into the Corner Menu 2026-07-26)

A narrow, deliberate exception to the site's otherwise icon-free, toggle-free chrome — an interactive control on the public site alongside the Book Now button (§7a) and the Corner Menu (§5b).

- **2026-07-26 revision.** No longer renders in-flow at the top of the page. It now renders inside the Corner Menu's slide-out drawer (§5b), in the first tier alongside search and Home, reachable from the same top-right control on every page — user-requested, so the toggle no longer needs its own position and doesn't compete with the site logo for space at the top of the page. It is still not itself fixed/floating; it sits inside the drawer's normal document flow, and the drawer remains the site's one named "never fixed, never floating" exception (§5b).
- A plain mono text control, in the "filters are text" idiom (§5) — not an icon, switch, or pill.
- Auto-detects the visitor's OS preference (`prefers-color-scheme`) by default; a click/keyboard-activated override persists via `localStorage` across the visit.
- No animated transition on switch — a plain state change, consistent with the site's restrained motion posture (§9) and `prefers-reduced-motion`.
- Admin app: auto (`prefers-color-scheme`) only, no manual toggle — it's a private, single-operator workbench (§8), not a visitor-facing surface.

## 5b. Corner Menu (2026-07-22 exception, reworked into a slide-out drawer 2026-07-26)

**Exception (user-approved, 2026-07-22).** A small fixed navigation control, superseding §3/§5a's "never fixed, never floating" rule — narrowly, for this one control only. Everything else in §3/§5a still holds: no modals, no toasts, no other floating chrome.

- A single button fixed to the top-right corner of the viewport on every page (*2026-07-23: moved from bottom-right at the user's request; no other change to this control*), labelled `MENU` in mono text (no new icon on the button itself — matches the "filters are text" idiom of §5).
- **2026-07-26 revision.** Click/tap now slides a full-height panel in from the right edge (`transform: translateX`, 0.35s ease) rather than dropping a small panel below the button — still click-to-open, not hover-only, for touch/mobile parity. No dimming scrim behind it: the page stays visible so the drawer reads as a folding-out leaf of the pamphlet, not an app-style off-canvas menu (§10's "generic dark-mode template" failure mode is exactly what a scrim risks). The panel is permanently mounted and toggled via a class plus `inert`/`aria-hidden` (not the `hidden` attribute, which can't be transitioned).
- **Contents, restructured into three tiers (2026-07-26):** (1) search + Home + the theme toggle (§5a, moved in here the same day); (2) primary tier, "Find a bath by state" — every state with ≥1 published venue, each with its present pool-type sub-rows (indoor/outdoor/springs/other) directly beneath it, reinstated from the 2026-07-26-earlier removal (§5); (3) a single "More" group holding three sub-sections — "Browse by feature" (the five amenities, now with a small 20px icon each, a narrow exception to §5b's prior icon-free posture for this one new usage), "By venue type" (the four business categories, relabelled from "Find a bath by type" to avoid reading as a duplicate of the state tier), and Glossary/Journal.
- The panel itself keeps the rest of the visual system exactly: `--paper-raised` background, hairline `--ink-faded` border (now a left border, drawer-style), no border-radius above 2px, no box-shadow, no banned colours or gradients (§2/§4).
- Keyboard-operable: reachable by Tab, opens on Enter/Space, closes on `Escape` (focus returns to the button), same posture as any other interactive control on the site. The closed drawer is `inert` so its links aren't tabbable while off-screen.

## 5c. Site Logo / Home Button (2026-07-26 addition)

**Exception (user-approved, 2026-07-26), narrowly superseding §1's "never a logo mark, pure typography" posture.** The seal is the site's mascot — the user designated it the "main character" — and gets a persistent home-link lockup (seal artwork, DESIGN.md §6a's `icons/animals.ts` `seal` entry, + the `Bathers'` wordmark) rendered by `BaseLayout.astro` on **every page**, above that page's own opening content, same in-flow-never-floating posture as §5a:

- One shared renderer (`site/src/components/SiteLogo.astro`): the seal icon recoloured via the same CSS-mask technique as §6a's margin animals (`--ink-faded` light mode, pure white dark mode), beside the wordmark in Fraunces.
- Two sizes, not scaled per-page beyond these two: ~~**large** (`clamp(2.75rem, 6vw, 5rem)` text / 4.5rem icon — bumped one size tier up 2026-07-26, was `clamp(2.5rem, 6vw, 4.5rem)`/4rem) on the index only, replacing what was previously a page-specific `<h1>{SITE_NAME}</h1>` there — same visual weight as before, just componentised and now also a working `<a href="/">`.~~ *(Superseded 2026-07-31 — see below; large is now a hero-scale, stacked, appear-then-fade treatment, index-only.)* **Default** (`clamp(1.75rem, 4vw, 3rem)` text / 2rem icon, unchanged) on every other page — deliberately smaller than the index treatment so it reads as a persistent home button rather than repeating the hero treatment on top of each page's own heading (a venue name, a state foreword, a post title).
- A real `<a href="/">`, not a decorative image — this is navigation chrome, not a §6a margin motif (those stay purely decorative and unlinked).

**Favicon and social share image (same 2026-07-26 exception):** the seal also replaces the earlier inline thermal-ring SVG favicon — `site/public/favicon-16x16.png` / `favicon-32x32.png` / `apple-touch-icon.png`, generated from the same source artwork (opaque `--paper`-coloured background on the apple-touch variant only, per Apple's guidance against transparency there; the two browser favicons stay transparent). `site/public/images/og-share.webp` (1200×630, the default `og:image`/`twitter:image` across the site unless a page sets its own) is the same lockup — seal, wordmark, tagline — on the light-mode palette, since share-card surfaces are outside this site's own theme toggle and light reads reliably across chat/social clients. Neither asset is theme-aware; both are static files, not rendered per request.

**2026-07-27 rebrand.** The site's name changes from `Bathers'` to `Where We Bathe` (`SITE_NAME`, `site/src/config.ts`) — new logo artwork, same seal mascot (a fresh seal-with-towel illustration replacing the earlier seal source, still masked/recoloured the same way). This section's earlier references to the `Bathers'` wordmark above are superseded by this note, kept unedited for the record. The lockup mechanics described above — seal icon + live Fraunces text beside/above it, the favicon set, and `og-share.webp` — are unchanged in *technique*; only the wordmark text and the mascot source artwork change.

**2026-07-31 hero-masthead revision (further narrows *large* above).** On the index only, the seal grows to a real hero fixture rather than sitting beside the wordmark in a row: `.site-logo-large` is a centred, block-level column (icon above, wordmark below — a frontispiece emblem-and-title composition, not a lockup row), with generous top clearance (`clamp(1.5rem, 6vh, 4rem)`) before it. The icon is sized `clamp(7rem, 30vh, 13rem)` square — roughly 30–35% of a typical viewport's height, without exceeding a sane ceiling on very tall screens or floor on very short ones (§9's 360px-width floor is a separate, width-driven constraint, unaffected). The ceiling was chosen with the seal artwork's native raster resolution in mind (re-exported at ~444×462px from `Icons and logos/where-we-bathe-logo.png`, replacing the previous 246×256px derivative) — checked crisp at up to 3× device pixel ratio. It stays at this size permanently; only the wordmark beneath it animates: on load it fades/rises in (0.7s), holds legibly (0.9s), then fades out permanently (0.7s) — it does not shrink to the Default tier, it disappears, leaving an icon-only masthead for the rest of that page view. The wordmark's un-animated resting style is itself `opacity: 0`; `prefers-reduced-motion` shows it already gone, with no flash. Runs every page load — no session/`localStorage` gating. See §9 for the full timing writeup and §7 for the resulting content order.

---

## 5d. Footer (2026-07-27 addition)

**Exception (user-approved, 2026-07-27), a narrow extension of §6's icon-free posture (previously scoped only to venue-feature display, the corner menu's "Browse by feature" list, and the homepage chooser) to one additional use: three social/contact links in a new sitewide footer.**

- One shared component (`site/src/components/Footer.astro`), rendered once from `BaseLayout.astro` on every public page, as the last in-flow element of `.page-frame` — public site only, no equivalent in the admin app (§8).
- A single hairline top border (`--ink-faded` at 25% opacity, the same divider idiom used throughout §4/§5) — no card, no box, no background distinct from `--paper`.
- Three mono-text links (Bluesky, TikTok, email), each an icon (§6's renderer, 20px — matching the corner menu's "Browse by feature" size) plus a visible mono label, not icon-only. `--ink-faded` at rest, `--thermal` on hover/focus — the same treatment as every other interactive element on the site (§7a, §5b).
- A single mono colophon line beneath the links (site name + tagline). No further nav, no sitemap-style link column — this is a printer's colophon, not a SaaS footer.

---

## 6. Venue Feature Display — Icon System

**Exception (user-approved, 2026-07-21), superseding the section below.** The mono field-notation system (`Mg · IR · SA · CP`) is replaced by hand-authored inline SVG line icons for venue-feature display: the five amenities, plus the 2026-07-21 `hours`/`cost`/facilities additions (SCHEMA.md §1a/§2). This override is scoped narrowly to *venue-feature display* — it does not touch the rest of the site's icon-free posture:

- **Unaffected, still icon-free:** section openers (§4), the Book Now button (§7a), and the map's amenity filter toggles (§5's "Filters are text" — still plain mono text labels, unchanged).
- **Affected — now icon+label:** the venue dateline row, index/programmatic-page entries (icon-only, compact, with a `title` tooltip), the admin review pane's amenity/facility toggle chips, and programmatic state/amenity page headings (the `<title>` tag and meta description keep the old plain-text abbreviation register, since a `<title>` cannot render an icon).

Icon rules:
- One shared renderer (`site/src/components/Icon.astro`, paths in `site/src/icons/paths.ts`): 24×24 viewBox, stroke-only, `currentColor`, `stroke-width: 1.4`, round caps/joins — no fill, no colour beyond the surrounding text colour, so the icons stay tonal with the page rather than becoming decorative.
- Present features only; absent ones omitted (the "a field diary doesn't record what wasn't there" principle carries over unchanged from the old notation system).
- Full-size context (venue page) shows icon + label text; compact context (index/list entries) shows icon only with a `title` attribute for the full label, keeping list rows to one line.
- No icon package/font — every icon is hand-authored inline SVG, kept to simple primitives (circles, rects, short paths) for visual consistency across the set.

**Second icon-rendering context (2026-07-23 exception, sizes bumped one tier up 2026-07-26).** The homepage chooser section (§7) reuses this exact renderer and these exact rules — 24×24 viewBox, stroke-only, `currentColor`, no fill — at larger sizes than the base venue-feature set. Icon-size exceptions now in force, enumerated so they don't read as contradicting each other:

| Context | Size |
|---|---|
| Venue-feature "full" (venue page) | 18px (was 16px) |
| Venue-feature "compact" (list/card entries) | 16px (was 14px) |
| Venue-feature "secondary" (logistics chips) | 14px (was 12px) |
| State/state-filter page header | 16px (unified, was 14–15px) |
| Glossary index | 20px (was 18px) |
| Glossary detail page | 32px (was 28px) |
| Corner-menu "Browse by feature" (new usage) | 20px |
| Homepage chooser (feature tiles) | 40px (was 32px) |

Nowhere else on the site should adopt a size above this table without a further documented exception (margin animals, §6a, are a separately-scoped decorative exception, not a "venue-feature icon" one).

Superseded text, kept for record: amenities were previously recorded as a naturalist's notation — a two-to-three-letter mono abbreviation (`Mg` magnesium pool · `IR` infrared sauna · `SA` traditional sauna · `CP` cold plunge · `LED` light therapy), expanding to the full name on hover/focus. That system is no longer in use for venue-feature display as of 2026-07-21.

---

## 6a. Margin Animal Motifs (2026-07-26 addition)

A narrow, homepage-only exception adding sparse decorative illustration where §6's icons are strictly functional. **2026-07-26 revision:** the first version of this section described hand-authored inline-SVG animals; those read poorly and were replaced the same day with user-supplied raster artwork (bathing/sauna-themed — seal, capybara, otter and similar), sourced from the committed `Icons and logos/` folder (TRD.md §3) and served as downscaled, alpha-cropped copies from `site/public/animals/`:

- One shared renderer (`site/src/components/MarginAnimal.astro`). Because the source is raster (not hand-authored paths), recolouring uses a CSS mask (`mask-image`/`-webkit-mask-image` reading the PNG's alpha channel, painted with `background-color`) rather than `currentColor` stroke — the original export tint of each source file never matters, only its silhouette. Light mode paints `--ink-faded`; **dark mode is forced to pure white** (`#ffffff`, not `--ink`/`--ink-faded`) since the artwork reads better at full contrast against the near-black paper than the olive ink tones do — a deliberate, narrow exception to this file's usual "everything comes from the two-mode palette" posture, scoped to this one decorative element.
- Sized 40–64px — larger than the 32px homepage chooser icons (§6, "the only place icons render above 18px" is superseded narrowly by this section for this one decorative use), since these carry no label and read at a glance.
- Placement: the reading-spine's wide right margin (§5) beside section openers only — the masthead, "START HERE," and the results heading. Never inline with copy, never more than one per section break, never on any page but the homepage.
- No colour-coding by species or meaning — decoration, not notation. Collapses out of the layout below the 1024px breakpoint rather than being squeezed into the single-column reading spine (§9's 360px floor).

---

## 7. Page-Specific Notes

- **Index:** ~~the large site logo (§5c) serves as the masthead — seal + site name in large Fraunces, like a pamphlet title page — followed by a one-line mono subtitle~~ *(superseded 2026-07-31 — see below)* the large site logo (§5c) now serves as a hero masthead — the seal at hero scale, centred, permanently; the wordmark flashes in over it and fades for good, settling to icon-only, on its own independent timing — the page's own content below it (the one-line mono subtitle, then a short editorial foreword) keeps appearing on its existing timing regardless, rather than waiting for the hero to settle first (real prose, 2–3 paragraphs, ending "...choose by vibes" as of 2026-07-26), then a chooser section (*2026-07-23 exception, extended 2026-07-26, see §5*) — one short line of plain-prose usage guidance, a search field and a "near you" field, plus two equal-billing ways into the directory: by state and by pool setting (indoor/outdoor/springs/other), both plain mono text links (*2026-07-26: pool setting reinstated as a homepage column, see §5*) — below that row, a demoted, secondary "Browse by feature" block (large icon+label triggers, §6), quieter than the primary row's heading treatment so it reads as secondary rather than a third equal column — then the results area (§5, §7), empty by default, populated by the feature filter, the pool-setting filter, and/or the near-me 50km radius list (search has its own dropdown under the search field).
- **Venue page:** name → dateline/notation row → prose with 1–2 pull-quotes → tipped-in photo if one exists (mid-article, never top) → FAQ (if present) → appendix block (`--paper-raised`, mono, hairline-topped) with address, the Book Now button, hours, and the claim-this-listing button (*2026-07-23: upgraded from a plain mailto line to a `.book-now-btn`-styled button linking to `/claim/[slug]/`, hidden once `status` is `claimed`*). FAQ sits above the appendix, not inside it — it's still editorial content ("what is this place like"), while the appendix is the page's practical/logistics close and should stay a stable landing spot regardless of how much FAQ content exists.
- **Claim page** (*2026-07-23 addition*): same shell and prose register as a venue page — no pricing-table/SaaS treatment. Ends in a second usage of `.book-now-btn` (§7a) as its submit CTA. See UX.md §2.5.

  **Exception (user-approved, 2026-07-25).** The claim page now carries real form inputs: bordered text inputs/textareas and toggle-chips in the mono utility face (the exact `.toggle-chip` visual pattern already used in the admin app for amenities/facilities — active state fills `--thermal`, inactive stays outline — reused here, not native checkboxes/radio pills). The form stays inside the single reading-spine column, one field per row, no multi-column SaaS grid, no floating labels, no card-wrapped fieldsets, no box-shadow, no border-radius above 2px. This is a narrow, page-scoped exception to the site's otherwise text-only, input-free posture (UX.md §3) — scoped to this one page only, same pattern as the corner-menu (§5b) and homepage-motion (§9) exceptions. Nothing else on the public site gains form inputs because of this.
- **Programmatic pages** (state × amenity): identical shell; generated foreword paragraph; contents-style list. Must be indistinguishable in quality from the index.
- **Zero-image default:** every page must look complete and intentional with no images at all. Images are garnish, never load-bearing. (See UX.md §4 for the image approval pipeline.)
- **Blog (2026-07-21 addition):** same typographic-entries list style as the index (no cards, no thumbnails in the list — DESIGN.md §5). A post's cover image is a plain full-width image with a `--paper-raised` mount border, deliberately *not* the tipped-in/rotated/`PLATE I.` treatment (§4) — that treatment is the venue page's specimen-photograph signature; a blog cover image functions more like a banner than a mid-article aside, so it gets a plainer, undecorated treatment instead. In-body Quill images render at their natural HTML size with no special framing.

### 7a. Interactive elements — the Book Now button

The public site has exactly one button *style* (`.book-now-btn`), used in two places: the venue page's "Book now" link out to the venue's own website, and (*2026-07-23*) the "Claim this listing" button and the claim page's mailto CTA — the same class, not a second style. It must look like a stamped instruction, not a SaaS CTA:

- Element: a real `<a>` styled as a button (it navigates, so not `<button>`).
- Sits inline in the page flow, inside the appendix block, alongside the address and claim-this-listing button — never fixed or floating (UX.md §3 already bans floating buttons site-wide).
- Typography: IBM Plex Mono, uppercase, letterspaced 0.05em, 13px — matches the appendix block's existing mono register, not the display face.
- Colour: 1px solid `--thermal` border, `--thermal` text; background stays `--paper-raised` (the appendix block's own surface) — no filled thermal background, which would exceed the "<5% of screen" thermal budget on a page that may also show thermal in the notation row and links. Hover/focus keeps the border and text thermal-only (no colour-flip, no glow).
- Shape: 0 border-radius (the site-wide reset already enforces this — do not override it above 2px). No box-shadow, no gradient, no icon.
- Padding: roughly 0.75em vertical, 1.25em horizontal — a legible tappable target (44px minimum height) without becoming a hero element.

## 8. Admin UI (visual only — behaviour in UX.md)

The admin hub inherits the palette (both modes, §2) and the mono utility face but is allowed to be plainer: it's the workbench, not the pamphlet. Border-radius up to 4px and functional focus rings are fine here. Log output in mono on `--paper`, thermal for success lines, oxide for failures. No component library — hand-rolled, small, fast. Theme mode is auto (`prefers-color-scheme`) only — no manual toggle (§5a).

## 9. Quality Floor

Responsive to 360px. Visible keyboard focus (thermal 1px outline, offset 2px). `prefers-reduced-motion` respected — the only motion on the public site is subtle anyway (link underline transitions, map interactions; ~~no scroll-triggered reveals, no parallax~~ — *superseded 2026-07-30, see "Notebook Depth" below*). Semantic HTML; the site must read correctly with CSS off — and, as of the exception below, with JavaScript off too.

**Homepage on-load motion (user-approved, 2026-07-24 exception).** The homepage — and only the homepage — carries one restrained load animation: its top-level sections fade and rise ~10px into place, and the two section-divider hairlines draw in left-to-right. It runs once, on load; there are still no scroll-triggered reveals and no parallax anywhere. It is CSS-only (`rise-in` / `draw-line` in `global.css`), the at-rest state is the final state, and the existing `prefers-reduced-motion` kill-switch renders everything in place with no flash. This is a narrow exception to the "link underlines and map states only" posture, scoped to the homepage; it does not license motion on other pages or reopen scroll/parallax effects.

**Homepage masthead hero motion (user-approved, 2026-07-31 exception — a second, narrowly-scoped addition alongside "Homepage on-load motion" above, not a replacement for it).** On the index only, alongside the existing rise-in/draw-line cascade (unretimed — see below), the hero-scale site logo (§5c) plays a one-time, CSS-only, on-load sequence with no scroll trigger and no looping: the wordmark beneath the seal fades and rises in (0.7s, `ease-out` — the same idiom as `rise-in`), holds fully visible for a brief legible pause (0.9s, reusing `draw-line`'s own duration rather than inventing a third figure), then fades back out (0.7s) and stays gone — the seal itself never animates and never shrinks. This plays on every load, with no `sessionStorage`/`localStorage` gating, exactly like the rest of this file's homepage motion. Unlike `rise-in` (whose at-rest, unanimated state is the same as its visible end state), this sequence's un-animated resting style is itself `opacity: 0` — the keyframes exist to temporarily reveal-then-hide it, not the reverse — so the sitewide reduced-motion kill-switch leaves the wordmark in its plain resting state (invisible) with no flash, rather than merely freezing the animation mid-flight. **Deliberately not** used as a reason to delay the header/foreword/chooser/results cascade below it — that cascade keeps its existing 0/90/180/270ms stagger, unretimed, so real page content stays visible almost immediately; only the hero's own wordmark recedes independently above it.

**Sitewide restrained motion (user-approved, 2026-07-26 exception — extends the above beyond the homepage).** Two additions, both CSS-only and neutralised automatically by the same `prefers-reduced-motion` kill-switch (plain CSS transitions, not JS-driven animation):

1. The corner-menu drawer (§5b) slides in/out via a `transform` transition rather than an instant `hidden`-attribute toggle.
2. Subtle hover/focus colour transitions (the existing 0.15s link-underline idiom) extend to icon colour sitewide — icons use `stroke="currentColor"`, so transitioning `color` on the svg element animates the stroke wherever an ancestor's hover/focus state changes it (feature chips, corner-menu links, chooser tiles).

~~Still no scroll-triggered reveals, no parallax, and no looping anywhere on the site. This exception widens *where* the existing restrained-motion idiom applies, not *what kind* of motion is allowed.~~ *(Superseded 2026-07-30 — the exception below now widens both where and what kind.)*

**Sitewide "Notebook Depth" motion (user-approved, 2026-07-30 exception — supersedes the "no scroll-triggered reveals, no parallax" restriction above, in both the base paragraph and the 2026-07-26 exception's closing line).** Four additions, governed by the same `prefers-reduced-motion` kill-switch and a parallel no-JS-safe rule below:

1. **Restrained parallax.** The tipped-in photograph (§4) and margin-animal illustrations (§6a) drift a few pixels slower than the page scrolls — tuned tight enough to read as the weight of paper, not a product-site hero-parallax. Hard ceiling: no more than **~40px of accumulated offset** from a layer's natural scroll position over its full scroll-through, applied only to those two decorative/photographic layers — never to text or interactive elements.
2. **Section-divider hairlines draw themselves in.** The existing `draw-line` idiom (the 2026-07-24 exception above), previously homepage-load-only, now triggers sitewide — once per divider, the first time it scrolls into view, at the same 0.9s timing already in use.
3. **Line-by-line text reveal.** Headings and body copy stagger in by line as they enter view, ~60ms between lines, each line using the same fade-and-rise timing as the existing `rise-in` idiom — not a new, faster animation. A run longer than ~8–10 lines compresses rather than keeps stretching, so no block ever meaningfully outruns the ~0.7–0.9s family the rest of the site's motion already settles within.
4. **A persisting hero photograph between list and detail.** Where a venue has a published photo (§4), the transition from its listing row to its own page carries that photograph across as one continuous element, via Astro's native View Transitions — not a JS animation library. Venues with no photo (the zero-image default, §7) simply navigate normally.

Items 1–3 are implemented via a JS animation library (TRD.md §2, 2026-07-30 exception); item 4 via Astro's own `<ClientRouter />`. Both are dated exceptions to CLAUDE.md's "ask before adding any dependency" rule and to this file's prior posture.

**Binding no-JS rule (all four items).** Every element renders fully visible, in its final position, by plain CSS with no JavaScript at all — motion is something JS *adds* on top of an already-correct page, never something a missing script leaves hidden or broken. This is also what keeps the admin review pane's preview (which never loads site JS) rendering correctly.

**Binding reduced-motion rule.** `prefers-reduced-motion` renders the same final state, no flash, exactly as the 2026-07-24 exception already promises — for both the CSS kill-switch and the animation library's own reduced-motion handling.

Still governed by §10 — if in doubt, prefer less motion, not more.

Item 4's shared element requires a small, separately-scoped exception to §5's "No cards... No thumbnails in lists" — see §5's 2026-07-30 exception.

## 10. The Test

Before any gate closes, screenshot the work and ask: *could this screen be mistaken for a tech startup, a listings site, or a generic dark-mode template?* If yes, it fails the gate. The reference register is a letterpress pamphlet and a field notebook — not a product.
