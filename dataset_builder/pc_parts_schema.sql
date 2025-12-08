-- PC Parts Dataset Schema
-- Sparse dataset with dynamic attribute columns
-- Each attribute is stored as a separate column, allowing NULL values for attributes not applicable to a product type

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
    year INTEGER,                         -- Release year (important for knowledge graph)

    -- Pricing & seller
    price REAL,                      -- Minimum price across all sellers
    seller TEXT,                         -- Seller with minimum price (best deal)
    rating REAL,                         -- Product rating
    rating_count INTEGER,                -- Number of ratings

    -- CPU Attributes
    socket TEXT,                         -- CPU socket type (e.g., 'LGA 1700', 'AM5', 'sTR5')
    architecture TEXT,                   -- CPU architecture (e.g., 'Intel Core', 'AMD Ryzen')
    pcie_version TEXT,                   -- PCIe version supported (e.g., '5.0', '4.0')
    ram_standard TEXT,                   -- RAM standard supported (e.g., 'DDR5', 'DDR4')
    tdp TEXT,                            -- Thermal Design Power in watts (e.g., '125')

    -- GPU Attributes
    vram TEXT,                           -- Video RAM in GB (e.g., '12', '16')
    memory_type TEXT,                    -- Memory type (e.g., 'GDDR6X', 'GDDR6')
    cooler_type TEXT,                    -- Cooler type (e.g., 'air', 'liquid', 'blower')
    variant TEXT,                        -- GPU variant (e.g., 'Founders Edition', 'OC', 'Gaming')
    is_oc TEXT,                          -- Whether overclocked (boolean: 'true', 'false')
    revision TEXT,                       -- Revision number (e.g., 'A1', 'Rev 2.0')
    interface TEXT,                      -- PCIe interface (e.g., 'PCIe 4.0 x16', 'PCIe 5.0 x16')
    power_connector TEXT,                -- Power connector type (e.g., '8-pin + 8-pin', '12VHPWR')

    -- Motherboard Attributes
    chipset TEXT,                        -- Chipset model (e.g., 'Z790', 'B650', 'X570')
    form_factor TEXT,                   -- Form factor (e.g., 'ATX', 'Micro-ATX', 'Mini-ITX', 'E-ATX')

    -- PSU Attributes
    wattage TEXT,                        -- Total wattage in watts (e.g., '850', '1000')
    certification TEXT,                  -- Efficiency certification (e.g., '80+ Gold', '80+ Platinum', '80+ Bronze')
    modularity TEXT,                     -- Modularity type (e.g., 'fully modular', 'semi-modular', 'non-modular')
    atx_version TEXT,                   -- ATX version (e.g., 'ATX 3.0', 'ATX 2.52')
    noise TEXT,                          -- Noise level in dB (e.g., '20', '25')
    supports_pcie5_power TEXT,          -- Whether supports PCIe 5.0 power connector (boolean: 'true', 'false')

    -- Case Attributes
    storage TEXT,                        -- Storage drive support (e.g., '2x 3.5"', '4x 2.5"')
    capacity TEXT,                       -- Total capacity in GB or TB (e.g., '1000', '2TB')
    storage_type TEXT,                   -- Storage type (e.g., 'SSD', 'HDD', 'NVMe')

    -- RAM Attributes (ram_standard already defined above)
    -- form_factor already defined above for motherboards, reused for RAM

    -- Cooling Attributes
    cooling_type TEXT,                   -- Cooling type (e.g., 'air', 'liquid', 'AIO')
    tdp_support TEXT,                    -- TDP support in watts (e.g., '250', '300')

    -- Audit metadata
    created_at TEXT NOT NULL,            -- ISO timestamp when record was created
    updated_at TEXT,                     -- ISO timestamp when record was last updated (optional)

    -- Additional field
    raw_name TEXT,                       -- Raw product name from source
    imageurl TEXT                        -- URL to product image
);

-- Indexes to support fast filtering
CREATE INDEX IF NOT EXISTS idx_pc_parts_type ON pc_parts(product_type);
CREATE INDEX IF NOT EXISTS idx_pc_parts_price ON pc_parts(price);
CREATE INDEX IF NOT EXISTS idx_pc_parts_brand ON pc_parts(brand);
CREATE INDEX IF NOT EXISTS idx_pc_parts_year ON pc_parts(year);
CREATE INDEX IF NOT EXISTS idx_pc_parts_rating ON pc_parts(rating);

-- Indexes for common attribute filters
CREATE INDEX IF NOT EXISTS idx_pc_parts_socket ON pc_parts(socket);
CREATE INDEX IF NOT EXISTS idx_pc_parts_chipset ON pc_parts(chipset);
CREATE INDEX IF NOT EXISTS idx_pc_parts_form_factor ON pc_parts(form_factor);
CREATE INDEX IF NOT EXISTS idx_pc_parts_ram_standard ON pc_parts(ram_standard);
CREATE INDEX IF NOT EXISTS idx_pc_parts_wattage ON pc_parts(wattage);

-- Progress tracking table
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
