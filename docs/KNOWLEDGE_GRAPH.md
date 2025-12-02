# Knowledge Graph Documentation

## Table of Contents

1. [Overview](#overview)
2. [Graph Structure and Design](#graph-structure-and-design)
3. [Prerequisites and Setup](#prerequisites-and-setup)
4. [Building the Knowledge Graph](#building-the-knowledge-graph)
5. [Compatibility Edge Types](#compatibility-edge-types)
6. [Data Sources and Scraping](#data-sources-and-scraping)
7. [Scripts and Functions Reference](#scripts-and-functions-reference)
8. [Querying the Graph](#querying-the-graph)
   - [Querying from Frontend](#querying-from-frontend)
   - [Bidirectional Graph Traversal](#bidirectional-graph-traversal)
   - [Agent Processing of Compatibility Queries](#agent-processing-of-compatibility-queries)
   - [Example Cypher Queries](#example-cypher-queries)
9. [Viewing and Managing the Graph](#viewing-and-managing-the-graph)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The knowledge graph system stores PC component products as nodes in Neo4j and creates typed compatibility relationships as edges. The system follows a simplified design where products are the only nodes, compatibility relationships are edges, and product attributes are stored as node properties. This structure enables efficient compatibility queries and intuitive graph navigation.

The system supports a three-step build process: creating nodes from database, scraping compatibility data from web sources, and updating the graph with scraped attributes. Compatibility data is cached in SQLite for reuse, and the system can operate in cached mode (default) or active scraping mode.

### Benefits of the Knowledge Graph Approach

The knowledge graph provides several key advantages over traditional database approaches for PC compatibility checking:

**1. Relationship-First Design**
- **Efficient Compatibility Queries**: Direct graph traversal allows O(1) compatibility lookups between products, rather than complex JOIN operations across multiple tables
- **Bidirectional Relationships**: Compatibility relationships are naturally bidirectional - finding compatible GPUs for a PSU is as efficient as finding compatible PSUs for a GPU
- **Multi-dimensional Compatibility**: Products can have multiple compatibility relationships (socket, PCIe, power, form factor) represented as separate edges, enabling nuanced compatibility checking

**2. Real-World Accuracy**
- **Web-Scraped Data**: Compatibility relationships are built from real product specifications scraped from manufacturer websites, Newegg, MicroCenter, and Wikipedia
- **Verified Attributes**: Product attributes (socket, PCIe version, wattage, etc.) are extracted from official sources, ensuring accuracy over heuristic parsing
- **Continuous Updates**: The scraping system can be updated to refresh compatibility data as new products are released

**3. Scalability and Performance**
- **Graph Database Optimization**: Neo4j is optimized for relationship traversal, making complex compatibility queries fast even with thousands of products
- **Cached Scraping**: Scraped data is cached in SQLite, allowing the system to build the graph quickly without re-scraping on every build
- **Incremental Updates**: New products can be added to the graph without rebuilding the entire structure

**4. Intelligent PC Building**
- **Complete Build Generation**: The graph enables building complete PC configurations by traversing compatibility relationships across all required components
- **Budget-Aware Selection**: Compatible parts can be filtered and ranked by price, enabling budget-constrained builds
- **Alternative Part Discovery**: Finding alternative compatible parts for any component in a build is a simple graph traversal operation

**5. Domain Knowledge Encapsulation**
- **Separation of Concerns**: PC part compatibility logic is encapsulated in the knowledge graph, separate from general product search
- **MCP Server Integration**: The graph can be exposed via MCP (Model Context Protocol) servers, allowing LLM agents to query compatibility without domain-specific code
- **Reusable Compatibility Engine**: The same compatibility checking logic can be used across different interfaces (web UI, API, CLI)

**6. Validation and Quality Assurance**
- **Automated Testing**: The graph structure enables automated validation of compatibility relationships against known-good configurations
- **Data Quality Metrics**: Scraping confidence scores and source attribution allow tracking data quality
- **Error Detection**: Inconsistent compatibility relationships can be detected through graph analysis

---

## Graph Structure and Design

### Design Philosophy

The knowledge graph has been designed with simplicity and efficiency in mind:

- **Products are the ONLY nodes** - Each product (CPU, GPU, motherboard, etc.) is a single node
- **Compatibility relationships are edges** - Compatibility between products is represented as typed edges
- **Attributes are properties** - Product attributes (product_type, brand, sellers, socket, PCIe version, etc.) are stored as properties on product nodes

This design eliminates the need for separate Attribute or Constraint nodes, making the graph simpler to query and understand.

### Node Structure

Each product is represented as a `PCProduct` node with labels `Product` and `PCProduct`:

```cypher
(:Product:PCProduct {
  slug: String                    // Unique identifier (e.g., "nvidia-rtx-4090")
  name: String                    // Full product name
  product_type: String            // cpu, gpu, motherboard, psu, ram, case, cooling
  brand: String                   // Manufacturer brand
  model: String                    // Model number
  sellers: List[String]           // List of sellers/stores
  price_min: Float                // Minimum price seen
  price_max: Float                // Maximum price seen
  price_avg: Float                // Average price
  namespace: String               // Namespace tag (e.g., "pc_parts")
  updated_at: Integer             // Timestamp of last update
  
  // Dynamic attributes (from parsing/scraping):
  socket: String                  // e.g., "LGA 1700", "AM5"
  pcie_version: String           // e.g., "PCIe:5.0", "PCIe:4.0"
  ram_standard: String           // e.g., "DDR5", "DDR4"
  wattage: String                // e.g., "850W"
  form_factor: String            // e.g., "ATX", "Micro-ATX"
  recommended_psu_watts: String // GPU power requirement
  tdp_watts: String             // CPU thermal design power
  supported_form_factors: List[String] // Case form factor support
  supported_sockets: List[String]     // Cooler socket support
  // ... and more attributes
})
```

### Edge Structure

Each compatibility type has its own relationship type. **Multiple relationship types can exist between the same two products**, representing different aspects of compatibility.

**ELECTRICAL_COMPATIBLE_WITH** (PSU → GPU):
```cypher
(:PCProduct)-[:ELECTRICAL_COMPATIBLE_WITH {
  margin_watts: Float      // PSU wattage - GPU requirement
  psu_watts: Float         // PSU wattage
  required_watts: Float    // GPU power requirement
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

**SOCKET_COMPATIBLE_WITH** (CPU → Motherboard):
```cypher
(:PCProduct)-[:SOCKET_COMPATIBLE_WITH {
  socket: String           // e.g., "LGA 1700"
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

**INTERFACE_COMPATIBLE_WITH** (Motherboard → GPU):
```cypher
(:PCProduct)-[:INTERFACE_COMPATIBLE_WITH {
  board_pcie: Float        // Motherboard PCIe version
  gpu_requirement: Float   // GPU PCIe requirement
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

**RAM_COMPATIBLE_WITH** (RAM → Motherboard):
```cypher
(:PCProduct)-[:RAM_COMPATIBLE_WITH {
  ram_standard: String     // e.g., "DDR5"
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

**FORM_FACTOR_COMPATIBLE_WITH** (Case → Motherboard):
```cypher
(:PCProduct)-[:FORM_FACTOR_COMPATIBLE_WITH {
  form_factor: String      // e.g., "ATX"
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

**MEMORY_COMPATIBLE_WITH** (CPU → RAM):
```cypher
(:PCProduct)-[:MEMORY_COMPATIBLE_WITH {
  ram_standard: String    // e.g., "DDR5"
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

**THERMAL_COMPATIBLE_WITH** (Cooler → CPU):
```cypher
(:PCProduct)-[:THERMAL_COMPATIBLE_WITH {
  cooler_support_watts: Float    // Cooler TDP capacity
  cpu_requirement_watts: Float   // CPU TDP requirement
  margin_watts: Float            // Capacity - requirement
  namespace: String
  updated_at: Integer
}]->(:PCProduct)
```

### Multiple Compatibility Types

Two products can have multiple compatibility edges representing different aspects. For example, a motherboard and GPU can have:
- `INTERFACE_COMPATIBLE_WITH` (PCIe version compatibility)
- And potentially other compatibility types if applicable

Each relationship type is independent - MERGE only merges relationships of the same type, so different types can coexist between the same products.

### Key Design Benefits

**Before (Previous Design)**:
- Separate `Attribute` nodes connected via `HAS_ATTRIBUTE` edges
- Separate `Constraint` nodes connected via `REQUIRES` edges
- Products connected to constraints via `SATISFIES` edges
- More complex graph structure with multiple node types

**After (Current Design)**:
- All attributes stored as properties on Product nodes
- Compatibility relationships are direct edges between Products
- Simpler, more intuitive structure
- Easier to query and understand
- Better performance for compatibility queries

---

## Prerequisites and Setup

### Starting Neo4j Server

#### Local Neo4j Installation

**Using Docker (Recommended)**:
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
1. Download Neo4j from https://neo4j.com/download/
2. Extract and run: `./bin/neo4j start`
3. Access Neo4j Browser at http://localhost:7474

**Verification**:
```bash
# Check if Neo4j is running
lsof -i :7687  # Bolt protocol port
lsof -i :7474  # HTTP port (Browser)

# Test connection
cypher-shell -u neo4j -p your-password
```

#### Neo4j Aura Cloud

**Creating an Aura Account**:
1. Navigate to https://console.neo4j.io/
2. Sign up with email or Google account
3. Verify email and accept Terms of Service

**Creating a Database Instance**:
1. In Aura Console, click "Create a Database"
2. Choose instance type (Free tier available)
3. Select region closest to your application
4. Set database name and password
5. Wait for provisioning (typically 2-3 minutes)

**Connection Details**:
After creation, Aura provides:
- **Connection URI**: `neo4j+s://xxxxx.databases.neo4j.io`
- **Username**: `neo4j` (default)
- **Password**: The password you set during creation

**Environment Variables**:
```bash
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password
```

**Accessing Neo4j Browser**:
1. Log in to Aura Console
2. Select your database instance
3. Click "Open with Neo4j Browser"
4. Enter password when prompted

### Python Dependencies

```bash
pip install -r requirements.txt

# Additional dependencies for PDF parsing (optional but recommended)
pip install pdfplumber PyPDF2

# For LLM extraction (optional)
pip install langchain-openai pydantic
```

### Data Files

Ensure you have the PC parts database:
- `data/pc_parts.db` - SQLite database with product data

### Environment Variables

Create a `.env` file in the project root:
```bash
# Neo4j Connection (required)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# PC Parts Database (optional, defaults to data/pc_parts.db)
PC_PARTS_DB=data/pc_parts.db

# OpenAI API Key (only needed if using LLM extraction)
OPENAI_API_KEY=your-openai-api-key-here
```

---

## Building the Knowledge Graph

### Build Process Overview

The knowledge graph builder has two modes for compatibility data:

1. **Cached mode (default)**: Uses previously scraped compatibility data from SQLite cache
2. **Scraping mode**: Actively scrapes new compatibility data (slower, requires `--enable-scraping`)

**Important**: The KG builder does NOT automatically scrape during build. It only uses cached data unless you explicitly enable scraping.

The knowledge graph is built in three steps:

1. **Step 1**: Create product nodes from `pc_parts.db` database
2. **Step 2**: Scrape compatibility data from web sources (optional)
3. **Step 3**: Update graph with scraped compatibility attributes

### Step 1: Create Nodes from Database

**Command**:
```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password \
    --namespace pc_parts \
    --step 1 \
    --purge
```

**What it does**:
- Loads products from SQLite database (`pc_parts.db`)
- Parses product names to extract attributes (socket, PCIe version, wattage, etc.)
- Creates `PCProduct` nodes in Neo4j with attributes as properties
- Creates compatibility edges based on parsed attributes
- Uses hardcoded metadata defaults for missing attributes

**Output**: Product nodes and compatibility edges created in Neo4j

**Time**: ~30 seconds - 2 minutes (depending on number of products)

### Step 2: Scrape Compatibility Data

**Command**:
```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --compatibility-db data/compatibility_cache.db \
    --step 2 \
    --limit 200 \
    --enable-scraping
```

**Or use the dedicated script**:
```bash
python scripts/kg/kg_step2_scrape.py \
    --db-path data/pc_parts.db \
    --compatibility-db data/compatibility_cache.db \
    --limit 200 \
    --delay 2.0
```

**With LLM extraction (optional, requires OpenAI API key)**:
```bash
python scripts/kg/kg_step2_scrape.py \
    --db-path data/pc_parts.db \
    --compatibility-db data/compatibility_cache.db \
    --use-llm \
    --limit 200 \
    --delay 2.0
```

**What it does**:
- Reads products from database
- Scrapes compatibility data from multiple sources:
  - Newegg product pages
  - MicroCenter product pages
  - Wikipedia technical specifications
  - Manufacturer documentation (PDFs and web pages)
- Extracts product attributes (socket, PCIe version, RAM standard, wattage, etc.)
- Caches scraped data in `compatibility_cache.db` SQLite database
- Uses LLM extraction (optional) for structured attribute parsing
- Skips products that are already cached

**Output**: Scraped compatibility data cached in `compatibility_cache.db`

**Time**: ~2-5 minutes per product (with rate limiting)
- For 200 products: ~7-17 hours (can be interrupted and resumed)
- Already cached products are skipped instantly

**Tips**:
- Can be interrupted and resumed (cached products are skipped)
- Use `--limit` to test with fewer products first
- Use `--delay` to adjust rate limiting (default 2 seconds)
- Check logs to see progress

### Step 3: Update Graph with Scraped Data

**Command**:
```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password \
    --namespace pc_parts \
    --compatibility-db data/compatibility_cache.db \
    --step 3
```

**What it does**:
- Loads cached scraped data from `compatibility_cache.db`
- Updates existing product nodes with scraped attributes
- Rebuilds compatibility edges using improved attribute data
- Replaces default values with verified specifications

**Output**: Updated Neo4j graph with enhanced compatibility data

**Time**: ~30 seconds - 2 minutes

### How Scraping Works

**Default Behavior (Without `--enable-scraping`)**:
1. KG builder initializes `CompatibilityScraper` with cache-only mode
2. For each product, checks `compatibility_cache.db` for cached attributes
3. Uses cached data if available
4. If no cache exists, product is built without scraped attributes (uses only parsed attributes)

**With `--enable-scraping`**:
1. KG builder initializes `CompatibilityScraper` with scraping enabled
2. For each product:
   - Checks cache first
   - If not cached, scrapes from configured sources (Newegg, MicroCenter, Wikipedia, Manufacturer)
   - Caches results for future use
   - Uses scraped attributes in KG

**Note**: Active scraping during build is slower. It's recommended to pre-scrape data separately.

### Data Flow

```
┌─────────────────┐
│  pc_parts.db    │  ← Product data (names, prices, sellers)
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ build_pc_parts_kg.py    │
└────────┬─────────────────┘
         │
         ├──► Parse products from DB
         │
         ├──► CompatibilityScraper (optional)
         │    ├──► Check cache (compatibility_cache.db)
         │    └──► Scrape if --enable-scraping (Newegg, Wikipedia, etc.)
         │
         └──► Create Neo4j Graph
              ├──► Product nodes (with attributes as properties)
              └──► Compatibility edges
```

### Backup and Restore

Before running Step 2 (which can take hours), you can backup your Step 1 graph:

**Backup Step 1 Graph**:
```bash
python scripts/kg/backup_kg.py backup \
    --namespace pc_parts \
    --output data/kg_backups/step1_backup.json
```

This saves all nodes and relationships to a JSON file.

**Restore Step 1 Graph**:
```bash
python scripts/kg/backup_kg.py restore \
    --backup-file data/kg_backups/step1_backup.json \
    --namespace pc_parts \
    --purge
```

This restores the graph from the backup file (and purges any corrupted data).

### Complete Build Workflow

**Option 1: Sequential Steps**:
```bash
# Step 1: Create nodes
python scripts/kg/build_pc_parts_kg.py --step 1 --purge

# Step 2: Scrape data (can take hours for full dataset)
python scripts/kg/build_pc_parts_kg.py --step 2 --use-llm

# Step 3: Update graph
python scripts/kg/build_pc_parts_kg.py --step 3
```

**Option 2: Single Command (Steps 1 and 3)**:
```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password \
    --namespace pc_parts \
    --compatibility-db data/compatibility_cache.db \
    --purge
```

This runs Step 1 (create nodes) and Step 3 (update with cached scraped data) in one command.

**Complete Workflow Example**:
```bash
# Step 1: Create nodes (fast)
python scripts/kg/build_pc_parts_kg.py --step 1 --purge --limit 200

# Step 2: Scrape data (slow - can run overnight)
# Run this in a screen/tmux session so it can run in background
python scripts/kg/kg_step2_scrape.py --limit 200 --delay 2.0

# Step 3: Update graph (fast)
python scripts/kg/build_pc_parts_kg.py --step 3 --limit 200
```

### Incremental Updates

**Add More Products**:
```bash
# Step 1: Add new products to graph
python scripts/kg/build_pc_parts_kg.py --step 1 --limit 500

# Step 2: Scrape only new products (cached ones are skipped)
python scripts/kg/kg_step2_scrape.py --limit 500

# Step 3: Update graph with new scraped data
python scripts/kg/build_pc_parts_kg.py --step 3 --limit 500
```

**Re-scrape Specific Products**:
```bash
# Delete cached data for specific products
sqlite3 data/compatibility_cache.db "DELETE FROM product_attributes WHERE product_slug='nvidia-rtx-4090';"

# Re-scrape
python scripts/kg/kg_step2_scrape.py --limit 1
```

### Monitoring Progress

**Check Scraping Progress**:
```bash
# Count cached products
sqlite3 data/compatibility_cache.db "SELECT COUNT(DISTINCT product_slug) FROM product_attributes;"

# List scraped products
sqlite3 data/compatibility_cache.db "SELECT DISTINCT product_slug FROM product_attributes LIMIT 10;"
```

**Check Neo4j Graph**:
```bash
# Access Neo4j Browser
open http://localhost:7474

# Or use cypher-shell
cypher-shell -u neo4j -p password
```

Example queries:
```cypher
// Count products
MATCH (p:PCProduct) RETURN count(p);

// View a product with attributes
MATCH (p:PCProduct {slug: "nvidia-rtx-4090"}) RETURN p;

// View compatibility relationships
MATCH (a:PCProduct)-[r]-(b:PCProduct)
WHERE type(r) CONTAINS "COMPATIBLE"
RETURN a.name, type(r), b.name
LIMIT 10;
```

---

## Compatibility Edge Types

The knowledge graph builds compatibility edges based on these attributes:

### 1. **ELECTRICAL_COMPATIBLE_WITH** (PSU → GPU)
- **Required attributes:**
  - PSU: `wattage` (e.g., "750W")
  - GPU: `recommended_psu_watts` (e.g., "650W")
- **Wikipedia provides:** TDP/wattage information from product specifications
- **Impact:** More accurate PSU sizing recommendations
- **Edge properties:** `margin_watts`, `psu_watts`, `required_watts`

### 2. **INTERFACE_COMPATIBLE_WITH** (Motherboard → GPU)
- **Required attributes:**
  - Motherboard: `pcie_version` (e.g., "4.0")
  - GPU: `pcie_requirement` (e.g., "4.0")
- **Wikipedia provides:** PCIe version from technical specifications
- **Impact:** Ensures GPU/motherboard PCIe compatibility
- **Edge properties:** `board_pcie`, `gpu_requirement`

### 3. **SOCKET_COMPATIBLE_WITH** (CPU → Motherboard)
- **Required attributes:**
  - CPU: `socket` (e.g., "AM5", "LGA 1700")
  - Motherboard: `socket` (e.g., "AM5", "LGA 1700")
- **Wikipedia provides:** Socket information from CPU/motherboard specs
- **Impact:** Critical for CPU/motherboard compatibility
- **Edge properties:** `socket`

### 4. **RAM_COMPATIBLE_WITH** (RAM → Motherboard)
- **Required attributes:**
  - RAM: `ram_standard` (e.g., "DDR5", "DDR4")
  - Motherboard: `ram_standard` (e.g., "DDR5", "DDR4")
- **Wikipedia provides:** Memory type/standard from specifications
- **Impact:** Ensures RAM/motherboard compatibility
- **Edge properties:** `ram_standard`

### 5. **MEMORY_COMPATIBLE_WITH** (CPU → RAM)
- **Required attributes:**
  - CPU: `ram_standard` (e.g., "DDR5")
  - RAM: `ram_standard` (e.g., "DDR5")
- **Wikipedia provides:** CPU memory controller specifications
- **Impact:** Ensures CPU/RAM compatibility
- **Edge properties:** `ram_standard`

### 6. **FORM_FACTOR_COMPATIBLE_WITH** (Case → Motherboard)
- **Required attributes:**
  - Case: `supported_form_factors` (e.g., ["ATX", "mATX"])
  - Motherboard: `form_factor` (e.g., "ATX")
- **Wikipedia provides:** Form factor information
- **Impact:** Ensures case/motherboard physical compatibility
- **Edge properties:** `form_factor`

### 7. **THERMAL_COMPATIBLE_WITH** (Cooler → CPU)
- **Required attributes:**
  - Cooler: `supported_sockets` (e.g., ["AM5", "LGA 1700"])
  - CPU: `socket` (e.g., "AM5")
  - CPU: `tdp_watts` (e.g., "105W")
  - Cooler: `max_tdp` (e.g., "150W")
- **Wikipedia provides:** TDP information and socket compatibility
- **Impact:** Ensures cooler can handle CPU thermal load
- **Edge properties:** `cooler_support_watts`, `cpu_requirement_watts`, `margin_watts`

---

## Data Sources and Scraping

### Scraping Sources

The `scripts/kg/scrape_compatibility_data.py` script scrapes compatibility information from:

- **Newegg** - Product specifications and compatibility information
- **MicroCenter** - Product specifications and technical details
- **Wikipedia** - Technical specifications from infoboxes and specification sections
- **Manufacturer Official Documentation** - Product pages and PDF manuals/specifications

### Manufacturer Documentation Scraping

Manufacturer documentation scraping provides high-quality compatibility data:

- Automatically finds manufacturer product pages based on brand name
- Downloads and parses PDF manuals/specifications
- Extracts compatibility information from official documentation
- High confidence scores (0.95-0.98) for official sources
- Supports major manufacturers: NVIDIA, AMD, Intel, ASUS, MSI, Gigabyte, Corsair, etc.

**Usage**:
```bash
# Scrape only manufacturer official documentation
python scripts/kg/scrape_compatibility_data.py \
    --product-name "ASUS ROG Strix Z790-E" \
    --product-slug "asus-rog-strix-z790-e" \
    --brand "ASUS" \
    --sellers manufacturer
```

### LLM-Based Extraction

LLM-based extraction uses OpenAI models for structured attribute parsing:

- Uses GPT-4o-mini (or other OpenAI models) for structured extraction
- Better at handling unstructured text than regex patterns
- Uses Pydantic models with JSON schema to prevent hallucinations
- Extracts both product attributes and compatibility relationships
- Falls back to regex parsing if LLM is unavailable or fails
- Caches extractions to avoid redundant API calls

**Usage**:
```bash
# Use LLM-based extraction for better accuracy
python scripts/kg/scrape_compatibility_data.py \
    --product-name "NVIDIA RTX 4090" \
    --product-slug "nvidia-rtx-4090" \
    --brand "NVIDIA" \
    --use-llm \
    --sellers manufacturer
```

### Caching

Scraped data is cached in SQLite database (`data/compatibility_cache.db`) for reuse:

- `compatibility_facts` - Compatibility relationships between products
- `product_attributes` - Scraped product attributes
- `scrape_cache` - URLs already scraped (prevents duplicate work)

Cached products are automatically skipped during scraping, allowing interrupted processes to resume efficiently.

### Attribute Normalization

The `scripts/kg/normalize_attributes.py` module normalizes attributes from various sources to canonical forms:

- `PCIE_5`, `PCIE5`, `pcie-v5` → `PCIe:5.0`
- `DDR4`, `ddr4`, `DDR-4` → `DDR4`
- `LGA1700`, `LGA 1700`, `lga-1700` → `LGA 1700`
- And more normalization patterns for consistent attribute values

### What Wikipedia Provides

From Wikipedia infoboxes and specification sections, we extract:

- **PCIe version** (`pcie_version`) - for GPU/motherboard compatibility
- **TDP/Wattage** (`wattage`, `tdp_watts`) - for PSU/GPU and cooler/CPU compatibility  
- **Socket** (`socket`) - for CPU/motherboard and cooler/CPU compatibility
- **RAM standard** (`ram_standard`) - for motherboard/RAM and CPU/RAM compatibility
- **Form factor** (`form_factor`) - for case/motherboard compatibility
- **Architecture** (`architecture`) - useful for identification and grouping
- **Codename** (`codename`) - useful for product identification

### Impact of Scraping

Wikipedia scraping **significantly improves compatibility accuracy** by:
1. **Replacing defaults** with verified specifications
2. **Filling missing attributes** that weren't in product names
3. **Correcting errors** from heuristic parsing
4. **Adding edge cases** not covered by hardcoded metadata

The improved normalization achieves a 71% extraction rate.

---

## Scripts and Functions Reference

### `build_pc_parts_kg.py`

Main script for building the knowledge graph. Orchestrates loading, parsing, and Neo4j persistence.

#### Key Functions

**`load_components(conn: sqlite3.Connection, limit: Optional[int]) -> Dict[str, List[ComponentRecord]]`**

Loads products from SQLite database and consolidates into component records.

**Parameters**:
- `conn`: SQLite database connection
- `limit`: Maximum rows per component type (None for all)

**Returns**: Dictionary mapping component types to lists of `ComponentRecord` objects

**Usage**:
```python
import sqlite3
from scripts.kg.build_pc_parts_kg import load_components

conn = sqlite3.connect("data/pc_parts.db")
components = load_components(conn, limit=200)
conn.close()
```

**`upsert_components(driver, namespace: str, components: Sequence[ComponentRecord], scraper: Optional[CompatibilityScraper] = None) -> None`**

Creates or updates product nodes in Neo4j with all attributes as properties.

**Parameters**:
- `driver`: Neo4j driver instance
- `namespace`: Namespace tag for nodes (e.g., "pc_parts")
- `components`: List of `ComponentRecord` objects
- `scraper`: Optional scraper for cached scraped attributes

**Cypher Query**:
```cypher
UNWIND $rows AS row
MERGE (p:Product:PCProduct {slug: row.slug, namespace: $namespace})
SET
    p.name = row.name,
    p.product_type = row.product_type,
    p.brand = row.brand,
    p.model = row.model,
    p.sellers = row.sellers,
    p.price_min = row.price_min,
    p.price_max = row.price_max,
    p.price_avg = row.price_avg,
    p.updated_at = timestamp()
WITH p, row, keys(row) AS keys, $excluded_keys AS excluded
UNWIND keys AS key
WITH p, row, key, excluded
WHERE NOT key IN excluded
SET p[key] = row[key]
```

**Usage**:
```python
from neo4j import GraphDatabase
from scripts.kg.build_pc_parts_kg import upsert_components, ensure_driver

driver = ensure_driver("bolt://localhost:7687", "neo4j", "password")
components = [...]  # List of ComponentRecord objects
upsert_components(driver, "pc_parts", components)
driver.close()
```

**`upsert_compatibility_edges(driver, namespace: str, edge_specs: Sequence[Dict[str, Any]]) -> None`**

Creates typed compatibility edges between product nodes.

**Parameters**:
- `driver`: Neo4j driver instance
- `namespace`: Namespace tag for edges
- `edge_specs`: List of edge specifications, each with:
  - `type`: Relationship type (e.g., "ELECTRICAL_COMPATIBLE_WITH")
  - `edges`: List of edge dictionaries with `from`, `to`, and `props` keys

**Edge Dictionary Format**:
```python
{
    "from": "product-slug-1",
    "to": "product-slug-2",
    "props": {
        "margin_watts": 150.0,
        "psu_watts": 850.0,
        "required_watts": 700.0
    }
}
```

**Cypher Query**:
```cypher
UNWIND $rows AS row
MATCH (a:PCProduct {slug: row.from, namespace: $namespace})
MATCH (b:PCProduct {slug: row.to, namespace: $namespace})
MERGE (a)-[rel:ELECTRICAL_COMPATIBLE_WITH {namespace: $namespace}]->(b)
SET
    rel.updated_at = timestamp()
SET rel += row.props
```

**Usage**:
```python
from scripts.kg.build_pc_parts_kg import upsert_compatibility_edges

edge_specs = [
    {
        "type": "ELECTRICAL_COMPATIBLE_WITH",
        "edges": [
            {
                "from": "corsair-rm850x",
                "to": "nvidia-rtx-4090",
                "props": {"margin_watts": 150.0, "psu_watts": 850.0, "required_watts": 700.0}
            }
        ]
    }
]
upsert_compatibility_edges(driver, "pc_parts", edge_specs)
```

**Edge Building Functions**:

**`build_electrical_edges(psus: Sequence[ComponentRecord], gpus: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates electrical compatibility edges between PSUs and GPUs based on wattage requirements.

**Parameters**:
- `psus`: List of PSU component records
- `gpus`: List of GPU component records

**Returns**: List of edge dictionaries

**Logic**:
- Checks PSU wattage >= GPU requirement + 50W margin
- Validates realistic wattage ranges (350W-2000W for PSUs, 350W-850W for GPUs)
- Skips GPUs with inferred/default series metadata

**`build_interface_edges(motherboards: Sequence[ComponentRecord], gpus: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates PCIe interface compatibility edges between motherboards and GPUs.

**Logic**:
- Checks motherboard PCIe version >= GPU requirement
- Validates PCIe versions (3.0-5.0 for motherboards, 3.0-4.0 for GPUs)
- Skips default PCIe values when chipset is missing

**`build_socket_edges(cpus: Sequence[ComponentRecord], motherboards: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates socket compatibility edges between CPUs and motherboards.

**Logic**:
- Matches CPU socket to motherboard socket (case-insensitive)
- Requires exact socket match

**`build_ram_edges(rams: Sequence[ComponentRecord], motherboards: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates RAM standard compatibility edges between RAM modules and motherboards.

**Logic**:
- Matches RAM DDR standard to motherboard DDR standard

**`build_case_motherboard_edges(cases: Sequence[ComponentRecord], motherboards: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates form factor compatibility edges between cases and motherboards.

**Logic**:
- Checks if motherboard form factor is in case's supported form factors list

**`build_cpu_ram_edges(cpus: Sequence[ComponentRecord], rams: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates memory controller compatibility edges between CPUs and RAM.

**Logic**:
- Matches CPU RAM standard to RAM module standard

**`build_cooling_edges(coolers: Sequence[ComponentRecord], cpus: Sequence[ComponentRecord]) -> List[Dict[str, Any]]`**

Creates thermal compatibility edges between CPU coolers and CPUs.

**Logic**:
- Checks cooler TDP support >= CPU TDP requirement
- Verifies CPU socket is in cooler's supported sockets list

**`purge_namespace(driver, namespace: str) -> None`**

Deletes all nodes and relationships for a given namespace.

**Cypher Query**:
```cypher
MATCH (n {namespace: $namespace})
DETACH DELETE n
```

**Usage**:
```python
from scripts.kg.build_pc_parts_kg import purge_namespace, ensure_driver

driver = ensure_driver("bolt://localhost:7687", "neo4j", "password")
purge_namespace(driver, "pc_parts")
driver.close()
```

### `scrape_compatibility_data.py`

Scrapes compatibility data from web sources and caches in SQLite database.

#### Key Classes and Functions

**`CompatibilityScraper`**

Main scraper class for extracting compatibility data.

**Initialization**:
```python
from scripts.kg.scrape_compatibility_data import CompatibilityScraper

scraper = CompatibilityScraper(
    db_path="data/compatibility_cache.db",
    use_llm=False  # Set True for LLM extraction (requires OpenAI API key)
)
```

**`scrape_product(product_name: str, product_slug: str, sellers: List[str], brand: Optional[str] = None) -> List[ProductAttribute]`**

Scrapes compatibility attributes for a single product.

**Parameters**:
- `product_name`: Full product name
- `product_slug`: Product slug identifier
- `sellers`: List of seller sources ("newegg", "microcenter", "wikipedia", "manufacturer")
- `brand`: Optional brand name

**Returns**: List of `ProductAttribute` objects

**Usage**:
```python
attributes = scraper.scrape_product(
    product_name="NVIDIA RTX 4090",
    product_slug="nvidia-rtx-4090",
    sellers=["newegg", "wikipedia", "manufacturer"],
    brand="NVIDIA"
)
```

**`get_cached_attributes(product_slug: str) -> List[ProductAttribute]`**

Retrieves cached attributes from database.

**Parameters**:
- `product_slug`: Product slug identifier

**Returns**: List of cached `ProductAttribute` objects

**Usage**:
```python
cached = scraper.get_cached_attributes("nvidia-rtx-4090")
```

### `normalize_attributes.py`

Normalizes product attributes to canonical forms.

#### Key Functions

**`normalize_attribute_value(key: str, value: str) -> Optional[str]`**

Normalizes an attribute value based on its type.

**Parameters**:
- `key`: Attribute type (e.g., "socket", "pcie_version", "ram_standard")
- `value`: Raw attribute value

**Returns**: Normalized value or None

**Supported Attributes**:
- `socket`: Normalizes to format "LGA 1700", "AM5", "sTR5"
- `pcie_version`: Normalizes to format "PCIe:5.0", "PCIe:4.0"
- `ram_standard`: Normalizes to format "DDR4", "DDR5"
- `wattage`: Normalizes to format "850W"
- `form_factor`: Normalizes to format "ATX", "Micro-ATX", "Mini-ITX"

**Usage**:
```python
from scripts.kg.normalize_attributes import normalize_attribute_value

normalized = normalize_attribute_value("socket", "LGA1700")
# Returns: "LGA 1700"

normalized = normalize_attribute_value("pcie_version", "PCIe 5.0")
# Returns: "PCIe:5.0"
```

### `llm_extractor.py`

LLM-based extraction for structured attribute parsing.

#### Key Classes

**`LLMExtractor`**

Uses OpenAI models to extract structured product data from unstructured text.

**Initialization**:
```python
from scripts.kg.llm_extractor import LLMExtractor

extractor = LLMExtractor(
    model_name="gpt-4o-mini",  # Cost-efficient model
    temperature=0.0,  # Deterministic output
    use_cache=True  # Cache extractions
)
```

**`extract_from_text(text: str, product_context: Optional[Dict[str, Any]] = None) -> ExtractedProductData`**

Extracts product attributes and compatibility relationships from text.

**Parameters**:
- `text`: Unstructured text (HTML, PDF content, etc.)
- `product_context`: Optional product context dictionary

**Returns**: `ExtractedProductData` object with attributes and relationships

**Usage**:
```python
extracted = extractor.extract_from_text(
    text="<HTML content from product page>",
    product_context={"name": "NVIDIA RTX 4090", "brand": "NVIDIA"}
)
```

### `kg_step2_scrape.py`

Standalone script for Step 2 scraping process.

**Function**: `scrape_all_products(components: List[ComponentRecord], compatibility_db: str, use_llm: bool, limit: Optional[int], delay_between_products: float) -> None`

Scrapes compatibility data for all products in batch.

**Usage**:
```python
from scripts.kg.kg_step2_scrape import scrape_all_products
from scripts.kg.build_pc_parts_kg import load_components
import sqlite3

conn = sqlite3.connect("data/pc_parts.db")
components_dict = load_components(conn, limit=None)
all_components = [comp for comp_list in components_dict.values() for comp in comp_list]
conn.close()

scrape_all_products(
    components=all_components,
    compatibility_db="data/compatibility_cache.db",
    use_llm=True,
    limit=100,  # Limit for testing
    delay_between_products=2.0  # Rate limiting
)
```

---

## Querying the Graph

### Querying from Frontend

The frontend does not directly query Neo4j. Instead, compatibility queries flow through the backend agent system.

#### Query Flow

1. **User Input**: User asks compatibility question in chat interface
2. **Frontend API**: Message sent to `/api/chat/stream` endpoint
3. **Backend Processing**: Agent system processes message
4. **Compatibility Detection**: Keyword detection (`_should_attempt_compatibility()`) and LLM-based detection identify compatibility query
5. **Neo4j Query**: LLM calls `Neo4jCompatibilityTool` methods (via tools) to query Neo4j knowledge graph
6. **Response**: Compatibility result included in agent response
7. **Frontend Display**: `CompatibilityResult` component renders result

#### Backend Query Functions

**Location**: `idss_agent/tools/kg_compatibility.py`

**`Neo4jCompatibilityTool.check_compatibility(part1_slug: str, part2_slug: str, compatibility_types: Optional[List[str]] = None) -> Dict[str, Any]`**

Checks if two parts are compatible.

**Cypher Query**:
```cypher
MATCH (p1:PCProduct {slug: $slug1})
MATCH (p2:PCProduct {slug: $slug2})
RETURN p1.product_type AS type1, p2.product_type AS type2, p1.name AS name1, p2.name AS name2

MATCH (p1:PCProduct {slug: $slug1})-[r:ELECTRICAL_COMPATIBLE_WITH]-(p2:PCProduct {slug: $slug2})
RETURN r
LIMIT 1
```

**Returns**:
```python
{
    "compatible": True,
    "compatibility_types": ["ELECTRICAL_COMPATIBLE_WITH"],
    "explanation": "NVIDIA RTX 4090 is compatible with Corsair RM850x. They are compatible via power supply compatibility.",
    "part1_name": "NVIDIA RTX 4090",
    "part2_name": "Corsair RM850x"
}
```

**`Neo4jCompatibilityTool.find_compatible_parts(source_slug: str, target_type: str, compatibility_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]`**

Finds parts compatible with a source part.

**Cypher Query**:
```cypher
MATCH (source:PCProduct {slug: $slug})-[r:ELECTRICAL_COMPATIBLE_WITH]-(target:PCProduct)
WHERE target.product_type = $target_type
RETURN target, r
ORDER BY target.price_avg ASC
LIMIT $limit
```

**Returns**: List of compatible product dictionaries

**`Neo4jCompatibilityTool.find_product_by_name(product_name: str, product_type: Optional[str] = None) -> Optional[Dict[str, Any]]`**

Finds a product by name using fuzzy matching.

**Cypher Query**:
```cypher
MATCH (p:PCProduct {slug: $slug})
RETURN p
LIMIT 1

MATCH (p:PCProduct)
WHERE toLower(p.name) CONTAINS toLower($name)
   OR toLower(p.slug) CONTAINS toLower($name)
RETURN p
ORDER BY p.name
LIMIT 5
```

#### Frontend Response Handling

**Component**: `web/src/components/CompatibilityResult.tsx`

**Props**:
```typescript
interface CompatibilityResultProps {
  result: {
    compatible: boolean;
    explanation: string;
    part1_name?: string;
    part2_name?: string;
    compatibility_types?: string[];
    error?: string;
  };
}
```

**Display**: Renders compatibility status with visual indicators (green for compatible, red for incompatible) and explanation text.

### Bidirectional Graph Traversal

The knowledge graph implements bidirectional traversal to simulate bidirectionality for compatibility relationships. This allows queries to work regardless of the direction edges are stored in the graph (e.g., finding compatible PSUs for a GPU even if edges are stored as GPU→PSU or PSU→GPU).

#### Implementation Details

**Location**: `idss_agent/tools/kg_compatibility.py`

The bidirectional traversal is implemented through three mechanisms:

**1. Reverse Direction Type Mapping** (lines 195-201, 295-305)

When determining which compatibility type to check, the code tries both directions:

```python
# Determine compatibility types to check
# Check both directions since compatibility is symmetric
if not compatibility_types:
    key = (type1, type2)
    compatibility_types = PART_COMPATIBILITY_MAP.get(key, [])
    # Try reverse direction if not found
    if not compatibility_types:
        key = (type2, type1)
        compatibility_types = PART_COMPATIBILITY_MAP.get(key, [])
```

Similarly, when finding compatible parts (lines 295-305):

```python
# Determine compatibility type if not provided
# Check both (source_type, target_type) and (target_type, source_type) since compatibility is symmetric
if not compatibility_type:
    key = (source_type, target_type)
    types = PART_COMPATIBILITY_MAP.get(key, [])
    if not types:
        # Try reverse direction
        key = (target_type, source_type)
        types = PART_COMPATIBILITY_MAP.get(key, [])
```

**2. Bidirectional Relationship Matching in Cypher** (lines 209-227, 310-316)

The Cypher queries use undirected relationship syntax `-[r:REL_TYPE]-` (without arrow direction) to match edges in both directions:

```python
# Check each compatibility type (bidirectional - compatibility is symmetric)
for rel_type in compatibility_types:
    # Check both directions since compatibility is symmetric
    query = f"""
        MATCH (p1:PCProduct {{slug: $slug1}})-[r:{rel_type}]-(p2:PCProduct {{slug: $slug2}})
        RETURN r
        LIMIT 1
    """
```

And for finding compatible parts (lines 310-316):

```python
# Query compatible parts (bidirectional - check both directions)
# First try: source -> target (normal direction)
# Second try: target -> source (reverse direction, since compatibility is symmetric)
query = f"""
    MATCH (source:PCProduct {{slug: $slug}})-[r:{compatibility_type}]-(target:PCProduct)
    WHERE target.product_type = $target_type
    RETURN target, r
    ORDER BY target.price_avg ASC
    LIMIT $limit
"""
```

**3. Bidirectional Compatibility Mapping** (lines 32-49)

The `PART_COMPATIBILITY_MAP` explicitly defines compatibility types for both directions:

```python
PART_COMPATIBILITY_MAP = {
    ("cpu", "motherboard"): ["SOCKET_COMPATIBLE_WITH"],
    ("motherboard", "cpu"): ["SOCKET_COMPATIBLE_WITH"],
    ("gpu", "psu"): ["ELECTRICAL_COMPATIBLE_WITH"],
    ("psu", "gpu"): ["ELECTRICAL_COMPATIBLE_WITH"],
    # ... more bidirectional mappings
}
```

#### Example: Finding Compatible PSUs for a GPU

When querying for compatible PSUs for a GPU:

1. **Type Mapping**: The system checks `(gpu, psu)` first, then `(psu, gpu)` if needed (lines 295-305)
2. **Cypher Query**: Uses undirected relationship `-[r:ELECTRICAL_COMPATIBLE_WITH]-` to match edges in either direction (line 311)
3. **Result**: Returns compatible PSUs regardless of whether edges are stored as GPU→PSU or PSU→GPU

This design ensures that compatibility queries work symmetrically, allowing users to find compatible parts in either direction (e.g., "What PSUs work with my GPU?" or "What GPUs work with my PSU?").

### Agent Processing of Compatibility Queries

The agent system processes compatibility queries through a multi-stage pipeline that detects, classifies, and handles compatibility-related user requests.

#### Architecture Overview

**Key Components**:

1. **Compatibility Detection** (`idss_agent/agents/analytical.py` - keyword detection + LLM-based detection)
2. **Compatibility Helper Functions** (`idss_agent/processing/compatibility.py` - wrapper functions for tool calls)
3. **Knowledge Graph Tool** (`idss_agent/tools/kg_compatibility.py` - Neo4j query interface)
4. **Agent Integration** (`idss_agent/agents/analytical.py` - ReAct agent with compatibility tools)

#### Query Detection and Classification

Compatibility queries are detected using a combination of keyword detection and LLM-based detection, similar to comparison queries.

**Location**: `idss_agent/agents/analytical.py`

**`_should_attempt_compatibility()`** (lines 1101-1119)

Detects if a user query is about compatibility by checking for keywords:

```python
def _should_attempt_compatibility(user_input: str) -> bool:
    """
    Check if user input suggests a compatibility query using keyword detection.
    
    Args:
        user_input: User's query text
        
    Returns:
        True if query contains compatibility-related keywords
    """
    if not user_input:
        return False
    lowered = user_input.lower()
    compatibility_keywords = [
        "compatible", "compatibility", "works with", "fits", "supports",
        "will work", "can i use", "does it work", "compatible with",
        "work with", "compatible for"
    ]
    return any(keyword in lowered for keyword in compatibility_keywords)
```

**LLM-Based Detection** (`analytical.py:269-296`)

The analytical agent prompt includes explicit instructions for detecting and handling compatibility queries:

- Detects compatibility intent from natural language
- Extracts product names from the query
- Calls appropriate compatibility tools (`check_parts_compatibility` or `find_compatible_parts`)
- Formats results appropriately

The LLM is instructed to:
- **Binary compatibility check** ("Is X compatible with Y?"): Use `check_parts_compatibility` tool
- **Compatibility recommendations** ("What GPUs are compatible with my PSU?"): Use `find_compatible_parts` tool
- Extract product names and part types from the query
- Handle errors gracefully with user-friendly messages

#### Knowledge Graph Querying

**Location**: `idss_agent/tools/kg_compatibility.py`

**`Neo4jCompatibilityTool.check_compatibility()`** (lines 149-256)

Performs binary compatibility checks between two parts:

```python
def check_compatibility(
    self, 
    part1_slug: str, 
    part2_slug: str, 
    compatibility_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    # Get product types
    # Determine compatibility types to check (with reverse direction fallback)
    # Query Neo4j with bidirectional relationship matching
    # Return compatibility result with explanation
```

**Key Implementation** (lines 195-227):
- Checks both `(type1, type2)` and `(type2, type1)` for compatibility type mapping
- Uses bidirectional Cypher pattern `-[r:REL_TYPE]-` to match edges in both directions
- Returns structured result with compatibility status, types, and explanation

**`Neo4jCompatibilityTool.find_compatible_parts()`** (lines 258-335)

Finds compatible parts for a given source part:

```python
def find_compatible_parts(
    self,
    source_slug: str,
    target_type: str,
    compatibility_type: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    # Get source product type
    # Determine compatibility type (with reverse direction fallback)
    # Query Neo4j with bidirectional relationship matching
    # Return list of compatible products
```

**Key Implementation** (lines 295-316):
- Checks both `(source_type, target_type)` and `(target_type, source_type)` for type mapping
- Uses bidirectional Cypher query to find compatible parts regardless of edge direction
- Orders results by price and returns top matches

#### Helper Functions

**Location**: `idss_agent/processing/compatibility.py`

**`check_compatibility_binary()`** (lines 14-28)

Wrapper function for binary compatibility checks:

```python
def check_compatibility_binary(
    part1_slug: str,
    part2_slug: str,
    compatibility_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    tool = get_compatibility_tool()
    if not tool.is_available():
        return {"compatible": False, "error": "Compatibility checking unavailable"}
    result = tool.check_compatibility(part1_slug, part2_slug, compatibility_types)
    return result
```

**`find_compatible_parts_recommendations()`** (lines 30-53)

Wrapper function for finding compatible parts with reranking:

```python
def find_compatible_parts_recommendations(
    source_slug: str,
    target_type: str,
    compatibility_type: Optional[str] = None,
    limit: int = 3
) -> List[Dict[str, Any]]:
    tool = get_compatibility_tool()
    candidates = tool.find_compatible_parts(source_slug, target_type, compatibility_type, limit=50)
    # Simple reranking: by price (ascending), then by name
    candidates.sort(key=lambda x: (
        x.get("price_avg") or x.get("price_min") or float('inf'),
        x.get("name", "")
    ))
    return candidates[:limit]
```

**`format_compatibility_recommendations_table()`** (lines 56-143)

Formats compatible products as a comparison table for display:

```python
def format_compatibility_recommendations_table(
    products: List[Dict[str, Any]],
    source_product_name: str
) -> ComparisonTable:
    # Build headers and rows with product attributes
    # Include type-specific attributes (PCIe version for GPUs, socket for CPUs, etc.)
    return ComparisonTable(headers=headers, rows=rows)
```

#### Agent Integration

**Location**: `idss_agent/agents/analytical.py`

The analytical agent integrates compatibility checking into its workflow. When processing user queries:

1. **Query Analysis**: The agent analyzes the user's intent and extracts product information
2. **Compatibility Detection**: Uses keyword detection (`_should_attempt_compatibility()`) combined with LLM-based detection via prompt instructions
3. **Knowledge Graph Query**: LLM calls `Neo4jCompatibilityTool` methods (via tools) to query the graph
4. **Response Generation**: Formats compatibility results into natural language responses

**Key Integration Points**:
- Keyword detection for early compatibility query identification
- LLM extracts product names and part types from natural language queries
- LLM calls appropriate compatibility tools based on query intent
- Tool results are parsed and formatted for display
- Results can be formatted as comparison tables for compatible parts recommendations

#### Query Flow Example

For a query like "What PSUs are compatible with the RTX 4090?":

1. **Keyword Detection** (`analytical.py:1101-1119`): `_should_attempt_compatibility()` detects compatibility keywords ("compatible", "PSUs")
2. **Request Analysis** (`request_analyzer.py:118-120`): Request analyzer flags as analytical query requiring compatibility tools
3. **LLM Processing** (`analytical.py:269-296`): LLM detects compatibility intent from prompt instructions and extracts:
   - Source product: "RTX 4090"
   - Target part type: "psu" (from "PSUs")
4. **Tool Call** (`analytical.py:533-600`): LLM calls `find_compatible_parts(source_product_name="RTX 4090", target_part_type="gpu")`
5. **Product Lookup** (`kg_compatibility.py:93-147`): Tool uses `find_product_by_name()` to find RTX 4090 by slug
6. **Compatibility Query** (`kg_compatibility.py:258-335`): `find_compatible_parts()` queries Neo4j:
   - Maps `(gpu, psu)` → `ELECTRICAL_COMPATIBLE_WITH` (with reverse fallback)
   - Executes bidirectional Cypher query: `MATCH (source)-[r:ELECTRICAL_COMPATIBLE_WITH]-(target)`
   - Returns compatible PSUs ordered by price
7. **Result Parsing** (`analytical.py:800-846`): Tool results are parsed and formatted
8. **Reranking** (`compatibility.py:30-53`): `find_compatible_parts_recommendations()` reranks by price (if called)
9. **Formatting** (`compatibility.py:56-143`): `format_compatibility_recommendations_table()` creates comparison table
10. **Response**: Agent includes compatibility results in response to user

### Example Cypher Queries

#### Find Compatible GPUs for a Motherboard

```cypher
MATCH (mb:PCProduct {slug: "asus-rog-strix-z790-e"})-[r:INTERFACE_COMPATIBLE_WITH]-(gpu:PCProduct)
WHERE gpu.product_type = "gpu"
RETURN gpu.name, gpu.brand, gpu.price_min, gpu.price_max, r.board_pcie, r.gpu_requirement
ORDER BY gpu.price_avg ASC
LIMIT 10
```

#### Find Compatible PSUs for a GPU

```cypher
MATCH (gpu:PCProduct {slug: "nvidia-rtx-4090"})
MATCH (psu:PCProduct)-[r:ELECTRICAL_COMPATIBLE_WITH]->(gpu)
WHERE psu.product_type = "psu"
RETURN psu.name, psu.wattage, psu.price_min, psu.price_max, r.margin_watts, r.psu_watts, r.required_watts
ORDER BY psu.price_avg ASC
LIMIT 10
```

#### Find Compatible CPU-Motherboard Pairs

```cypher
MATCH (cpu:PCProduct {product_type: "cpu"})
MATCH (cpu)-[r:SOCKET_COMPATIBLE_WITH]->(mb:PCProduct {product_type: "motherboard"})
RETURN cpu.name, mb.name, cpu.socket, mb.socket, r.socket
LIMIT 10
```

#### Find All Compatibility Relationships for a Product

```cypher
MATCH (p:PCProduct {slug: "nvidia-rtx-4090"})
MATCH (p)-[r]->(compatible:PCProduct)
RETURN type(r) AS relationship_type, compatible.name, compatible.product_type, r
LIMIT 20
```

#### Multiple Compatibility Types Between Same Products

Two products can have multiple compatibility edges representing different aspects:

```cypher
// Example: A motherboard and GPU might have multiple compatibility types
MATCH (mb:PCProduct {slug: "asus-z790-motherboard"})-[r]->(gpu:PCProduct {slug: "nvidia-rtx-4090"})
RETURN type(r) AS compatibility_type, r
```

This could return:
- `INTERFACE_COMPATIBLE_WITH` (PCIe version compatibility)
- And potentially other types if they exist

Each relationship type is independent and represents a different dimension of compatibility.

#### View All Products

```cypher
MATCH (p:PCProduct)
RETURN p
LIMIT 50
```

#### View Products by Type

```cypher
MATCH (p:PCProduct {product_type: "gpu"})
RETURN p.name, p.brand, p.price_avg
LIMIT 20
```

#### View Compatibility Relationships

```cypher
MATCH (p1:PCProduct)-[r:ELECTRICAL_COMPATIBLE_WITH]-(p2:PCProduct)
RETURN p1.name, type(r), p2.name
LIMIT 50
```

#### Check Compatibility Between Two Parts

```cypher
MATCH (p1:PCProduct {slug: "intel-core-i9-13900k"})-[r]-(p2:PCProduct {slug: "asus-rog-strix-z790-e"})
RETURN type(r) AS relationship_type, p1.name, p2.name, r
```

#### View All Compatibility Types

```cypher
MATCH ()-[r]->()
WHERE type(r) CONTAINS "COMPATIBLE"
RETURN DISTINCT type(r) AS compatibility_type
```

#### Product Statistics

```cypher
MATCH (p:PCProduct)
RETURN p.product_type, count(p) AS count, avg(p.price_avg) AS avg_price
ORDER BY count DESC
```

#### Compatibility Graph Visualization

```cypher
MATCH (p1:PCProduct {product_type: "cpu"})-[r:SOCKET_COMPATIBLE_WITH]-(p2:PCProduct {product_type: "motherboard"})
RETURN p1, r, p2
LIMIT 100
```

---

## Viewing and Managing the Graph

### Accessing Neo4j Browser

#### Local Neo4j

1. Ensure Neo4j is running (see [Prerequisites and Setup](#prerequisites-and-setup))
2. Navigate to http://localhost:7474
3. Log in with credentials (default: username `neo4j`, password set during installation)

#### Neo4j Aura

1. Log in to Aura Console: Navigate to https://console.neo4j.io/
2. Select Database: Click on your database instance
3. Open Browser: Click "Open with Neo4j Browser"
4. Enter Password: Enter your database password

### Neo4j Browser Features

- **Graph Visualization**: Interactive graph view with zoom and pan
- **Table View**: Tabular results for queries
- **Query History**: Access to previously run queries
- **Export**: Export query results as CSV or JSON
- **Favorites**: Save frequently used queries

### Neo4j Aura Dashboards

For advanced visualizations and dashboards:

1. **Access Dashboards**: In Aura Console, select "Dashboards" tab
2. **Create Dashboard**: Click "Create Dashboard"
3. **Add Visualizations**: Add charts, graphs, and tables
4. **Configure Queries**: Set up Cypher queries for each visualization
5. **Share**: Share dashboards with team members

**Documentation**: https://neo4j.com/docs/aura/dashboards/getting-started/

### Migration Notes

When migrating from the old structure (if applicable):

1. **Purge old namespace**: Use `--purge` flag to delete old nodes
2. **Rebuild graph**: Run build script with new structure
3. **Update queries**: Update any Cypher queries to use new structure (no Attribute/Constraint nodes)

---

## Troubleshooting

### Step 1 Fails
- Check Neo4j is running: `docker ps | grep neo4j` or `neo4j status`
- Check `.env` file has correct Neo4j credentials
- Verify `data/pc_parts.db` exists
- Test Neo4j connection: `cypher-shell -u neo4j -p your-password`

### Step 2 Fails/Slow
- This is expected - scraping is slow
- Check internet connection
- Reduce `--delay` if too slow (but respect rate limits)
- Use `--limit` to test with fewer products first
- Can be interrupted and resumed (cached products are skipped)

### Step 3 Shows No Updates
- Verify Step 2 completed successfully
- Check `data/compatibility_cache.db` has data:
  ```bash
  sqlite3 data/compatibility_cache.db "SELECT COUNT(*) FROM product_attributes;"
  ```
- Ensure product slugs match between database and cache

### Missing Compatibility Data
- Check cache: `sqlite3 data/compatibility_cache.db "SELECT COUNT(*) FROM product_attributes;"`
- Pre-scrape: Run `scrape_compatibility_data.py` for specific products
- Enable scraping: Use `--enable-scraping` flag (slower)

### LLM Extraction Not Working
- Ensure `OPENAI_API_KEY` is set in `.env` or environment
- Check that `langchain-openai` and `pydantic` are installed
- LLM extraction is optional - regex parsing will be used as fallback

### Connection Issues
- Verify connection URI format: `neo4j+s://` for Aura (secure)
- Check firewall settings allow outbound connections
- Verify credentials match Aura Console

### Query Performance
- Add indexes on frequently queried properties:
  ```cypher
  CREATE INDEX ON :PCProduct(slug);
  CREATE INDEX ON :PCProduct(product_type);
  ```
- Use `LIMIT` clauses to restrict result sets
- Profile queries to identify bottlenecks: `PROFILE MATCH ...`

### Missing Data
- Verify nodes exist: `MATCH (p:PCProduct) RETURN count(p)`
- Check namespace matches: `MATCH (p {namespace: "pc_parts"}) RETURN count(p)`
- Verify relationships: `MATCH ()-[r]->() RETURN count(r)`

### Files Created

After building the knowledge graph, the following files are created:

- `data/compatibility_cache.db` - SQLite cache of scraped compatibility data
- `data/kg_backups/` - Backup files (if backups were created)
- Neo4j database - Knowledge graph with products and compatibility relationships
