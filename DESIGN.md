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
- **No cards.** Venue listings on the index are typographic entries — name, dateline, one-line notation — separated by hairlines, like a table of contents. No thumbnails in lists.
- **Whitespace is structural.** Section spacing at 6–10rem on desktop. When in doubt, add space, not decoration.
- **Filters are text.** Amenity filters render as inline mono toggles (`magnesium pool · infrared · cold plunge`); active state = thermal underline. No sidebar, no checkboxes, no pills.
- **2026-07-26 — map removed.** The map (Leaflet) chapter described in earlier revisions of this section is superseded: the homepage no longer carries a map. It's replaced by a manual-postcode "facilities around me" 50km radius list (UX.md §2.1) rendered in the same results slot as search. Kept here, struck through for the record: ~~The map (Leaflet) is a chapter within the index page, not the hero. Tiles must be styled/filtered to sit in the palette (CSS filter to warm-dark, or a dark tile theme with a warm overlay). Default markers replaced with a small thermal ring; active marker fills.~~

**Exception (user-approved, 2026-07-23).** The homepage carries one icon-based chooser section (§6, §7) between the foreword and the results area — a narrow, scoped departure from "never centred symmetric hero layouts" and "filters are text... no pills" above. It stays inside the reading-spine rhythm (asymmetric, not full-bleed, not centred) so it reads as the next section of the pamphlet rather than a hero banner, and it fronts the site's existing plain-text amenity filter and state pages rather than replacing either. Everything else covered by these two rules — the inline amenity-filter toggle bar, state/amenity page nav, and all venue listings — is unaffected and stays plain mono text and card-free.

**2026-07-25 extension.** The same chooser section also fronts a plain mono-text search field and a "near you" suburb/postcode field (TRD.md §8 exception), sitting above the existing by-state/by-amenity grid. Same idiom as everything else in §5 — text inputs and text buttons, underline-on-focus, no pill/card treatment, not a third icon grid or hero element. The search field also appears inside the corner menu panel (§5b) so it's reachable from every page, not just the homepage.

**2026-07-26 extension.** Below the chooser, a results area (also §7) replaces the former map-plus-contents-list pairing: empty by default with a direction line, populated by the amenity filter and/or the near-me 50km radius list (search keeps its own dropdown under the search field, unchanged), each row the existing `VenueEntry` typographic-entry treatment (§5, "no cards"). The pool-type grouping (thermal springs/indoor/outdoor/other) that the removed default contents list used to sort by no longer has a homepage entry point — it remains reachable via each state's `/[state]/[pooltype]/` pages (UX.md §2.3, unchanged) and is otherwise surfaced per-venue via promoted feature badges (§6, DESIGN.md's Features.astro ordering) rather than a new sitewide browse column, since no sitewide pool-type route exists to link to.

---

## 5a. Theme Toggle (2026-07-21 addition)

A narrow, deliberate exception to the site's otherwise icon-free, toggle-free chrome — the second interactive control on the public site after the Book Now button (§7a).

- Renders in-flow at the top of every page, above that page's own opening content (masthead on the index, the venue name on a venue page, the foreword on a programmatic page, the post title on a blog page) — never fixed, never floating (§3/UX.md's floating-UI ban still holds).
- A plain mono text control, in the "filters are text" idiom (§5) — not an icon, switch, or pill.
- Auto-detects the visitor's OS preference (`prefers-color-scheme`) by default; a click/keyboard-activated override persists via `localStorage` across the visit.
- No animated transition on switch — a plain state change, consistent with the site's restrained motion posture (§9) and `prefers-reduced-motion`.
- Admin app: auto (`prefers-color-scheme`) only, no manual toggle — it's a private, single-operator workbench (§8), not a visitor-facing surface.

## 5b. Corner Menu (2026-07-22 exception)

**Exception (user-approved, 2026-07-22).** A small fixed navigation control, superseding §3/§5a's "never fixed, never floating" rule — narrowly, for this one control only. Everything else in §3/§5a still holds: no modals, no toasts, no other floating chrome.

