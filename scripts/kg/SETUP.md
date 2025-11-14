# Knowledge Graph Setup Guide

## Overview

The knowledge graph builder has two modes for compatibility data:

1. **Cached mode (default)**: Uses previously scraped compatibility data from SQLite cache
2. **Scraping mode**: Actively scrapes new compatibility data (slower, requires `--enable-scraping`)

**Important**: The KG builder does NOT automatically scrape during build. It only uses cached data unless you explicitly enable scraping.

## Prerequisites

### 1. Neo4j Database

Install and start Neo4j:

```bash
# Using Docker (recommended)
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest

# Or install locally: https://neo4j.com/download/
```

### 2. Python Dependencies

```bash
pip install -r requirements.txt

# Additional dependencies for PDF parsing (optional but recommended)
pip install pdfplumber PyPDF2

# For LLM extraction (optional)
pip install langchain-openai pydantic
```

### 3. Data Files

Ensure you have the PC parts database:
- `data/pc_parts.db` - SQLite database with product data

## Environment Variables

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

## Usage Workflow

### Step 1: Pre-scrape Compatibility Data (Optional but Recommended)

Before building the KG, you can pre-scrape compatibility data for products:

```bash
# Scrape a specific product
python scripts/kg/scrape_compatibility_data.py \
    --product-name "NVIDIA RTX 4090" \
    --product-slug "nvidia-rtx-4090" \
    --brand "NVIDIA" \
    --sellers newegg microcenter wikipedia manufacturer

# Scrape with LLM extraction (better accuracy)
python scripts/kg/scrape_compatibility_data.py \
    --product-name "ASUS ROG Strix Z790-E" \
    --product-slug "asus-rog-strix-z790-e" \
    --brand "ASUS" \
    --use-llm \
    --sellers manufacturer
```

This will:
- Scrape compatibility data from multiple sources
- Cache results in `data/compatibility_cache.db`
- Reuse cached data in future builds

### Step 2: Build Knowledge Graph

#### Basic Build (Uses Cached Scraped Data)

```bash
python scripts/kg/build_pc_parts_kg.py \
    --db-path data/pc_parts.db \
    --neo4j-uri bolt://localhost:7687 \
    --neo4j-user neo4j \
    --neo4j-password your-password \
    --namespace pc_parts \
    --purge
```

This will:
- Load products from `pc_parts.db`
- Use cached compatibility data from `compatibility_cache.db` (if available)
- Create product nodes with attributes as properties
- Create compatibility edges between products
- **NOT** scrape new data (only uses cache)

#### Build with Active Scraping

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

This will:
- Load products from `pc_parts.db`
- **Actively scrape** compatibility data for products (slower)
- Cache scraped data for future use
- Create product nodes and compatibility edges

**Note**: Active scraping during build is slower. It's recommended to pre-scrape data separately.

## How Scraping Works

### Default Behavior (Without `--enable-scraping`)

1. KG builder initializes `CompatibilityScraper` with cache-only mode
2. For each product, checks `compatibility_cache.db` for cached attributes
3. Uses cached data if available
4. If no cache exists, product is built without scraped attributes (uses only parsed attributes)

### With `--enable-scraping`

1. KG builder initializes `CompatibilityScraper` with scraping enabled
2. For each product:
   - Checks cache first
   - If not cached, scrapes from configured sources (Newegg, MicroCenter, Wikipedia, Manufacturer)
   - Caches results for future use
   - Uses scraped attributes in KG

## Data Flow

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

## Troubleshooting

### Neo4j Connection Issues

```bash
# Test Neo4j connection
cypher-shell -u neo4j -p your-password

# Check if Neo4j is running
docker ps | grep neo4j
# or
neo4j status
```

### Missing Compatibility Data

If products don't have scraped attributes:

1. **Check cache**: `sqlite3 data/compatibility_cache.db "SELECT COUNT(*) FROM product_attributes;"`
2. **Pre-scrape**: Run `scrape_compatibility_data.py` for specific products
3. **Enable scraping**: Use `--enable-scraping` flag (slower)

### LLM Extraction Not Working

- Ensure `OPENAI_API_KEY` is set in `.env` or environment
- Check that `langchain-openai` and `pydantic` are installed
- LLM extraction is optional - regex parsing will be used as fallback

## Recommended Workflow

1. **Initial Setup**:
   ```bash
   # 1. Start Neo4j
   docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest
   
   # 2. Create .env file with Neo4j credentials
   # 3. Build KG with existing data
   python scripts/kg/build_pc_parts_kg.py --purge
   ```

2. **Enhance with Scraped Data**:
   ```bash
   # Pre-scrape important products
   python scripts/kg/scrape_compatibility_data.py --product-name "..." --brand "..."
   
   # Rebuild KG to include scraped attributes
   python scripts/kg/build_pc_parts_kg.py --purge
   ```

3. **Ongoing Updates**:
   ```bash
   # Add new products to pc_parts.db
   # Rebuild KG (uses cached scraped data automatically)
   python scripts/kg/build_pc_parts_kg.py --purge
   ```

## Files Created

- `data/compatibility_cache.db` - SQLite cache of scraped compatibility data
- Neo4j database - Knowledge graph with products and compatibility relationships

