// Centralised cross-cutting paths/constants (CLAUDE.md rule 4 — no hardcoded
// relative paths in feature code).

export const AMENITY_KEYS = [
  "magnesium_pool",
  "infrared_sauna",
  "traditional_sauna",
  "cold_plunge",
  "led_therapy",
] as const;

export const AMENITY_NOTATION: Record<(typeof AMENITY_KEYS)[number], { short: string; full: string }> = {
  magnesium_pool: { short: "Mg", full: "Magnesium pool" },
  infrared_sauna: { short: "IR", full: "Infrared sauna" },
  traditional_sauna: { short: "SA", full: "Traditional sauna" },
  cold_plunge: { short: "CP", full: "Cold plunge" },
  led_therapy: { short: "LED", full: "LED light therapy" },
};

// Facilities (2026-07-21 addition — practical/logistics info, distinct from
// the bathing-experience amenities above; see SCHEMA.md §2).
export const FACILITY_KEYS = [
  "parking",
  "towels_provided",
  "changerooms",
  "bookings_required",
  "wheelchair_access",
] as const;

export const FACILITY_LABELS: Record<(typeof FACILITY_KEYS)[number], string> = {
  parking: "Parking",
  towels_provided: "Towels provided",
  changerooms: "Changerooms",
  bookings_required: "Bookings required",
  wheelchair_access: "Wheelchair access",
};

export const STATES = ["VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT"] as const;

export const STATE_NAMES: Record<(typeof STATES)[number], string> = {
  VIC: "Victoria",
  NSW: "New South Wales",
  QLD: "Queensland",
  SA: "South Australia",
  WA: "Western Australia",
  TAS: "Tasmania",
  NT: "Northern Territory",
  ACT: "Australian Capital Territory",
};

export const AU_LATITUDE_BOUNDS = { min: -44.0, max: -9.0 } as const;
export const AU_LONGITUDE_BOUNDS = { min: 112.0, max: 154.0 } as const;

// Amenity keys are snake_case (SCHEMA.md §1); URL path segments use kebab-case.
export function amenityUrlSlug(key: (typeof AMENITY_KEYS)[number]): string {
  return key.replace(/_/g, "-");
}

export function amenityFromUrlSlug(segment: string): (typeof AMENITY_KEYS)[number] | undefined {
  return AMENITY_KEYS.find((key) => amenityUrlSlug(key) === segment);
}

// Blog video embeds (2026-07-21 addition) — external embeds only (YouTube/
// Vimeo), validated against the same host allowlist as the zod schema
// (site/src/content/config.ts). Converts a watch/share URL into an
// embeddable iframe src.
export function videoEmbedUrl(url: string): string {
  const youtubeWatch = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)/);
  if (youtubeWatch) return `https://www.youtube-nocookie.com/embed/${youtubeWatch[1]}`;
  const vimeoShare = url.match(/vimeo\.com\/(\d+)/);
  if (vimeoShare) return `https://player.vimeo.com/video/${vimeoShare[1]}`;
  return url; // already an embeddable player.vimeo.com/video/ID URL
}

export const SITE_NAME = "Bathers'";
export const SITE_TAGLINE = "Notes on heat, cold and water at Australian day spas and bathhouses.";

// GoatCounter click tracking (Book Now button only — TRD.md §8 exception).
// Site codes aren't secret; only the read-back API token stays server-side
// in admin/.env (GOATCOUNTER_API_TOKEN, see admin/pipeline/goatcounter.py).
// The Astro build has no .env loader of its own (TRD.md §2 — no runtime
// backend for the public site), so this lives here as a plain constant.
export const GOATCOUNTER_SITE = "bathers";
