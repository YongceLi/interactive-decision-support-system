# Changelog

All notable changes to the Interactive Decision Support System (IDSS) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## 2025-11-18

### Changed

#### Method 2: Proxy Description → Multi-Filter Sets → Dense Ranking + MMR
- **New Architecture**: `User query → Proxy description → LLM generates 10 distinct filter sets → Parallel SQL → Deduplicate → Dense ranking → MMR → Top 20`
- **Old Architecture**: `User query → Web search (Tavily) → Extract makes → Parallel SQL per make → Vector ranking → Combine`

**Key Improvements:**
1. **No web search dependency** - Pure LLM + SQL approach (faster, no external API)
2. **10 distinct filter sets** - LLM explores different market segments (brand combinations, price ranges, year ranges)
3. **Proxy description generator** - Converts structured filters to natural language for LLM context
4. **Two-tier fallback** - Never returns empty results (explicit_filters → entire database)
5. **Multi-dimensional exploration** - Varies make, price, year, mileage for better coverage
6. **Reuses Method 1 ranking** - Dense embeddings + clustered MMR (proven approach)

**LLM Prompt Constraints:**
- Preserves `must_have_filters` in ALL sets (respects strict requirements)
- Preserves `avoid_vehicles` in ALL sets (critical for user satisfaction)
- Infers ranges from implicit signals (luxury, budget, recent, low-mileage)
- Generates unique filter sets with NO duplicates or heavy overlaps
- Explores multiple dimensions (make, price, year, mileage) not just make/price

**Configuration:**
```yaml
method2:
  top_k: 20                        # Total vehicles to return
  num_filter_sets: 10              # Number of distinct filter sets to generate
  lambda_param: 0.85               # MMR diversity parameter
  cluster_size: 5                  # Vehicles per cluster
```

**Files Modified:**
- `idss_agent/processing/recommendation_method2.py` - Complete rewrite (650 lines)
  - `generate_proxy_description()` - Converts filters to natural language (includes is_used, is_cpo, all filters)
  - `generate_multi_filter_sets()` - LLM generates 10 diverse filter sets with validation
  - `recommend_method2()` - Main pipeline with two-tier fallback
- `config/agent_config.yaml` - Added method2 configuration
- `scripts/test_recommendation_methods.py` - Updated to use `num_filter_sets` parameter

**Example Output:**
```
Proxy: A vehicle SUV, priced between $0 and $30000, prioritizing reliability, with budget-conscious budget focus.

Generated 10 filter sets:
  Set 1: {make: "Toyota,Honda", body_style: "SUV", price: "0-30000"}
  Set 2: {make: "Mazda,Subaru", body_style: "SUV", price: "0-30000", year: "2020-2024"}
  Set 3: {make: "Ford,Chevrolet", body_style: "SUV", price: "0-25000"}
  ... (7 more distinct sets)

Retrieved: 5,250 total vehicles → 3,747 unique → Ranked 1,000 → Selected 20 diverse vehicles
Final diversity: 4 makes, 8 models
```

---

## 2025-11-17

### Added

#### Filter Validation
- Validates categorical filters (body_style, fuel_type, drivetrain, transmission) against database values
- Uses gpt-4o-mini to auto-correct invalid values (e.g., "truck" → "pickup", "ev" → "electric")
- Only calls LLM when value is invalid (valid values pass through)
- Prevents 0-result errors from typos or synonyms
- Files: `filter_validator.py`, `valid_filter_values.json`, `extract_valid_filter_values.py`

---

## 2025-11-14

### Added

#### Quick Reply Testing Script
- **`scripts/test_quick_replies.py`**: Standalone script for testing quick replies and suggested followups
  - Supports single-turn testing with any query
  - Multi-turn conversation testing with state persistence (--save/--state options)
  - Displays agent response, quick replies, suggested followups, and extracted filters
  - Shows which mode was triggered (interview, discovery, analytical, general)
  - Useful for debugging interactive elements without running full API server
  - Usage: `python scripts/test_quick_replies.py "I want a reliable SUV under $30k"`

