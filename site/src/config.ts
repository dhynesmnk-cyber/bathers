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
  "outdoor_pool",
  "indoor_pool",
  "natural_spring",
] as const;

export const FACILITY_LABELS: Record<(typeof FACILITY_KEYS)[number], string> = {
  parking: "Parking",
  towels_provided: "Towels provided",
  changerooms: "Changerooms",
  bookings_required: "Bookings required",
  wheelchair_access: "Wheelchair access",
  outdoor_pool: "Outdoor pool",
  indoor_pool: "Indoor pool",
  natural_spring: "Natural spring",
};

// Pool-type settings (2026-07-24 addition). Not a schema field of their own —
// derived from the three pool-related `facilities` booleans (SCHEMA.md §1a).
// A venue can satisfy more than one; "other" catches venues with none of the
// three so nothing drops off the by-setting listings. Shared by the homepage
// contents grouping, the /[state]/[filter] pages and the corner menu, so the
// grouping rule lives here once rather than being re-inlined at each site.
type Facilities = Partial<Record<(typeof FACILITY_KEYS)[number], boolean>> | undefined;

export const POOL_TYPES = [
  { slug: "thermal-springs", label: "Thermal springs", short: "Springs", match: (f: Facilities) => !!f?.natural_spring },
  { slug: "indoor", label: "Indoor pools", short: "Indoor", match: (f: Facilities) => !!f?.indoor_pool },
  { slug: "outdoor", label: "Outdoor pools", short: "Outdoor", match: (f: Facilities) => !!f?.outdoor_pool },
  {
    slug: "other",
    label: "Other",
    short: "Other",
    match: (f: Facilities) => !f?.natural_spring && !f?.indoor_pool && !f?.outdoor_pool,
  },
] as const;

export function poolTypeFromUrlSlug(segment: string): (typeof POOL_TYPES)[number] | undefined {
  return POOL_TYPES.find((t) => t.slug === segment);
}

// Venue categories (2026-07-22 addition — see SCHEMA.md §2). Values match the
// discovery-keyword vocabulary already in use (UX.md §1.1): "day spa,
// bathhouse, hot springs, thermal baths".
export const CATEGORIES = ["thermal_springs", "bathhouse", "day_spa", "other"] as const;

export const CATEGORY_LABELS: Record<(typeof CATEGORIES)[number], string> = {
  thermal_springs: "Thermal springs",
  bathhouse: "Bathhouse",
  day_spa: "Day spa",
  other: "Other",
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

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

// Straight-line (great-circle) distance in km. Shared by the venue page's
// build-time "Nearby" block and the client-side near-me sort (2026-07-25
// addition, TRD.md §8 exception) so the distance rule lives once rather than
// being reimplemented per caller. Has no server-only dependency, so it's
// importable from both Astro frontmatter (build time) and browser <script>
// modules (client-side).
export function haversineDistanceKm(a: GeoPoint, b: GeoPoint): number {
  const R = 6371;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

// Nearest-N candidates by straight-line distance, any category. `getCoords`
// lets one helper serve both build-time content-collection entries
// (spa/[slug].astro) and plain client-side marker objects (Map.astro's
// near-me mode) — candidates without resolvable coordinates are dropped
// rather than sorted arbitrarily.
export function nearestByDistance<T>(
  origin: GeoPoint,
  candidates: T[],
  n: number,
  getCoords: (item: T) => GeoPoint | null,
): Array<{ item: T; distanceKm: number }> {
  return candidates
    .map((item) => {
      const coords = getCoords(item);
      return coords ? { item, distanceKm: haversineDistanceKm(origin, coords) } : null;
    })
    .filter((x): x is { item: T; distanceKm: number } => x !== null)
    .sort((a, b) => a.distanceKm - b.distanceKm)
    .slice(0, n);
}

// Distance display: one decimal place under 10 km, whole km at/above —
// shared by the Nearby block and the near-me distance-slot span.
export function formatDistanceKm(distanceKm: number): string {
  return distanceKm < 10 ? `${distanceKm.toFixed(1)} km` : `${Math.round(distanceKm)} km`;
}

// Amenity keys are snake_case (SCHEMA.md §1); URL path segments use kebab-case.
export function amenityUrlSlug(key: (typeof AMENITY_KEYS)[number]): string {
  return key.replace(/_/g, "-");
}

export function amenityFromUrlSlug(segment: string): (typeof AMENITY_KEYS)[number] | undefined {
  return AMENITY_KEYS.find((key) => amenityUrlSlug(key) === segment);
}

// Category keys are snake_case (SCHEMA.md §2); URL path segments use kebab-case.
export function categoryUrlSlug(key: (typeof CATEGORIES)[number]): string {
  return key.replace(/_/g, "-");
}

export function categoryFromUrlSlug(segment: string): (typeof CATEGORIES)[number] | undefined {
  return CATEGORIES.find((key) => categoryUrlSlug(key) === segment);
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

// Cost display (2026-07-23). `cost` frontmatter is a freeform Architect-
// drafted string that can run long ("Early Bird from $39 (weekday) / $49
// (Fri–Sun); standard Soak from $59…"). Summary contexts show a compact
// range derived from every dollar amount in the string; the full text
// stays on the venue page's appendix. Returns null when no $ amount is
// found so callers can fall back to the raw string.
export function priceRange(cost: string): string | null {
  const amounts = Array.from(cost.matchAll(/\$\s?(\d[\d,]*(?:\.\d{1,2})?)/g), (m) =>
    Number(m[1].replace(/,/g, "")),
  ).filter((n) => Number.isFinite(n));
  if (amounts.length === 0) return null;
  const min = Math.min(...amounts);
  const max = Math.max(...amounts);
  const fmt = (n: number) => `$${n % 1 === 0 ? n.toLocaleString("en-AU") : n.toFixed(2)}`;
  if (min === max) return /\bfrom\b/i.test(cost) ? `from ${fmt(min)}` : fmt(min);
  return `${fmt(min)}–${fmt(max)}`;
}

export const SITE_NAME = "Bathers'";
export const SITE_TAGLINE = "Notes on heat, cold and water at Australian day spas and bathhouses.";

// Claim-listing CTA (2026-07-23 addition — TRD.md §8 exception, UX.md §2.5).
// No longer used by the claim page itself since the 2026-07-25 form/payment
// exception replaced its mailto CTA, but harmless to keep as a record.
export const CLAIM_EMAIL = "d.hynes.mnk@gmail.com";

// The deployed admin app's public origin (Fly.io) — the claim form's fetch
// target, since the static site has no backend of its own (2026-07-25,
// TRD.md §8 exception). Same "plain exported constant, no site-side .env
// loader" pattern as SITE_URL/GOATCOUNTER_SITE below.
export const CLAIM_API_BASE_URL = "https://bathers-admin.fly.dev";

// GoatCounter click tracking (Book Now button only — TRD.md §8 exception).
// Site codes aren't secret; only the read-back API token stays server-side
// in admin/.env (GOATCOUNTER_API_TOKEN, see admin/pipeline/goatcounter.py).
// The Astro build has no .env loader of its own (TRD.md §2 — no runtime
// backend for the public site), so this lives here as a plain constant.
export const GOATCOUNTER_SITE = "bathers";
