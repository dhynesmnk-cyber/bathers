// Comparison-page dataset + registry (Gate 10, 2026-07-31). Generated
// entirely from the Gate 7 fact model on the published venues — superlative,
// constraint, occasion and geographic roll-up pages, each a ranked/tabular
// comparison (distinct from the /[scope]/ amenity *lists*, which don't rank
// or tabulate). A comparison only generates when it clears the >=5-venue
// threshold; thinner ones are skipped and logged, never a hard failure
// (mirrors SCHEMA.md's "omit if thin" posture).
import type { CollectionEntry } from "astro:content";
import { AMENITY_NOTATION, CATEGORY_LABELS, STATE_NAMES, priceRange } from "../config";

export const COMPARISON_MIN_VENUES = 5;

type Venue = CollectionEntry<"spas">;

export interface Column {
  header: string;
  // Cell text for a venue; null renders an em-dash-free "—" placeholder.
  cell: (v: Venue) => string | null;
  // Numeric key for the row sort (ascending). Missing sorts last.
  sortKey?: (v: Venue) => number | null;
}

export interface Comparison {
  slug: string;
  kind: "superlative" | "constraint" | "occasion";
  title: string; // <h1> / page title
  metaDescription: string;
  // One-line factual lead; audited by admin/pipeline/comparison_copy.py.
  lead: string;
  caption: string; // <caption> for the semantic table
  columns: Column[];
  // Which venues qualify, already in display order.
  select: (venues: Venue[]) => Venue[];
}

// ---- shared cell helpers ----
const locationCell = (v: Venue) => `${v.data.suburb}, ${v.data.state}`;
const categoryCell = (v: Venue) => CATEGORY_LABELS[v.data.category];
const dropIn = (v: Venue) => v.data.price?.adult_drop_in_aud ?? null;
const priceCell = (v: Venue) => {
  const n = dropIn(v);
  if (n != null) return `$${n % 1 === 0 ? n : n.toFixed(2)}`;
  return v.data.cost ? priceRange(v.data.cost) : null;
};
const amenityCell = (v: Venue) =>
  (["magnesium_pool", "infrared_sauna", "traditional_sauna", "cold_plunge", "led_therapy"] as const)
    .filter((k) => v.data.amenities[k])
    .map((k) => AMENITY_NOTATION[k].full)
    .join(", ") || null;

const PRICE_COL: Column = { header: "Adult drop-in", cell: priceCell, sortKey: dropIn };
const LOCATION_COL: Column = { header: "Location", cell: locationCell };
const CATEGORY_COL: Column = { header: "Type", cell: categoryCell };
const FEATURES_COL: Column = { header: "Features", cell: amenityCell };

const byPriceAsc = (venues: Venue[]) =>
  venues
    .filter((v) => dropIn(v) != null)
    .sort((a, b) => (dropIn(a)! - dropIn(b)!) || a.data.name.localeCompare(b.data.name));

const hasSaunaAndPlunge = (v: Venue) =>
  (v.data.amenities.traditional_sauna || v.data.amenities.infrared_sauna) && v.data.amenities.cold_plunge;

// Order all venues with a predicate true: priced ascending first, then the
// unpriced alphabetically — the shared ordering for amenity/category/pool-type
// comparisons so every table reads the same way.
const rankByPriceThenName = (pred: (v: Venue) => boolean) => (venues: Venue[]) => {
  const matching = venues.filter(pred);
  return [
    ...byPriceAsc(matching),
    ...matching.filter((v) => dropIn(v) == null).sort((a, b) => a.data.name.localeCompare(b.data.name)),
  ];
};

// ---- the registry ----
// Every entry that clears the threshold at build time becomes a page; the
// select() results also drive the >=3-comparisons-per-venue link graph.
const BASE_COMPARISONS: Comparison[] = [
  {
    slug: "cheapest",
    kind: "superlative",
    title: "Cheapest bathhouses & hot springs in Australia",
    metaDescription:
      "Australian bathhouses, saunas and hot springs ranked by adult drop-in price — the cheapest ways to bathe, compared side by side.",
    lead: "These are the published adult drop-in prices for venues in the directory that sell a single-session entry, cheapest first. Package-only and treatment-led venues, which don't price a plain drop-in, aren't ranked here.",
    caption: "Australian bathing venues ranked by adult drop-in price, cheapest first",
    columns: [PRICE_COL, CATEGORY_COL, LOCATION_COL],
    select: byPriceAsc,
  },
  {
    slug: "natural-thermal-springs",
    kind: "constraint",
    title: "Natural thermal & mineral springs in Australia",
    metaDescription:
      "Australian venues fed by a natural thermal or mineral spring rather than heated mains water, compared by location and price.",
    lead: "These venues draw on a natural spring — geothermal or mineral water reaching the surface — rather than heating mains supply. Ordered by drop-in price where one is published, then alphabetically.",
    caption: "Australian venues fed by a natural thermal or mineral spring",
    columns: [PRICE_COL, LOCATION_COL, FEATURES_COL],
    select: (venues) => {
      const springs = venues.filter((v) => v.data.facilities?.natural_spring);
      return [...byPriceAsc(springs), ...springs.filter((v) => dropIn(v) == null).sort((a, b) => a.data.name.localeCompare(b.data.name))];
    },
  },
  {
    slug: "contrast-therapy",
    kind: "occasion",
    title: "Best venues for contrast therapy (sauna + cold plunge)",
    metaDescription:
      "Australian bathhouses with both a sauna and a cold plunge for contrast bathing — the hot-cold circuit, compared by location and price.",
    lead: "Contrast bathing alternates heat and cold. These venues pair a sauna (traditional or infrared) with a cold plunge, so the full circuit is on site. Ordered by drop-in price where published.",
    caption: "Australian venues offering both a sauna and a cold plunge for contrast bathing",
    columns: [PRICE_COL, LOCATION_COL, FEATURES_COL],
    select: (venues) => {
      const ct = venues.filter(hasSaunaAndPlunge);
      return [...byPriceAsc(ct), ...ct.filter((v) => dropIn(v) == null).sort((a, b) => a.data.name.localeCompare(b.data.name))];
    },
  },
];

