-- PC Parts Dataset Schema
-- Mirrors the structure of california_vehicles.db with normalized attributes,
-- search-friendly indexes, and complete raw payload preservation.

CREATE TABLE IF NOT EXISTS pc_parts (
    -- Primary Key
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Unique identifiers
    part_id TEXT NOT NULL UNIQUE,        -- Canonical identifier (source:id)
    source TEXT NOT NULL,                -- Data source (pcpartpicker, bestbuy, rapidapi)

    -- Core product metadata
    part_type TEXT NOT NULL,             -- Component category (cpu, gpu, motherboard, etc.)
    manufacturer TEXT,
    product_name TEXT NOT NULL,
    model_number TEXT,
    series TEXT,

    -- Pricing & availability
    price REAL,
    currency TEXT DEFAULT 'USD',
    availability TEXT,                   -- Free-form availability text
    stock_status TEXT,                   -- Normalized stock status (in_stock, out_of_stock, preorder, unknown)
    seller TEXT,                         -- Retailer or marketplace name

    -- Ratings & engagement
    rating REAL,
    review_count INTEGER,

    -- Media & references
    url TEXT,
    image_url TEXT,
    description TEXT,

    -- Structured attributes
    specs_json TEXT,                     -- JSON blob for technical specs (clock speeds, chipset, etc.)
    attributes_json TEXT,                -- JSON for miscellaneous attributes (warranty, bundle info, etc.)

    -- Audit metadata
    data_fetched_at TEXT NOT NULL,       -- ISO timestamp when record was fetched
    last_seen_at TEXT,                   -- ISO timestamp when record was last observed in source

    -- Complete raw payload
    raw_json TEXT                        -- Original payload for traceability
);

-- Indexes to support fast filtering (mirrors vehicle dataset philosophy)
CREATE INDEX IF NOT EXISTS idx_pc_parts_type ON pc_parts(part_type);
CREATE INDEX IF NOT EXISTS idx_pc_parts_manufacturer ON pc_parts(manufacturer);
CREATE INDEX IF NOT EXISTS idx_pc_parts_price ON pc_parts(price);
CREATE INDEX IF NOT EXISTS idx_pc_parts_source ON pc_parts(source);
CREATE INDEX IF NOT EXISTS idx_pc_parts_type_manufacturer ON pc_parts(part_type, manufacturer);

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

