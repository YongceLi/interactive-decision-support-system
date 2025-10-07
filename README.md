# IDSS

A conversational product decision support assistant built with LangGraph that helps users find and evaluate vehicles through natural dialogue.

## Architecture Overview
 ![Workflow Graph](graph_visualization.png)
The agent uses a multi-node LangGraph workflow with two operating modes:
- **Discovery Mode** (simple mode, simple LLM node): Helps users explore and refine their vehicle search, asking questions to get user's implicit preferences.
- **Analytical Mode** (complex mode, ReAct agent with SQL database, api tools, etc.): Answers specific questions about vehicles using tools. E.g. compare two vehicles, list features of a vehicle, etc.

## State Variables

```python
VehicleSearchState = {
    "explicit_filters": VehicleFilters,           # Extracted search criteria
    "conversation_history": List[BaseMessage],    # Full chat history
    "implicit_preferences": ImplicitPreferences,  # Inferred preferences
    "recommended_vehicles": List[Dict],           # Top 20 matches
    "questions_asked": List[str],                 # Topics already discussed
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

## Node Descriptions

### 1. Semantic Parser
- extract structured data from user's natural language input
- Merges new filters with existing state
- Updates implicit preferences throughout conversation

### 2. Update Recommendations
- ReAct agent with API tools and SQL database
- Update the recommended list everytime the filter changes

### 3. Mode Router
- **Discovery**: When user update filters and preferences, or ask simple questions, the discovery agent will describe the current recommendation list and ask follow-up questions to extract more user preferences.
- **Analytical**: When user ask more complex questions that needs tool use / query database. E.g. compare the pros and cons of two vehicles.

### 4. Discovery Responder
- Displays top 10 vehicles with details
- Summarizes listings with recommendations
- Asks 2-3 elicitation questions
- Tracks questions to avoid repetition

### 5. Analytical Responder
- ReAct agent with multiple tools:
  - `get_vehicle_listing`: Detailed listing of vehicles given filters.
  - `get_vehicle_listing_by_vin`: Detailed listing by VIN
  - `get_vehicle_photos_by_vin`: Photos by VIN
  - SQL tools: `sql_db_query`, `sql_db_schema`, `sql_db_list_tables`
- Can query safety_data (NHTSA ratings) and feature_data (EPA fuel economy) databases

## Project Structure

```
.
├── state_schema.py           # State definitions
├── semantic_parser.py        # Semantic parsing node
├── recommendation_agent.py   # Vehicle search with ReAct
├── mode_router.py            # Discovery vs analytical routing
├── discovery_agent.py        # Vehicle listing & questions
├── analytical_agent.py       # Answer questions with tools
├── vehicle_agent.py          # Main workflow
├── demo.py                   # Interactive demo
├── tools/
│   ├── autodev_apis.py      # Auto.dev API tools
│   └── vehicle_database.py  # SQL database tools
├── safety_data.db           # NHTSA safety ratings
├── feature_data.db          # EPA fuel economy data
└── requirements.txt
```

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

```bash
pip install -r requirements.txt
```

Set environment variables:
- `OPENAI_API_KEY`
- `AUTODEV_API_KEY`

## Usage

### Interactive Demo

```bash
python demo.py
```

Commands: `state` (view filters), `reset`, `quit`/`exit`

