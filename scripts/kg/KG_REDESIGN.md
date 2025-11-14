# Knowledge Graph Redesign

## Overview

The knowledge graph has been redesigned to follow a simpler, more intuitive structure:

- **Products are the ONLY nodes** - Each product (CPU, GPU, motherboard, etc.) is a single node
- **Constraints are edges** - Compatibility relationships between products are represented as edges
- **Attributes are properties** - Product attributes (product_type, brand, sellers, socket, PCIe version, etc.) are stored as properties on product nodes

## Structure

### Node Structure (Product)
```
(:Product:PCProduct {
  slug: String (unique identifier)
  name: String
  product_type: String (cpu, gpu, motherboard, psu, etc.)
  brand: String
  model: String
  sellers: List[String]
  price_min: Float
  price_max: Float
  price_avg: Float
  
  // Dynamic attributes (from parsing/scraping):
  socket: String (e.g., "LGA 1700")
  pcie_version: String (e.g., "PCIe:5.0")
  ram_standard: String (e.g., "DDR5")
  wattage: String (e.g., "850W")
  form_factor: String (e.g., "ATX")
  // ... and more
})
```

### Edge Structure (Compatibility)

Each compatibility type has its own relationship type. **Multiple relationship types can exist between the same two products**, representing different aspects of compatibility.

```
(:Product)-[:ELECTRICAL_COMPATIBLE_WITH {
  margin_watts: Float
  psu_watts: Float
  required_watts: Float
}]->(:Product)

(:Product)-[:SOCKET_COMPATIBLE_WITH {
  socket: String (e.g., "LGA 1700")
}]->(:Product)

(:Product)-[:INTERFACE_COMPATIBLE_WITH {
  board_pcie: Float
  gpu_requirement: Float
}]->(:Product)

(:Product)-[:RAM_COMPATIBLE_WITH {
  ram_standard: String (e.g., "DDR5")
}]->(:Product)

(:Product)-[:FORM_FACTOR_COMPATIBLE_WITH {
  form_factor: String (e.g., "ATX")
}]->(:Product)

(:Product)-[:MEMORY_COMPATIBLE_WITH {
  ram_standard: String
}]->(:Product)

(:Product)-[:THERMAL_COMPATIBLE_WITH {
  cooler_support_watts: Float
  cpu_requirement_watts: Float
  margin_watts: Float
}]->(:Product)
```

**Example:** A motherboard and GPU can have both:
- `INTERFACE_COMPATIBLE_WITH` (PCIe compatibility)
- And potentially other compatibility types if applicable

Each relationship type is independent - MERGE only merges relationships of the same type, so different types can coexist between the same products.

## Key Changes from Previous Design

### Before
- Separate `Attribute` nodes connected via `HAS_ATTRIBUTE` edges
- Separate `Constraint` nodes connected via `REQUIRES` edges
- Products connected to constraints via `SATISFIES` edges
- More complex graph structure

### After
- All attributes stored as properties on Product nodes
- Compatibility relationships are direct edges between Products
- Simpler, more intuitive structure
- Easier to query and understand

## Web Scraping Integration

### Compatibility Data Scraper

The `scripts/kg/scrape_compatibility_data.py` script scrapes compatibility information from:
- **Amazon** (placeholder - requires API)
- **Newegg** - Product specifications
- **MicroCenter** - Product specifications  
- **Wikipedia** - Technical specifications
- **Manufacturer Official Documentation** - Product pages and PDF manuals/specifications

### Caching

Scraped data is cached in SQLite database (`data/compatibility_cache.db`) for reuse:
- `compatibility_facts` - Compatibility relationships between products
- `product_attributes` - Scraped product attributes
- `scrape_cache` - URLs already scraped (prevents duplicate work)

### Attribute Normalization

The `scripts/kg/normalize_attributes.py` module normalizes attributes from various sources:
- `PCIE_5`, `PCIE5`, `pcie-v5` → `PCIe:5.0`
- `DDR4`, `ddr4`, `DDR-4` → `DDR4`
- `LGA1700`, `LGA 1700`, `lga-1700` → `LGA 1700`
- And more...

## Usage

### Building the Knowledge Graph

