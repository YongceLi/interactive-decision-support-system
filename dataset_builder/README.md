# California Vehicle Dataset Builder

Build a comprehensive local SQLite database of California vehicle listings for the MVP, eliminating high-latency API calls.

## Overview

This module fetches every vehicle listing available from California's Bay Area (zip codes listed in `bay_area_zip.csv`) and stores them in a fast, queryable SQLite database.

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
- **Location**: California Bay Area zip codes (`bay_area_zip.csv`)
- **Years**: All available model years (no filter applied)
- **Mileage Range**: All available odometer readings (no filter applied)
- **Listings per Zip**: All available Bay Area listings (new and used when present)
- **Total Zip Codes**: Matches entries in `bay_area_zip.csv`
- **Expected API Calls**: Dependent on inventory volume across Bay Area zip codes
- **Estimated Runtime**: Varies with API responses and available inventory
- **Database Size**: Dependent on available inventory

## Files

```
dataset_builder/
├── README.md                          # This file
├── schema.sql                         # Auto.dev SQLite schema
├── unified_schema.sql                 # Unified schema shared by merged datasets
├── unified_schema_reference.md        # Column-by-column documentation for the unified schema
├── fetch_california_dataset.py        # Auto.dev fetcher script
├── marketcheck_schema.sql             # Marketcheck SQLite schema
├── fetch_marketcheck_dataset.py       # Marketcheck fetcher script
├── marketcheck_stats.py               # Marketcheck reporting helper
├── merge_sqlite_datasets.py           # Merge Auto.dev & Marketcheck SQLite files
├── fetch_unified_dataset.py           # Fetch Auto.dev/Marketcheck data directly into the unified schema
├── unified_stats.py                   # Summary statistics for unified_vehicle_listings
├── visualize_california_zip_map.py    # Choropleth map of California inventory by ZIP
└── (output)
    ├── data/california_vehicles.db    # Auto.dev dataset
    └── data/marketcheck_vehicles.db   # Marketcheck dataset
```

## Usage

### Prerequisites

1. Ensure `AUTODEV_API_KEY` and/or `MARKETCHECK_API_KEY` are set in `.env`
2. Dependencies already installed (requests, python-dotenv, sqlite3 is built-in)

### Run the Fetcher

From project root:

```bash
python dataset_builder/fetch_california_dataset.py
```

or, for Marketcheck listings:

```bash
python dataset_builder/fetch_marketcheck_dataset.py
```

The script automatically:

1. Loads Bay Area zip codes from `dataset_builder/bay_area_zip.csv`
2. Iterates over every zip code in the Bay Area list
3. Fetches every available Bay Area listing per zip, balancing new and used requests
4. Restricts all API requests to the Bay Area zip codes
5. Stores the deduplicated (by VIN) results in `data/california_vehicles.db`

### Output

Creates `data/california_vehicles.db` with:
- `vehicle_listings` table: All vehicles with indexed fields
- `zip_fetch_progress` table: Progress tracking for resume support

Creates `data/marketcheck_vehicles.db` with:
- `marketcheck_listings` table: Marketcheck inventory search results (all listing fields + raw JSON)
- `marketcheck_zip_progress` table: Bay Area zip code progress tracker

### Explore California Dataset Statistics

Summarize make/model distribution, inventory mix, pricing buckets, and dealer hotspots for the Auto.dev dataset without re-running the fetcher:

```bash
python dataset_builder/california_stats.py
```

### Explore Marketcheck Statistics

Generate distribution summaries for make, model, inventory type, pricing buckets, and dealer coverage without refetching data:

```bash
python dataset_builder/marketcheck_stats.py
```

### Merge Auto.dev and Marketcheck Datasets

Convert any combination of Auto.dev (`vehicle_listings`) and Marketcheck
(`marketcheck_listings`) SQLite files into a single database with a unified
schema. Duplicate VINs are resolved in favour of Marketcheck entries.

```bash
python dataset_builder/merge_sqlite_datasets.py \
  data/unified_vehicles.db \
  data/california_vehicles.db \
  data/marketcheck_vehicles.db
```

The output database uses the schema stored in `dataset_builder/unified_schema.sql`
and records the origin of each row in the `source` column (`autodev` or
`marketcheck`).

For a detailed description of every field, refer to
[`unified_schema_reference.md`](./unified_schema_reference.md).

### Normalize legacy unified databases

Older unified databases may lack the canonical body type, fuel type, and usage flags.
Run the normalization helper to backfill the new columns in-place:

```bash
python dataset_builder/normalize_unified_database.py data/unified_vehicles.db
```

The script adds any missing columns and normalizes their values using the priority
rules described in the updated schema reference.

### Fetch directly into the unified schema

Skip the intermediate source-specific databases by fetching Auto.dev or
Marketcheck listings straight into `unified_vehicle_listings`:

```bash
# Auto.dev example with custom filters
python dataset_builder/fetch_unified_dataset.py autodev \
  --base-params '{"retailListing.state": "CA", "vehicle.make": "Tesla"}' \
  --output-db data/unified_vehicles.db

# Marketcheck example using raw query parameters
python dataset_builder/fetch_unified_dataset.py marketcheck \
  --base-params '{"zip": "94105", "radius": "25"}'
```

Pass `--base-params` either as an inline JSON string or a path to a JSON
file containing request parameters. The script honours the VIN priority used
during merges (Marketcheck rows replace Auto.dev rows when duplicates are
encountered).

### Unified dataset statistics

Inspect the combined dataset with `unified_stats.py`:

```bash
python dataset_builder/unified_stats.py --db data/unified_vehicles.db
```

The report shows:

- Top 20 makes with dataset share percentages
- Top 10 models within each leading make
- Inventory mix, price buckets, and location breakdowns (state, city, ZIP)

### California ZIP choropleth

Render an interactive California map coloured by listing density per ZIP:

```bash
python dataset_builder/visualize_california_zip_map.py \
  --db data/unified_vehicles.db \
  --output data/california_zip_map.html
```

The script downloads a lightweight California ZIP GeoJSON boundary file the
first time it runs (or you can supply a custom file via `--geojson`). Open the
generated HTML file in a browser to explore the distribution.

### Resume Interrupted Runs

If the script stops, simply re-run it - it automatically resumes from where it left off.

### View Dataset Statistics

Statistics are printed at the end of the run and can be regenerated without refetching:

```bash
python -c "from dataset_builder.fetch_california_dataset import DatasetFetcher; DatasetFetcher().generate_stats()"
```

The output includes total vehicles, unique VINs, top makes, and price distribution.

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
- Database tracks completed Bay Area zip codes
- Real-time progress updates per zip code processed
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
    limit_per_zip=None,    # Fetch all available vehicles per Bay Area zip code
    rate_limit_delay=0.2   # Seconds between API calls
)

# In fetch_vehicles_for_zip()
params = {
    "retailListing.state": "CA",  # Change state if needed
    "retailListing.zip": zip_code, # Replace or expand with other filters
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
  "SELECT COUNT(*) as completed FROM zip_fetch_progress WHERE status='completed'"
```

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
