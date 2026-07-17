import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
import { AMENITY_KEYS, AU_LATITUDE_BOUNDS, AU_LONGITUDE_BOUNDS, STATES } from "../config";

// Mirrors SCHEMA.md §2 exactly. Any change to this file must be propagated
// to the SQLite schema, the Harvester JSON contract, and the admin
// frontmatter editor in the same commit (SCHEMA.md, top).

const amenitiesSchema = z
  .object(
    Object.fromEntries(AMENITY_KEYS.map((key) => [key, z.boolean()])) as Record<
      (typeof AMENITY_KEYS)[number],
      z.ZodBoolean
    >,
  )
  .strict();

const spasCollection = defineCollection({
  // Astro globs directly into _published — content-staging/_staging and
  // _rejected live outside site/src/content entirely (TRD.md §3), so this
  // collection only ever sees approved venues, and ids come out as bare
  // kebab-case slugs (no "_published/" prefix) per SCHEMA.md's slug rule.
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/spas/_published" }),
  schema: z
    .object({
      name: z.string(),
      state: z.enum(STATES),
      suburb: z.string(),
      address: z.string(),
      latitude: z.number().min(AU_LATITUDE_BOUNDS.min).max(AU_LATITUDE_BOUNDS.max),
      longitude: z.number().min(AU_LONGITUDE_BOUNDS.min).max(AU_LONGITUDE_BOUNDS.max),
      website: z.string().url(),
      amenities: amenitiesSchema,
      status: z.enum(["unclaimed", "claimed"]).default("unclaimed"),
      summary: z.string().max(160),
      drafted: z.date(),
      source_url: z.string().url(),
      image: z.string().optional(),
      image_source: z.string().url().optional(),
      image_caption: z.string().optional(),
    })
    .strict()
    .refine((data) => !data.image || !!data.image_source, {
      message: "image_source is required when image is present",
      path: ["image_source"],
    })
    .refine((data) => !data.image || !!data.image_caption, {
      message: "image_caption is required when image is present",
      path: ["image_caption"],
    }),
});

export const collections = {
  spas: spasCollection,
};
