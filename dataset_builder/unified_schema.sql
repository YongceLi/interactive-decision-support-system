-- Unified Vehicle Listings Schema
-- Combines Auto.dev and Marketcheck listing fields into a single table.

CREATE TABLE IF NOT EXISTS unified_vehicle_listings (
    vin TEXT PRIMARY KEY,

    -- Listing level metadata
    listing_id TEXT,
    heading TEXT,
    source TEXT NOT NULL, -- autodev or marketcheck

    -- Pricing and mileage
    price INTEGER,
    mileage INTEGER,
    msrp INTEGER,
    ref_price INTEGER,
    price_change_percent REAL,
    ref_price_dt INTEGER,
    ref_miles INTEGER,
    ref_miles_dt INTEGER,

    -- Temporal metadata
    listing_created_at TEXT,
    online INTEGER,
    first_seen_at INTEGER,
    first_seen_at_date TEXT,
    first_seen_at_source INTEGER,
    first_seen_at_source_date TEXT,
    first_seen_at_mc INTEGER,
    first_seen_at_mc_date TEXT,
    last_seen_at INTEGER,
    last_seen_at_date TEXT,
    scraped_at INTEGER,
    scraped_at_date TEXT,
    data_fetched_at TEXT,

    -- Vehicle build/description
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
    base_ext_color TEXT,
    base_int_color TEXT,

    -- Marketcheck build data
    build_year INTEGER,
    build_make TEXT,
    build_model TEXT,
    build_trim TEXT,
    build_version TEXT,
    build_body_type TEXT,
    build_vehicle_type TEXT,
    build_transmission TEXT,
    build_drivetrain TEXT,
    build_fuel_type TEXT,
    build_engine TEXT,
    build_doors INTEGER,
    build_cylinders INTEGER,
    build_std_seating TEXT,
    build_highway_mpg INTEGER,
    build_city_mpg INTEGER,

    -- Listing classification
    seller_type TEXT,
    inventory_type TEXT,
    availability_status TEXT,
    is_certified INTEGER,
    is_cpo INTEGER,
    is_used INTEGER,
    in_transit INTEGER,
    model_code TEXT,
    stock_number TEXT,

    -- Dealer/location information
    dealer_name TEXT,
    dealer_city TEXT,
    dealer_state TEXT,
    dealer_zip TEXT,
    dealer_phone TEXT,
    dealer_latitude REAL,
    dealer_longitude REAL,
    dealer_country TEXT,
    dealer_type TEXT,
    dealer_msa_code TEXT,
    dist REAL,

    -- Media and links
    vdp_url TEXT,
    carfax_url TEXT,
    primary_image_url TEXT,
    photo_count INTEGER,
    media_json TEXT,

    -- Financial options
    financing_options_json TEXT,
    leasing_options_json TEXT,

    -- Dealer/build raw JSON blobs
    dealer_json TEXT,
    mc_dealership_json TEXT,
    build_json TEXT,

    -- Data provenance
    data_source TEXT,
    carfax_one_owner INTEGER,
    carfax_clean_title INTEGER,

    -- Days on market metrics
    dom INTEGER,
    dom_180 INTEGER,
    dom_active INTEGER,
    dos_active INTEGER,

    -- Raw payload
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_unified_make_model ON unified_vehicle_listings(make, model);
CREATE INDEX IF NOT EXISTS idx_unified_year ON unified_vehicle_listings(year);
CREATE INDEX IF NOT EXISTS idx_unified_price ON unified_vehicle_listings(price);
CREATE INDEX IF NOT EXISTS idx_unified_mileage ON unified_vehicle_listings(mileage);
CREATE INDEX IF NOT EXISTS idx_unified_inventory ON unified_vehicle_listings(inventory_type);
CREATE INDEX IF NOT EXISTS idx_unified_source ON unified_vehicle_listings(source);