```bash
# Basic usage (uses cached scraped data)
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password password \
    --namespace pc_parts \
    --purge

# Enable web scraping (slower, but gets fresh data)
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password password \
    --namespace pc_parts \
    --enable-scraping \
    --purge
```

### Scraping Compatibility Data

```bash
# Scrape a specific product (includes manufacturer docs by default)
python scripts/kg/scrape_compatibility_data.py \
    --product-name "NVIDIA RTX 4090" \
    --product-slug "nvidia-rtx-4090" \
    --brand "NVIDIA" \
    --sellers newegg microcenter wikipedia manufacturer

# Scrape only manufacturer official documentation
python scripts/kg/scrape_compatibility_data.py \
    --product-name "ASUS ROG Strix Z790-E" \
    --product-slug "asus-rog-strix-z790-e" \
    --brand "ASUS" \
    --sellers manufacturer

# Use LLM-based extraction for better accuracy (requires OpenAI API key)
python scripts/kg/scrape_compatibility_data.py \
    --product-name "NVIDIA RTX 4090" \
    --product-slug "nvidia-rtx-4090" \
    --brand "NVIDIA" \
    --use-llm \
    --sellers manufacturer
```

**Manufacturer Documentation Scraping:**
- Automatically finds manufacturer product pages based on brand name
- Downloads and parses PDF manuals/specifications
- Extracts compatibility information from official documentation
- High confidence scores (0.95-0.98) for official sources
- Supports major manufacturers: NVIDIA, AMD, Intel, ASUS, MSI, Gigabyte, Corsair, etc.

**LLM-Based Extraction (Optional):**
- Uses GPT-4o-mini (or other OpenAI models) for structured extraction
- Better at handling unstructured text than regex patterns
- Uses Pydantic models with JSON schema to prevent hallucinations
- Extracts both product attributes and compatibility relationships
- Falls back to regex parsing if LLM is unavailable or fails
- Caches extractions to avoid redundant API calls
- Enable with `--use-llm` flag (requires `OPENAI_API_KEY` environment variable)

## Example Queries

### Find all GPUs compatible with a motherboard
```cypher
MATCH (mb:PCProduct {slug: "asus-z790-motherboard"})
MATCH (mb)-[:INTERFACE_COMPATIBLE_WITH]->(gpu:PCProduct)
WHERE gpu.product_type = "gpu"
RETURN gpu.name, gpu.brand, gpu.price_min, gpu.price_max
```

### Find all PSUs compatible with a GPU
```cypher
MATCH (gpu:PCProduct {slug: "nvidia-rtx-4090"})
MATCH (psu:PCProduct)-[:ELECTRICAL_COMPATIBLE_WITH]->(gpu)
WHERE psu.product_type = "psu"
RETURN psu.name, psu.wattage, psu.price_min, psu.price_max
```

### Find compatible CPU-Motherboard pairs
```cypher
MATCH (cpu:PCProduct {product_type: "cpu"})
MATCH (cpu)-[:SOCKET_COMPATIBLE_WITH]->(mb:PCProduct {product_type: "motherboard"})
RETURN cpu.name, mb.name, cpu.socket, mb.socket
LIMIT 10
```

### Find all compatibility relationships for a product
```cypher
MATCH (p:PCProduct {slug: "nvidia-rtx-4090"})
MATCH (p)-[r]->(compatible:PCProduct)
RETURN type(r) AS relationship_type, compatible.name, compatible.product_type
LIMIT 20
```

### Multiple Compatibility Types Between Same Products

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

## Migration Notes

When migrating from the old structure:

1. **Purge old namespace**: Use `--purge` flag to delete old nodes
2. **Rebuild graph**: Run build script with new structure
3. **Update queries**: Update any Cypher queries to use new structure (no Attribute/Constraint nodes)

## Future Enhancements

- [x] Manufacturer PDF parsing for deep constraints
- [x] LLM-based extraction with structured output to prevent hallucinations
- [ ] More comprehensive Wikipedia scraping
- [ ] Amazon Product Advertising API integration
- [ ] Enhanced PDF parsing with table extraction
- [ ] Support for more manufacturer websites
- [ ] Fine-tuned model for PC component specifications
- [ ] Multi-model ensemble for higher accuracy

