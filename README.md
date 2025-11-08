# Interactive Decision Support System (IDSS)

An intelligent conversational AI assistant designed to help users discover and evaluate vehicles through natural dialogue. The system employs a supervisor-based multi-agent architecture built on LangGraph, orchestrating specialized agents to deliver personalized vehicle recommendations.

---

## Installation and Deployment

### Setup Instructions

```bash
# Clone repository
git clone https://github.com/YongceLi/interactive-decision-support-system.git
cd interactive-decision-support-system

# Create conda environment
conda create -n idss python=3.10
conda activate idss

# Install Python dependencies
pip install -r requirements.txt

# Download vehicle database from Google Drive
# Download the car_dataset_idss.zip file from:  https://drive.google.com/drive/folders/17TqIRStI9mwEvcshx4jjzqiN9rLfTcZZ?usp=drive_link
# Extract and place it in the data/ directory:
mkdir -p data
# Extract car_dataset_idss.zip to data/car_dataset_idss/
# The final structure should be: data/car_dataset_idss/uni_vehicles.db

# Create .env file in project root
cat > .env << EOF
OPENAI_API_KEY=your-openai-api-key-here
TAVILY_API_KEY=your-tavily-api-key-here  # for analytical agent web search
AUTODEV_API_KEY=your-autodev-api-key-here  # if using Auto.dev API instead of local DB
EOF

# Start API server
python -m api.server

# In separate terminal, start web interface
cd web
npm install
npm run dev
```

**Note**: The application will be available at:
- API: `http://localhost:8000`
- Web Interface: `http://localhost:3000`

### Database Setup

The system requires the unified vehicle database to function. Due to its size (~840MB), the database is hosted externally.

**Download Instructions:**

1. **Download** the database from Google Drive: `[GOOGLE_DRIVE_LINK_HERE]`
2. **Extract** the downloaded `car_dataset_idss.zip` file
3. **Place** the extracted `car_dataset_idss` folder in the `data/` directory

**Expected directory structure:**
```
interactive-decision-support-system/
├── data/
│   ├── car_dataset_idss/
│   │   └── uni_vehicles.db          # 167,760 vehicles (840MB)
│   ├── feature_data.db
│   ├── safety_data.db
│   └── zip_code_database.csv
```

**Verification:**
```bash
# Verify the database is in the correct location
ls -lh data/car_dataset_idss/uni_vehicles.db

# Should show: uni_vehicles.db (~840MB)
```

**Database Contents:**
- **167,760 vehicles** from nationwide dealers
- Includes both MarketCheck and Auto.dev data sources
- California: 55,818 vehicles with location data
- Price range: $0 - $500,000+
- Years: 1990 - 2026

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Main conversation interface |
| `/session/{id}/event` | POST | Server-Sent Events stream |
| `/session/{id}/favorite` | POST | Mark vehicle as favorite |
| `/session/{id}/history` | GET | Retrieve conversation history |

---

## Project Structure

