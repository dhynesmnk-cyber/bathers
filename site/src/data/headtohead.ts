// Head-to-head pairs (Gate 10, 2026-07-31). These four pairs are the
// user-approved list (contract: head-to-head generates ONLY from approved
// pairs, never a raw heuristic sweep). Each pairs two genuinely comparable
// venues in the same region and category. To add a pair, it must be approved
// first, then added here.
import type { CollectionEntry } from "astro:content";
import {
  AMENITY_KEYS,
  AMENITY_NOTATION,
  CATEGORY_LABELS,
  coldPlungeTemperatureLine,
  priceRange,
  saunaTemperatureLine,
  STATE_NAMES,
} from "../config";

type Venue = CollectionEntry<"spas">;

export interface H2HPair {
  slug: string;
  a: string; // venue slug
  b: string; // venue slug
}

export const HEAD_TO_HEAD: H2HPair[] = [
  { slug: "alba-vs-peninsula-hot-springs", a: "alba-thermal-springs-spa", b: "mornington-peninsula-hot-springs" },
  { slug: "chuan-vs-crown-melbourne", a: "chuan-spa", b: "crown-spa-melbourne" },
  { slug: "sense-of-self-vs-soma", a: "sense-of-self", b: "s-ma-bathhouse" },
  { slug: "mineral-springs-hotel-vs-the-mineral-spa", a: "mineral-springs-hotel", b: "the-mineral-spa" },
];

const fmtAud = (n: number) => `$${n % 1 === 0 ? n : n.toFixed(2)}`;

export interface H2HRow {
  label: string;
  value: (v: Venue) => string | null;
}

// Attribute rows, transposed (rows = facts, columns = the two venues). Every
// value comes straight from the Gate 7 fact model — no editorialising, so
// there's nothing for the copy audit to catch here.
export const H2H_ROWS: H2HRow[] = [
  {
    label: "Adult drop-in",
    value: (v) => {
      const n = v.data.price?.adult_drop_in_aud;
      if (n != null) return fmtAud(n);
      return v.data.cost ? priceRange(v.data.cost) : null;
    },
  },
  { label: "Location", value: (v) => `${v.data.suburb}, ${STATE_NAMES[v.data.state]}` },
  { label: "Type", value: (v) => CATEGORY_LABELS[v.data.category] },
  {
    label: "Features",
    value: (v) =>
      AMENITY_KEYS.filter((k) => v.data.amenities[k]).map((k) => AMENITY_NOTATION[k].full).join(", ") || null,
  },
  {
    label: "Sauna",
    value: (v) =>
      saunaTemperatureLine(v.data.temperatures ?? {}) ??
      (v.data.amenities.traditional_sauna || v.data.amenities.infrared_sauna ? "Yes" : null),
  },
  {
    label: "Cold plunge",
    value: (v) => coldPlungeTemperatureLine(v.data.temperatures ?? {}) ?? (v.data.amenities.cold_plunge ? "Yes" : null),
  },
  { label: "Natural spring", value: (v) => (v.data.facilities?.natural_spring ? "Yes" : null) },
  { label: "Hours", value: (v) => v.data.hours ?? null },
];

export function h2hTitle(a: Venue, b: Venue): string {
  return `${a.data.name} vs ${b.data.name}`;
}

export function h2hLead(a: Venue, b: Venue): string {
  const where =
    a.data.state === b.data.state && a.data.suburb === b.data.suburb
      ? `both in ${a.data.suburb}, ${STATE_NAMES[a.data.state]}`
      : `both in ${STATE_NAMES[a.data.state]}`;
  const kind = a.data.category === b.data.category ? CATEGORY_LABELS[a.data.category].toLowerCase() : "bathing";
  return `${a.data.name} and ${b.data.name} are ${where} — two ${kind} venues, side by side. Every figure below is drawn from each venue's own published materials.`;
}