// Generated amenity/category/pool-type comparisons (ranked by price). These
// broaden the link graph so most venues appear in >=3 comparisons; each is
// still >=5-gated by resolveComparisons, so thin ones simply don't generate.
const AMENITY_COMPARISONS: Comparison[] = (
  ["magnesium_pool", "infrared_sauna", "traditional_sauna", "cold_plunge", "led_therapy"] as const
).map((key) => {
  const label = AMENITY_NOTATION[key].full;
  return {
    slug: `${key.replace(/_/g, "-")}-compared`,
    kind: "superlative" as const,
    title: `${label} venues in Australia, compared`,
    metaDescription: `Australian bathhouses and hot springs with ${label.toLowerCase()}, ranked by adult drop-in price and compared by location.`,
    lead: `Every venue in the directory offering ${label.toLowerCase()}, ranked by adult drop-in price where one is published, then alphabetically.`,
    caption: `Australian venues offering ${label.toLowerCase()}, ranked by price`,
    columns: [PRICE_COL, LOCATION_COL, CATEGORY_COL],
    select: rankByPriceThenName((v) => v.data.amenities[key]),
  };
});

const CATEGORY_COMPARISONS: Comparison[] = (["thermal_springs", "bathhouse", "hotel_spa"] as const).map((cat) => ({
  slug: `${cat.replace(/_/g, "-")}-compared`,
  kind: "constraint" as const,
  title: `${CATEGORY_LABELS[cat]} venues in Australia, compared`,
  metaDescription: `Australian ${CATEGORY_LABELS[cat].toLowerCase()} venues compared by adult drop-in price, location and features.`,
  lead: `Every ${CATEGORY_LABELS[cat].toLowerCase()} venue in the directory, ranked by adult drop-in price where published, then alphabetically.`,
  caption: `Australian ${CATEGORY_LABELS[cat].toLowerCase()} venues, ranked by price`,
  columns: [PRICE_COL, LOCATION_COL, FEATURES_COL],
  select: rankByPriceThenName((v) => v.data.category === cat),
}));

const POOL_COMPARISONS: Comparison[] = (
  [
    ["indoor-pools", "an indoor pool", (v: Venue) => !!v.data.facilities?.indoor_pool],
    ["outdoor-pools", "an outdoor pool", (v: Venue) => !!v.data.facilities?.outdoor_pool],
  ] as const
).map(([slug, phrase, pred]) => ({
  slug,
  kind: "constraint" as const,
  title: `Australian bathing venues with ${phrase}, compared`,
  metaDescription: `Australian bathhouses and hot springs with ${phrase}, ranked by adult drop-in price and compared by location.`,
  lead: `Every venue in the directory with ${phrase}, ranked by adult drop-in price where published, then alphabetically.`,
  caption: `Australian venues with ${phrase}, ranked by price`,
  columns: [PRICE_COL, LOCATION_COL, CATEGORY_COL],
  select: rankByPriceThenName(pred),
}));

export const COMPARISONS: Comparison[] = [
  ...BASE_COMPARISONS,
  ...AMENITY_COMPARISONS,
  ...CATEGORY_COMPARISONS,
  ...POOL_COMPARISONS,
];

export interface EligibleComparison extends Comparison {
  venues: Venue[];
}

// Split the registry into pages that clear the threshold and ones skipped for
// thin data (the caller logs the latter, per the done-condition).
export function resolveComparisons(venues: Venue[]): {
  eligible: EligibleComparison[];
  skipped: { slug: string; count: number }[];
} {
  const eligible: EligibleComparison[] = [];
  const skipped: { slug: string; count: number }[] = [];
  for (const c of COMPARISONS) {
    const selected = c.select(venues);
    if (selected.length >= COMPARISON_MIN_VENUES) {
      eligible.push({ ...c, venues: selected });
    } else {
      skipped.push({ slug: c.slug, count: selected.length });
    }
  }
  return { eligible, skipped };
}

// Superlative/constraint/occasion pages are grouped under the /compare/ hub;
// this is the canonical path builder so the hub, pages, breadcrumbs and the
// venue-side "featured in" links all agree.
export const comparePath = (slug: string) => `/compare/${slug}/`;
export function stateHeading(v: Venue): string {
  return STATE_NAMES[v.data.state];
}
