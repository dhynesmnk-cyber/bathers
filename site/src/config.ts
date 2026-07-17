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

export const STATES = ["VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT"] as const;

export const AU_LATITUDE_BOUNDS = { min: -44.0, max: -9.0 } as const;
export const AU_LONGITUDE_BOUNDS = { min: 112.0, max: 154.0 } as const;

export const SITE_NAME = "Bathers'";
export const SITE_TAGLINE = "A field guide to Australian day spas and bathhouses.";
