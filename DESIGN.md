# DESIGN.md — Visual Specification

**Read this before touching any UI code. Every visual decision derives from this file. If a choice is not covered here, ask — do not default.**

---

## 1. Direction

**A naturalist's field diary meets a European bathhouse pamphlet. Ink on warm paper, inverted for dark mode.**

The site should feel like a privately printed guide — something set in metal type, annotated by hand, carried damp into a bathhouse. Restrained, textured, editorial. It records places the way a field guide records species: with a notation system, a dateline, and prose that takes its time.

It should **never** feel like: a SaaS product, an Airbnb listing, a Google Maps sidebar, a wellness startup, a link directory. If a screen could belong to any of those, it is wrong.

---

## 2. Colour

Dark mode is the only mode. The palette is warm paper inverted: the "paper" is deep warm charcoal, the "ink" is warm off-white. One mineral accent, one oxide secondary. Nothing else.

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#191614` | Page background. Warm near-black — charcoal with brown, never blue-black. |
| `--paper-raised` | `#211d1a` | Slightly lifted surfaces (review appendix block, admin panes). Difference should be barely perceptible. |
| `--ink` | `#e8e2d6` | Primary text. Warm off-white, like aged paper made luminous. |
| `--ink-faded` | `#a89f8f` | Secondary text, datelines, captions. Ink that has sat in sun. |
| `--thermal` | `#7fb5a4` | The mineral accent. Thermal-pool green — links, active states, the current map marker. Used sparingly: if more than ~5% of a screen is thermal, it's overused. |
| `--oxide` | `#b4633a` | Secondary accent. Rust/iron-oxide — reject actions, warnings, the occasional annotation. Rarer than thermal. |

**Banned:** the Tailwind default grey scale (`slate`, `gray`, `zinc`, `neutral`, `stone` utilities for colour), pure `#000`/`#fff`, any blue that reads "tech", any purple, gradients of any kind, coloured glows/shadows.

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

