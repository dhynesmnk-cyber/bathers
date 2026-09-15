// Hand-rolled sitemap endpoint (2026-07-24 SEO/GEO pass) — CLAUDE.md rule 2
// says ask before adding any dependency; this avoids adding @astrojs/sitemap
// by reusing the same collection/loop patterns the pages themselves use for
// getStaticPaths, rather than a new package. Static build, so this runs once
// at build time like every other page.
import type { APIRoute } from "astro";
import { getCollection } from "astro:content";
import {
  AMENITY_KEYS,
  CATEGORIES,
  CROSS_CUTTING_FACILITY_FILTERS,
  FACILITY_KEYS,
  POOL_NATIONAL_FILTERS,
  POOL_TYPES,
  SUBDIVISION_NAMES,
  WORLD_REGIONS,
  amenityUrlSlug,
  categoryUrlSlug,
  placePath,
} from "../config";

interface UrlEntry {
  path: string;
  lastmod?: string;
}

export const GET: APIRoute = async ({ site }) => {
  const venues = await getCollection("spas");
  const posts = await getCollection("blog");

  const entries: UrlEntry[] = [
    { path: "/" },
    { path: "/blog/" },
    { path: "/glossary/" },
  ];

  for (const venue of venues) {
    entries.push({ path: `/spa/${venue.id}/`, lastmod: venue.data.verified.toISOString().slice(0, 10) });
  }

  for (const post of posts) {
    entries.push({ path: `/blog/${post.id}/`, lastmod: post.data.dateline.toISOString().slice(0, 10) });
  }

  // Geography lives under /places/ since 2026-09-08 (TRD.md §1). Emitted from
  // the same WORLD_REGIONS/SUBDIVISION_NAMES tables the routes build from, so
  // the sitemap cannot drift from what was actually generated.
  entries.push({ path: "/places/" });
  for (const region of WORLD_REGIONS) {
    const regionCountries = region.countries.filter((c) => venues.some((v) => v.data.country === c));
    if (regionCountries.length === 0) continue;
    entries.push({ path: `/places/${region.slug}/` });

    for (const country of regionCountries) {
      entries.push({ path: placePath(country) });
      for (const code of Object.keys(SUBDIVISION_NAMES[country])) {
        const inState = venues.filter(
          (v) => v.data.country === country && v.data.state_province === code,
        );
        if (inState.length === 0) continue;
        entries.push({ path: placePath(country, code) });

        for (const amenityKey of AMENITY_KEYS) {
          if (inState.some((v) => v.data.amenities[amenityKey])) {
            entries.push({ path: placePath(country, code, amenityUrlSlug(amenityKey)) });
          }
        }
        for (const poolType of POOL_TYPES) {
          if (inState.some((v) => poolType.match(v.data.facilities))) {
            entries.push({ path: placePath(country, code, poolType.slug) });
          }
        }
        for (const f of CROSS_CUTTING_FACILITY_FILTERS) {
          if (inState.some((v) => v.data.facilities?.[f.key])) {
            entries.push({ path: placePath(country, code, f.slug) });
          }
        }
      }
    }
  }

  for (const category of CATEGORIES) {
    if (venues.some((v) => v.data.category === category)) {
      entries.push({ path: `/category/${categoryUrlSlug(category)}/` });
    }
  }

  // National amenity/facility routes (2026-07-31, Gate 6) — same /[scope]/
  // slot as the state pages above; see site/src/pages/[scope]/index.astro.
  for (const amenityKey of AMENITY_KEYS) {
    if (venues.some((v) => v.data.amenities[amenityKey])) {
      entries.push({ path: `/${amenityUrlSlug(amenityKey)}/` });
    }
  }
  for (const facilityFilter of CROSS_CUTTING_FACILITY_FILTERS) {
    if (venues.some((v) => v.data.facilities?.[facilityFilter.key])) {
      entries.push({ path: `/${facilityFilter.slug}/` });
    }
  }
  // National pool-setting routes (Gate E3) — same /[scope]/ slot; see
  // POOL_NATIONAL_FILTERS in config.ts and [scope]/index.astro.
  for (const poolFilter of POOL_NATIONAL_FILTERS) {
    if (venues.some((v) => v.data.facilities?.[poolFilter.key])) {
      entries.push({ path: `/${poolFilter.slug}/` });
    }
  }

  for (const key of [...AMENITY_KEYS, ...FACILITY_KEYS]) {
    entries.push({ path: `/glossary/${key.replace(/_/g, "-")}/` });
  }

  // Comparison + region roll-up pages (2026-07-31, Gate 10).
  const { resolveComparisons, comparePath } = await import("../data/comparisons");
  const { REGIONS, regionForCity } = await import("../data/regions");
  entries.push({ path: "/compare/" }, { path: "/methodology/" });
  for (const c of resolveComparisons(venues).eligible) {
    entries.push({ path: comparePath(c.slug) });
  }
  const { HEAD_TO_HEAD } = await import("../data/headtohead");
  const venueIds = new Set(venues.map((v) => v.id));
  for (const p of HEAD_TO_HEAD) {
    if (venueIds.has(p.a) && venueIds.has(p.b)) entries.push({ path: comparePath(p.slug) });
  }
  const regionKey = (r: { country: string; subdivision: string; slug: string }) =>
    `${r.country}:${r.subdivision}:${r.slug}`;
  const regionCounts = new Map<string, number>();
  for (const v of venues) {
    const r = regionForCity(v.data.country, v.data.state_province, v.data.city);
    if (r) regionCounts.set(regionKey(r), (regionCounts.get(regionKey(r)) ?? 0) + 1);
  }
  // Area pages sit under their subdivision now, not at /region/<slug>/.
  for (const r of REGIONS) {
    if ((regionCounts.get(regionKey(r)) ?? 0) >= 2) {
      entries.push({ path: placePath(r.country, r.subdivision, r.slug) });
    }
  }

  const urls = entries
    .map((entry) => {
      const loc = new URL(entry.path, site).toString();
      const lastmod = entry.lastmod ? `<lastmod>${entry.lastmod}</lastmod>` : "";
      return `<url><loc>${loc}</loc>${lastmod}</url>`;
    })
    .join("");

  const xml = `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`;

  return new Response(xml, { headers: { "Content-Type": "application/xml" } });
};
