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
- Venue images only via the TippedPhoto treatment (mount border, deterministic slug-hash rotation, PLATE-register mono caption). Never full-bleed, never in lists. Blog cover images (2026-07-21, DESIGN.md §7) are the one exception — plain full-width image with a `--paper-raised` mount border, no rotation/caption; see DESIGN.md §7 for why.
- Blog (2026-07-21): same typographic-entries list style as the index, no cards. Admin authoring screen at `/blog` uses Quill.js (vendored, `admin/static/vendor/quill/`) repainted to the site's dark palette — see `admin/static/blog.css`.
- Grain overlay present on every public page. Motion: link underlines and map states only; `prefers-reduced-motion` kills those.
- Admin app: same palette + mono, radius ≤4px allowed, focus rings required, oxide = destructive/failure, thermal = confirm/success.

## Session discipline

1. When a design decision isn't covered by DESIGN.md/UX.md, stop and ask — don't default. Defaults regress to tech-startup generic, which is the one named failure mode.
2. After any visual change, screenshot if possible and apply the DESIGN.md §10 test: *could this be mistaken for a SaaS product, a listings site, or a dark-mode template?* If yes, it fails.
3. Write user-facing copy in Australian English, in the register of the site (dry, specific, no marketing vocabulary — the Gatekeeper banned list in PROMPTS/gatekeeper.md applies to UI copy too).