- **Grain:** a full-page noise overlay — SVG `feTurbulence` fractal noise, ~3% opacity, `mix-blend-mode: overlay`, fixed position, pointer-events none. Subtle enough that you only notice it when it's gone.
- **Rules, not borders:** dividers are 1px hairlines in `--ink-faded` at 25% opacity. No boxed borders around content blocks. No border-radius above 2px anywhere on the public site. No box-shadows on the public site, ever.
- **The tipped-in photograph** (see §6, Signature): when a venue has an image, it is treated as a physical photo tipped into a diary — inset, not full-bleed; 2–4px `--paper-raised` mount border; rotated between −1.2° and +1.2° (derive deterministically from the slug hash so it's stable per venue); mono caption beneath, e.g. `PLATE I. — THE MAGNESIUM POOL, LOOKING SOUTH.`
- **Section openers:** small-caps mono eyebrow + hairline, in the manner of a pamphlet chapter head. No icons.

---

## 5. Layout Grammar

- **Single reading spine.** One column of prose, max 65ch, asymmetrically placed (offset left of centre on wide screens, with the wide right margin used for occasional mono margin-notes). Never centred symmetric hero layouts.
- **No cards.** Venue listings on the index are typographic entries — name, dateline, one-line notation — separated by hairlines, like a table of contents. No thumbnails in lists.
- **Whitespace is structural.** Section spacing at 6–10rem on desktop. When in doubt, add space, not decoration.
- **Filters are text.** Amenity filters render as inline mono toggles (`magnesium pool · infrared · cold plunge`); active state = thermal underline. No sidebar, no checkboxes, no pills.
- The map (Leaflet) is a chapter within the index page, not the hero. Tiles must be styled/filtered to sit in the palette (CSS filter to warm-dark, or a dark tile theme with a warm overlay). Default markers replaced with a small thermal ring; active marker fills.

---

## 6. Signature Element — the Field Notation System

The one thing this site is remembered by: **amenities are recorded as a naturalist's notation, not icons.**

Each amenity has a two-to-three-letter mono abbreviation, printed as a specimen label in the venue dateline row and in index entries:

```
37.8136° S, 144.9631° E   ·   VIC   ·   Mg · IR · SA · CP
```

- `Mg` magnesium pool · `IR` infrared sauna · `SA` traditional sauna · `CP` cold plunge · `LED` light therapy
- Present amenities in `--ink`; absent ones omitted (never greyed-out — a field diary doesn't record what wasn't there).
- On hover/focus, the abbreviation expands inline to its full name in italic Newsreader.
- The same notation drives the filter toggles and the programmatic SEO page headings ("Bathhouses of Victoria — Mg · CP").

This system must be used consistently everywhere amenities appear, including the admin review pane.

---

## 7. Page-Specific Notes

- **Index:** masthead first — site name in large Fraunces with a one-line mono subtitle (like a pamphlet title page), then a short editorial foreword (real prose, 2–3 paragraphs), then the map chapter, then the state-grouped contents list.
- **Venue page:** name → dateline/notation row → prose with 1–2 pull-quotes → tipped-in photo if one exists (mid-article, never top) → FAQ (if present) → appendix block (`--paper-raised`, mono, hairline-topped) with address, the Book Now button, hours, and the claim-this-listing line. FAQ sits above the appendix, not inside it — it's still editorial content ("what is this place like"), while the appendix is the page's practical/logistics close and should stay a stable landing spot regardless of how much FAQ content exists.
- **Programmatic pages** (state × amenity): identical shell; generated foreword paragraph; contents-style list. Must be indistinguishable in quality from the index.
- **Zero-image default:** every page must look complete and intentional with no images at all. Images are garnish, never load-bearing. (See UX.md §4 for the image approval pipeline.)

### 7a. Interactive elements — the Book Now button

The public site has exactly one button-styled element: the venue page's "Book now" link out to the venue's own website. It must look like a stamped instruction, not a SaaS CTA:

- Element: a real `<a>` styled as a button (it navigates, so not `<button>`).
- Sits inline in the page flow, inside the appendix block, alongside the address and claim-this-listing lines — never fixed or floating (UX.md §3 already bans floating buttons site-wide).
- Typography: IBM Plex Mono, uppercase, letterspaced 0.05em, 13px — matches the appendix block's existing mono register, not the display face.
- Colour: 1px solid `--thermal` border, `--thermal` text; background stays `--paper-raised` (the appendix block's own surface) — no filled thermal background, which would exceed the "<5% of screen" thermal budget on a page that may also show thermal in the notation row and links. Hover/focus keeps the border and text thermal-only (no colour-flip, no glow).
- Shape: 0 border-radius (the site-wide reset already enforces this — do not override it above 2px). No box-shadow, no gradient, no icon.
- Padding: roughly 0.75em vertical, 1.25em horizontal — a legible tappable target (44px minimum height) without becoming a hero element.

## 8. Admin UI (visual only — behaviour in UX.md)

The admin hub inherits the palette and the mono utility face but is allowed to be plainer: it's the workbench, not the pamphlet. Border-radius up to 4px and functional focus rings are fine here. Log output in mono on `--paper`, thermal for success lines, oxide for failures. No component library — hand-rolled, small, fast.

## 9. Quality Floor

Responsive to 360px. Visible keyboard focus (thermal 1px outline, offset 2px). `prefers-reduced-motion` respected — the only motion on the public site is subtle anyway (link underline transitions, map interactions; no scroll-triggered reveals, no parallax). Semantic HTML; the site must read correctly with CSS off.

## 10. The Test

Before any gate closes, screenshot the work and ask: *could this screen be mistaken for a tech startup, a listings site, or a generic dark-mode template?* If yes, it fails the gate. The reference register is a letterpress pamphlet and a field notebook — not a product.