#### BM25 Final Ranking for Method 1
- **Step 4 re-ranking**: Changed from simple year/price/mileage sorting to BM25 keyword relevance
  - Computes BM25 scores for final 20 vehicles based on user query terms
  - Ranks by keyword relevance to user's actual query (e.g., "reliable", "safety", "family")
  - Falls back to year/price/mileage sorting if BM25 fails
  - Logs top vehicle with BM25 score for debugging
  - File: `idss_agent/processing/recommendation_method1.py` (lines 341-386)

#### NULL Price/Mileage Filtering
- **Dense backfill filtering**: Added NULL checks when backfilling candidates via dense search
  - Ensures vehicles from dense search have valid price and mileage
  - Applies to both main backfill (Step 1.5) and fallback dense search (Step 1b)
  - Prevents incomplete vehicle data from entering final results
  - Files: `idss_agent/processing/recommendation_method1.py` (lines 151-168, 233-259)

#### Negative Filter Support (Avoid Vehicles)
- **`avoid_vehicles` filter**: Allows users to exclude specific vehicles from search results
  - Format: `[{"make": "Toyota", "model": "RAV4"}]` for specific model, `[{"make": "Honda"}]` for entire make
  - Added to `VehicleFiltersPydantic` schema in `idss_agent/state/schema.py`
  - SQL exclusion logic in `idss_agent/tools/local_vehicle_store.py` using `NOT (UPPER(make) = ? AND UPPER(model) = ?)` clauses
  - Semantic parser extracts negative signals: "disappointed with", "hate", "avoid", "never again", "alternatives to"
  - Updated `config/prompts/semantic_parser.j2` with documentation and Example 13 showing negative filter extraction

#### Recommendation Method 1 Major Refactor
- **Switched to Dense Embeddings**: Replaced vector_ranker with dense_ranker using sentence transformers (all-mpnet-base-v2)
- **Clustered MMR Algorithm**: Replaced simple MMR with clustered MMR for better diversity
  - Groups similar vehicles into clusters, then selects diverse representatives
  - Configurable `cluster_size` parameter (default: 3-5 vehicles per cluster)
- **Simplified SQL Strategy**:
  - Old: Hybrid exact matches (40%) + diverse alternatives (60%) with SQL window functions
  - New: Single query with only strict "must_have" filters, no SQL-level diversity
  - Let dense ranking and MMR handle all relevance and diversity
- **Configuration-Driven Parameters**:
  - `top_k`: Number of results to return (default: 20)
  - `lambda_param`: MMR diversity parameter (default: 0.7-0.85)
  - `cluster_size`: Vehicles per cluster (default: 3-5)
  - `vector_limit`: Max candidates for dense ranking (default: 1000)
- **Fallback Search**: When SQL returns no results, automatically falls back to full database dense search
- **Always includes `avoid_vehicles`** in SQL query (even if not in `must_have_filters`)
- Added comprehensive logging for diversity metrics at each step

### Fixed

#### Critical Bug: System Recommending Avoided Vehicles
- **Issue**: User said "disappointed with my 2024 Toyota RAV4" but system returned 20/20 Toyota RAV4 results
- **Root Cause**: `avoid_vehicles` field was documented in prompt but not defined in Pydantic schema, so LLM couldn't extract it
- **Fix**: Added `avoid_vehicles` field to `VehicleFiltersPydantic` schema with detailed extraction guidelines
- **Result**: 0/20 RAV4s in results after fix, system now recommends diverse alternatives (Toyota bZ4X, Audi SQ5, Cadillac XT5, Acura RDX, etc.)

#### Files Modified
- `idss_agent/state/schema.py`: Added `avoid_vehicles` field to VehicleFiltersPydantic (lines 101-110)
- `config/prompts/semantic_parser.j2`: Added Example 13 demonstrating avoid_vehicles extraction
- `idss_agent/tools/local_vehicle_store.py`: Added SQL exclusion logic for avoid_vehicles (lines 341-356)
- `idss_agent/processing/recommendation_method1.py`: Major refactor - dense embeddings, clustered MMR, simplified SQL strategy, avoid_vehicles support
- `idss_agent/processing/diversification.py`: Added clustered MMR algorithm (`diversify_with_clustered_mmr`)
- `idss_agent/processing/dense_ranker.py`: New dense embedding ranking module with sentence transformers
- `config/agent_config.yaml`: Added method1 configuration (top_k, lambda_param, cluster_size, vector_limit)
- `idss_agent/utils/config.py`: Added recommendation config accessor

