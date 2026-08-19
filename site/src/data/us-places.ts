// US Places gazetteer for near-me distance sort (US expansion 2026)
// Mirrors the structure of au-places.ts — hand-curated, no external dependencies.
// Coverage: major Florida cities (initial US launch focus), plus key thermal spa destinations.
// Extend by adding a row as the directory grows.

export interface UsPlace {
  name: string;
  state: string; // 2-letter state code (FL, CA, AZ, etc.)
  zipcode: string;
  latitude: number;
  longitude: number;
}

export const US_PLACES: UsPlace[] = [
  // Florida (initial US launch focus - thermal springs region)
  { name: "Miami", state: "FL", zipcode: "33101", latitude: 25.7617, longitude: -80.1918 },
  { name: "Fort Lauderdale", state: "FL", zipcode: "33301", latitude: 26.1224, longitude: -80.1373 },
  { name: "West Palm Beach", state: "FL", zipcode: "33401", latitude: 26.7153, longitude: -80.0534 },
  { name: "Orlando", state: "FL", zipcode: "32801", latitude: 28.5383, longitude: -81.3792 },
  { name: "Tampa", state: "FL", zipcode: "33601", latitude: 27.9506, longitude: -82.4572 },
  { name: "St. Petersburg", state: "FL", zipcode: "33701", latitude: 27.7676, longitude: -82.6403 },
  { name: "Sarasota", state: "FL", zipcode: "34236", latitude: 27.3364, longitude: -82.5307 },
  { name: "Naples", state: "FL", zipcode: "34102", latitude: 26.1420, longitude: -81.7948 },
  { name: "Fort Myers", state: "FL", zipcode: "33901", latitude: 26.6406, longitude: -81.8723 },
  { name: "Key West", state: "FL", zipcode: "33040", latitude: 24.5551, longitude: -81.7800 },
  { name: "Gainesville", state: "FL", zipcode: "32601", latitude: 29.6516, longitude: -82.3248 },
  { name: "Jacksonville", state: "FL", zipcode: "32099", latitude: 30.3322, longitude: -81.6557 },
  { name: "Tallahassee", state: "FL", zipcode: "32301", latitude: 30.4383, longitude: -84.2807 },
  { name: "Pensacola", state: "FL", zipcode: "32501", latitude: 30.4213, longitude: -87.2169 },
  { name: "Panama City Beach", state: "FL", zipcode: "32407", latitude: 30.1766, longitude: -85.8055 },
  { name: "Daytona Beach", state: "FL", zipcode: "32114", latitude: 29.2108, longitude: -81.0228 },
  { name: "Melbourne", state: "FL", zipcode: "32901", latitude: 28.0836, longitude: -80.6081 },
  { name: "Boca Raton", state: "FL", zipcode: "33432", latitude: 26.3683, longitude: -80.1289 },
  
  // California (thermal springs destinations)
  { name: "San Francisco", state: "CA", zipcode: "94102", latitude: 37.7749, longitude: -122.4194 },
  { name: "Los Angeles", state: "CA", zipcode: "90001", latitude: 34.0522, longitude: -118.2437 },
  { name: "San Diego", state: "CA", zipcode: "92101", latitude: 32.7157, longitude: -117.1611 },
  { name: "Santa Barbara", state: "CA", zipcode: "93101", latitude: 34.4208, longitude: -119.6982 },
  { name: "Napa", state: "CA", zipcode: "94559", latitude: 38.2975, longitude: -122.2869 },
  { name: "Calistoga", state: "CA", zipcode: "94515", latitude: 38.5796, longitude: -122.5808 },
  
  // Arizona (desert hot springs)
  { name: "Phoenix", state: "AZ", zipcode: "85001", latitude: 33.4484, longitude: -112.0740 },
  { name: "Tucson", state: "AZ", zipcode: "85701", latitude: 32.2226, longitude: -110.9747 },
  { name: "Sedona", state: "AZ", zipcode: "86336", latitude: 34.8697, longitude: -111.7610 },
  
  // Colorado (mountain hot springs)
  { name: "Denver", state: "CO", zipcode: "80201", latitude: 39.7392, longitude: -104.9903 },
  { name: "Colorado Springs", state: "CO", zipcode: "80901", latitude: 38.8339, longitude: -104.8214 },
  { name: "Glenwood Springs", state: "CO", zipcode: "81601", latitude: 39.5505, longitude: -107.3248 },
  { name: "Steamboat Springs", state: "CO", zipcode: "80487", latitude: 40.4850, longitude: -106.8317 },
  { name: "Pagosa Springs", state: "CO", zipcode: "81147", latitude: 37.2694, longitude: -107.0097 },
  
  // Texas (hot springs regions)
  { name: "Austin", state: "TX", zipcode: "78701", latitude: 30.2672, longitude: -97.7431 },
  { name: "San Antonio", state: "TX", zipcode: "78201", latitude: 29.4241, longitude: -98.4936 },
  { name: "Houston", state: "TX", zipcode: "77001", latitude: 29.7604, longitude: -95.3698 },
  { name: "Dallas", state: "TX", zipcode: "75201", latitude: 32.7767, longitude: -96.7970 },
  
  // New Mexico (natural hot springs)
  { name: "Santa Fe", state: "NM", zipcode: "87501", latitude: 35.6870, longitude: -105.9378 },
  { name: "Albuquerque", state: "NM", zipcode: "87101", latitude: 35.0844, longitude: -106.6504 },
  { name: "Truth or Consequences", state: "NM", zipcode: "87901", latitude: 33.1284, longitude: -107.2528 },
];
