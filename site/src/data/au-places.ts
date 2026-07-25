// Hand-curated gazetteer for the near-me distance sort (2026-07-25, TRD.md §8
// exception). Deliberately NOT a bulk postcode/suburb database — this site
// hand-curates everything it ships, and a multi-thousand-row generic dataset
// would be both overkill for the directory's current footprint and would
// carry a licensing/attribution obligation a hand-typed list of well-known
// place names and centroid coordinates does not. Coordinates are approximate
// town/suburb centroids (2-4 decimal places), which is the right precision
// for "which published venues are roughly nearby" — not survey-grade.
//
// Coverage: all 8 state/territory capitals, every suburb a published venue
// already sits in (so a search from a venue's own town always resolves), and
// a spread of well-known regional centres across all states/territories so
// near-me keeps working as the directory grows beyond its current VIC/TAS
// footprint. Extend by adding a row — no schema migration, no new dependency.
//
// Imported directly by client JS (not embedded as inline build-time JSON,
// unlike the search index) — this is static author-time data, so a normal
// bundled/cached module is cheaper than re-downloading an inline blob on
// every page load.
import type { STATES } from "../config";

export interface AuPlace {
  name: string;
  state: (typeof STATES)[number];
  postcode: string;
  latitude: number;
  longitude: number;
}

