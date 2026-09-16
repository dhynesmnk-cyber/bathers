// Region taxonomy (Gate 6, SEO/AI-citation remediation, 2026-07-31 — data
// only; route generation is Gate 10). Scaffolded for all eight AU states per
// the 2026-07-31 decision, even where no venue exists yet, so a region
// exists ready to receive venues as Gate 9's coverage work lands them —
// most SA/WA/NT/ACT/most-of-NSW/most-of-QLD regions are empty today by
// design, not an oversight.
//
// City matching is a plain, case-insensitive exact match against the venue's
// `city` frontmatter field (SCHEMA.md §2) — the same posture as the
// hand-curated gazetteer in places.ts, not a geometry/polygon computation (no
// new geospatial dependency). A region's `cities` list only needs to cover
// places that actually have (or are expected to shortly gain) a venue; it
// isn't an exhaustive locality list.
//
// Country is part of a region's identity (2026-09-15, Gate 16), not a filter
// applied afterwards. Until then the taxonomy was Australian by construction
// and `regionForCity` refused every non-AU venue outright — the honest guard
// for a table that had no way to tell Western Australia from Washington.
import type { Country } from "../config";

export interface Region {
  slug: string;
  name: string;
  country: Country;
  subdivision: string;
  cities: string[];
  /** Prepositional phrase for page copy, where plain "in <name>" reads wrong.
   *  You are ON the Mornington Peninsula and ALONG the Great Ocean Road, but
   *  merely IN Melbourne. Omitted for the majority, which take "in". */
  locative?: string;
}

