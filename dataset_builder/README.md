# California Vehicle Dataset Builder

Build a comprehensive local SQLite database of California vehicle listings for the MVP, eliminating high-latency API calls.

## Overview

This module fetches vehicle listings from California's Bay Area (zip codes listed in `bay_area_zip.csv`) across all 2,479 make/model combinations found in `safety_data.db` and stores them in a fast, queryable SQLite database.

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
- **Years**: 2018-2026
- **Mileage Range**: 0-150,000 miles
- **Vehicles per Model**: All available Bay Area listings (new and used when present)
- **Total Make/Model Combinations**: 2,479
- **Expected API Calls**: Dependent on available inventory in Bay Area (fewer than statewide)
- **Estimated Runtime**: 8-12 minutes (varies with API responses)
- **Database Size**: Dependent on available inventory (smaller than statewide dataset)

## Files

```
dataset_builder/
├── README.md                     # This file
├── schema.sql                    # SQLite database schema
├── fetch_california_dataset.py   # Main fetcher script
└── (output) → data/california_vehicles.db
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

The script automatically:

1. Loads Bay Area zip codes from `dataset_builder/bay_area_zip.csv`
2. Iterates over all make/model combinations in `data/safety_data.db`
3. Fetches every available Bay Area listing per model, balancing new and used requests
4. Restricts all API requests to the Bay Area zip codes
5. Stores the deduplicated (by VIN) results in `data/california_vehicles.db`

### Output

Creates `data/california_vehicles.db` with:
- `vehicle_listings` table: All vehicles with indexed fields
- `fetch_progress` table: Progress tracking for resume support

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
    limit_per_model=None,    # Fetch all available vehicles per make/model
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