```
interactive-decision-support-system/
│
├── idss_agent/                     # Core agent system
│   ├── core/
│   │   ├── agent.py                # Main entry point
│   │   ├── supervisor.py           # Supervisor orchestration
│   │   └── request_analyzer.py     # Mode delegation
│   │
│   ├── workflows/
│   │   └── interview.py            # Interview workflow
│   │
│   ├── agents/
│   │   ├── analytical.py           # Analytical ReAct agent
│   │   ├── discovery.py            # Vehicle presentation
│   │   └── general.py              # General conversation
│   │
│   ├── processing/
│   │   ├── semantic_parser.py      # Filter extraction
│   │   ├── recommendation.py       # Vehicle search engine
│   │   └── vector_ranker.py        # Similarity ranking
│   │
│   ├── tools/
│   │   ├── local_vehicle_store.py  # SQLite interface
│   │   ├── zipcode_lookup.py       # Geographic lookup
│   │   └── autodev_api.py          # External API client
│   │
│   ├── state/
│   │   └── schema.py               # State type definitions
│   │
│   └── utils/
│       ├── config.py               # Configuration management
│       ├── logger.py               # Logging utilities
│       └── prompts.py              # Template rendering
│
├── api/                            # FastAPI backend
│   ├── server.py                   # API server
│   └── models.py                   # Request/response models
│
├── web/                            # Next.js frontend
│   └── src/
│       ├── app/
│       └── components/
│
├── config/
│   ├── agent_config.yaml           # System configuration
│   └── prompts/                    # Jinja2 templates
│
├── data/
│   ├── car_dataset_idss/
│   │   └── uni_vehicles.db         # Unified vehicle database (167,760 vehicles, nationwide)
│   ├── feature_data.db             # Vehicle features database
│   ├── safety_data.db              # Safety ratings database
│   └── zip_code_database.csv       # ZIP coordinate data (41,695 ZIP codes)
│
├── tests/                          # Test suites
│   └── test_location_system.py
│
├── review_simulation/              # Review-driven single turn simulator
│   ├── persona.py                  # CSV loaders and affinity parsing
│   ├── simulation.py               # Core simulation + evaluation logic
│   ├── ui.py                       # Rich terminal renderer
│   └── run.py                      # CLI entry point
└── scripts/                        # Utility scripts
    ├── convert_zipcode_to_sqlite.py  # Convert ZIP CSV to SQLite (optional)
    ├── demo.py                       # Demo/testing script
    ├── review_scraper.py             # Fetch top make/model pairs and scrape reviews
    ├── review_enricher.py            # Derive personas from scraped reviews via GPT-4o-mini
    └── test_recommendation.py        # Standalone recommendation runner
```

### Review-based single turn simulation workflow

The repository now includes a complete pipeline for building single-turn user personas straight from real-world review data.

1. **Collect top makes/models and scrape reviews**
   ```bash
   python scripts/review_scraper.py --top-k 10 --output data/reviews/raw_reviews.csv
   ```
   This query looks up the most common make/model pairs in `data/car_dataset_idss/uni_vehicles.db` and downloads up to 20
   consumer reviews per pair from Edmunds. The script stores the consolidated dataset (make, model, review text, rating, date)
   in CSV format. Network hiccups are logged and skipped so partial progress is preserved.

2. **Enrich reviews with GPT-4o-mini**
   ```bash
   python scripts/review_enricher.py data/reviews/raw_reviews.csv --output data/reviews/enriched_reviews.csv
   ```
   Each review is sent to `gpt-4o-mini`, which infers the vehicles/configurations the author likes or dislikes and why, along
   with their intent when seeking a recommender. The output file keeps the original review fields and adds JSON columns
   (`liked_options`, `disliked_options`) plus the natural-language `user_intention` summary.

3. **Run the review-driven simulation**
   ```bash
   python review_simulation/run.py data/reviews/enriched_reviews.csv --max-personas 3 --limit 20 --metric-k 20
   ```
   The simulator creates a single-turn user query for each persona, executes the full recommendation pipeline via
   `scripts/test_recommendation.py`, and has the LLM judge each of the top-k vehicles based on the persona's expressed likes
   and dislikes. A Rich-powered terminal UI displays the persona description, their one-shot message, each recommended
   vehicle (make/model/year/condition/location), the satisfaction verdict, rationale, and precision@k/recall@k metrics.

All steps require the OpenAI API key (set in `.env`). The scraping stage also needs outbound internet access to Edmunds.

---

## System Architecture

### Supervisor Agent

The supervisor agent serves as the central orchestrator, analyzing each user message to determine appropriate agent activation and response coordination.

```
User Message
    ↓
Request Analyzer
    │ - Intent Classification
    │ - Mode Detection
    │ - Analytical Question Extracting 
    ↓
Semantic Parser
    │ - Filter/State Extraction
    ↓
Supervisor Decision Engine
    │ - Agent Selection
    │ - Sub-Agent/Mode Delegation
    ↓
Sub-Agent Execution
    │ - Interview Workflow
    │ - Analytical Agent
    │ - Search/Recommendation
    │ - General Conversation
    ↓
Response Synthesis
    │ - Multi-Mode Integration
    │ - Output Formatting
    ↓
Unified Response to User
```

### Sub-Agent Components