---

## 2025-11-09

### Added

#### Experimental Recommendation Methods
- **Method 1 (SQL + Vector + MMR)**: Hybrid SQL query with diversity enforcement via window functions (max 20 vehicles per make/model), vector ranking, and MMR diversification (λ=0.7)
- **Method 2 (Web Search + Parallel SQL)**: LLM + web search (Tavily) suggests relevant makes, spawns parallel SQL queries per make, vector ranks within each make, proportional selection ensures diversity
- Created `idss_agent/processing/diversification.py` with MMR algorithm utilities
- Created `idss_agent/processing/recommendation_method1.py` implementing Method 1
- Created `idss_agent/processing/recommendation_method2.py` implementing Method 2 with Tavily integration
- Created `scripts/test_recommendation_methods.py` standalone test script for natural language queries

#### SQL-Level Diversity Enforcement
- Added `max_per_make_model` parameter to `LocalVehicleStore.search_listings()`
- Implemented SQL window functions (`ROW_NUMBER() OVER PARTITION BY make, model`) to limit vehicles per combination
- Prevents homogeneous results when SQL returns clustered data (e.g., 100 Honda Civics)

#### Diversity Statistics
- Added comprehensive diversity metrics to test output: unique makes/models/combinations, distribution counts
- Test scripts output JSON with full vehicle lists and diversity stats

### Documentation
- **README.md**: Added "New Recommendation Methods (Experimental)" section with usage examples and concise method descriptions
- **README.md**: Updated testing section with bash commands for both methods

---

## 2025-11-06

### Changed

#### Database Migration: california_vehicles.db → uni_vehicles.db
- Migrated to unified vehicle database with 7.4x more vehicles (22,623 → 167,760)

#### Semantic Parser Filter Normalization
- Added Valid Filter Options section with exact categorical values from database

### Fixed