export const AU_PLACES: AuPlace[] = [
  // --- Capitals ---
  { name: "Sydney", state: "NSW", postcode: "2000", latitude: -33.8688, longitude: 151.2093 },
  { name: "Melbourne", state: "VIC", postcode: "3000", latitude: -37.8136, longitude: 144.9631 },
  { name: "Brisbane", state: "QLD", postcode: "4000", latitude: -27.4698, longitude: 153.0251 },
  { name: "Perth", state: "WA", postcode: "6000", latitude: -31.9505, longitude: 115.8605 },
  { name: "Adelaide", state: "SA", postcode: "5000", latitude: -34.9285, longitude: 138.6007 },
  { name: "Hobart", state: "TAS", postcode: "7000", latitude: -42.8821, longitude: 147.3272 },
  { name: "Darwin", state: "NT", postcode: "0800", latitude: -12.4634, longitude: 130.8456 },
  { name: "Canberra", state: "ACT", postcode: "2600", latitude: -35.2809, longitude: 149.13 },

  // --- Published-venue suburbs (VIC) ---
  { name: "Braybrook", state: "VIC", postcode: "3019", latitude: -37.7789, longitude: 144.8496 },
  { name: "Collingwood", state: "VIC", postcode: "3066", latitude: -37.8033, longitude: 144.9857 },
  { name: "Daylesford", state: "VIC", postcode: "3460", latitude: -37.3407, longitude: 144.1469 },
  { name: "Essendon", state: "VIC", postcode: "3040", latitude: -37.7469, longitude: 144.9158 },
  { name: "Fingal", state: "VIC", postcode: "3939", latitude: -38.3789, longitude: 144.94 },
  { name: "Hawthorn", state: "VIC", postcode: "3122", latitude: -37.8226, longitude: 145.0339 },
  { name: "Hepburn Springs", state: "VIC", postcode: "3461", latitude: -37.3336, longitude: 144.1444 },
  { name: "Malvern East", state: "VIC", postcode: "3145", latitude: -37.8672, longitude: 145.0508 },
  { name: "Metung", state: "VIC", postcode: "3904", latitude: -37.8916, longitude: 147.8562 },
  { name: "Mornington", state: "VIC", postcode: "3931", latitude: -38.2201, longitude: 145.0384 },
  { name: "Narbethong", state: "VIC", postcode: "3778", latitude: -37.5167, longitude: 145.7333 },
  { name: "North Melbourne", state: "VIC", postcode: "3051", latitude: -37.8017, longitude: 144.9427 },
  { name: "Port Melbourne", state: "VIC", postcode: "3207", latitude: -37.8342, longitude: 144.9351 },
  { name: "Seaford", state: "VIC", postcode: "3198", latitude: -38.0989, longitude: 145.1225 },
  { name: "Sorrento", state: "VIC", postcode: "3943", latitude: -38.3372, longitude: 144.7469 },
  { name: "South Yarra", state: "VIC", postcode: "3141", latitude: -37.839, longitude: 144.993 },
  { name: "Torquay", state: "VIC", postcode: "3228", latitude: -38.3333, longitude: 144.3167 },
  { name: "Warrnambool", state: "VIC", postcode: "3280", latitude: -38.3818, longitude: 142.4874 },

  // --- Published-venue suburbs (TAS) ---
  { name: "Cradle Mountain", state: "TAS", postcode: "7306", latitude: -41.639, longitude: 145.955 },
  { name: "East Tinderbox", state: "TAS", postcode: "7054", latitude: -43.0333, longitude: 147.3167 },
  { name: "Launceston", state: "TAS", postcode: "7250", latitude: -41.4332, longitude: 147.1441 },

  // --- NSW regional spread ---
  { name: "Newcastle", state: "NSW", postcode: "2300", latitude: -32.9283, longitude: 151.7817 },
  { name: "Wollongong", state: "NSW", postcode: "2500", latitude: -34.4278, longitude: 150.8931 },
  { name: "Gosford", state: "NSW", postcode: "2250", latitude: -33.4269, longitude: 151.3428 },
  { name: "Coffs Harbour", state: "NSW", postcode: "2450", latitude: -30.2963, longitude: 153.1135 },
  { name: "Byron Bay", state: "NSW", postcode: "2481", latitude: -28.6474, longitude: 153.602 },
  { name: "Tamworth", state: "NSW", postcode: "2340", latitude: -31.0927, longitude: 150.9294 },
  { name: "Wagga Wagga", state: "NSW", postcode: "2650", latitude: -35.1082, longitude: 147.3598 },
  { name: "Albury", state: "NSW", postcode: "2640", latitude: -36.0737, longitude: 146.9135 },
  { name: "Orange", state: "NSW", postcode: "2800", latitude: -33.2839, longitude: 149.101 },
  { name: "Dubbo", state: "NSW", postcode: "2830", latitude: -32.2431, longitude: 148.6017 },
  { name: "Port Macquarie", state: "NSW", postcode: "2444", latitude: -31.4333, longitude: 152.9098 },
  { name: "Bathurst", state: "NSW", postcode: "2795", latitude: -33.4193, longitude: 149.5775 },
  { name: "Katoomba", state: "NSW", postcode: "2780", latitude: -33.7128, longitude: 150.3119 },
  { name: "Nowra", state: "NSW", postcode: "2541", latitude: -34.8805, longitude: 150.6015 },
  { name: "Queanbeyan", state: "NSW", postcode: "2620", latitude: -35.3549, longitude: 149.2334 },

  // --- VIC regional spread (beyond venue suburbs above) ---
  { name: "Geelong", state: "VIC", postcode: "3220", latitude: -38.1499, longitude: 144.3617 },
  { name: "Ballarat", state: "VIC", postcode: "3350", latitude: -37.5622, longitude: 143.8503 },
  { name: "Bendigo", state: "VIC", postcode: "3550", latitude: -36.757, longitude: 144.2794 },
  { name: "Shepparton", state: "VIC", postcode: "3630", latitude: -36.3805, longitude: 145.399 },
  { name: "Mildura", state: "VIC", postcode: "3500", latitude: -34.1855, longitude: 142.1625 },
  { name: "Traralgon", state: "VIC", postcode: "3844", latitude: -38.1954, longitude: 146.5397 },
  { name: "Wodonga", state: "VIC", postcode: "3690", latitude: -36.1214, longitude: 146.8887 },
  { name: "Portland", state: "VIC", postcode: "3305", latitude: -38.3455, longitude: 141.6039 },
  { name: "Bright", state: "VIC", postcode: "3741", latitude: -36.73, longitude: 146.96 },
  { name: "Lorne", state: "VIC", postcode: "3232", latitude: -38.5423, longitude: 143.975 },
  { name: "Cowes", state: "VIC", postcode: "3922", latitude: -38.4551, longitude: 145.2419 },
  { name: "Queenscliff", state: "VIC", postcode: "3225", latitude: -38.2667, longitude: 144.6667 },

  // --- QLD regional spread ---
  { name: "Gold Coast", state: "QLD", postcode: "4217", latitude: -28.0167, longitude: 153.4 },
  { name: "Maroochydore", state: "QLD", postcode: "4558", latitude: -26.65, longitude: 153.0667 },
  { name: "Cairns", state: "QLD", postcode: "4870", latitude: -16.9186, longitude: 145.7781 },
  { name: "Townsville", state: "QLD", postcode: "4810", latitude: -19.259, longitude: 146.8169 },
  { name: "Toowoomba", state: "QLD", postcode: "4350", latitude: -27.5598, longitude: 151.9507 },
  { name: "Rockhampton", state: "QLD", postcode: "4700", latitude: -23.3791, longitude: 150.51 },
  { name: "Mackay", state: "QLD", postcode: "4740", latitude: -21.155, longitude: 149.1867 },
  { name: "Bundaberg", state: "QLD", postcode: "4670", latitude: -24.8661, longitude: 152.3489 },
  { name: "Hervey Bay", state: "QLD", postcode: "4655", latitude: -25.2882, longitude: 152.8523 },
  { name: "Noosa Heads", state: "QLD", postcode: "4567", latitude: -26.3971, longitude: 153.0917 },

  // --- WA regional spread ---
  { name: "Fremantle", state: "WA", postcode: "6160", latitude: -32.0569, longitude: 115.7439 },
  { name: "Bunbury", state: "WA", postcode: "6230", latitude: -33.3271, longitude: 115.6414 },
  { name: "Margaret River", state: "WA", postcode: "6285", latitude: -33.955, longitude: 115.075 },
  { name: "Broome", state: "WA", postcode: "6725", latitude: -17.9614, longitude: 122.2359 },
  { name: "Albany", state: "WA", postcode: "6330", latitude: -35.0269, longitude: 117.8837 },
  { name: "Geraldton", state: "WA", postcode: "6530", latitude: -28.7774, longitude: 114.615 },
  { name: "Kalgoorlie", state: "WA", postcode: "6430", latitude: -30.7489, longitude: 121.4658 },

  // --- SA regional spread ---
  { name: "Nuriootpa", state: "SA", postcode: "5355", latitude: -34.47, longitude: 138.9926 },
  { name: "McLaren Vale", state: "SA", postcode: "5171", latitude: -35.216, longitude: 138.545 },
  { name: "Mount Gambier", state: "SA", postcode: "5290", latitude: -37.8284, longitude: 140.7828 },
  { name: "Port Lincoln", state: "SA", postcode: "5606", latitude: -34.7288, longitude: 135.8586 },
  { name: "Victor Harbor", state: "SA", postcode: "5211", latitude: -35.5522, longitude: 138.6198 },
  { name: "Glenelg", state: "SA", postcode: "5045", latitude: -34.9805, longitude: 138.5175 },

  // --- TAS regional spread (beyond venue suburbs above) ---
  { name: "Devonport", state: "TAS", postcode: "7310", latitude: -41.1789, longitude: 146.3499 },
  { name: "Burnie", state: "TAS", postcode: "7320", latitude: -41.0558, longitude: 145.9067 },
  { name: "Coles Bay", state: "TAS", postcode: "7215", latitude: -42.1167, longitude: 148.2833 },
  { name: "Port Arthur", state: "TAS", postcode: "7182", latitude: -43.1497, longitude: 147.8503 },
  { name: "St Helens", state: "TAS", postcode: "7216", latitude: -41.3208, longitude: 148.2664 },

  // --- NT regional spread ---
  { name: "Alice Springs", state: "NT", postcode: "0870", latitude: -23.698, longitude: 133.8807 },
  { name: "Katherine", state: "NT", postcode: "0850", latitude: -14.4652, longitude: 132.2635 },
  { name: "Palmerston", state: "NT", postcode: "0830", latitude: -12.487, longitude: 130.9834 },
];
