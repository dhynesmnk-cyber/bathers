// Hand-authored inline SVG icon set (2026-07-21 DESIGN.md §6 exception — see
// that section for the rationale). Every icon shares the same visual
// language: 24x24 viewBox, stroke-only, currentColor, no fill, so a single
// Icon.astro renderer can apply consistent stroke-width/cap/join site-wide.
// Keys match the amenity/facility keys in config.ts exactly, plus "hours"
// and "cost".

export type IconKey =
  | "magnesium_pool"
  | "infrared_sauna"
  | "traditional_sauna"
  | "cold_plunge"
  | "led_therapy"
  | "hours"
  | "cost"
  | "parking"
  | "towels_provided"
  | "changerooms"
  | "bookings_required"
  | "wheelchair_access";

export const ICON_PATHS: Record<IconKey, string> = {
  magnesium_pool: `
    <path d="M2 8c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0" />
    <path d="M2 13c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0" />
    <path d="M2 18c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0" />
  `,
  infrared_sauna: `
    <rect x="5" y="11" width="14" height="7" rx="1" />
    <path d="M9 11V5M12 11V3M15 11V5" />
  `,
  traditional_sauna: `
    <path d="M12 3c2.2 3 3 5 3 7.5a3 3 0 1 1-6 0C9 8 9.8 6 12 3z" />
    <path d="M9 14.5a3 3 0 0 0 6 0" />
  `,
  cold_plunge: `
    <path d="M12 2v20" />
    <path d="M4.5 6.5l15 11" />
    <path d="M4.5 17.5l15-11" />
    <path d="M10 6.3l2 1.2 2-1.2M10 17.7l2-1.2 2 1.2M6 9.3l.3-2.3-2-1M6 14.7l.3 2.3-2 1M18 9.3l-.3-2.3 2-1M18 14.7l-.3 2.3 2 1" />
  `,
  led_therapy: `
    <path d="M12 3.5a5.5 5.5 0 0 0-3.2 10c.5.4.9 1 .9 1.7h4.6c0-.7.4-1.3.9-1.7A5.5 5.5 0 0 0 12 3.5z" />
    <path d="M9.5 18h5M10.2 20.5h3.6" />
  `,
  hours: `
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5V12l3.2 2" />
  `,
  cost: `
    <path d="M3 11.2V5a1 1 0 0 1 1-1h6.2a1 1 0 0 1 .7.3l8.4 8.4a1 1 0 0 1 0 1.4l-6.3 6.3a1 1 0 0 1-1.4 0L3.3 11.9a1 1 0 0 1-.3-.7z" />
    <circle cx="7.8" cy="7.8" r="1.3" />
  `,
  parking: `
    <rect x="3.5" y="3.5" width="17" height="17" rx="1.5" />
    <path d="M9 17V7h3.3a2.8 2.8 0 0 1 0 5.6H9" />
  `,
  towels_provided: `
    <rect x="4.5" y="5" width="15" height="3.6" rx="1" />
    <rect x="4.5" y="10.2" width="15" height="3.6" rx="1" />
    <rect x="4.5" y="15.4" width="9" height="3.6" rx="1" />
  `,
  changerooms: `
    <path d="M12 4.2a2 2 0 1 1 1.8 2c-.5.3-.8.7-.8 1.3v.3" />
    <path d="M12 7.8L3.2 13.6c-.8.5-.4 1.7.5 1.7h16.6c.9 0 1.3-1.2.5-1.7L12 7.8z" />
  `,
  bookings_required: `
    <rect x="3.5" y="4.8" width="17" height="15.5" rx="1.5" />
    <path d="M3.5 9.3h17M8 2.8v4M16 2.8v4" />
    <path d="M8.3 14.3l2 2 4.4-4.4" />
  `,
  wheelchair_access: `
    <circle cx="11" cy="4.3" r="1.6" />
    <path d="M11 7.7v3.3l4 1.6" />
    <path d="M10.7 11H7a4 4 0 1 0 2.5 7.1L13 22" />
  `,
};
