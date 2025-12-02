-- PC Parts Dataset Schema
-- Mirrors the structure of california_vehicles.db with normalized attributes,
-- search-friendly indexes, and complete raw payload preservation.

CREATE TABLE IF NOT EXISTS pc_parts (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Unique identifiers
    product_id TEXT NOT NULL UNIQUE,     -- Canonical product identifier
    slug TEXT NOT NULL UNIQUE,           -- brand + series + model (computed field)

    -- Core product metadata
    product_type TEXT NOT NULL,          -- Component category (cpu, gpu, motherboard, etc.)
    series TEXT,
    model TEXT,
    brand TEXT,

    -- Optional attributes
    size TEXT,                           -- Optional
    color TEXT,                          -- Optional

    -- Pricing & seller
    price REAL,                          -- Minimum price (for backward compatibility)
    price_min REAL,                      -- Minimum price across all sellers
    price_max REAL,                      -- Maximum price across all sellers
    price_avg REAL,                      -- Average price across all sellers
    year INTEGER,
    seller TEXT,                         -- Current retailer or marketplace name (for backward compatibility)
    sellers TEXT,                        -- Comma-delimited list of all sellers
    rating REAL,                         -- Product rating
    rating_count INTEGER,                -- Number of ratings

    -- Structured attributes
    base_attributes TEXT,                -- JSON string for base attributes

    -- Audit metadata
    created_at TEXT NOT NULL,            -- ISO timestamp when record was created
    updated_at TEXT,                     -- ISO timestamp when record was last updated (optional)

    -- Additional field
    raw_name TEXT                        -- Raw product name from source
);

-- Indexes to support fast filtering (mirrors vehicle dataset philosophy)
CREATE INDEX IF NOT EXISTS idx_pc_parts_type ON pc_parts(product_type);
CREATE INDEX IF NOT EXISTS idx_pc_parts_seller ON pc_parts(seller);
CREATE INDEX IF NOT EXISTS idx_pc_parts_price ON pc_parts(price);
CREATE INDEX IF NOT EXISTS idx_pc_parts_brand ON pc_parts(brand);
CREATE INDEX IF NOT EXISTS idx_pc_parts_year ON pc_parts(year);
CREATE INDEX IF NOT EXISTS idx_pc_parts_rating ON pc_parts(rating);

-- Progress tracking table (inspired by fetch_progress in vehicle dataset)
CREATE TABLE IF NOT EXISTS pc_parts_fetch_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    part_type TEXT NOT NULL,
    items_fetched INTEGER DEFAULT 0,
    fetched_at TEXT NOT NULL,
    status TEXT DEFAULT 'completed',     -- completed, failed, partial
    error_message TEXT,
    UNIQUE(source, part_type)
);

-- Dataset statistics table (optional quick stats cache)
CREATE TABLE IF NOT EXISTS pc_parts_dataset_stats (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

