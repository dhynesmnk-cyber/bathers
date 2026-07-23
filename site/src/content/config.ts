import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
import { AMENITY_KEYS, AU_LATITUDE_BOUNDS, AU_LONGITUDE_BOUNDS, CATEGORIES, FACILITY_KEYS, STATES } from "../config";

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

// Optional — added 2026-07-21, absent on venues published before then.
const facilitiesSchema = z
  .object(
    Object.fromEntries(FACILITY_KEYS.map((key) => [key, z.boolean().default(false)])) as Record<
      (typeof FACILITY_KEYS)[number],
      z.ZodDefault<z.ZodBoolean>
    >,
  )
  .strict()
  .optional();

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
      category: z.enum(CATEGORIES),
      suburb: z.string(),
      address: z.string(),
      latitude: z.number().min(AU_LATITUDE_BOUNDS.min).max(AU_LATITUDE_BOUNDS.max).nullable().optional(),
      longitude: z.number().min(AU_LONGITUDE_BOUNDS.min).max(AU_LONGITUDE_BOUNDS.max).nullable().optional(),
      website: z.string().url(),
      amenities: amenitiesSchema,
      facilities: facilitiesSchema,
      hours: z.string().nullable().optional(),
      cost: z.string().nullable().optional(),
      access: z.string().nullable().optional(),
      status: z.enum(["unclaimed", "claimed"]).default("unclaimed"),
      summary: z.string().max(160),
      drafted: z.date(),
      verified: z.date(),
      source_url: z.string().url(),
      image: z.string().nullable().optional(),
      image_source: z.string().url().nullable().optional(),
      image_caption: z.string().nullable().optional(),
      faq: z
        .array(z.object({ question: z.string(), answer: z.string() }))
        .max(8)
        .optional(),
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

// Blog (2026-07-21 addition, SCHEMA.md §7). Mirrors the venue staging/
// published split: content-staging/_blog_staging holds drafts outside this
// tree entirely; this collection only ever sees published posts.
const VIDEO_HOST_RE = /^https:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/|player\.vimeo\.com\/video\/|vimeo\.com\/)/;

const blogCollection = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/blog/_published" }),
  schema: z.object({
    title: z.string(),
    dateline: z.date(),
    summary: z.string().max(160),
    cover_image: z.string().optional(),
    video_url: z
      .string()
      .url()
      .refine((url) => VIDEO_HOST_RE.test(url), {
        message: "video_url must be a YouTube or Vimeo URL",
      })
      .optional(),
  }),
});

export const collections = {
  spas: spasCollection,
  blog: blogCollection,
};
