// Hand-curated gazetteer for the near-me distance sort (2026-07-25, TRD.md §8
// exception; unified across countries 2026-09-15 for Gate 16). Deliberately
// NOT a bulk postcode/ZIP database — this site hand-curates everything it
// ships, and a multi-thousand-row generic dataset would be both overkill for
// the directory's footprint and would carry a licensing/attribution obligation
// a hand-typed list of well-known place names and centroid coordinates does
// not. Coordinates are approximate town/suburb centroids (2-4 decimal places),
// which is the right precision for "which published venues are roughly
// nearby" — not survey-grade.
//
// One list, not one per country. The split it replaced (au-places.ts with a
// `postcode`, us-places.ts with a `zipcode`) described the same fact under two
// names, and the US half was imported by nothing at all — near-me matched a
// four-digit AU postcode, so a five-digit ZIP resolved to nothing.
//
// `postcode` carries ZIPs too. A postcode and a ZIP answer the same question
// and there is no reason for the field to change its name at a border.
//
// Coverage: all 8 AU state/territory capitals, every suburb an AU published
// venue sits in, a spread of AU regional centres, and Florida — its cities
// plus the spring belt, which is where Florida's bathing actually is. Extend by
// adding a row — no schema migration, no new dependency.
//
// Imported directly by client JS (not embedded as inline build-time JSON,
// unlike the search index) — this is static author-time data, so a normal
// bundled/cached module is cheaper than re-downloading an inline blob on
// every page load.
import type { Country } from "../config";

export interface Place {
  name: string;
  country: Country;
  /** Subdivision code within `country` — an AU state/territory or a US state.
   *  Not unique on its own: "WA" is Western Australia or Washington. */
  subdivision: string;
  /** AU postcode or US ZIP. */
  postcode: string;
  latitude: number;
  longitude: number;
}

