// Region taxonomy (Gate 6, SEO/AI-citation remediation, 2026-07-31 — data
// only; route generation is Gate 10). Scaffolded for all eight states per
// the 2026-07-31 decision, even where no venue exists yet, so a region
// exists ready to receive venues as Gate 9's coverage work lands them —
// most SA/WA/NT/ACT/most-of-NSW/most-of-QLD regions are empty today by
// design, not an oversight.
//
// Suburb matching is a plain, case-insensitive exact match against the
// venue's `suburb` frontmatter field (SCHEMA.md §2) — the same posture as
// the hand-curated gazetteer in au-places.ts, not a geometry/polygon
// computation (no new geospatial dependency). A region's `suburbs` list only
// needs to cover suburbs that actually have (or are expected to shortly
// gain) a venue; it isn't a exhaustive locality list.
import { STATES } from "../config";

export interface Region {
  slug: string;
  name: string;
  state: (typeof STATES)[number];
  suburbs: string[];
}

export const REGIONS: Region[] = [
  // VIC — the only state with live coverage today (20 of 25 venues).
  { slug: "melbourne", name: "Melbourne", state: "VIC", suburbs: [
    "Melbourne", "North Melbourne", "South Yarra", "Collingwood", "Essendon", "Port Melbourne",
  ] },
  { slug: "mornington-peninsula", name: "Mornington Peninsula", state: "VIC", suburbs: [
    "Sorrento", "Fingal", "Mornington", "Seaford", "Rye", "Rosebud", "Portsea",
  ] },
  { slug: "daylesford-hepburn", name: "Daylesford & Hepburn", state: "VIC", suburbs: [
    "Daylesford", "Hepburn Springs", "Hepburn",
  ] },
  { slug: "geelong-surf-coast", name: "Geelong & Surf Coast", state: "VIC", suburbs: [
    "Geelong", "Torquay", "Ocean Grove", "Barwon Heads",
  ] },
  { slug: "great-ocean-road", name: "Great Ocean Road", state: "VIC", suburbs: [
    "Warrnambool", "Lorne", "Apollo Bay", "Port Fairy",
  ] },
  { slug: "gippsland", name: "Gippsland", state: "VIC", suburbs: [
    "Metung", "Lakes Entrance", "Sale", "Bairnsdale",
  ] },
  { slug: "yarra-ranges", name: "Yarra Ranges", state: "VIC", suburbs: [
    "Narbethong", "Marysville", "Healesville", "Warburton",
  ] },

  // TAS — 3 venues, both Hobart and Cradle Mountain already covered.
  { slug: "hobart", name: "Hobart", state: "TAS", suburbs: ["Hobart"] },
  { slug: "cradle-mountain", name: "Cradle Mountain", state: "TAS", suburbs: ["Cradle Mountain"] },

  // NSW — 1 venue (Pilliga); Sydney and the Snowy Mountains are named
  // coverage-gap targets (TRD.md §8 coverage note) with no venue yet.
  { slug: "sydney", name: "Sydney", state: "NSW", suburbs: [] },
  { slug: "north-west-nsw", name: "North West NSW", state: "NSW", suburbs: ["Pilliga", "Narrabri", "Moree"] },
  { slug: "snowy-mountains", name: "Snowy Mountains", state: "NSW", suburbs: ["Yarrangobilly"] },

  // QLD — 1 venue (Eulo); Brisbane/Gold Coast and Far North QLD are named
  // coverage-gap targets with no venue yet.
  { slug: "brisbane-gold-coast", name: "Brisbane & Gold Coast", state: "QLD", suburbs: [] },
  { slug: "outback-queensland", name: "Outback Queensland", state: "QLD", suburbs: ["Eulo", "Cunnamulla"] },
  { slug: "far-north-queensland", name: "Far North Queensland", state: "QLD", suburbs: ["Innot Hot Springs"] },

  // SA — no venues yet. Adelaide and the Far North (Dalhousie Springs) are
  // named coverage-gap targets.
  { slug: "adelaide", name: "Adelaide", state: "SA", suburbs: [] },
  { slug: "far-north-sa", name: "Far North SA", state: "SA", suburbs: ["Dalhousie Springs"] },

  // WA — no venues yet. Perth and the Kimberley (Zebedee Springs) are named
  // coverage-gap targets.
  { slug: "perth", name: "Perth", state: "WA", suburbs: [] },
  { slug: "the-kimberley", name: "The Kimberley", state: "WA", suburbs: ["El Questro", "Zebedee Springs"] },

  // NT — no venues yet. Darwin (capital-anchored) and Katherine/Mataranka
  // are named coverage-gap targets.
  { slug: "darwin", name: "Darwin", state: "NT", suburbs: [] },
  { slug: "katherine-mataranka", name: "Katherine & Mataranka", state: "NT", suburbs: ["Mataranka", "Katherine"] },

  // ACT — no venues yet. The territory is small enough for one region.
  { slug: "canberra", name: "Canberra", state: "ACT", suburbs: [] },
];

export function regionForSuburb(state: (typeof STATES)[number], suburb: string): Region | undefined {
  const needle = suburb.trim().toLowerCase();
  return REGIONS.find((r) => r.state === state && r.suburbs.some((s) => s.toLowerCase() === needle));
}

export function regionsForState(state: (typeof STATES)[number]): Region[] {
  return REGIONS.filter((r) => r.state === state);
}