#### Interview Workflow
**Purpose**: Systematic requirement gathering through guided conversation

**Implementation**: `workflows/interview.py`

**Capabilities**:
- Context-aware question generation based on missing information
- Structured preference extraction (budget, usage patterns, priorities)
- Automatic recommendation trigger upon completion
- Configurable question limit (default: 3 turns)

**Output**: Extracted filters and implicit preferences stored in state

---

#### Analytical Agent
**Purpose**: Research-backed insights and vehicle comparisons

**Implementation**: `agents/analytical.py`

**Architecture**: ReAct agent with web search integration (Tavily API)

**Capabilities**:
- Comparative analysis between vehicle models
- Market research and reliability data
- Structured comparison table generation
- Safety ratings and feature comparisons

**Output**: Analytical insights with source citations

---

#### Discovery Agent
**Purpose**: Conversational presentation of vehicle recommendations

**Implementation**: `agents/discovery.py`

**Capabilities**:
- Natural language vehicle presentation
- Context-aware follow-up questions
- Avoids redundant questions from interview phase
- Personalized recommendations based on user preferences

**Output**: Engaging vehicle descriptions with actionable questions

---

#### Search/Recommendation Engine
**Purpose**: Vehicle discovery through semantic matching

**Implementation**: `processing/recommendation.py`

**Pipeline**:
1. SQL-based filtering with user constraints
2. Vehicle deduplication by VIN
3. Photo enrichment (parallel fetching, 8 workers)
4. Vector similarity ranking
5. Multi-dimensional sorting

**Features**:
- Progressive fallback strategy (model → make → open search)
- Geographic filtering via haversine distance
- Configurable result limits (default: 20 vehicles)

---

## State Management

### VehicleSearchState Schema

The system maintains comprehensive state across conversation turns:

```python
{
    # Core Data Structures
    "explicit_filters": VehicleFilters,        # User-specified search criteria
    "conversation_history": List[BaseMessage], # Complete dialogue history
    "implicit_preferences": ImplicitPreferences, # Inferred user preferences
    "recommended_vehicles": List[Dict],        # Current recommendation set

    # Location Data
    "user_latitude": Optional[float],          # From browser geolocation
    "user_longitude": Optional[float],         # From browser geolocation

    # Session Tracking
    "previous_filters": VehicleFilters,        # Change detection
    "interviewed": bool,                       # Interview completion flag
    "questions_asked": List[str],              # Covered topics
    "favorites": List[Dict],                   # User-favorited vehicles
    "interaction_events": List[Dict],          # User interaction log

    # Response Components
    "ai_response": str,                        # Generated response text
    "quick_replies": Optional[List[str]],      # Suggested quick replies
    "comparison_table": Optional[Dict]         # Structured comparison data
}
```

### Filter System

The system supports 17 distinct vehicle filters organized into semantic categories:

| Category | Filters | Type | Example |
|----------|---------|------|---------|
| **Vehicle Specifications** | `make`, `model`, `year`, `trim`, `body_style` | String/Range | `"Honda"`, `"2020-2023"` |
| **Powertrain** | `engine`, `transmission`, `drivetrain`, `fuel_type` | Multi-value | `"Electric,Hybrid"` |
| **Appearance** | `exterior_color`, `interior_color` | Multi-value | `"Red,Blue,White"` |
| **Physical Attributes** | `doors`, `seating_capacity` | Integer | `4`, `7` |
| **Pricing** | `price`, `mileage` | Range | `"20000-30000"`, `"0-50000"` |
| **Location** | `state`, `zip`, `search_radius` | String/Integer | `"CA"`, `"94043"`, `50` |

### Implicit Preference System

The system infers and tracks user preferences beyond explicit filters:

- **Priorities**: Safety, fuel efficiency, reliability, luxury, performance
- **Lifestyle Indicators**: Family-oriented, urban commuter, outdoor enthusiast
- **Usage Patterns**: Daily commuter, weekend trips, family transportation
- **Financial Sensitivity**: Budget-conscious, moderate, luxury-focused
- **Brand Affinity**: Preferred manufacturers based on conversation
- **Concerns**: Maintenance costs, resale value, insurance costs