export const PLACES: Place[] = [
  // --- AU: Capitals ---
  { name: "Sydney", country: "AU", subdivision: "NSW", postcode: "2000", latitude: -33.8688, longitude: 151.2093 },
  { name: "Melbourne", country: "AU", subdivision: "VIC", postcode: "3000", latitude: -37.8136, longitude: 144.9631 },
  { name: "Brisbane", country: "AU", subdivision: "QLD", postcode: "4000", latitude: -27.4698, longitude: 153.0251 },
  { name: "Perth", country: "AU", subdivision: "WA", postcode: "6000", latitude: -31.9505, longitude: 115.8605 },
  { name: "Adelaide", country: "AU", subdivision: "SA", postcode: "5000", latitude: -34.9285, longitude: 138.6007 },
  { name: "Hobart", country: "AU", subdivision: "TAS", postcode: "7000", latitude: -42.8821, longitude: 147.3272 },
  { name: "Darwin", country: "AU", subdivision: "NT", postcode: "0800", latitude: -12.4634, longitude: 130.8456 },
  { name: "Canberra", country: "AU", subdivision: "ACT", postcode: "2600", latitude: -35.2809, longitude: 149.13 },

  // --- AU: Published-venue suburbs (VIC) ---
  { name: "Braybrook", country: "AU", subdivision: "VIC", postcode: "3019", latitude: -37.7789, longitude: 144.8496 },
  { name: "Collingwood", country: "AU", subdivision: "VIC", postcode: "3066", latitude: -37.8033, longitude: 144.9857 },
  { name: "Daylesford", country: "AU", subdivision: "VIC", postcode: "3460", latitude: -37.3407, longitude: 144.1469 },
  { name: "Essendon", country: "AU", subdivision: "VIC", postcode: "3040", latitude: -37.7469, longitude: 144.9158 },
  { name: "Fingal", country: "AU", subdivision: "VIC", postcode: "3939", latitude: -38.3789, longitude: 144.94 },
  { name: "Hawthorn", country: "AU", subdivision: "VIC", postcode: "3122", latitude: -37.8226, longitude: 145.0339 },
  { name: "Hepburn Springs", country: "AU", subdivision: "VIC", postcode: "3461", latitude: -37.3336, longitude: 144.1444 },
  { name: "Malvern East", country: "AU", subdivision: "VIC", postcode: "3145", latitude: -37.8672, longitude: 145.0508 },
  { name: "Metung", country: "AU", subdivision: "VIC", postcode: "3904", latitude: -37.8916, longitude: 147.8562 },
  { name: "Mornington", country: "AU", subdivision: "VIC", postcode: "3931", latitude: -38.2201, longitude: 145.0384 },
  { name: "Narbethong", country: "AU", subdivision: "VIC", postcode: "3778", latitude: -37.5167, longitude: 145.7333 },
  { name: "North Melbourne", country: "AU", subdivision: "VIC", postcode: "3051", latitude: -37.8017, longitude: 144.9427 },
  { name: "Port Melbourne", country: "AU", subdivision: "VIC", postcode: "3207", latitude: -37.8342, longitude: 144.9351 },
  { name: "Seaford", country: "AU", subdivision: "VIC", postcode: "3198", latitude: -38.0989, longitude: 145.1225 },
  { name: "Sorrento", country: "AU", subdivision: "VIC", postcode: "3943", latitude: -38.3372, longitude: 144.7469 },
  { name: "South Yarra", country: "AU", subdivision: "VIC", postcode: "3141", latitude: -37.839, longitude: 144.993 },
  { name: "Torquay", country: "AU", subdivision: "VIC", postcode: "3228", latitude: -38.3333, longitude: 144.3167 },
  { name: "Warrnambool", country: "AU", subdivision: "VIC", postcode: "3280", latitude: -38.3818, longitude: 142.4874 },

  // --- AU: Published-venue suburbs (TAS) ---
  { name: "Cradle Mountain", country: "AU", subdivision: "TAS", postcode: "7306", latitude: -41.639, longitude: 145.955 },
  { name: "East Tinderbox", country: "AU", subdivision: "TAS", postcode: "7054", latitude: -43.0333, longitude: 147.3167 },
  { name: "Launceston", country: "AU", subdivision: "TAS", postcode: "7250", latitude: -41.4332, longitude: 147.1441 },

  // --- AU: NSW regional spread ---
  { name: "Newcastle", country: "AU", subdivision: "NSW", postcode: "2300", latitude: -32.9283, longitude: 151.7817 },
  { name: "Wollongong", country: "AU", subdivision: "NSW", postcode: "2500", latitude: -34.4278, longitude: 150.8931 },
  { name: "Gosford", country: "AU", subdivision: "NSW", postcode: "2250", latitude: -33.4269, longitude: 151.3428 },
  { name: "Coffs Harbour", country: "AU", subdivision: "NSW", postcode: "2450", latitude: -30.2963, longitude: 153.1135 },
  { name: "Byron Bay", country: "AU", subdivision: "NSW", postcode: "2481", latitude: -28.6474, longitude: 153.602 },
  { name: "Tamworth", country: "AU", subdivision: "NSW", postcode: "2340", latitude: -31.0927, longitude: 150.9294 },
  { name: "Wagga Wagga", country: "AU", subdivision: "NSW", postcode: "2650", latitude: -35.1082, longitude: 147.3598 },
  { name: "Albury", country: "AU", subdivision: "NSW", postcode: "2640", latitude: -36.0737, longitude: 146.9135 },
  { name: "Orange", country: "AU", subdivision: "NSW", postcode: "2800", latitude: -33.2839, longitude: 149.101 },
  { name: "Dubbo", country: "AU", subdivision: "NSW", postcode: "2830", latitude: -32.2431, longitude: 148.6017 },
  { name: "Port Macquarie", country: "AU", subdivision: "NSW", postcode: "2444", latitude: -31.4333, longitude: 152.9098 },
  { name: "Bathurst", country: "AU", subdivision: "NSW", postcode: "2795", latitude: -33.4193, longitude: 149.5775 },
  { name: "Katoomba", country: "AU", subdivision: "NSW", postcode: "2780", latitude: -33.7128, longitude: 150.3119 },
  { name: "Nowra", country: "AU", subdivision: "NSW", postcode: "2541", latitude: -34.8805, longitude: 150.6015 },
  { name: "Queanbeyan", country: "AU", subdivision: "NSW", postcode: "2620", latitude: -35.3549, longitude: 149.2334 },

  // --- AU: VIC regional spread (beyond venue suburbs above) ---
  { name: "Geelong", country: "AU", subdivision: "VIC", postcode: "3220", latitude: -38.1499, longitude: 144.3617 },
  { name: "Ballarat", country: "AU", subdivision: "VIC", postcode: "3350", latitude: -37.5622, longitude: 143.8503 },
  { name: "Bendigo", country: "AU", subdivision: "VIC", postcode: "3550", latitude: -36.757, longitude: 144.2794 },
  { name: "Shepparton", country: "AU", subdivision: "VIC", postcode: "3630", latitude: -36.3805, longitude: 145.399 },
  { name: "Mildura", country: "AU", subdivision: "VIC", postcode: "3500", latitude: -34.1855, longitude: 142.1625 },
  { name: "Traralgon", country: "AU", subdivision: "VIC", postcode: "3844", latitude: -38.1954, longitude: 146.5397 },
  { name: "Wodonga", country: "AU", subdivision: "VIC", postcode: "3690", latitude: -36.1214, longitude: 146.8887 },
  { name: "Portland", country: "AU", subdivision: "VIC", postcode: "3305", latitude: -38.3455, longitude: 141.6039 },
  { name: "Bright", country: "AU", subdivision: "VIC", postcode: "3741", latitude: -36.73, longitude: 146.96 },
  { name: "Lorne", country: "AU", subdivision: "VIC", postcode: "3232", latitude: -38.5423, longitude: 143.975 },
  { name: "Cowes", country: "AU", subdivision: "VIC", postcode: "3922", latitude: -38.4551, longitude: 145.2419 },
  { name: "Queenscliff", country: "AU", subdivision: "VIC", postcode: "3225", latitude: -38.2667, longitude: 144.6667 },

  // --- AU: QLD regional spread ---
  { name: "Gold Coast", country: "AU", subdivision: "QLD", postcode: "4217", latitude: -28.0167, longitude: 153.4 },
  { name: "Maroochydore", country: "AU", subdivision: "QLD", postcode: "4558", latitude: -26.65, longitude: 153.0667 },
  { name: "Cairns", country: "AU", subdivision: "QLD", postcode: "4870", latitude: -16.9186, longitude: 145.7781 },
  { name: "Townsville", country: "AU", subdivision: "QLD", postcode: "4810", latitude: -19.259, longitude: 146.8169 },
  { name: "Toowoomba", country: "AU", subdivision: "QLD", postcode: "4350", latitude: -27.5598, longitude: 151.9507 },
  { name: "Rockhampton", country: "AU", subdivision: "QLD", postcode: "4700", latitude: -23.3791, longitude: 150.51 },
  { name: "Mackay", country: "AU", subdivision: "QLD", postcode: "4740", latitude: -21.155, longitude: 149.1867 },
  { name: "Bundaberg", country: "AU", subdivision: "QLD", postcode: "4670", latitude: -24.8661, longitude: 152.3489 },
  { name: "Hervey Bay", country: "AU", subdivision: "QLD", postcode: "4655", latitude: -25.2882, longitude: 152.8523 },
  { name: "Noosa Heads", country: "AU", subdivision: "QLD", postcode: "4567", latitude: -26.3971, longitude: 153.0917 },

  // --- AU: WA regional spread ---
  { name: "Fremantle", country: "AU", subdivision: "WA", postcode: "6160", latitude: -32.0569, longitude: 115.7439 },
  { name: "Bunbury", country: "AU", subdivision: "WA", postcode: "6230", latitude: -33.3271, longitude: 115.6414 },
  { name: "Margaret River", country: "AU", subdivision: "WA", postcode: "6285", latitude: -33.955, longitude: 115.075 },
  { name: "Broome", country: "AU", subdivision: "WA", postcode: "6725", latitude: -17.9614, longitude: 122.2359 },
  { name: "Albany", country: "AU", subdivision: "WA", postcode: "6330", latitude: -35.0269, longitude: 117.8837 },
  { name: "Geraldton", country: "AU", subdivision: "WA", postcode: "6530", latitude: -28.7774, longitude: 114.615 },
  { name: "Kalgoorlie", country: "AU", subdivision: "WA", postcode: "6430", latitude: -30.7489, longitude: 121.4658 },

  // --- AU: SA regional spread ---
  { name: "Nuriootpa", country: "AU", subdivision: "SA", postcode: "5355", latitude: -34.47, longitude: 138.9926 },
  { name: "McLaren Vale", country: "AU", subdivision: "SA", postcode: "5171", latitude: -35.216, longitude: 138.545 },
  { name: "Mount Gambier", country: "AU", subdivision: "SA", postcode: "5290", latitude: -37.8284, longitude: 140.7828 },
  { name: "Port Lincoln", country: "AU", subdivision: "SA", postcode: "5606", latitude: -34.7288, longitude: 135.8586 },
  { name: "Victor Harbor", country: "AU", subdivision: "SA", postcode: "5211", latitude: -35.5522, longitude: 138.6198 },
  { name: "Glenelg", country: "AU", subdivision: "SA", postcode: "5045", latitude: -34.9805, longitude: 138.5175 },

  // --- AU: TAS regional spread (beyond venue suburbs above) ---
  { name: "Devonport", country: "AU", subdivision: "TAS", postcode: "7310", latitude: -41.1789, longitude: 146.3499 },
  { name: "Burnie", country: "AU", subdivision: "TAS", postcode: "7320", latitude: -41.0558, longitude: 145.9067 },
  { name: "Coles Bay", country: "AU", subdivision: "TAS", postcode: "7215", latitude: -42.1167, longitude: 148.2833 },
  { name: "Port Arthur", country: "AU", subdivision: "TAS", postcode: "7182", latitude: -43.1497, longitude: 147.8503 },
  { name: "St Helens", country: "AU", subdivision: "TAS", postcode: "7216", latitude: -41.3208, longitude: 148.2664 },

  // --- AU: NT regional spread ---
  { name: "Alice Springs", country: "AU", subdivision: "NT", postcode: "0870", latitude: -23.698, longitude: 133.8807 },
  { name: "Katherine", country: "AU", subdivision: "NT", postcode: "0850", latitude: -14.4652, longitude: 132.2635 },
  { name: "Palmerston", country: "AU", subdivision: "NT", postcode: "0830", latitude: -12.487, longitude: 130.9834 },

  // --- US: Florida cities ---
  { name: "Miami", country: "US", subdivision: "FL", postcode: "33101", latitude: 25.7617, longitude: -80.1918 },
  { name: "Fort Lauderdale", country: "US", subdivision: "FL", postcode: "33301", latitude: 26.1224, longitude: -80.1373 },
  { name: "West Palm Beach", country: "US", subdivision: "FL", postcode: "33401", latitude: 26.7153, longitude: -80.0534 },
  { name: "Orlando", country: "US", subdivision: "FL", postcode: "32801", latitude: 28.5383, longitude: -81.3792 },
  { name: "Tampa", country: "US", subdivision: "FL", postcode: "33601", latitude: 27.9506, longitude: -82.4572 },
  { name: "St. Petersburg", country: "US", subdivision: "FL", postcode: "33701", latitude: 27.7676, longitude: -82.6403 },
  { name: "Sarasota", country: "US", subdivision: "FL", postcode: "34236", latitude: 27.3364, longitude: -82.5307 },
  { name: "Naples", country: "US", subdivision: "FL", postcode: "34102", latitude: 26.1420, longitude: -81.7948 },
  { name: "Fort Myers", country: "US", subdivision: "FL", postcode: "33901", latitude: 26.6406, longitude: -81.8723 },
  { name: "Key West", country: "US", subdivision: "FL", postcode: "33040", latitude: 24.5551, longitude: -81.7800 },
  { name: "Gainesville", country: "US", subdivision: "FL", postcode: "32601", latitude: 29.6516, longitude: -82.3248 },
  { name: "Jacksonville", country: "US", subdivision: "FL", postcode: "32099", latitude: 30.3322, longitude: -81.6557 },
  { name: "Tallahassee", country: "US", subdivision: "FL", postcode: "32301", latitude: 30.4383, longitude: -84.2807 },
  { name: "Pensacola", country: "US", subdivision: "FL", postcode: "32501", latitude: 30.4213, longitude: -87.2169 },
  { name: "Panama City Beach", country: "US", subdivision: "FL", postcode: "32407", latitude: 30.1766, longitude: -85.8055 },
  { name: "Daytona Beach", country: "US", subdivision: "FL", postcode: "32114", latitude: 29.2108, longitude: -81.0228 },
  { name: "Melbourne", country: "US", subdivision: "FL", postcode: "32901", latitude: 28.0836, longitude: -80.6081 },
  { name: "Boca Raton", country: "US", subdivision: "FL", postcode: "33432", latitude: 26.3683, longitude: -80.1289 },

  // --- US: Florida spring belt and bathing towns ---
  { name: "High Springs", country: "US", subdivision: "FL", postcode: "32643", latitude: 29.8269, longitude: -82.5968 },
  { name: "Ocala", country: "US", subdivision: "FL", postcode: "34470", latitude: 29.1872, longitude: -82.1401 },
  { name: "Williston", country: "US", subdivision: "FL", postcode: "32696", latitude: 29.3872, longitude: -82.4473 },
  { name: "Silver Springs", country: "US", subdivision: "FL", postcode: "34488", latitude: 29.2158, longitude: -82.0576 },
  { name: "Crystal River", country: "US", subdivision: "FL", postcode: "34428", latitude: 28.9025, longitude: -82.5926 },
  { name: "Homosassa", country: "US", subdivision: "FL", postcode: "34446", latitude: 28.7811, longitude: -82.6126 },
  { name: "DeLand", country: "US", subdivision: "FL", postcode: "32720", latitude: 29.0283, longitude: -81.3031 },
  { name: "Apopka", country: "US", subdivision: "FL", postcode: "32703", latitude: 28.6934, longitude: -81.5322 },
  { name: "Crawfordville", country: "US", subdivision: "FL", postcode: "32327", latitude: 30.1752, longitude: -84.3752 },
  { name: "Safety Harbor", country: "US", subdivision: "FL", postcode: "34695", latitude: 27.9911, longitude: -82.6929 },
  { name: "North Port", country: "US", subdivision: "FL", postcode: "34287", latitude: 27.0592, longitude: -82.2593 },
  { name: "Venice", country: "US", subdivision: "FL", postcode: "34285", latitude: 27.0998, longitude: -82.4543 },
  { name: "Bradenton", country: "US", subdivision: "FL", postcode: "34205", latitude: 27.4989, longitude: -82.5748 },
  { name: "Clearwater", country: "US", subdivision: "FL", postcode: "33755", latitude: 27.9659, longitude: -82.8001 },
  { name: "Coral Gables", country: "US", subdivision: "FL", postcode: "33134", latitude: 25.7215, longitude: -80.2684 },
  { name: "Hollywood", country: "US", subdivision: "FL", postcode: "33019", latitude: 26.0112, longitude: -80.1495 },
  { name: "Delray Beach", country: "US", subdivision: "FL", postcode: "33444", latitude: 26.4615, longitude: -80.0728 },
];
