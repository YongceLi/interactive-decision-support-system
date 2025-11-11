# California Vehicle Dataset Builder

Build a comprehensive local SQLite database of California vehicle listings for the MVP, eliminating high-latency API calls.

## Overview

This module fetches vehicle listings from California across all 2,479 make/model combinations found in `safety_data.db` and stores them in a fast, queryable SQLite database.

## Why SQLite?

✅ **Fast Filtering**: Indexed columns for instant searches by make, model, price, mileage, etc.
✅ **Low Latency**: Sub-millisecond queries vs. 500ms+ API calls
✅ **Complete Data**: Stores full JSON payload + extracted searchable fields
✅ **Resume Support**: Progress tracking allows interruption and resumption
✅ **No API Dependency**: Works offline after initial fetch

## Database Schema

### Main Table: `vehicle_listings`

| Column | Type | Indexed | Description |
|--------|------|---------|-------------|
| `vin` | TEXT | ✅ | Unique 17-character identifier |
| `make` | TEXT | ✅ | Vehicle manufacturer (e.g., "Toyota") |
| `model` | TEXT | ✅ | Model name (e.g., "Camry") |
| `year` | INTEGER | ✅ | Model year (2018-2026) |
| `body_style` | TEXT | ✅ | Body type (sedan, suv, truck, etc.) |
| `price` | INTEGER | ✅ | Listing price in USD |
| `mileage` | INTEGER | ✅ | Odometer reading |
| `fuel_type` | TEXT | ✅ | Fuel type (Gasoline, Electric, Hybrid) |
| `dealer_state` | TEXT | ✅ | State (always "CA" for this dataset) |
| `raw_json` | TEXT | - | Complete API response |
| ... | ... | ... | 30+ additional fields |

**Composite Indexes**:
- `(make, model)` - Fast make/model filtering
- `(make, model, year)` - Common search pattern
- `(body_style, price)` - Body type + price range queries

Full schema: `dataset_builder/schema.sql`

## Dataset Specifications

- **Source**: Auto.dev Listings API
- **Location**: California only (`retailListing.state=CA`)
- **Years**: 2018-2026
- **Mileage Range**: 0-150,000 miles
- **Vehicles per Model**: Up to 50
- **Total Make/Model Combinations**: 2,479
- **Expected Total Vehicles**: 60,000-100,000 (unique VINs)
- **Expected API Calls**: ~2,500
- **Estimated Runtime**: 8-12 minutes
- **Database Size**: ~100-200 MB

## Files

```
dataset_builder/
├── README.md                     # This file
├── schema.sql                    # SQLite database schema
├── fetch_california_dataset.py   # Vehicle dataset fetcher
├── pc_parts_schema.sql           # PC parts SQLite schema
├── fetch_pc_parts_dataset.py     # Electronics dataset builder (PC + consumer electronics)
├── (output) → data/california_vehicles.db
└── (output) → data/pc_parts.db
```

## Usage

### Prerequisites

1. Ensure `AUTODEV_API_KEY` is set in `.env`
2. Dependencies already installed (requests, python-dotenv, sqlite3 is built-in)

### Run the Fetcher

From project root:

```bash
python dataset_builder/fetch_california_dataset.py
```

### Output

Creates `data/california_vehicles.db` with:
- `vehicle_listings` table: All vehicles with indexed fields
- `fetch_progress` table: Progress tracking for resume support

### Resume Interrupted Runs

If the script stops, simply re-run it - it automatically resumes from where it left off.

## Features

### Progressive Saving
- Vehicles saved immediately after each API call
- No data loss even if interrupted

### Error Handling
- Automatic retries for failed requests (3 attempts)
- Rate limit handling with exponential backoff
- 500 errors treated as "no results" (common for obscure models)
- Timeouts with retry logic

### Progress Tracking
- Database tracks completed make/model combinations
- Real-time progress updates every 50 models
- Final statistics with database size

## Querying the Database

### Example Queries