export const REGIONS: Region[] = [
  // VIC — the only state with live coverage today (20 of 25 venues).
  { slug: "melbourne", name: "Melbourne", country: "AU", subdivision: "VIC", cities: [
    "Melbourne", "North Melbourne", "South Yarra", "Collingwood", "Essendon", "Port Melbourne",
    "Southbank", "Northcote", "Braybrook", "Brunswick", "Fitzroy", "Richmond", "Prahran",
  ] },
  { slug: "mornington-peninsula", name: "Mornington Peninsula", country: "AU", subdivision: "VIC", cities: [
    "Sorrento", "Fingal", "Mornington", "Seaford", "Rye", "Rosebud", "Portsea",
  ], locative: "on the Mornington Peninsula" },
  { slug: "daylesford-hepburn", name: "Daylesford & Hepburn", country: "AU", subdivision: "VIC", cities: [
    "Daylesford", "Hepburn Springs", "Hepburn",
  ] },
  { slug: "geelong-surf-coast", name: "Geelong & Surf Coast", country: "AU", subdivision: "VIC", cities: [
    "Geelong", "Torquay", "Ocean Grove", "Barwon Heads", "Point Lonsdale", "Queenscliff",
    "Anglesea",
  ] },
  { slug: "great-ocean-road", name: "Great Ocean Road", country: "AU", subdivision: "VIC", cities: [
    "Warrnambool", "Lorne", "Apollo Bay", "Port Fairy",
  ], locative: "along the Great Ocean Road" },
  { slug: "gippsland", name: "Gippsland", country: "AU", subdivision: "VIC", cities: [
    "Metung", "Lakes Entrance", "Sale", "Bairnsdale",
  ] },
  { slug: "yarra-ranges", name: "Yarra Ranges", country: "AU", subdivision: "VIC", cities: [
    "Narbethong", "Marysville", "Healesville", "Warburton",
  ] },
  // Added 2026-09-16: Beechworth sat in no region at all, and none of the
  // existing seven is honest about where it is — the Ovens Valley is its own
  // drive, not an outer edge of the Yarra Ranges.
  { slug: "high-country", name: "Victorian High Country", country: "AU", subdivision: "VIC", cities: [
    "Beechworth", "Bright", "Myrtleford", "Mount Beauty", "Wangaratta", "Falls Creek",
  ], locative: "in the Victorian High Country" },

  // TAS — 3 venues, both Hobart and Cradle Mountain already covered.
  { slug: "hobart", name: "Hobart", country: "AU", subdivision: "TAS", cities: ["Hobart"] },
  { slug: "cradle-mountain", name: "Cradle Mountain", country: "AU", subdivision: "TAS", cities: ["Cradle Mountain"] },

  // NSW — 1 venue (Pilliga); Sydney and the Snowy Mountains are named
  // coverage-gap targets (TRD.md §8 coverage note) with no venue yet.
  { slug: "sydney", name: "Sydney", country: "AU", subdivision: "NSW", cities: [] },
  { slug: "north-west-nsw", name: "North West NSW", country: "AU", subdivision: "NSW", cities: [
    "Pilliga", "Narrabri", "Moree", "Boomi", "Burren Junction", "Walgett", "Lightning Ridge",
  ] },
  { slug: "snowy-mountains", name: "Snowy Mountains", country: "AU", subdivision: "NSW", cities: ["Yarrangobilly"] },

  // QLD — 1 venue (Eulo); Brisbane/Gold Coast and Far North QLD are named
  // coverage-gap targets with no venue yet.
  { slug: "brisbane-gold-coast", name: "Brisbane & Gold Coast", country: "AU", subdivision: "QLD", cities: [] },
  { slug: "outback-queensland", name: "Outback Queensland", country: "AU", subdivision: "QLD", cities: ["Eulo", "Cunnamulla"] },
  { slug: "far-north-queensland", name: "Far North Queensland", country: "AU", subdivision: "QLD", cities: ["Innot Hot Springs"] },

  // SA — no venues yet. Adelaide and the Far North (Dalhousie Springs) are
  // named coverage-gap targets.
  { slug: "adelaide", name: "Adelaide", country: "AU", subdivision: "SA", cities: ["Adelaide", "Torrensville", "Glenelg", "Goodwood"] },
  { slug: "far-north-sa", name: "Far North SA", country: "AU", subdivision: "SA", cities: ["Dalhousie Springs"] },

  // WA — no venues yet. Perth and the Kimberley (Zebedee Springs) are named
  // coverage-gap targets.
  { slug: "perth", name: "Perth", country: "AU", subdivision: "WA", cities: ["Perth", "Osborne Park", "Claremont", "Fremantle"] },
  { slug: "the-kimberley", name: "The Kimberley", country: "AU", subdivision: "WA", cities: ["El Questro", "Zebedee Springs"], locative: "in the Kimberley" },

  // NT — no venues yet. Darwin (capital-anchored) and Katherine/Mataranka
  // are named coverage-gap targets.
  { slug: "darwin", name: "Darwin", country: "AU", subdivision: "NT", cities: [] },
  { slug: "katherine-mataranka", name: "Katherine & Mataranka", country: "AU", subdivision: "NT", cities: ["Mataranka", "Katherine"] },

  // ACT — no venues yet. The territory is small enough for one region.
  { slug: "canberra", name: "Canberra", country: "AU", subdivision: "ACT", cities: ["Canberra", "Barton", "Braddon", "City"] },
  // --- US ---
  // FL — the first US subdivision to carry venues (Gate 16). Grouped the way a
  // Floridian would say them, not by county: the spring belt is one region
  // because it is one drive, and it is where Florida's bathing actually is.
  { slug: "south-florida", name: "South Florida", country: "US", subdivision: "FL", cities: [
    "Miami", "Miami Beach", "Coral Gables", "Fort Lauderdale", "Hollywood",
    "Boca Raton", "Delray Beach", "West Palm Beach",
  ] },
  { slug: "the-keys", name: "The Florida Keys", country: "US", subdivision: "FL", cities: [
    "Key West", "Key Largo", "Islamorada", "Marathon",
  ], locative: "in the Florida Keys" },
  { slug: "tampa-bay", name: "Tampa Bay", country: "US", subdivision: "FL", cities: [
    "Tampa", "St. Petersburg", "Clearwater", "Safety Harbor", "Dunedin",
  ] },
  { slug: "central-florida", name: "Central Florida", country: "US", subdivision: "FL", cities: [
    "Orlando", "Winter Park", "Apopka", "Kissimmee", "DeLand", "Deltona",
  ] },
  { slug: "north-central-florida", name: "North Central Florida", country: "US", subdivision: "FL", cities: [
    "Gainesville", "High Springs", "Ocala", "Williston", "Silver Springs", "Salt Springs",
  ] },
  { slug: "northeast-florida", name: "Northeast Florida", country: "US", subdivision: "FL", cities: [
    "Jacksonville", "St. Augustine", "Daytona Beach",
  ] },
  { slug: "southwest-florida", name: "Southwest Florida", country: "US", subdivision: "FL", cities: [
    "Naples", "Fort Myers", "Sarasota", "Venice", "North Port", "Bradenton",
  ] },
  { slug: "the-panhandle", name: "The Florida Panhandle", country: "US", subdivision: "FL", cities: [
    "Tallahassee", "Crawfordville", "Panama City Beach", "Destin", "Pensacola",
  ], locative: "in the Florida Panhandle" },
];

// Matches on country AND subdivision, never subdivision alone: "WA" is Western
// Australia under AU and Washington under US, and matching the code by itself
// would file a Seattle venue in the Kimberley.
export function regionForCity(
  country: string,
  stateProvince: string,
  city: string | undefined,
): Region | undefined {
  if (!city) return undefined;
  const needle = city.trim().toLowerCase();
  return REGIONS.find(
    (r) =>
      r.country === country &&
      r.subdivision === stateProvince &&
      r.cities.some((s) => s.toLowerCase() === needle),
  );
}

export function regionsForSubdivision(country: string, subdivision: string): Region[] {
  return REGIONS.filter((r) => r.country === country && r.subdivision === subdivision);
}
