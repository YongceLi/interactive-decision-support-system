# PC Parts Database Augmentation

This script augments the `pc_parts.db` database with missing compatibility attributes extracted via web scraping and LLM extraction.

## Overview

The augmentation process:
1. Reads products from `pc_parts.db`
2. Creates `pc_parts_augmented.db` with the same base schema plus augmentation tables
3. Scrapes attributes from multiple sources (Newegg, Amazon, Wikipedia, Manufacturer)
4. Validates attributes using cross-source validation (requires at least 2 sources to agree)
5. Stores validated attributes with source tracking, timestamps, and confidence scores
6. Tags products for manual review if no manufacturer source is found

## Usage

### Basic Usage

```bash
# Copy base data and augment all products
python scripts/kg/augment_pc_parts_db.py

# Augment with LLM extraction (recommended)
python scripts/kg/augment_pc_parts_db.py --use-llm

# Limit to first 10 products (for testing)
python scripts/kg/augment_pc_parts_db.py --use-llm --limit 10

# Only copy base data without augmentation
python scripts/kg/augment_pc_parts_db.py --copy-only
```

### Command Line Options

- `--source-db`: Path to source database (default: `data/pc_parts.db`)
- `--target-db`: Path to target database (default: `data/pc_parts_augmented.db`)
- `--use-llm`: Enable LLM-based extraction (requires OpenAI API key)
- `--limit`: Limit number of products to process
- `--delay`: Delay between products in seconds (default: 2.0)
- `--copy-only`: Only copy base data, don't augment
- `--log-level`: Logging level (default: INFO)

## Database Schema

### Main Table: `pc_parts_augmented`

Same as `pc_parts` table plus:
- `needs_manual_review`: Boolean flag indicating if product needs manual review
- `base_attributes`: JSON string containing base attributes from RapidAPI (parsed at KG creation time)

**Note**: Attributes are NOT stored as individual columns to avoid sparse tables. Instead:
- `base_attributes` JSON is preserved from source database
- Attributes are parsed and stored in `validated_attributes` table
- Attributes will be parsed from both `base_attributes` JSON and `validated_attributes` table at knowledge graph creation time
- The `pc_parts_attributes.json` config defines which attributes each product type should have

### Attribute Tracking: `product_attributes_augmented`

Stores all attribute extractions from all sources:
- `product_id`: Product identifier
- `attribute_name`: Attribute name (snake_case)
- `attribute_value`: Attribute value
- `source`: Source name (e.g., "newegg", "wikipedia_llm", "manufacturer_official")
- `source_url`: URL where attribute was found
- `timestamp`: ISO timestamp of extraction
- `confidence`: Confidence score (0.0-1.0)
- `is_manufacturer`: Boolean indicating if source is manufacturer

### Validated Attributes: `validated_attributes`

Stores validated attributes (agreed upon by at least 2 sources):
- `product_id`: Product identifier
- `attribute_name`: Attribute name
- `attribute_value`: Validated attribute value
- `final_confidence`: Final confidence score
- `has_manufacturer_source`: Boolean indicating if manufacturer source exists
- `needs_manual_review`: Boolean indicating if manual review needed
- `sources_json`: JSON array of all sources that agreed on this value

### Manufacturer Map: `manufacturer_map`

Stores manufacturer documentation URLs:
- `brand`: Manufacturer brand name
- `domain`: Manufacturer website domain
- `product_url_pattern`: URL pattern for product pages
- `docs_url_pattern`: URL pattern for documentation

## Validation Rules

1. **Cross-Source Validation**: At least 2 sources must agree on an attribute value
2. **Source Priority**: Manufacturer sources are ranked highest, followed by Wikipedia, then retailers
3. **Manual Review**: Products without manufacturer sources are tagged for manual review
4. **Protected Fields**: These fields are never modified:
   - `product_id`, `product_type`, `raw_name`, `brand`, `series`, `model`, `seller`, `price`, `rating`, `rating_count`

## Attribute Extraction

The script extracts attributes based on the allowed attributes defined in `dataset_builder/pc_parts_attributes.json`:

- **CPU**: socket, architecture, pcie_version, ram_standard, tdp, year, color, size
- **GPU**: vram, memory_type, cooler_type, variant, is_oc, revision, interface, power_connector, year, color, size
- **Motherboard**: chipset, form_factor, pcie_version, ram_standard, socket, year, color, size
- **PSU**: wattage, certification, modularity, form_factor, atx_version, noise, supports_pcie5_power, year, color, size
- **Case**: storage, capacity, storage_type, year, color, size
- **RAM**: ram_standard, form_factor, capacity, year, color, size
- **Cooling**: cooling_type, tdp_support, year, color, size
- **Storage**: storage_type, capacity, interface, form_factor, year, color, size

## Source Priority

Sources are ranked by priority (higher = more trusted):
- Manufacturer official: 100
- Manufacturer official (LLM): 95
- Wikipedia: 80
- Wikipedia (LLM): 75
- Newegg: 60
- Newegg (LLM): 55
- Amazon: 50
- Amazon (LLM): 45

## Example Queries

### Find products needing manual review

```sql
SELECT product_id, raw_name, brand, product_type
FROM pc_parts_augmented
WHERE needs_manual_review = 1;
```

### Get validated attributes for a product

```sql
SELECT attribute_name, attribute_value, final_confidence, has_manufacturer_source
FROM validated_attributes
WHERE product_id = 'rapidapi:1234567890';
```

### Get all sources for an attribute

```sql
SELECT attribute_name, attribute_value, source, source_url, confidence, timestamp
FROM product_attributes_augmented
WHERE product_id = 'rapidapi:1234567890' AND attribute_name = 'socket'
ORDER BY confidence DESC;
```

### Find products with manufacturer-confirmed attributes

```sql
SELECT va.product_id, pa.raw_name, va.attribute_name, va.attribute_value
FROM validated_attributes va
JOIN pc_parts_augmented pa ON va.product_id = pa.product_id
WHERE va.has_manufacturer_source = 1;
```

## Attribute Storage Strategy

Attributes are stored in two places:

1. **`base_attributes` JSON field**: Original attributes from RapidAPI, preserved as JSON
2. **`validated_attributes` table**: All validated attributes (from base + scraped sources) with source tracking

**Why not individual columns?**
- Different product types have different attributes (CPU has socket, GPU has vram, etc.)
- Creating columns for all attributes would create a very sparse table
- The `pc_parts_attributes.json` config defines what attributes each product type should have
- Attributes are parsed at knowledge graph creation time (Step 2) using the config

**At KG creation time:**
- Parse `base_attributes` JSON for each product
- Merge with `validated_attributes` table entries
- Use `pc_parts_attributes.json` to determine which attributes should exist for each product type
- Create knowledge graph nodes with appropriate attributes based on product type

## Next Steps

After augmentation is complete:
1. Review products tagged for manual review
2. Use validated attributes to build knowledge graph (Step 2)
   - Parse `base_attributes` JSON
   - Merge with `validated_attributes` table
   - Use `pc_parts_attributes.json` to determine expected attributes per product type
3. Export validated attributes to knowledge graph format

## Notes

- The script respects rate limits with delays between requests
- LLM extraction requires OpenAI API key in environment
- Manufacturer URLs are automatically constructed from brand names
- All timestamps are in UTC ISO format
- Attribute values are normalized to snake_case