- A single button fixed to the top-right corner of the viewport on every page (*2026-07-23: moved from bottom-right at the user's request; no other change to this control*), labelled `MENU` in mono text (no new icon — matches the "filters are text" idiom of §5 rather than adding an 11th icon to the set in §6).
- Click/tap opens a panel listing: Home, every state with ≥1 published venue, every category with ≥1 published venue, and links to the glossary and journal. Click-to-open, not hover-only, for touch/mobile parity.
- The panel itself keeps the rest of the visual system exactly: `--paper-raised` background, hairline `--ink-faded` border, no border-radius above 2px, no box-shadow, no banned colours or gradients (§2/§4).
- Keyboard-operable: reachable by Tab, opens on Enter/Space, closes on `Escape` (focus returns to the button), same posture as any other interactive control on the site.

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

**Second icon-rendering context (2026-07-23 exception).** The homepage chooser section (§7) reuses this exact renderer and these exact rules — 24×24 viewBox, stroke-only, `currentColor`, no fill — at a single larger size, 32px, roughly double the largest existing usage (16px, full-size venue-page context). This is the only place icons render above 18px; nowhere else on the site should adopt this larger size without a further documented exception.

Superseded text, kept for record: amenities were previously recorded as a naturalist's notation — a two-to-three-letter mono abbreviation (`Mg` magnesium pool · `IR` infrared sauna · `SA` traditional sauna · `CP` cold plunge · `LED` light therapy), expanding to the full name on hover/focus. That system is no longer in use for venue-feature display as of 2026-07-21.

---

## 6a. Margin Animal Motifs (2026-07-26 addition)

A narrow, homepage-only exception adding sparse decorative illustration where §6's icons are strictly functional. Hand-authored, stroke-only line-art animals (bathing/sauna-themed — otter, capybara, penguin, duck and similar), drawn in the same authoring spirit as §6's icon set, not lifted wholesale from any external reference:

- One shared renderer (`site/src/components/MarginAnimal.astro`, paths in `site/src/icons/animals.ts`), mirroring `Icon.astro`'s shape: `currentColor` stroke, `stroke-width: 1.4–1.8`, no fill, simple primitives (circles, rects, short paths) — same visual family as §6, just decorative rather than functional.
- Sized 40–64px — larger than the 32px homepage chooser icons (§6, "the only place icons render above 18px" is superseded narrowly by this section for this one decorative use), since these carry no label and read at a glance.
- Placement: the reading-spine's wide right margin (§5) beside section openers only — the masthead, "START HERE," and the results heading. Never inline with copy, never more than one per section break, never on any page but the homepage.
- Single colour, no colour-coding by species or meaning — decoration, not notation. Collapses out of the layout below the 640px breakpoint rather than being squeezed into the single-column reading spine (§9's 360px floor).

---

## 7. Page-Specific Notes

- **Index:** masthead first — site name in large Fraunces with a one-line mono subtitle (like a pamphlet title page), then a short editorial foreword (real prose, 2–3 paragraphs), then a chooser section (*2026-07-23 exception, extended 2026-07-26, see §5*) — one short line of plain-prose usage guidance, a search field and a "near you" field, plus two ways into the directory: by state (plain mono text links) and by amenity (large icon+label triggers, §6) — then the results area (§5, §7), empty by default, populated by the amenity filter and/or the near-me 50km radius list (search has its own dropdown under the search field).
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

Responsive to 360px. Visible keyboard focus (thermal 1px outline, offset 2px). `prefers-reduced-motion` respected — the only motion on the public site is subtle anyway (link underline transitions, map interactions; no scroll-triggered reveals, no parallax). Semantic HTML; the site must read correctly with CSS off.

**Homepage on-load motion (user-approved, 2026-07-24 exception).** The homepage — and only the homepage — carries one restrained load animation: its top-level sections fade and rise ~10px into place, and the two section-divider hairlines draw in left-to-right. It runs once, on load; there are still no scroll-triggered reveals and no parallax anywhere. It is CSS-only (`rise-in` / `draw-line` in `global.css`), the at-rest state is the final state, and the existing `prefers-reduced-motion` kill-switch renders everything in place with no flash. This is a narrow exception to the "link underlines and map states only" posture, scoped to the homepage; it does not license motion on other pages or reopen scroll/parallax effects.

## 10. The Test

Before any gate closes, screenshot the work and ask: *could this screen be mistaken for a tech startup, a listings site, or a generic dark-mode template?* If yes, it fails the gate. The reference register is a letterpress pamphlet and a field notebook — not a product.
