-- California Vehicle Listings Dataset Schema
-- This schema is optimized for fast filtering and searching while preserving complete data

CREATE TABLE IF NOT EXISTS vehicle_listings (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vin TEXT NOT NULL UNIQUE,  -- 17-character VIN (unique identifier)

    -- Vehicle Information (commonly filtered fields)
    year INTEGER,
    make TEXT,
    model TEXT,
    trim TEXT,
    body_style TEXT,
    drivetrain TEXT,
    engine TEXT,
    fuel_type TEXT,
    transmission TEXT,
    doors INTEGER,
    seats INTEGER,
    exterior_color TEXT,
    interior_color TEXT,

    -- Retail Listing Information
    price INTEGER,  -- Price in USD
    mileage INTEGER,  -- Odometer reading
    is_used BOOLEAN,
    is_cpo BOOLEAN,  -- Certified Pre-Owned

    -- Dealer/Location Information
    dealer_name TEXT,
    dealer_city TEXT,
    dealer_state TEXT,  -- 2-letter state code (CA for California)
    dealer_zip TEXT,
    longitude REAL,
    latitude REAL,

    -- Photos
    primary_image_url TEXT,
    photo_count INTEGER DEFAULT 0,

    -- URLs
    vdp_url TEXT,  -- Vehicle Detail Page
    carfax_url TEXT,

    -- Metadata
    listing_created_at TEXT,  -- When the listing was created
    online BOOLEAN,  -- Whether available online
    data_fetched_at TEXT,  -- When we fetched this data

    -- Complete JSON Payload (for full data access)
    raw_json TEXT,  -- Complete JSON from API

    -- Search optimization indexes will be created separately
    CONSTRAINT valid_vin CHECK (length(vin) = 17)
);

-- Indexes for fast filtering (most common search patterns)
CREATE INDEX IF NOT EXISTS idx_make_model ON vehicle_listings(make, model);
CREATE INDEX IF NOT EXISTS idx_year ON vehicle_listings(year);
CREATE INDEX IF NOT EXISTS idx_price ON vehicle_listings(price);
CREATE INDEX IF NOT EXISTS idx_mileage ON vehicle_listings(mileage);
CREATE INDEX IF NOT EXISTS idx_body_style ON vehicle_listings(body_style);
CREATE INDEX IF NOT EXISTS idx_make ON vehicle_listings(make);
CREATE INDEX IF NOT EXISTS idx_state ON vehicle_listings(dealer_state);
CREATE INDEX IF NOT EXISTS idx_fuel_type ON vehicle_listings(fuel_type);

-- Composite indexes for common filter combinations
CREATE INDEX IF NOT EXISTS idx_make_model_year ON vehicle_listings(make, model, year);
CREATE INDEX IF NOT EXISTS idx_make_price ON vehicle_listings(make, price);
CREATE INDEX IF NOT EXISTS idx_body_style_price ON vehicle_listings(body_style, price);

-- Progress tracking table
CREATE TABLE IF NOT EXISTS fetch_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    vehicles_fetched INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL,
    status TEXT DEFAULT 'completed',  -- 'completed', 'failed', 'partial'
    error_message TEXT,
    UNIQUE(make, model)
);

-- Statistics table (optional, for quick stats access)
CREATE TABLE IF NOT EXISTS dataset_stats (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