---

## Data Layer

### Local Vehicle Database

**Technology**: SQLite
**Location**: `data/california_vehicles.db`
**Size**: 22,623 vehicles in California

### Query Construction

Example SQL query generation:

```sql
SELECT raw_json, price, mileage, primary_image_url, photo_count
FROM vehicle_listings
WHERE
    UPPER(make) IN ('HONDA', 'TOYOTA')
    AND year >= 2020 AND year <= 2023
    AND price >= 20000 AND price <= 30000
    AND UPPER(fuel_type) IN ('ELECTRIC', 'HYBRID')
    AND (
        (3959.0 * 2 * ASIN(SQRT(
            POW(SIN((RADIANS(latitude) - RADIANS(37.41)) / 2), 2) +
            COS(RADIANS(37.41)) * COS(RADIANS(latitude)) *
            POW(SIN((RADIANS(longitude) - RADIANS(-122.05)) / 2), 2)
        ))) <= 50.0
    )
    AND (COALESCE(photo_count, 0) > 0 OR primary_image_url IS NOT NULL)
ORDER BY price ASC, vin ASC
LIMIT 60
```

### Vector Similarity Ranking

**Implementation**: `processing/vector_ranker.py`

**Algorithm**:

1. **User Vector Construction**
   - Tokenize explicit filters with semantic weighting
   - Integrate implicit preferences
   - Apply category-specific weights (make: 3.0, color: 1.0)

2. **Vehicle Embedding**
   - Generate per-vehicle token vectors
   - Cache embeddings for performance
   - Include price and mileage bins

3. **Similarity Computation**
   - Calculate cosine similarity between user vector and vehicle embeddings
   - Rank vehicles by similarity score
   - Apply multi-factor sorting (similarity, photos, value ratio)

---

## Location System

### Dual-Mode Architecture

The system implements a two-tier location strategy to maximize geographic search capabilities:

#### Primary Mode: Browser Geolocation

When users grant location permissions, the system directly captures coordinates via the browser's Geolocation API:

```javascript
navigator.geolocation.getCurrentPosition((position) => {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude
});
```

#### Fallback Mode: ZIP Code Lookup

When browser geolocation is unavailable or denied:

1. System prompts user for ZIP code
2. Lookup performed against cached dictionary (41,695 US ZIP codes)
3. ZIP code converted to geocoordinates
4. Same geographic search applied as primary mode

**Implementation**: `tools/zipcode_lookup.py`

### Geographic Distance Calculation

All location-based searches utilize the haversine formula for great-circle distance:

```python
earth_radius = 3959.0  # miles
distance = earth_radius * 2 * ASIN(SQRT(
    POW(SIN((RADIANS(lat1) - RADIANS(lat2)) / 2), 2) +
    COS(RADIANS(lat1)) * COS(RADIANS(lat2)) *
    POW(SIN((RADIANS(lon1) - RADIANS(lon2)) / 2), 2)
))
```

**Default Search Radius**: 100 miles (configurable)

---

## Configuration

### System Configuration (`config/agent_config.yaml`)

#### Model Selection

```yaml
models:
  intent_classifier: gpt-4o-mini
  semantic_parser: gpt-4o-mini
  interview: gpt-4o
  discovery: gpt-4o
  analytical: gpt-4o
  general: gpt-4o-mini
```

#### System Limits

```yaml
limits:
  max_recommended_items: 20
  max_conversation_history: 10
  max_interview_questions: 3
  default_search_radius: 100
  top_vehicles_to_show: 3
  web_search_max_results: 3
```

#### Feature Flags

```yaml
features:
  use_local_vehicle_store: true
  require_photos: true
  enable_quick_replies: true
  enable_streaming: true
```

---

## Testing

### Recommendation Engine Test Script

Test the recommendation pipeline in isolation with natural language queries:

```bash
# Basic usage
python scripts/test_recommendation.py "I want a safe car for my daughter"

# Save to file
python scripts/test_recommendation.py "I want a safe car for my daughter" > results.json
```

**Output**: JSON with extracted filters, SQL query, location data, and 20 recommended vehicles.
