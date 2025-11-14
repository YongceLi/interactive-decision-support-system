# Knowledge Graph Build Commands

## Three-Step Build Process

The knowledge graph build is split into 3 steps for reliability and incremental progress:

1. **Step 1**: Create product nodes from database (fast, no scraping)
2. **Step 2**: Scrape compatibility data for all products (slow, can be retried)
3. **Step 3**: Update graph with scraped data (fast, uses cached scraped data)

## Prerequisites

1. **Neo4j running**:
   ```bash
   docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest
   ```

2. **`.env` file** in project root:
   ```bash
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your-password
   PC_PARTS_DB=data/pc_parts.db
   ```

3. **Dependencies installed**:
   ```bash
   pip install -r requirements.txt
   pip install pdfplumber PyPDF2  # Optional but recommended
   ```

## Backup and Restore

Before running Step 2 (which can have bugs), you can backup your Step 1 graph:

### Backup Step 1 Graph

```bash
python scripts/kg/backup_kg.py backup \
    --namespace pc_parts \
    --output data/kg_backups/step1_backup.json
```

This saves all nodes and relationships to a JSON file.

### Restore Step 1 Graph

If Step 2 has bugs and you need to restore:

```bash
python scripts/kg/backup_kg.py restore \
    --backup-file data/kg_backups/step1_backup.json \
    --namespace pc_parts \
    --purge
```

This restores the graph from the backup file (and purges any corrupted data).

---

## Commands to Run

### Step 1: Create Product Nodes

```bash
python scripts/kg/build_pc_parts_kg.py \
    --step 1 \
    --purge \
    --limit 200
```

**What it does:**
- Loads products from `data/pc_parts.db`
- Creates product nodes in Neo4j with attributes from database
- Creates compatibility edges based on parsed attributes
- **Does NOT scrape** - uses only data from database

**Output:**
- Neo4j graph with product nodes
- Basic compatibility edges

**Time:** ~30 seconds - 2 minutes (depending on number of products)

---

### Step 2: Scrape Compatibility Data

```bash
python scripts/kg/build_pc_parts_kg.py \
    --step 2 \
    --limit 200 \
    --enable-scraping
```

**Or use the dedicated script:**

```bash
python scripts/kg/kg_step2_scrape.py \
    --db-path data/pc_parts.db \
    --compatibility-db data/compatibility_cache.db \
    --limit 200 \
    --delay 2.0
```

**With LLM extraction (optional, requires OpenAI API key):**

```bash
python scripts/kg/kg_step2_scrape.py \
    --db-path data/pc_parts.db \
    --compatibility-db data/compatibility_cache.db \
    --use-llm \
    --limit 200 \
    --delay 2.0
```

**What it does:**
- Reads product information from database
- Scrapes compatibility data from:
  - Newegg
  - MicroCenter
  - Wikipedia
  - Manufacturer official documentation
- Caches scraped data in `data/compatibility_cache.db`
- Skips products that are already cached

**Output:**
- `data/compatibility_cache.db` with scraped attributes and compatibility facts

**Time:** ~2-5 minutes per product (with rate limiting)
- For 200 products: ~7-17 hours (can be interrupted and resumed)
- Already cached products are skipped instantly

**Tips:**
- Can be interrupted and resumed (cached products are skipped)
- Use `--limit` to test with fewer products first
- Use `--delay` to adjust rate limiting (default 2 seconds)
- Check logs to see progress

---

### Step 3: Update Graph with Scraped Data

```bash
python scripts/kg/build_pc_parts_kg.py \
    --step 3 \
    --limit 200
```

**What it does:**
- Reads scraped data from `data/compatibility_cache.db`
- Updates existing Neo4j nodes with scraped attributes
- Updates compatibility edges based on scraped data
- **Does NOT scrape** - only uses cached scraped data

**Output:**
- Updated Neo4j graph with enhanced product attributes
- Enhanced compatibility edges

**Time:** ~30 seconds - 2 minutes

---

## Complete Workflow Example

```bash
# Step 1: Create nodes (fast)
python scripts/kg/build_pc_parts_kg.py --step 1 --purge --limit 200

# Step 2: Scrape data (slow - can run overnight)
# Run this in a screen/tmux session so it can run in background
python scripts/kg/kg_step2_scrape.py --limit 200 --delay 2.0

# Step 3: Update graph (fast)
python scripts/kg/build_pc_parts_kg.py --step 3 --limit 200
```

## Incremental Updates

### Add More Products

```bash
# Step 1: Add new products to graph
python scripts/kg/build_pc_parts_kg.py --step 1 --limit 500

# Step 2: Scrape only new products (cached ones are skipped)
python scripts/kg/kg_step2_scrape.py --limit 500

# Step 3: Update graph with new scraped data
python scripts/kg/build_pc_parts_kg.py --step 3 --limit 500
```

### Re-scrape Specific Products

```bash
# Delete cached data for specific products
sqlite3 data/compatibility_cache.db "DELETE FROM product_attributes WHERE product_slug='nvidia-rtx-4090';"

# Re-scrape
python scripts/kg/kg_step2_scrape.py --limit 1
```

## Monitoring Progress

### Check Scraping Progress

```bash
# Count cached products
sqlite3 data/compatibility_cache.db "SELECT COUNT(DISTINCT product_slug) FROM product_attributes;"

# List scraped products
sqlite3 data/compatibility_cache.db "SELECT DISTINCT product_slug FROM product_attributes LIMIT 10;"
```

### Check Neo4j Graph

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
MATCH (a:PCProduct)-[r:COMPATIBLE_WITH]->(b:PCProduct)
RETURN a.name, r.compatibility_type, b.name
LIMIT 10;
```

## Troubleshooting

### Step 1 Fails
- Check Neo4j is running: `docker ps | grep neo4j`
- Check `.env` file has correct Neo4j credentials
- Verify `data/pc_parts.db` exists

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

## Environment Variables

All steps respect these environment variables (or use command-line args):

- `NEO4J_URI` (default: `bolt://localhost:7687`)
- `NEO4J_USER` (default: `neo4j`)
- `NEO4J_PASSWORD` (required)
- `PC_PARTS_DB` (default: `data/pc_parts.db`)
- `OPENAI_API_KEY` (only needed if using `--use-llm`)

