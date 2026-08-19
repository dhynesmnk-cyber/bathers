/**
 * MDX Frontmatter Migration Script
 * Migrates old venue schema to new international schema
 */

const fs = require('fs');
const path = require('path');
const yaml = require('yaml');

const SPAS_DIR = path.join(__dirname, 'src/content/spas/_published');

// Read all MDX files
const mdxFiles = fs.readdirSync(SPAS_DIR).filter(f => f.endsWith('.mdx'));

console.log(`Found ${mdxFiles.length} MDX files to migrate...\n`);

let migratedCount = 0;
let errorCount = 0;

mdxFiles.forEach(filename => {
  const filepath = path.join(SPAS_DIR, filename);
  
  try {
    const content = fs.readFileSync(filepath, 'utf8');
    
    // Split frontmatter and body
    const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (!match) {
      console.error(`❌ ${filename}: Invalid frontmatter format`);
      errorCount++;
      return;
    }
    
    const [, frontmatterStr, body] = match;
    const frontmatter = yaml.parse(frontmatterStr);
    
    // Skip if already migrated
    if (frontmatter.country) {
      console.log(`⏭️  ${filename}: Already migrated`);
      return;
    }
    
    // Apply migrations
    const newFrontmatter = { ...frontmatter };
    
    // 1. Add country
    newFrontmatter.country = 'AU';
    
    // 2. Rename state to state_province
    if (newFrontmatter.state) {
      newFrontmatter.state_province = newFrontmatter.state;
      delete newFrontmatter.state;
    }
    
    // 3. Add city from suburb
    if (newFrontmatter.suburb) {
      newFrontmatter.city = newFrontmatter.suburb;
      // Keep suburb as alias for backwards compatibility (optional)
    }
    
    // 4. Add zipcode (null for now, can be populated later)
    if (!newFrontmatter.zipcode) {
      newFrontmatter.zipcode = null;
    }
    
    // 5. Ensure website and contact_email exist
    if (!newFrontmatter.website) {
      newFrontmatter.website = null;
    }
    if (!newFrontmatter.contact_email) {
      newFrontmatter.contact_email = null;
    }
    
    // 6. Migrate price object
    if (newFrontmatter.price) {
      const price = { ...newFrontmatter.price };
      
      // Rename AUD fields
      if (price.adult_drop_in_aud !== undefined) {
        price.adult_drop_in = price.adult_drop_in_aud;
        delete price.adult_drop_in_aud;
      }
      if (price.standard_session_aud !== undefined) {
        price.standard_session = price.standard_session_aud;
        delete price.standard_session_aud;
      }
      
      newFrontmatter.price = price;
    }
    
    // 7. Add currency
    newFrontmatter.currency = 'AUD';
    
    // Serialize back to YAML
    const newFrontmatterStr = yaml.stringify(newFrontmatter).trim();
    const newContent = `---\n${newFrontmatterStr}\n---\n${body}`;
    
    // Write back
    fs.writeFileSync(filepath, newContent, 'utf8');
    console.log(`✅ ${filename}: Migrated`);
    migratedCount++;
    
  } catch (err) {
    console.error(`❌ ${filename}: ${err.message}`);
    errorCount++;
  }
});

console.log(`\n─────────────────────────────────────`);
console.log(`Migration complete!`);
console.log(`  ✅ Migrated: ${migratedCount}`);
console.log(`  ⏭️  Skipped: ${mdxFiles.length - migratedCount - errorCount}`);
console.log(`  ❌ Errors: ${errorCount}`);
console.log(`─────────────────────────────────────`);