```python
import sqlite3

conn = sqlite3.connect('data/california_vehicles.db')
cursor = conn.cursor()

# Find Toyota Camrys under $30k
cursor.execute("""
    SELECT make, model, year, price, mileage, dealer_city
    FROM vehicle_listings
    WHERE make = 'TOYOTA' AND model = 'CAMRY' AND price < 30000
    ORDER BY price
    LIMIT 20
""")

# Find all SUVs between $20k-$40k
cursor.execute("""
    SELECT make, model, year, price
    FROM vehicle_listings
    WHERE body_style = 'suv' AND price BETWEEN 20000 AND 40000
    ORDER BY price
    LIMIT 20
""")

# Get statistics
cursor.execute("SELECT COUNT(*), AVG(price) FROM vehicle_listings")
total, avg_price = cursor.fetchone()
print(f"Total: {total:,} vehicles, Average price: ${avg_price:,.2f}")
```

### Command Line Queries

```bash
# Count total vehicles
sqlite3 data/california_vehicles.db "SELECT COUNT(*) FROM vehicle_listings"

# Top 10 cheapest cars
sqlite3 data/california_vehicles.db \
  "SELECT make, model, year, price FROM vehicle_listings ORDER BY price LIMIT 10"

# Distribution by body style
sqlite3 data/california_vehicles.db \
  "SELECT body_style, COUNT(*) FROM vehicle_listings GROUP BY body_style"
```

## Configuration

Edit parameters in `fetch_california_dataset.py`:

```python
# In main() function
fetcher = DatasetFetcher(db_path="data/california_vehicles.db")
fetcher.fetch_all(
    limit_per_model=50,      # Vehicles to fetch per make/model
    rate_limit_delay=0.2     # Seconds between API calls
)

# In fetch_vehicles_for_model()
params = {
    "vehicle.year": "2018-2026",           # Customize year range
    "retailListing.state": "CA",           # Change state
    "retailListing.miles": "0-150000",     # Customize mileage
}
```

## Performance Comparison

| Metric | Auto.dev API | Local SQLite |
|--------|--------------|--------------|
| Search Latency | 500-2000ms | <5ms |
| Concurrent Users | Rate limited | Unlimited |
| Offline Support | ❌ | ✅ |
| Filtering Speed | Slow | Instant |
| Cost per Query | API call | Free |

## Next Steps

After building the dataset:

1. ✅ **Dataset Built** - Run `fetch_california_dataset.py`
2. 🔄 **Update Recommendation Engine** - Modify `idss_agent/components/recommendation.py` to query local DB
3. 🔄 **Remove API Dependency** - Make Auto.dev API optional for MVP
4. 🔄 **Add Photo Caching** - Optionally download and cache vehicle photos locally

## Troubleshooting

**Script stops unexpectedly**
- Re-run the script - it resumes automatically

**Rate limit errors**
- Increase `rate_limit_delay` to 0.5 or 1.0 seconds

**Database locked error**
- Close any other programs accessing the database
- Delete `data/california_vehicles.db` and start fresh

**Want to start over**
- Delete `data/california_vehicles.db`
- Re-run the script

**Check progress during run**
```bash
sqlite3 data/california_vehicles.db \
  "SELECT COUNT(*) as completed FROM fetch_progress WHERE status='completed'"
```

---

# Electronics Dataset Builder

Build a unified local database of consumer electronics spanning core PC components, complete systems (laptops and desktops), peripherals, home entertainment, smart home gear, wearables, drones, cameras, networking hardware, and more. The schema mirrors the vehicle dataset philosophy: fast filterable columns plus preserved raw payloads for downstream enrichment.

## Sources

- **PCPartPicker** — Canonical component catalog with rich spec tables (HTML scrape).
- **Best Buy** — Retail pricing and availability (HTML scrape).
- **RapidAPI** — Third-party catalog feed (defaults to the Newegg data API, override via env vars).

## Schema Overview

