# Changelog

All notable changes to the Interactive Decision Support System (IDSS) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

#### Knowledge Graph Integration for PC Parts Recommendations
- **Neo4j Knowledge Graph**: PC parts recommendations now query Neo4j knowledge graph instead of SQLite for PC components
- **Automatic Routing**: System automatically detects PC parts queries and routes to Neo4j; other electronics use SQLite
- **Compatibility Checking**: Added compatibility checking using knowledge graph relationships (socket, PCIe, RAM, power, form factor, thermal)
- **Updated Files**:
  - `idss_agent/processing/recommendation.py`: Added Neo4j routing and product normalization
  - `idss_agent/processing/recommendation_method1.py`: Integrated Neo4j queries for PC parts
  - `idss_agent/processing/recommendation_method2.py`: Integrated Neo4j queries for PC parts
  - `idss_agent/agents/analytical.py`: Updated product search to use Neo4j for PC parts
  - `idss_agent/tools/kg_compatibility.py`: Added `search_products` method for flexible KG queries
- **Consumer Product Filtering**: Added filtering to prioritize consumer products over professional/workstation products
- **Fallback Strategy**: Gracefully falls back to SQLite if Neo4j is unavailable

#### Knowledge Graph Building Script
- **Created**: `scripts/kg/build_kg_from_augmented.py` - Builds Neo4j knowledge graph from augmented database
- **Features**:
  - Loads products from `pc_parts_augmented.db`
  - Creates `PCProduct` nodes with type-specific labels
  - Creates compatibility relationships based on attribute matching
  - Replaces entire graph (purges existing nodes first)
  - Creates indexes for performance

#### Database Augmentation System
- **Created**: `scripts/kg/augment_pc_parts_db.py` - Augments base database with validated attributes
- **Features**:
  - Scrapes attributes from multiple sources (Newegg, Amazon, Wikipedia, Manufacturer)
  - Cross-source validation (requires at least 2 sources to agree)
  - Stores validated attributes with source tracking and confidence scores
  - Tags products for manual review if no manufacturer source found

### Changed

#### Recommendation System: RapidAPI → Local Database + Neo4j Knowledge Graph
- **Migration**: Switched from RapidAPI product search API to local SQLite database (`pc_parts.db`)
- **New Module**: Created `idss_agent/tools/local_electronics_store.py` for querying local electronics database
- **Updated Files**:
  - `idss_agent/processing/recommendation.py`: Now uses `LocalElectronicsStore` instead of RapidAPI
  - `idss_agent/processing/recommendation_method1.py`: Updated to query local database
  - `idss_agent/processing/recommendation_method2.py`: Updated to query local database
- **Benefits**: 
  - No API rate limits or costs
  - Faster query performance
  - Offline operation capability
  - Consistent data format
- **Note**: RapidAPI integration (`idss_agent/tools/electronics_api.py`) remains available for database population via dataset builder script

#### Similarity Score Filtering
- **Fixed**: Recommendation system now filters out items with similarity score of 0
- **Updated Files**:
  - `idss_agent/processing/vector_ranker.py`: Added filtering for zero similarity scores
  - `idss_agent/processing/recommendation_method1.py`: Added additional filtering after ranking
  - `idss_agent/processing/recommendation_method2.py`: Added filtering when selecting products per brand
- **Impact**: Prevents irrelevant products with zero similarity from appearing in recommendations

### Documentation

- **Consolidated**: All documentation merged into unified `README.md` in root directory
- **Moved**: API documentation to `api/README.md` (updated for PC parts domain)
- **Moved**: UI documentation to `web/README.md` (updated for current architecture)
- **Moved**: `.env.example` from `docs/` to root directory
- **Updated**: `CHANGELOG.md` with all missing changes
- **Deleted**: Removed `docs/ELECTRONICS_DOMAIN.md`, `docs/KNOWLEDGE_GRAPH.md`, `DEV_SETUP.md` (content merged into README)
- **Updated**: API documentation reflects PC parts domain and Neo4j integration
- **Updated**: UI documentation reflects current frontend architecture

### Fixed

#### Environment Variable Requirements
- **Changed**: `AUTODEV_API_KEY` no longer required (made optional, only used for legacy vehicle image support)
- **Updated**: `api/server.py` to only require `OPENAI_API_KEY`

---

## 2025-11-11

### Added

#### Electronics Vector Ranking & Diversification
- `idss_agent/processing/vector_ranker.py`, `idss_agent/processing/diversification.py`: migrated embeddings to electronics-focused tokenization with optional sqlite caching and added Maximal Marginal Relevance diversification utilities.

#### Modular Recommendation Methods
- `idss_agent/processing/recommendation_method1.py`, `idss_agent/processing/recommendation_method2.py`, `idss_agent/processing/__init__.py`: introduced reusable RapidAPI pipelines (primary+exploratory search and Tavily-guided parallel search) that share normalization and ranking helpers.

### Changed

#### Recommendation Test Harness
- `scripts/test_recommendation.py`: updated the standalone CLI to operate purely in the electronics domain, surface RapidAPI payload diagnostics, and report product-centric results.

#### Supervisor Entry Point Cleanup
- `idss_agent/core/agent.py`, `config/agent_config.yaml`, `docs/agent_architecture_updates.md`: removed the temporary `single_turn_conversations` feature flag so all user turns flow through the supervisor, cleaning up configuration and documentation.

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

## 2025-11-11

### Changed

#### Conversation Logging
- Conversation logs are now stored per session (single file per conversation) instead of per turn.
- Each log persists both the latest turn latency and the running average latency for the session.

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

