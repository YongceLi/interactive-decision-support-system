# Electronics Domain Documentation

## Table of Contents

1. [Overview](#overview)
2. [Major Changes from Cars Domain](#major-changes-from-cars-domain)
3. [Local Database](#local-database)
4. [Knowledge Graph and Compatibility](#knowledge-graph-and-compatibility)

---

## Overview

The Interactive Decision Support System (IDSS) has been extended from the original vehicle shopping domain to support electronics products, with a particular focus on PC components. This extension introduces new data sources, compatibility checking capabilities, and specialized knowledge graph functionality.

---

## Major Changes from Cars Domain

### Data Source Migration

**From**: Local SQLite database (`california_vehicles.db`, `uni_vehicles.db`) with vehicle listings
**To**: Local SQLite database (`pc_parts.db`) with electronics product listings

### Product Type Changes

**From**: Vehicles (cars, trucks, SUVs) with attributes like:
- Make, model, year
- Mileage, price, location
- Body style, engine, transmission
- Safety ratings, fuel economy

**To**: Electronics products (PC components, consumer electronics) with attributes like:
- Product name, brand, model number
- Price, seller, availability
- Technical specifications (socket, PCIe version, wattage, etc.)
- Compatibility attributes for PC parts

### API Integration Changes

**From**: Auto.dev API for vehicle data and images
**To**: Local SQLite database (`pc_parts.db`) for electronics product search and details

### New Features

1. **Compatibility Checking**: Neo4j knowledge graph for PC part compatibility
2. **Technical Specifications**: Focus on hardware compatibility (sockets, PCIe, power requirements)
3. **Local Database**: Pre-populated SQLite database with electronics products from multiple sellers
4. **Knowledge Graph**: Structured compatibility relationships between PC components

### Code Changes

**Database Tools**:
- `idss_agent/tools/local_vehicle_store.py` → Still used for legacy vehicle data
- `idss_agent/tools/local_electronics_store.py` → New local database integration for electronics
- `idss_agent/tools/kg_compatibility.py` → New Neo4j compatibility tool

**Processing Modules**:
- `idss_agent/processing/recommendation.py` → Updated for electronics product search
- `idss_agent/processing/compatibility.py` → New compatibility checking handler
- `idss_agent/processing/vector_ranker.py` → Updated for electronics tokenization

**State Schema**:
- Product type field extended to support electronics categories
- Compatibility result field added to state
- Comparison table structure adapted for technical specifications

---

## Local Database

### Database Schema

The electronics domain uses a SQLite database (`data/pc_parts.db`) with the following structure:

**Main Table: `pc_parts`**
- `part_id`: Unique identifier (format: `source:identifier`)
- `source`: Data source (e.g., `rapidapi`)
- `part_type`: Product category (cpu, gpu, motherboard, psu, ram, etc.)
- `product_name`: Full product name
- `model_number`: Manufacturer model number
- `series`: Product series name
- `price`: Price in USD
- `currency`: Currency code (default: USD)
- `availability`: Availability status
- `stock_status`: Normalized stock status (in_stock, out_of_stock, preorder)
- `seller`: Seller/store name
- `rating`: Product rating
- `review_count`: Number of reviews
- `url`: Product URL
- `image_url`: Product image URL
- `description`: Product description
- `specs_json`: JSON field for technical specifications
- `attributes_json`: JSON field for parsed attributes
- `data_fetched_at`: Timestamp of data fetch
- `last_seen_at`: Last update timestamp
- `raw_json`: Complete raw API response for traceability

**Supporting Tables**:
- `pc_parts_fetch_progress`: Tracks data collection progress per category
- `pc_parts_dataset_stats`: Dataset statistics and metadata

### Database Creation

The database is created using the schema defined in `dataset_builder/pc_parts_schema.sql`. The schema includes:
- Primary key on `part_id`
- Indexes on `part_type`, `source`, and `product_name`
- JSON fields for flexible attribute storage
- Timestamp tracking for data freshness

### Database Builder Script

**Location**: `dataset_builder/fetch_pc_parts_dataset.py`

**Usage**:
```bash
python dataset_builder/fetch_pc_parts_dataset.py \
    --db-path data/pc_parts.db \
    --limit 100
```

**Functionality**:
1. Connects to RapidAPI Shopping API (for initial data population)
2. Fetches products for predefined categories (CPU, GPU, motherboard, PSU, RAM, etc.)
3. Normalizes product data
4. Stores in SQLite database with deduplication
5. Tracks fetch progress and statistics

**Note**: The database builder script is used to populate the local database. Once populated, the recommendation system uses the local database directly without requiring RapidAPI access.

**Categories Supported**:
- PC Components: cpu, gpu, motherboard, psu, ram, storage, case, cooling
- Consumer Electronics: laptop, desktop_pc, monitor, keyboard, mouse, headset, headphones, speakers
- Smart Devices: smart_home_hub, smart_speaker, smart_display, smart_light, smart_thermostat
- And many more categories (see `ELECTRONICS_CATEGORIES` in the script)

**Data Normalization**:
- Price parsing and conversion to float
- Stock status normalization (in_stock, out_of_stock, preorder)
- Product ID generation from multiple identifier fields
- Deduplication by `part_id` and product name

### Database Access

The database is accessed through `LocalElectronicsStore` class in the agent system. Products are queried by:
- Part type (category)
- Price range
- Seller
- Brand
- Text search on product name, model number, series, and description

**Location**: `idss_agent/tools/local_electronics_store.py`

**Class**: `LocalElectronicsStore`

**Methods**:

1. **`search_products`**: Search for electronics products in local database
   - Parameters: `query`, `part_type`, `brand`, `min_price`, `max_price`, `seller`, `limit`, `offset`
   - Returns: List of product dictionaries matching RapidAPI format
   - Performs SQL queries with LIKE matching for text search
   - Supports filtering by multiple criteria simultaneously

**Benefits of Local Database**:
- No API rate limits or costs
- Faster query performance
- Offline operation capability
- Consistent data format
- Full control over data quality

**Note**: RapidAPI integration (`idss_agent/tools/electronics_api.py`) is still available for data population via the dataset builder script, but the recommendation system now uses the local database exclusively.

---

## Knowledge Graph and Compatibility

### Overview

The knowledge graph system provides compatibility checking for PC components using Neo4j. It stores product nodes with attributes and creates compatibility relationships between compatible parts.

### Neo4j Setup

**Installation**:

**Using Docker (recommended)**:
```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:latest
```

**Using Homebrew (macOS)**:
```bash
brew install neo4j
brew services start neo4j
```

**Direct Installation**:
Download from https://neo4j.com/download/

**Connection Configuration**:
Set in `.env` file:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

### Knowledge Graph Structure

**Node Type**: `PCProduct`
- Properties: `slug`, `name`, `product_type`, `brand`, `price_avg`, `price_min`, and various compatibility attributes

**Compatibility Relationship Types**:
1. **ELECTRICAL_COMPATIBLE_WITH**: Power supply compatibility (PSU wattage requirements)
2. **SOCKET_COMPATIBLE_WITH**: Socket compatibility (CPU and motherboard socket matching)
3. **INTERFACE_COMPATIBLE_WITH**: PCIe interface compatibility (GPU and motherboard)
4. **RAM_COMPATIBLE_WITH**: RAM standard compatibility (RAM and motherboard DDR standard)
5. **MEMORY_COMPATIBLE_WITH**: Memory controller compatibility (CPU and RAM)
6. **FORM_FACTOR_COMPATIBLE_WITH**: Form factor compatibility (case and motherboard physical size)
7. **THERMAL_COMPATIBLE_WITH**: Thermal compatibility (cooler socket and TDP capacity)

**Part Type Compatibility Mapping**:
- CPU ↔ Motherboard: `SOCKET_COMPATIBLE_WITH`
- GPU ↔ PSU: `ELECTRICAL_COMPATIBLE_WITH`
- CPU ↔ PSU: `ELECTRICAL_COMPATIBLE_WITH`
- Motherboard ↔ GPU: `INTERFACE_COMPATIBLE_WITH`
- RAM ↔ Motherboard: `RAM_COMPATIBLE_WITH`
- CPU ↔ RAM: `MEMORY_COMPATIBLE_WITH`
- Case ↔ Motherboard: `FORM_FACTOR_COMPATIBLE_WITH`
- Cooler ↔ CPU: `THERMAL_COMPATIBLE_WITH`

### Building the Knowledge Graph

**Script**: `scripts/kg/build_pc_parts_kg.py`

**Basic Build** (uses cached scraped data):
```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password \
    --namespace pc_parts \
    --purge
```

**Build with Active Scraping**:
```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password \
    --namespace pc_parts \
    --enable-scraping \
    --purge
```

**Process**:
1. Loads products from `pc_parts.db`
2. Parses product names to extract attributes (socket, PCIe version, wattage, etc.)
3. Optionally scrapes compatibility data from Wikipedia, Newegg, MicroCenter, manufacturer sites
4. Caches scraped data in `data/compatibility_cache.db`
5. Creates product nodes in Neo4j with attributes as properties
6. Creates compatibility edges between compatible products based on attribute matching

### Compatibility Data Scraping

**Script**: `scripts/kg/scrape_compatibility_data.py`

**Sources**:
- **Wikipedia**: Product specifications from infoboxes
- **Newegg**: Product detail pages
- **MicroCenter**: Product specifications
- **Manufacturer Sites**: Official product documentation

**Usage**:
```bash
python scripts/kg/scrape_compatibility_data.py \
    --product-name "NVIDIA RTX 4090" \
    --product-slug "nvidia-rtx-4090" \
    --brand "NVIDIA" \
    --sellers newegg microcenter wikipedia manufacturer
```

**LLM Extraction** (optional, requires OpenAI API key):
```bash
python scripts/kg/scrape_compatibility_data.py \
    --product-name "ASUS ROG Strix Z790-E" \
    --product-slug "asus-rog-strix-z790-e" \
    --brand "ASUS" \
    --use-llm \
    --sellers manufacturer
```

**Cached Data**: Scraped compatibility data is cached in `data/compatibility_cache.db` for reuse in future builds.

### Compatibility Tool

**Location**: `idss_agent/tools/kg_compatibility.py`

**Class**: `Neo4jCompatibilityTool`

**Methods**:

1. **`find_product_by_name`**: Find a product in the knowledge graph by name (fuzzy matching)
   - Searches by slug (exact match) or name (contains match)
   - Returns product node data or None

2. **`check_compatibility`**: Check if two parts are compatible
   - Parameters: `part1_slug`, `part2_slug`, `compatibility_types` (optional)
   - Returns: Dict with `compatible`, `compatibility_types`, `explanation`, `part1_name`, `part2_name`
   - Checks bidirectional compatibility relationships

3. **`find_compatible_parts`**: Find parts compatible with a source part
   - Parameters: `source_slug`, `target_type`, `compatibility_type` (optional), `limit`
   - Returns: List of compatible product nodes
   - Orders results by price (ascending)

4. **`get_product_info`**: Get full product information from knowledge graph
   - Parameters: `slug`
   - Returns: Product node data or None

### Compatibility Handler

**Location**: `idss_agent/processing/compatibility.py`

**Class**: `CompatibilityHandler`

**Functionality**:
- Detects compatibility queries from user input
- Classifies intent (compare vs. recommend)
- Extracts part information from queries and cached products
- Handles compatibility checking and recommendation generation
- Formats compatibility results for display

**Query Detection**: Identifies compatibility queries using keywords:
- "compatible", "compatibility", "works with", "fits", "supports"
- "will work", "can i use", "does it work"

**Intent Classification**:
- **Compare**: Binary compatibility check ("Is X compatible with Y?")
- **Recommend**: Find compatible parts ("What GPUs work with my motherboard?")

### Compatibility Checking Functions

**Location**: `idss_agent/processing/compatibility.py`

1. **`check_compatibility_binary`**: Check if two parts are compatible
   - Uses `Neo4jCompatibilityTool.check_compatibility`
   - Returns compatibility result dict

2. **`find_compatible_parts_recommendations`**: Find compatible parts recommendations
   - Uses `Neo4jCompatibilityTool.find_compatible_parts`
   - Reranks by price
   - Returns top N recommendations

3. **`format_compatibility_recommendations_table`**: Format compatible products as comparison table
   - Creates `ComparisonTable` object with headers and rows
   - Includes price, brand, and product-type-specific attributes

### Web UI Integration

**Frontend Component**: `web/src/components/CompatibilityResult.tsx`

**Display Features**:
- Compatible/incompatible status indicator
- Part names and compatibility types
- Explanation text
- Visual styling (green for compatible, red for incompatible)

**API Integration**:
- Compatibility results included in chat response (`compatibility_result` field)
- Displayed below agent response in chat interface
- Logged to browser console for debugging

**Viewing Compatibility Results**:
1. User asks compatibility question in chat
2. Agent detects compatibility query
3. Agent queries Neo4j knowledge graph
4. Compatibility result included in response
5. Frontend renders `CompatibilityResult` component

### Viewing the Knowledge Graph

**Neo4j Browser**:
1. Start Neo4j (see setup instructions above)
2. Open http://localhost:7474 in browser
3. Log in with Neo4j credentials
4. Run Cypher queries to explore the graph

**Example Queries**:

```cypher
// View all products
MATCH (p:PCProduct)
RETURN p
LIMIT 50

// Find compatible GPUs for a specific motherboard
MATCH (mb:PCProduct {slug: "asus-rog-strix-z790-e"})-[:INTERFACE_COMPATIBLE_WITH]-(gpu:PCProduct)
WHERE gpu.product_type = "gpu"
RETURN gpu.name, gpu.price_avg
ORDER BY gpu.price_avg ASC

// Check compatibility between two parts
MATCH (p1:PCProduct {slug: "intel-core-i9-13900k"})-[r]-(p2:PCProduct {slug: "asus-rog-strix-z790-e"})
RETURN type(r) AS relationship_type, p1.name, p2.name

// View all compatibility relationships
MATCH (p1:PCProduct)-[r]-(p2:PCProduct)
RETURN p1.name, type(r), p2.name
LIMIT 100
```

**Cypher Shell** (command line):
```bash
cypher-shell -u neo4j -p your-password
```

### Knowledge Graph Maintenance

**Backup**:
```bash
python scripts/kg/backup_kg.py \
    --backup \
    --namespace pc_parts \
    --output data/kg_backups/pc_parts_backup.json
```

**Restore**:
```bash
python scripts/kg/backup_kg.py \
    --restore \
    --namespace pc_parts \
    --input data/kg_backups/pc_parts_backup.json
```

**Updating the Graph**:
1. Add new products to `pc_parts.db`
2. Optionally scrape compatibility data for new products
3. Rebuild knowledge graph: `python scripts/kg/build_pc_parts_kg.py --purge`

### Troubleshooting

**Neo4j Connection Issues**:
- Verify Neo4j is running: `docker ps | grep neo4j` or `neo4j status`
- Check credentials in `.env` file
- Test connection: `cypher-shell -u neo4j -p your-password`
- Check firewall settings for port 7687

**Missing Compatibility Data**:
- Check cache: `sqlite3 data/compatibility_cache.db "SELECT COUNT(*) FROM product_attributes;"`
- Pre-scrape products: `python scripts/kg/scrape_compatibility_data.py ...`
- Enable scraping during build: `--enable-scraping` flag

**Compatibility Queries Not Working**:
- Verify knowledge graph is built: Check Neo4j for `PCProduct` nodes
- Check product slugs match between database and knowledge graph
- Verify compatibility relationships exist: Run Cypher queries in Neo4j Browser
- Check logs for Neo4j connection errors

**Performance Issues**:
- Index product slugs in Neo4j: `CREATE INDEX ON :PCProduct(slug)`
- Limit query results: Use `LIMIT` in Cypher queries
- Cache compatibility results: Consider caching frequently checked pairs

