// Script to fix and migrate venues.json
import { readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Go up one level from scripts/ to site/
const venuesPath = join(__dirname, '..', 'src', 'data', 'venues.json');

// Read the JSON file
const rawData = readFileSync(venuesPath, 'utf-8');
let venues = JSON.parse(rawData);

// Helper function to strip whitespace from keys and string values recursively
function cleanObject(obj) {
  if (Array.isArray(obj)) {
    return obj.map(item => cleanObject(item));
  } else if (obj !== null && typeof obj === 'object') {
    const cleaned = {};
    for (const [key, value] of Object.entries(obj)) {
      const cleanKey = key.trim();
      const cleanValue = typeof value === 'string' ? value.trim() : cleanObject(value);
      cleaned[cleanKey] = cleanValue;
    }
    return cleaned;
  }
  return obj;
}

// Clean all venues - strip whitespace from keys and string values
venues = venues.map(venue => cleanObject(venue));

// Schema migration for each venue
venues = venues.map(venue => {
  // Add country: "AU" for all existing venues
  venue.country = 'AU';
  
  // Rename state to state_province
  if (venue.state !== undefined) {
    venue.state_province = venue.state;
    delete venue.state;
  }
  
  // Add city (use suburb value), keep suburb as alias for now
  if (venue.suburb !== undefined) {
    venue.city = venue.suburb;
    // Keep suburb as an alias for backward compatibility
  }
  
  // Add zipcode: null for US compatibility
  if (venue.zipcode === undefined) {
    venue.zipcode = null;
  }
  
  // Add website: null and contact_email: null for future outreach
  if (venue.website === undefined) {
    venue.website = null;
  }
  if (venue.contact_email === undefined) {
    venue.contact_email = null;
  }
  
  // Price/Currency migration
  if (venue.price !== undefined) {
    // Rename adult_drop_in_aud to adult_drop_in
    if (venue.price.adult_drop_in_aud !== undefined) {
      venue.price.adult_drop_in = venue.price.adult_drop_in_aud;
      delete venue.price.adult_drop_in_aud;
    }
    // Rename standard_session_aud to standard_session
    if (venue.price.standard_session_aud !== undefined) {
      venue.price.standard_session = venue.price.standard_session_aud;
      delete venue.price.standard_session_aud;
    }
  }
  
  // Add currency: "AUD" for all existing venues
  venue.currency = 'AUD';
  
  return venue;
});

// Add sample US venue
const usVenue = {
  slug: "example-miami-spa",
  name: "Example Miami Thermal Spa",
  country: "US",
  state_province: "FL",
  city: "Miami",
  zipcode: "33101",
  currency: "USD",
  category: "thermal_springs",
  status: "unclaimed",
  summary: "Placeholder thermal springs in Miami, Florida.",
  suburb: "Miami",
  latitude: null,
  longitude: null,
  has_image: false,
  hours: null,
  cost: null,
  access: null,
  dress_code: null,
  session_gender: null,
  session_gender_note: null,
  silence_policy: null,
  phone_policy: null,
  minimum_age: null,
  amenities: {
    magnesium_pool: false,
    infrared_sauna: false,
    traditional_sauna: false,
    cold_plunge: false,
    led_therapy: false
  },
  facilities: {
    parking: false,
    towels_provided: false,
    changerooms: false,
    bookings_required: false,
    wheelchair_access: false,
    outdoor_pool: false,
    indoor_pool: false,
    natural_spring: false,
    pregnancy_safe: false,
    step_free_entry: false,
    hoist_available: false,
    accessible_changerooms: false
  },
  website: null,
  contact_email: null,
  price: {}
};

venues.push(usVenue);

// Write the updated JSON with 2-space indentation
writeFileSync(venuesPath, JSON.stringify(venues, null, 2) + '\n');

console.log('✓ venues.json has been fixed and migrated successfully!');
console.log(`  - Stripped whitespace from all keys and string values`);
console.log(`  - Added country field to all venues`);
console.log(`  - Renamed state to state_province`);
console.log(`  - Added city, zipcode, website, contact_email fields`);
console.log(`  - Migrated price schema (removed _aud suffix)`);
console.log(`  - Added currency field to all venues`);
console.log(`  - Added sample US venue: example-miami-spa`);
console.log(`  - Total venues: ${venues.length}`);
