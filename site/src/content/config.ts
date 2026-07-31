import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";
import {
  AMENITY_KEYS,
  AU_LATITUDE_BOUNDS,
  AU_LONGITUDE_BOUNDS,
  CATEGORIES,
  CONFIDENCE_TIERS,
  DRESS_CODE_KEYS,
  FACILITY_KEYS,
  SESSION_GENDER_KEYS,
  STATES,
  VERIFIABLE_FIELDS,
} from "../config";

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

// Optional — added 2026-07-26 (SCHEMA.md §2). Sanity bounds only, not a
// strict physical limit: catches data-entry errors without being fussy about
// the odd hot-spring outlier.
const temperaturesSchema = z
  .object({
    sauna_min_c: z.number().min(0).max(150).nullable().optional(),
    sauna_max_c: z.number().min(0).max(150).nullable().optional(),
    sauna_display: z.string().nullable().optional(),
    cold_plunge_min_c: z.number().min(-5).max(40).nullable().optional(),
    cold_plunge_max_c: z.number().min(-5).max(40).nullable().optional(),
    cold_plunge_display: z.string().nullable().optional(),
  })
  .strict()
  .optional();

// Structured pricing (Gate 7, SCHEMA.md §2a) — the numeric adult drop-in /
// standard session alongside the freeform `cost` string, for comparison
// pages. Both optional/nullable; absent on package- or treatment-led venues
// with no general-admission bathing price. Cross-validated against the cost
// string by /validate, not zod (zod can't see `cost` from here cheaply).
const priceSchema = z
  .object({
    adult_drop_in_aud: z.number().nonnegative().nullable().optional(),
    standard_session_aud: z.number().nonnegative().nullable().optional(),
  })
  .strict()
  .optional();

// Drive-time from the nearest capital (Gate 7, OSRM — TRD.md §2). Present only
// where the venue has coordinates; cleanly absent otherwise.
const driveTimeSchema = z
  .object({
    from: z.string(),
    minutes: z.number().int().nonnegative(),
    km: z.number().nonnegative(),
  })
  .strict()
  .optional();

// Per-field verification (Gate 7, SCHEMA.md §2a) — a {source, tier, date}
// record per populated verifiable field. Keys are a subset of
// VERIFIABLE_FIELDS; each entry optional so a venue only carries records for
// the facts it actually states.
const verificationEntrySchema = z.object({
  source: z.string(),
  tier: z.enum(CONFIDENCE_TIERS),
  // Coerced, not strict z.date(): the backfill writes an unquoted YAML date
  // (parsed as a Date) while the pipeline's yaml.safe_dump writes a quoted
  // "YYYY-MM-DD" string. Both are valid provenance dates — coerce to a Date.
  date: z.coerce.date(),
});

const verificationSchema = z
  .object(
    Object.fromEntries(VERIFIABLE_FIELDS.map((key) => [key, verificationEntrySchema.optional()])) as Record<
      (typeof VERIFIABLE_FIELDS)[number],
      z.ZodOptional<typeof verificationEntrySchema>
    >,
  )
  .strict()
  .optional();

// Computed change-log (Gate 7, SCHEMA.md §2a) — one entry per verifiable field
// whose value changed on a re-harvest/outreach update. Empty/absent at first
// draft. `from`/`to` are untyped (any prior value shape); not rendered.
const changeLogSchema = z
  .array(
    z.object({
      field: z.string(),
      from: z.any(),
      to: z.any(),
      date: z.coerce.date(),
      trigger: z.string(),
    }),
  )
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
      temperatures: temperaturesSchema,
      dress_code: z.enum(DRESS_CODE_KEYS).nullable().optional(),
      session_gender: z.enum(SESSION_GENDER_KEYS).nullable().optional(),
      session_gender_note: z.string().nullable().optional(),
      silence_policy: z.string().nullable().optional(),
      phone_policy: z.string().nullable().optional(),
      minimum_age: z.number().int().positive().nullable().optional(),
      price: priceSchema,
      drive_time: driveTimeSchema,
      verification: verificationSchema,
      change_log: changeLogSchema,
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
