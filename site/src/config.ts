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
  "pregnancy_safe",
  "step_free_entry",
  "hoist_available",
  "accessible_changerooms",
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
  // 2026-07-26 addition (SCHEMA.md §1a) — manual reviewer-set flag only, never
  // Harvester/Architect/Gatekeeper-derived: no structured temperature/depth
  // field exists in the schema to determine this automatically.
  pregnancy_safe: "Pregnancy-safe bathing",
  // 2026-07-26 additions (SCHEMA.md §1a) — ordinary Architect-settable facts.
  step_free_entry: "Step-free entry",
  hoist_available: "Hoist available",
  accessible_changerooms: "Accessible changerooms",
};

// Dress code / session-gender (2026-07-26 addition, SCHEMA.md §2). Small
// closed enums, same pattern as CATEGORIES/CATEGORY_LABELS — used by both the
// admin editor's <select> and any future site copy.
export const DRESS_CODE_KEYS = ["nude", "swimwear", "swimwear_optional", "mixed"] as const;

export const DRESS_CODE_LABELS: Record<(typeof DRESS_CODE_KEYS)[number], string> = {
  nude: "Nude",
  swimwear: "Swimwear required",
  swimwear_optional: "Swimwear optional",
  mixed: "Mixed (varies by area/session)",
};

export const SESSION_GENDER_KEYS = ["mixed", "single_sex", "varies"] as const;

export const SESSION_GENDER_LABELS: Record<(typeof SESSION_GENDER_KEYS)[number], string> = {
  mixed: "Mixed",
  single_sex: "Single-sex",
  varies: "Varies (see note)",
};

// ---------------------------------------------------------------------------
// Gate 7 (verification metadata / structured facts, 2026-07-31). Mirrors
// admin/config.py's CONFIDENCE_TIERS / VERIFIABLE_FIELDS / CAPITAL_CITIES
// exactly (SCHEMA.md "one contract" rule).
// ---------------------------------------------------------------------------

// Per-field verification confidence, weakest → strongest (SCHEMA.md §2a).
export const CONFIDENCE_TIERS = [
  "unverified",
  "published_by_venue",
  "observed_on_visit",
  "operator_confirmed",
] as const;

export const CONFIDENCE_TIER_LABELS: Record<(typeof CONFIDENCE_TIERS)[number], string> = {
  unverified: "Unverified",
  published_by_venue: "Published by the venue",
  observed_on_visit: "Observed on a visit",
  operator_confirmed: "Confirmed by the operator",
};

// The venue-sourced factual claims a `verification:` block keys on. Not every
// field — drive_time is OSRM-computed (own provenance), amenity/facility
// booleans ride the venue-level `verified` date.
export const VERIFIABLE_FIELDS = [
  "price",
  "hours",
  "temperatures",
  "dress_code",
  "session_gender",
  "silence_policy",
  "phone_policy",
  "minimum_age",
] as const;

export interface Verification {
  source: string;
  tier: (typeof CONFIDENCE_TIERS)[number];
  date: Date | string;
}

// State capital CBDs — drive-time reference origins (user sign-off 2026-07-31,
// "from nearest capital").
export const CAPITAL_CITIES: Record<(typeof STATES)[number], { name: string; latitude: number; longitude: number }> = {
  VIC: { name: "Melbourne", latitude: -37.8136, longitude: 144.9631 },
  NSW: { name: "Sydney", latitude: -33.8688, longitude: 151.2093 },
  QLD: { name: "Brisbane", latitude: -27.4698, longitude: 153.0251 },
  SA: { name: "Adelaide", latitude: -34.9285, longitude: 138.6007 },
  WA: { name: "Perth", latitude: -31.9523, longitude: 115.8613 },
  TAS: { name: "Hobart", latitude: -42.8826, longitude: 147.3257 },
  NT: { name: "Darwin", latitude: -12.4637, longitude: 130.8444 },
  ACT: { name: "Canberra", latitude: -35.2809, longitude: 149.13 },
};

export interface DriveTime {
  from: string;
  minutes: number;
  km: number;
}

// "1 hr 40 min from Melbourne" / "25 min from Hobart" — the display form of a
// drive_time object. Whole hours/minutes only; drive-time is not a precise
// figure and shouldn't read like one.
export function formatDriveTime(dt: DriveTime): string {
  const h = Math.floor(dt.minutes / 60);
  const m = dt.minutes % 60;
  const time = h > 0 ? (m > 0 ? `${h} hr ${m} min` : `${h} hr`) : `${m} min`;
  return `${time} from ${dt.from}`;
}

