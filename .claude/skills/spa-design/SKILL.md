---
name: spa-design
description: Visual and interaction constraints for the spa directory project. Use before writing or editing ANY UI code — Astro components, pages, layouts, Tailwind classes, admin templates, CSS, or map styling. Also use when reviewing screenshots of the site or admin app.
---

# Spa Directory Design Enforcement

Before touching any UI code, read `DESIGN.md` (visual spec) and the relevant section of `UX.md` (behaviour spec) at the repo root. They are binding. This skill is the checklist that keeps sessions honest.

## Hard rules (violation = the work is wrong, redo it)

- Palette is the six DESIGN.md tokens only. **Never** Tailwind's slate/gray/zinc/neutral/stone colour utilities, pure #000/#fff, gradients, or coloured shadows.
- Type: Fraunces (display) / Newsreader (body) / IBM Plex Mono (utility). **No sans-serif exists on the public site.** No font-weight ≥700 anywhere.
- Public site: no border-radius >2px, no box-shadows, no cards, no modals, no toasts. The site is icon-free everywhere **except** venue-feature display (DESIGN.md §6, 2026-07-21 exception) — section openers, the Book Now button, and filter toggles stay text/icon-free as before.
- Body measure capped at 65ch. Section spacing 6–10rem desktop. Hairline rules, not borders.
- Amenity/facility display uses the hand-authored inline SVG icon set (`site/src/components/Icon.astro` / `Features.astro`) per DESIGN.md §6, present-only, icon+label in full context and icon-only with a `title` tooltip in compact/list contexts.
- Venue images only via the TippedPhoto treatment (mount border, PLATE-register mono caption). Never full-bleed. The rotation this treatment used to apply was removed 2026-07-22 (DESIGN.md §4) — photos now sit flat; mount border/caption unchanged. Blog cover images (2026-07-21, DESIGN.md §7) are a separate, longer-standing exception — plain full-width image with a `--paper-raised` mount border, no caption; see DESIGN.md §7 for why. **2026-07-30 exception (DESIGN.md §5):** venue list rows now show a small (~56–72px), unbordered thumbnail when a venue has a published photo — narrowly scoped to feeding the sitewide hero-photo page transition (below), not a general reopening of "no thumbnails in lists."
- A small fixed corner menu (bottom-right, `MENU` text button) and a single hairline page-frame border are both named, dated exceptions (DESIGN.md §5b and §4/2026-07-22) to the "never fixed/floating" and "no boxed borders" rules — narrowly scoped to those two elements, not a general reopening.
- Blog (2026-07-21): same typographic-entries list style as the index, no cards. Admin authoring screen at `/blog` uses Quill.js (vendored, `admin/static/vendor/quill/`) repainted to the site's dark palette — see `admin/static/blog.css`.
- Grain overlay present on every public page. **Motion doctrine superseded 2026-07-30 (DESIGN.md §9 / UX.md §3) — "Notebook Depth."** Sitewide, not homepage-only, now: restrained parallax (capped ~40px) on the tipped-in photo and margin animals; section-divider hairlines draw themselves in on scroll-into-view (`.draw-line-on-view`, `site/src/scripts/motion.ts`); headings/paragraphs reveal line-by-line (~60ms/line stagger) on scroll-into-view; a venue's hero photo persists between its list thumbnail and its own page via Astro's `<ClientRouter />`. Built with `gsap`/`ScrollTrigger`/`SplitText` (TRD.md §2, 2026-07-30 exception) for the in-page effects. **Binding regardless of any of the above:** every element must render fully visible, in final position, in plain server-rendered HTML with no JS at all (the admin review-pane preview never loads site JS, so this isn't optional) — motion only ever adds to an already-correct page. `prefers-reduced-motion` must show the same final state, no flash, via **both** the CSS kill-switch **and** `gsap.matchMedia()` (the CSS kill-switch alone does not stop GSAP, which animates via `requestAnimationFrame`, not CSS `transition`/`animation`). Still no parallax/reveal effect should read as looping or as a generic scroll-hijacking product site — apply the §10 test below at a mid-scroll position, not just top-of-page.
- Admin app: same palette + mono, radius ≤4px allowed, focus rings required, oxide = destructive/failure, thermal = confirm/success.

## Session discipline

1. When a design decision isn't covered by DESIGN.md/UX.md, stop and ask — don't default. Defaults regress to tech-startup generic, which is the one named failure mode.
2. After any visual change, screenshot if possible and apply the DESIGN.md §10 test: *could this be mistaken for a SaaS product, a listings site, or a dark-mode template?* If yes, it fails.
3. Write user-facing copy in Australian English, in the register of the site (dry, specific, no marketing vocabulary — the Gatekeeper banned list in PROMPTS/gatekeeper.md applies to UI copy too).