- `pc_parts`: Normalized product metadata (`part_type`, `manufacturer`, `price`, `stock_status`, etc.) with `specs_json` capturing PCPartPicker-style tables and `attributes_json` for auxiliary data.
- `pc_parts_fetch_progress`: Mirrors `fetch_progress`, enabling resume support per `{source, part_type}`.
- `pc_parts_dataset_stats`: Cached stats (`total_records`, `unique_parts`, `last_build`, `upserted_this_run`).
- Built-in deduplication: records are filtered by canonical `part_id` and `(source, manufacturer, product_name)` to avoid duplicate inserts (especially from RapidAPI feeds).

Full definition: `dataset_builder/pc_parts_schema.sql`.

## Running the Builder

### Prerequisites

1. Install dependencies (includes `beautifulsoup4`):
   ```bash
   pip install -r requirements.txt
   ```
2. Set up RapidAPI (optional but recommended):
   - Add `RAPIDAPI_KEY` to `.env`.
   - Defaults now target `product-search-api.p.rapidapi.com/shopping`, matching the RapidAPI request snippet you shared (`Content-Type: application/x-www-form-urlencoded` with `query`, `page`, `country`).
   - Override `RAPIDAPI_HOST`, `RAPIDAPI_ENDPOINT`, or `RAPIDAPI_COUNTRY` in `.env` if you need a different provider or locale.

### Command

```bash
python dataset_builder/fetch_pc_parts_dataset.py --db-path data/pc_parts.db
# RapidAPI only, capped to 100 per category
python dataset_builder/fetch_pc_parts_dataset.py --db-path data/pc_parts.db --limit 100 --sources rapidapi
# Best Buy + PCPartPicker only, unlimited
python dataset_builder/fetch_pc_parts_dataset.py --db-path data/pc_parts.db --sources pcpartpicker bestbuy
```

- `--limit` controls the per-source-per-category cap (default `0`, which means unlimited). Provide a positive value to cap records if you want quicker runs.
- `--sources` lets you choose any subset of `pcpartpicker`, `bestbuy`, `rapidapi` (default order prioritises `rapidapi`, then `pcpartpicker`, then `bestbuy`). Pass sources in your preferred priority order.
- Requests are rate-limited (`time.sleep`) to avoid overloading upstream sites; a full run typically completes in a few minutes.

### Output

- `data/pc_parts.db`
  - `pc_parts`: Deduplicated records with canonical IDs (`source:origin_id` or hashed fallback).
  - `pc_parts_fetch_progress`: Ingestion status for each `{source, category}`.
  - `pc_parts_dataset_stats`: Summary metrics updated after each run.

## Customisation Tips

- Edit `ELECTRONICS_CATEGORIES` in `fetch_pc_parts_dataset.py` to adjust PCPartPicker slugs, Best Buy keywords, or RapidAPI search terms.
- Override RapidAPI host/endpoint via environment without touching code.
- Use `--sources` to focus on a single feed (e.g., `--sources rapidapi`) or skip unreliable scrapers.
- Extend `_canonical_part_id` if you need custom dedupe semantics.

## Troubleshooting

- **RapidAPI skipped**: Log warning indicates missing `RAPIDAPI_KEY`; script still ingests PCPartPicker + Best Buy data.
- **Selector changes**: If HTML scraping breaks, update the CSS selectors in `PCPartPickerScraper` or `BestBuyScraper`.
- **Duplicate entries**: Script now skips duplicates by `part_id` and normalized `(source, manufacturer, product_name)`. If you still see dupes, inspect upstream payload IDs or adjust `_canonical_part_id`.

## Database Maintenance

### View Statistics

```python
from dataset_builder.fetch_california_dataset import DatasetFetcher
fetcher = DatasetFetcher()
stats = fetcher.generate_stats()
```

### Optimize Database

```bash
sqlite3 data/california_vehicles.db "VACUUM; ANALYZE;"
```

### Export to CSV

```bash
sqlite3 -header -csv data/california_vehicles.db \
  "SELECT * FROM vehicle_listings" > california_vehicles.csv
```

## Data Freshness

Vehicle listings change daily. To refresh:

1. Delete `data/california_vehicles.db`
2. Re-run fetcher script
3. Optionally, set up a cron job for weekly updates

## License & Data Usage

Data sourced from Auto.dev API. Ensure compliance with Auto.dev terms of service for commercial use.
