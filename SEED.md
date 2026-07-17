# SEED.md — Pipeline Test Venues

Gate 4's done-condition runs against these URLs. All four primary URLs were verified live in July 2026. They are deliberately varied: a large hot-springs destination, a design-led springs complex, an inner-city warehouse bathhouse, and a multi-site urban chain — different site structures, different amenity vocabularies, a good spread for testing extraction.

| # | Venue | URL | State | Why it's a good test |
|---|---|---|---|---|
| 1 | Sense of Self | https://www.sos-senseofself.com/ | VIC | Warehouse bathhouse; magnesium bath, Finnish sauna, cold plunge, hammam. Rich specific facts (temperatures, session lengths). Also the SCHEMA.md sample — pipeline output can be compared directly against the hand-written fixture. |
| 2 | Peninsula Hot Springs | https://www.peninsulahotsprings.com/bathe/bath-house | VIC | Large multi-experience site; tests fact extraction from a sprawling page and the Harvester's discipline about what *isn't* evidenced on this specific page. |
| 3 | Alba Thermal Springs & Spa | https://albathermalsprings.com.au/ | VIC | Heavily marketed copy ("sanctuary", "rejuvenation" throughout) — the ideal stress test for the Architect/Gatekeeper banned list. Sauna and steam room stated; magnesium is not — amenity extraction should reflect that. |
| 4 | Soak Bathhouse | https://soakbathhouse.com.au/ | QLD | Multi-location chain (Gold Coast, Brisbane, more) — tests how the pipeline handles one URL describing several venues. Expected behaviour: Harvester notes the ambiguity in `confidence_notes`; reviewer decides. Also the only non-VIC seed, exercising state handling. |
| 5 | Hepburn Bathhouse & Spa | (find current official URL at harvest time — historic mineral-springs bathhouse, Hepburn Springs VIC) | VIC | Optional fifth. Verify the URL before harvesting rather than trusting this file. |

## Expectations per run

- Seeds 1–3 should each produce a schema-valid staged draft with ≥6 items across the `facts` arrays and zero banned words in the final MDX.
- Seed 3's draft must not claim a magnesium pool.
- Seed 4 is allowed to produce a draft needing reviewer intervention — that's the point. What it must not do is silently blend multiple locations into one confident venue record.
- Coordinates will be null or geocoded-approximate on all seeds; correcting them in the review pane's map thumbnail is part of the Gate 4 walkthrough, not a failure.

Do not publish any of these drafts to the live site during testing without reviewing them as a human first — they are real businesses.