#### Filter Extraction Issues
- **Issue**: "compact gas cars" extracted `body_style="compact"` (doesn't exist) → 0 results
- **Fix**: "compact" now goes to `implicit_preferences.priorities` instead
- **Issue**: "electric and hybrid" extracted `engine="electric,hybrid,gas"` (wrong column) → 0 results
- **Fix**: Now correctly uses `fuel_type` filter with normalized values

#### Files Modified
- `idss_agent/tools/local_vehicle_store.py`: Database path, table name, location columns, format transformation
- `config/prompts/semantic_parser.j2`: Added filter normalization guidelines and updated examples
- `README.md`: Updated project structure with new database location, added database download instructions
- `.gitignore`: Added data/car_dataset_idss/ to exclude large database from git

---

## 2025-11-05

### Added

#### Standalone Recommendation Test Script
- Created `scripts/test_recommendation.py` for testing recommendation engine in isolation

### Documentation
- **README.md**: Added "Testing" section with usage examples for recommendation test script
- **README.md**: Updated scripts section to include `test_recommendation.py`

---

## 2025-11-04

### Added

#### Two-Tier Location System
- **Browser Geolocation Priority**: Uses latitude/longitude from browser geolocation API when user shares location
- **ZIP Code Fallback**: If browser location denied, prompts for ZIP code and converts to coordinates
- Created `idss_agent/tools/zipcode_lookup.py` with dictionary-based caching
  - Loads **41,695 US ZIP codes** from CSV into memory (~3 MB)
  - Lazy loading with global cache for O(1) lookups after first load
  - `get_location_from_zip_or_coords()` handles priority logic
- Added `user_latitude` and `user_longitude` to `VehicleSearchState` for location storage
- ZIP code database lookup eliminates need for external geocoding APIs
- Geographic search now works universally with haversine distance calculation

#### New Vehicle Filters
- **`drivetrain` filter**: AWD, FWD, RWD, 4WD (8,676 vehicles with AWD in database)
- **`fuel_type` filter**: Gasoline, Electric, Hybrid, Plug-In Hybrid, Diesel (17,263 gasoline, 3,353 electric)
- Both filters added to:
  - `VehicleFilters` schema (TypedDict + Pydantic)
  - SQL query construction (`local_vehicle_store.py`)
  - Vector ranking system (`vector_ranker.py`)

#### Default Search Radius
- Automatically applies 100-mile search radius when user provides location but no explicit radius
- Configurable via `config/agent_config.yaml`: `limits.default_search_radius`
- Prevents empty results when user shares location without specifying distance

#### Utilities & Scripts
- Created `scripts/convert_zipcode_to_sqlite.py` for converting ZIP CSV to SQLite (optional)
- Created `tests/test_location_system.py` with comprehensive location system tests
- All 5 location tests passing (browser priority, ZIP fallback, geographic search)

### Changed

#### Filter Renaming for Semantic Clarity
- **`miles` → `mileage`**: Renamed to clarify it's vehicle odometer reading (not travel distance)
  - Updated in: `VehicleFilters`, SQL queries, vector ranker
  - Description: "Vehicle's odometer reading in miles (e.g., '0-50000' for cars with under 50k miles)"
- **`distance` → `search_radius`**: Renamed to clarify it's maximum travel distance to dealer
  - Updated in: `VehicleFilters`, SQL queries, haversine calculation
  - Description: "Maximum distance in miles you're willing to travel to pick up vehicle from dealer"
- Prevents LLM confusion between odometer mileage, search radius, and commute distance

#### Location Filtering Architecture
- **Removed ZIP exact-match filtering**: No longer uses `WHERE dealer_zip = '94043'`
- **Geographic-only filtering**: All location searches now use haversine distance calculation
- ZIP code is now an **input method** (converted to coordinates) rather than a **filter**
- Removed `zip` token from vector ranking (no longer a filterable attribute)
- State filter removed from exact-match; kept only for optional state-specific searches

#### Filter-to-SQL Mapping Improvements
- Verified and corrected all 17 filter mappings
- Ensured database columns match filter names or have explicit mapping comments
- Multi-value filters properly handle comma-separated values
- Range filters properly parse "min-max" format

### Removed

#### Features Filter Cleanup
- **Removed `features` filter** from schema (TypedDict + Pydantic)
- Reason: Auto.dev API does not provide structured feature data (sunroof, leather seats, etc.)
- Prevents LLM from extracting non-functional filters that would fail SQL queries
- Removed `features` token from vehicle embeddings in vector ranker

### Fixed

#### Geographic Search Issues
- **Issue**: ZIP code being used as exact match filter instead of coordinate lookup
- **Fix**: Implemented proper two-tier system with coordinate conversion
- **Issue**: Missing search radius when location provided
- **Fix**: Auto-apply default 100-mile radius when location exists but no explicit radius

#### Filter Mapping Correctness
- **Issue**: `miles` (vehicle odometer) confused with `distance` (search radius) and commute distance
- **Fix**: Renamed both filters with explicit descriptions
- **Issue**: `drivetrain` and `fuel_type` columns in database but not exposed as filters
- **Fix**: Added both filters to schema and query construction

#### Location System Consistency
- All location searches now use consistent haversine distance calculation
- SQL queries properly include `WHERE latitude IS NOT NULL AND longitude IS NOT NULL`
- User location properly passed through: API → state → recommendation → SQL

### Documentation

- **README.md**: updated README.md
---

## 2025-10-29

### Added

#### Proactive Favorite Response Feature
- When user favorites a vehicle (clicks ❤️), system immediately generates contextual question about the vehicle
- Added `favorites` field to `VehicleSearchState` to track favorited vehicles in session
- `POST /session/{session_id}/favorite` for handling favorite/unfavorite actions
- Favorite actions logged to `interaction_events` for analytics
- Created `idss_agent/components/proactive_responses.py` for LLM-based response generation
- Created `config/prompts/proactive_favorite.j2` prompt template with detailed instructions
- Added `FavoriteRequest` Pydantic model to `api/models.py`

#### Interview→Discovery Handoff Improvements
- Added `questions_asked` field to `ExtractionResult` model to track topics covered during interview
- Interview extraction now identifies which topics were discussed (budget, location, usage, priorities, etc.)
- Discovery mode receives list of already-covered topics and avoids re-asking
- Enhanced `interview_extraction.j2` prompt with explicit instructions for topic extraction
- Updated `make_initial_recommendation()` to populate `state['questions_asked']` for discovery mode

### Changed

- Suggested Followups Disabled for now.
- Improved prompts for quick reply feature

### Fixed

#### Comparison Table Persistence Bug
- **Issue**: Comparison tables from previous requests were persisting into subsequent non-comparison responses
- **Fix**: Added `state['comparison_table'] = None` at start of supervisor request processing
- Now comparison table only shows when relevant to current response

## 2025-10-28

### Added

#### UI Improvements
- **Responsive layout**: Implemented percentage-based heights (50% recommendations, 40% chat, 10% input) for consistent sizing across screen sizes
- **Enhanced recommendation cards**: Increased card size from 240px to 280px with improved text sizing for better readability
- **Quick reply buttons**: Added dynamic button suggestions below agent responses
- **Agent latency tracking**: Added event logging for agent response times for performance monitoring

#### Event Logging
- **Favorite/unfavorite events**: User favorite actions now logged as `vehicle_favorited` and `vehicle_unfavorited` events
- **Agent latency events**: Response times logged as `agent_latency` events with latency_ms, message, and timestamp
- Added `logFavoriteToggle()` method to LoggingService
- Added `logAgentLatency()` method to LoggingService

### Changed

#### Layout & UI
- Removed counter from recommendation carousel to maximize card space

## 2025-10-24

### Added

#### Interactive Elements Feature
- **Quick Replies**: 
  - Added support for clickable answer options when AI asks direct questions
- **Suggested Follow-ups**: 
  - Added contextual conversation starters (3-5 short phrases) representing user's potential next inputs
  - Examples: "Show me hybrids", "What about safety?", "Compare top 3"

#### State Management
- Added `quick_replies` field to `VehicleSearchState` (Optional[List[str]])
- Added `suggested_followups` field to `VehicleSearchState` (List[str])
- Added `AgentResponse` Pydantic model for unified structured output across modes

#### API Updates
- Updated `ChatResponse` model with `quick_replies` and `suggested_followups` fields
- Updated `/chat` endpoint to return interactive elements
- Updated `/chat/stream` endpoint to include interactive elements in complete event
- Both fields are now included in all API responses

#### Agent Improvements
- **Interview Mode**: Generates quick replies for interview questions and follow-ups for user guidance
- **Discovery Mode**: Generates both quick replies (for questions asked) and follow-ups (for exploration)
- **Analytical Mode**: Post-processes ReAct agent output to generate contextual suggestions
- **General Mode**: Generates follow-ups to guide users into productive conversation modes

#### Documentation
- Created `API_DOCUMENTATION.md` with full endpoint reference
- Added interactive elements section explaining implementation guidelines

#### Demo & Testing
- Updated `scripts/demo.py` to display quick replies and suggested follow-ups
- Updated `notebooks/test_api.ipynb` to showcase interactive elements

#### Configurations
- Added configuration and prompt templates in `idss_agent/config.py` and `config/` folder

### Changed

#### Agent Architecture Change
- Added intent classifier before entering any mode
- Detailed architecture illustration documented in README.md

#### Model Optimization
- Interview mode extraction now uses `gpt-4o-mini` instead of `gpt-4o` for cost efficiency
- Discovery mode uses `gpt-4o` for higher quality vehicle presentations
- Analytical mode uses `gpt-4o-mini` for tool execution and post-processing

#### Response Format
- All agent responses now consistently include interactive elements

#### Dependencies
- Added `PyYAML>=6.0.0` for YAML configuration parsing
- Added `Jinja2>=3.1.0` for prompt template rendering

