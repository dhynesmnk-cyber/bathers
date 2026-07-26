// Hand-authored glossary copy (2026-07-22 addition) — one plain-language
// paragraph per amenity/facility icon (see site/src/config.ts and
// site/src/icons/paths.ts for the underlying key/icon set). Not part of the
// AI pipeline: this is static site chrome, not a venue record, so it carries
// no Harvester/Architect/Gatekeeper involvement.
import type { AMENITY_KEYS, FACILITY_KEYS } from "../config";

type GlossaryKey = (typeof AMENITY_KEYS)[number] | (typeof FACILITY_KEYS)[number];

export const GLOSSARY: Record<GlossaryKey, string> = {
  magnesium_pool:
    "A pool dosed with magnesium salts, rather than plain heated water. Magnesium is absorbed through the skin and is generally associated with easing muscle tension, though the size of that effect versus an ordinary hot bath is debated. A stated concentration or temperature on the venue's own page is a better guide than the label alone.",
  infrared_sauna:
    "A sauna heated by infrared panels rather than a wood or electric stove. The panels warm the body directly, so the room itself runs cooler than a traditional sauna even though you still sweat heavily. Sessions tend to run longer than a traditional sauna's, since the air isn't as hot to sit in.",
  traditional_sauna:
    "A sauna heated by a stove — wood or electric — that heats the air, which then heats you. Ambient temperature is usually higher (often 70–100 degrees) and sessions shorter than an infrared sauna's. Water poured over hot rocks to lift humidity is a common variant.",
  cold_plunge:
    "A pool or tub held cold — typically somewhere between 5 and 15 degrees — for brief immersion straight after heat. The contrast is the point: alternating hot and cold underpins most bathhouse circuits, not the cold plunge in isolation.",
  led_therapy:
    "Light exposure at specific wavelengths, usually red or near-infrared, delivered via panels or masks and marketed for skin and recovery benefits. Evidence for spa-grade devices is mixed and dose-dependent — treat a venue's specific claims as its own, not independently verified here.",
  parking:
    "On-site parking is available. Whether it's free, paid, or limited isn't always stated — check the venue's own page for specifics before you drive.",
  towels_provided:
    "Towels are supplied as part of entry, so you don't need to bring your own. This doesn't necessarily extend to robes or other linen — check the venue's own page if that matters.",
  changerooms:
    "Dedicated changerooms are on-site. Whether they're shared, gendered, or private is venue-specific and not covered by this flag alone.",
  bookings_required:
    "You need to book ahead rather than arrive and pay at the door. Sessions at these venues are often sold as timed sittings, so the booking usually also sets how long you're there for.",
  wheelchair_access:
    "The venue states step-free or wheelchair access to at least part of the site. This doesn't guarantee every area is equally accessible — call ahead if a specific pool, sauna, or changeroom matters for your visit.",
  outdoor_pool:
    "The venue has a pool, spa, or bathing area that's open to the air — no roof between you and the sky. Coverage and shade vary by venue; check the venue's own page if weather protection matters for your visit.",
  indoor_pool:
    "The venue has a pool or bathing area under cover, inside a building or an enclosed structure. This flag says nothing about ventilation, natural light, or how the space feels — just that it's roofed.",
  natural_spring:
    "The bathing water is drawn from a natural spring or geothermal source, rather than being municipal water heated and mineral-dosed on site. Temperature, mineral composition, and flow vary by source and aren't independently verified here — check the venue's own page for specifics.",
  // 2026-07-26 addition — manual reviewer-set flag only (SCHEMA.md §1a); no
  // structured temperature/depth field exists to derive this automatically,
  // so it's never Harvester/Architect/Gatekeeper-inferred.
  pregnancy_safe:
    "Marked here only when a venue's own materials explicitly describe pregnancy-safe conditions — for example, a specifically designated pool kept below a stated temperature, or an area excluded from the venue's higher-heat circuit. This is not medical guidance; confirm current conditions with the venue and with your own healthcare provider before bathing while pregnant.",
  // 2026-07-26 additions.
  step_free_entry:
    "The venue states step-free entry to at least part of the site — no stairs to get in. This doesn't guarantee every pool, sauna, or changeroom is step-free; call ahead if a specific area matters for your visit.",
  hoist_available:
    "A hoist is available on-site to help with getting into or out of a pool or bath. Coverage of specific pools varies by venue — check ahead if a particular facility matters for your visit.",
  accessible_changerooms:
    "At least one changeroom is set up for accessible use (wider doorways, grab rails, or similar). This is distinct from wheelchair access to the bathing areas themselves — check the venue's own page if both matter for your visit.",
};
