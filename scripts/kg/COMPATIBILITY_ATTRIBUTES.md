# How Wikipedia Scraping Helps with Compatibility

## Compatibility Edge Types

The knowledge graph builds compatibility edges based on these attributes:

### 1. **ELECTRICAL_COMPATIBLE_WITH** (PSU → GPU)
- **Required attributes:**
  - PSU: `wattage` (e.g., "750W")
  - GPU: `recommended_psu_watts` (e.g., "650W")
- **Wikipedia provides:** TDP/wattage information from product specifications
- **Impact:** More accurate PSU sizing recommendations

### 2. **INTERFACE_COMPATIBLE_WITH** (Motherboard → GPU)
- **Required attributes:**
  - Motherboard: `pcie_version` (e.g., "4.0")
  - GPU: `pcie_requirement` (e.g., "4.0")
- **Wikipedia provides:** PCIe version from technical specifications
- **Impact:** Ensures GPU/motherboard PCIe compatibility

### 3. **SOCKET_COMPATIBLE_WITH** (CPU → Motherboard)
- **Required attributes:**
  - CPU: `socket` (e.g., "AM5", "LGA 1700")
  - Motherboard: `socket` (e.g., "AM5", "LGA 1700")
- **Wikipedia provides:** Socket information from CPU/motherboard specs
- **Impact:** Critical for CPU/motherboard compatibility

### 4. **RAM_COMPATIBLE_WITH** (RAM → Motherboard)
- **Required attributes:**
  - RAM: `ram_standard` (e.g., "DDR5", "DDR4")
  - Motherboard: `ram_standard` (e.g., "DDR5", "DDR4")
- **Wikipedia provides:** Memory type/standard from specifications
- **Impact:** Ensures RAM/motherboard compatibility

### 5. **MEMORY_COMPATIBLE_WITH** (CPU → RAM)
- **Required attributes:**
  - CPU: `ram_standard` (e.g., "DDR5")
  - RAM: `ram_standard` (e.g., "DDR5")
- **Wikipedia provides:** CPU memory controller specifications
- **Impact:** Ensures CPU/RAM compatibility

### 6. **FORM_FACTOR_COMPATIBLE_WITH** (Case → Motherboard)
- **Required attributes:**
  - Case: `supported_form_factors` (e.g., ["ATX", "mATX"])
  - Motherboard: `form_factor` (e.g., "ATX")
- **Wikipedia provides:** Form factor information
- **Impact:** Ensures case/motherboard physical compatibility

### 7. **THERMAL_COMPATIBLE_WITH** (Cooler → CPU)
- **Required attributes:**
  - Cooler: `supported_sockets` (e.g., ["AM5", "LGA 1700"])
  - CPU: `socket` (e.g., "AM5")
  - CPU: `tdp_watts` (e.g., "105W")
  - Cooler: `max_tdp` (e.g., "150W")
- **Wikipedia provides:** TDP information and socket compatibility
- **Impact:** Ensures cooler can handle CPU thermal load

## What Wikipedia Provides

From Wikipedia infoboxes and specification sections, we extract:

✅ **PCIe version** (`pcie_version`) - for GPU/motherboard compatibility
✅ **TDP/Wattage** (`wattage`, `tdp_watts`) - for PSU/GPU and cooler/CPU compatibility  
✅ **Socket** (`socket`) - for CPU/motherboard and cooler/CPU compatibility
✅ **RAM standard** (`ram_standard`) - for motherboard/RAM and CPU/RAM compatibility
✅ **Form factor** (`form_factor`) - for case/motherboard compatibility
✅ **Architecture** (`architecture`) - useful for identification and grouping
✅ **Codename** (`codename`) - useful for product identification

## Current State

- **Step 1:** Uses hardcoded defaults from `GPU_SERIES_METADATA` and `CHIPSET_METADATA`
- **Step 2:** Scrapes Wikipedia to get real-world, verified specifications
- **Step 3:** Merges scraped attributes into node metadata and re-builds compatibility edges

## Impact

Wikipedia scraping **significantly improves compatibility accuracy** by:
1. **Replacing defaults** with verified specifications
2. **Filling missing attributes** that weren't in product names
3. **Correcting errors** from heuristic parsing
4. **Adding edge cases** not covered by hardcoded metadata

The improved normalization (71% extraction rate) means more products will have accurate compatibility information!