// Cross-cutting facility filters (2026-07-26 addition) — single-facility
// booleans that get their own /[state]/[filter]/ listing route, the same way
// POOL_TYPES does, but without belonging to the pool-type grouping itself.
// Extensible for any future flag of this shape.
export const CROSS_CUTTING_FACILITY_FILTERS = [
  { slug: "pregnancy-safe", key: "pregnancy_safe" as const, label: "Pregnancy-safe bathing" },
] as const;

export function crossCuttingFacilityFromUrlSlug(
  segment: string,
): (typeof CROSS_CUTTING_FACILITY_FILTERS)[number] | undefined {
  return CROSS_CUTTING_FACILITY_FILTERS.find((f) => f.slug === segment);
}

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

// National pool-setting routes (Gate E3, 2026-08-01). The homepage "By pool
// setting" chooser needs crawlable static destinations instead of the old
// client-only `/?pooltype=` deep links, so each concrete pool facility gets a
// national /[scope]/ page (the same slot + render as the amenity/facility
// nationals in [scope]/index.astro). The residual POOL_TYPES.other setting has
// no national page — it is "none of the above", not a browsable listing — and
// stays a client-side results filter only. Slugs are descriptive (indoor-pool,
// not indoor) so they read as national listings and don't shadow the
// /[state]/[pooltype]/ slugs. Deliberately NOT folded into
// CROSS_CUTTING_FACILITY_FILTERS: those also generate /[state]/[filter]/
// routes, which for these keys would collide with the POOL_TYPES state routes
// (/vic/indoor/ etc.).
export const POOL_NATIONAL_FILTERS = [
  { slug: "natural-spring", key: "natural_spring" as const, label: "Thermal springs" },
  { slug: "indoor-pool", key: "indoor_pool" as const, label: "Indoor pools" },
  { slug: "outdoor-pool", key: "outdoor_pool" as const, label: "Outdoor pools" },
] as const;

// Venue categories (2026-07-22 addition, day_spa retired 2026-07-26 — see
// SCHEMA.md §2). A venue must have a pool or a sauna as a central offering;
// hotel_spa covers hotel/lodge venues with a real bathing circuit, distinct
// from a standalone communal bathhouse.
export const CATEGORIES = ["thermal_springs", "bathhouse", "hotel_spa", "other"] as const;

export const CATEGORY_LABELS: Record<(typeof CATEGORIES)[number], string> = {
  thermal_springs: "Thermal springs",
  bathhouse: "Bathhouse",
  hotel_spa: "Hotel spa",
  // 2026-07-26: labelled "Other venues" (not "Other") to avoid reading as a
  // duplicate of the pool-setting POOL_TYPES.other entry now that both sit
  // in the corner menu together.
  other: "Other venues",
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
// lets one helper serve build-time content-collection entries
// (spa/[slug].astro's "Nearby" block) — candidates without resolvable
// coordinates are dropped rather than sorted arbitrarily.
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

// Temperature display (2026-07-26). `temperatures` frontmatter (SCHEMA.md §2)
// prefers a hand-drafted display string when a venue has more than one heat
// source at materially different temperatures; falls back to the structured
// min/max otherwise. Same "prefer structured, fall back to raw" posture as
// priceRange above. Returns null when nothing is set so callers can omit the
// line entirely.
interface TemperatureRange {
  sauna_min_c?: number | null;
  sauna_max_c?: number | null;
  sauna_display?: string | null;
  cold_plunge_min_c?: number | null;
  cold_plunge_max_c?: number | null;
  cold_plunge_display?: string | null;
}

function formatTempRange(min?: number | null, max?: number | null): string | null {
  if (min == null || max == null) return null;
  return min === max ? `${min}°C` : `${min}–${max}°C`;
}

export function saunaTemperatureLine(t: TemperatureRange): string | null {
  return t.sauna_display ?? formatTempRange(t.sauna_min_c, t.sauna_max_c);
}

export function coldPlungeTemperatureLine(t: TemperatureRange): string | null {
  return t.cold_plunge_display ?? formatTempRange(t.cold_plunge_min_c, t.cold_plunge_max_c);
}

export const SITE_NAME = "Where We Bathe";
export const SITE_TAGLINE = "A field guide to Australian saunas, hot pools and bathhouses.";

// Footer contact/social links (2026-07-27 addition, DESIGN.md §5d).
export const SITE_CONTACT_EMAIL = "sebastian@wherewebathe.com";
export const SITE_TIKTOK_URL = "https://www.tiktok.com/@bathersbathe";
// Bluesky: account not set up yet (2026-08-01, Gate E3) — the footer link is
// omitted rather than left as a dead anchor. To restore it later, re-add
// `export const SITE_BLUESKY_URL = "…";` here and the Bluesky block in
// Footer.astro (the `bluesky` icon in icons/paths.ts is still defined).

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
