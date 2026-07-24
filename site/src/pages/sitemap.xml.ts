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
  FACILITY_KEYS,
  POOL_TYPES,
  STATES,
  amenityUrlSlug,
  categoryUrlSlug,
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

  for (const state of STATES) {
    const stateVenues = venues.filter((v) => v.data.state === state);
    if (stateVenues.length === 0) continue;
    entries.push({ path: `/${state.toLowerCase()}/` });

    for (const amenityKey of AMENITY_KEYS) {
      if (stateVenues.some((v) => v.data.amenities[amenityKey])) {
        entries.push({ path: `/${state.toLowerCase()}/${amenityUrlSlug(amenityKey)}/` });
      }
    }
    for (const poolType of POOL_TYPES) {
      if (stateVenues.some((v) => poolType.match(v.data.facilities))) {
        entries.push({ path: `/${state.toLowerCase()}/${poolType.slug}/` });
      }
    }
  }

  for (const category of CATEGORIES) {
    if (venues.some((v) => v.data.category === category)) {
      entries.push({ path: `/category/${categoryUrlSlug(category)}/` });
    }
  }

  for (const key of [...AMENITY_KEYS, ...FACILITY_KEYS]) {
    entries.push({ path: `/glossary/${key.replace(/_/g, "-")}/` });
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
