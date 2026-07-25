// Hand-authored decorative line-art animals (DESIGN.md §6a, 2026-07-26
// addition). Same visual language as paths.ts — 24x24 viewBox, stroke-only,
// currentColor, no fill, simple primitives — but decorative rather than
// functional, so kept in a separate set with its own renderer
// (MarginAnimal.astro) instead of extending IconKey/Icon.astro.

export type AnimalKey = "otter" | "capybara" | "penguin" | "duck";

export const ANIMAL_PATHS: Record<AnimalKey, string> = {
  otter: `
    <ellipse cx="12" cy="15" rx="8" ry="4" />
    <circle cx="6.5" cy="10.5" r="3" />
    <circle cx="14" cy="13.2" r="1.1" />
    <path d="M4 15.5c-1 .4-1 1.4 0 1.8M20 15.5c1 .4 1 1.4 0 1.8" />
  `,
  capybara: `
    <path d="M4 12v5a8 4 0 0 0 16 0v-5" />
    <path d="M4 12a8 4 0 0 1 16 0" />
    <ellipse cx="12" cy="9" rx="5" ry="3.2" />
    <circle cx="9.3" cy="8.6" r=".6" />
    <path d="M6.5 11.5v2M17.5 11.5v2" />
  `,
  penguin: `
    <ellipse cx="12" cy="14" rx="5" ry="7" />
    <circle cx="12" cy="6" r="3" />
    <circle cx="13.1" cy="5.5" r=".5" />
    <path d="M7 12c-1 3 .5 6 5 6s6-3 5-6" />
    <path d="M10 20.5l1 1.8M14 20.5l-1 1.8" />
  `,
  duck: `
    <ellipse cx="11" cy="14.5" rx="7" ry="5" />
    <circle cx="17" cy="10" r="3.2" />
    <path d="M20 10.3c1 .2 1 1 0 1.2" />
    <circle cx="18" cy="9" r=".5" />
    <path d="M3 19c1.2 1.4 2.4 1.4 3.6 0s2.4-1.4 3.6 0 2.4 1.4 3.6 0 2.4-1.4 3.6 0" />
  `,
};
