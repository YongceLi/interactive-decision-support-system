# IDSS

A conversational product decision support assistant built with LangGraph that helps users find and evaluate vehicles through natural dialogue.

## 📐 Complete System Architecture

**🎨 [View Complete Visual System Architecture →](IDSS_workflow.png)**

## Architecture Overview

The agent uses an **intent-based routing architecture** that classifies user intent on every message and routes to the appropriate mode:

## State Variables

```python
VehicleSearchState = {
    # Core data
    "explicit_filters": VehicleFilters,           # Extracted search criteria
    "conversation_history": List[BaseMessage],    # Full chat history (with prompt caching)
    "implicit_preferences": ImplicitPreferences,  # Inferred preferences
    "recommended_vehicles": List[Dict],           # Top 20 matches

    # Intent-based routing (NEW)
    "current_intent": str,                        # Latest intent (buying/browsing/research/general)
    "current_mode": str,                          # Current mode (buying/discovery/analytical/general)
    "intent_history": List[IntentRecord],         # All intent classifications
    "mode_switch_count": int,                     # Number of mode switches

    # Tracking
    "previous_filters": VehicleFilters,           # Previous filters for change detection
    "interviewed": bool,                          # Interview completion status

    # Note: Discovery agent determines what to ask by checking missing filters/preferences
    # rather than tracking abstract question topics

    # Output
    "ai_response": str                            # Latest response
}
```

**VehicleFilters** (extracted from user input):
- Basic: make, model, year, body_style, transmission, fuel_type, drivetrain
- Pricing: price_min, price_max, miles_max
- Appearance: exterior_color, interior_color
- Physical: seating_capacity, doors
- Location: state, zip, distance

**ImplicitPreferences** (inferred):
- priorities, lifestyle, budget_sensitivity, concerns, brand_affinity

## Component Descriptions

### 1. Intent Classifier (`intent_classifier.py`)
- Classifies user intent on every message using GPT-4o-mini
- Returns intent, confidence score, and reasoning
- Uses full conversation history with prompt caching for efficiency
- Intents: buying, browsing, research, general

### 2. Mode Handlers

#### Buying Mode (`modes/buying_mode.py`)
- Routes to interview workflow if not interviewed
- Updates recommendations if already interviewed
- Preserves interview state across mode switches

#### Discovery Mode (`modes/discovery_mode.py`)
- Semantic parser extracts filters
- Updates recommendations when filters change
- Discovery agent shows vehicles and asks elicitation questions
- No interview required

#### Analytical Mode (`modes/analytical_mode.py`)
- Semantic parser extracts vehicle mentions
- Conditionally updates recommendations (only if vehicle filters detected)
- ReAct agent with tools answers data-driven questions

#### General Mode (`modes/general_mode.py`)
- Simple conversational responses
- Handles greetings, thanks, meta questions
- Uses last 3 messages for context

### 3. Semantic Parser (`semantic_parser.py`)
- Extracts structured filters from natural language
- Merges new filters with existing state
- Updates implicit preferences throughout conversation
- Handles ranges, multiple values, and complex queries

### 4. Discovery Agent (`discovery.py`)
- Generates friendly vehicle summaries
- Highlights top vehicle with bullet points
- Intelligently asks 1-2 strategic questions based on missing filters/preferences
- Questions focus on what's unknown in the current state (budget, location, usage, priorities)
- Self-correcting: always asks about missing information, never redundant

### 5. Analytical Agent (`analytical.py`)
- ReAct agent with multiple tools:
  - `get_vehicle_listing_by_vin`: Detailed listing by VIN
  - `get_vehicle_photos_by_vin`: Photos by VIN
  - `sql_db_query`, `sql_db_schema`, `sql_db_list_tables`: Database queries
- Can query safety_data (NHTSA ratings) and feature_data (EPA fuel economy) databases

### 6. Recommendation Engine (`recommendation.py`)
- Searches Auto.dev API for matching vehicles
- Deduplicates by VIN (keeps lowest price)
- Fetches photos in parallel (up to 8 workers)
- Returns up to 20 vehicles

## Tools & Data Sources

### Auto.dev API
- `search_vehicle_listings`: Search millions of active vehicle listings
- `get_vehicle_listing_by_vin`: Get detailed info for specific VIN
- `get_vehicle_photos_by_vin`: Get photos for specific VIN

### SQL Databases
- **safety_data.db**: NHTSA crash tests, safety ratings, features (query by make, model, model_yr)
- **feature_data.db**: EPA MPG ratings, fuel economy, emissions, engine specs (query by Make, Model, Year)

Both databases combined using SQLite ATTACH for unified querying.

## Installation

### 1. Create Conda Environment

```bash
conda create -n idss python=3.10
conda activate idss
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Environment Variables

Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_key_here
AUTODEV_API_KEY=your_autodev_key_here

# Optional: Prioritize vehicles with photos in recommendations (default: false)
REQUIRE_PHOTOS_IN_RECOMMENDATIONS=true
```

## Usage

### Interactive CLI Demo

```bash
python scripts/demo.py
```

Commands: `state` (view filters), `reset`, `quit`/`exit`

### API Server

Start the server:
```bash
python api/server.py
```

Stop the server:
```bash
# Press Ctrl+C for graceful shutdown
```

API Documentation: http://localhost:8000/docs

### API Endpoints

- `GET /` - Health check
- `POST /chat` - Main conversation endpoint
  - Request: `{"message": "I want a Jeep", "session_id": "optional"}`
  - Response: `{"response": "...", "vehicles": [...], "filters": {...}, "preferences": {...}, "session_id": "..."}`
- `GET /session/{session_id}` - Get session state
- `POST /session/reset` - Reset session
- `DELETE /session/{session_id}` - Delete session
- `GET /sessions` - List all active sessions (debug)
