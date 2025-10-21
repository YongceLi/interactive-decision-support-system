# User Simulation for Car Recommendation Agent

This repository contains a **LangGraph-based user simulator** that interacts with a car recommendation backend. It simulates realistic shoppers with distinct personalities and interaction styles.

## Key Features

- **Personality pipeline**: A seed persona is expanded in parallel by 4 shaper agents:
  - *Family background* (size, location, preferences)
  - *Writing style* (grammar, spelling, consistency)
  - *Interaction style* (clarification-seeking, topic coherence)
  - *Intent* (market research, checking, comparing)
- **User Agent** (multi-action): Generates the next user message + **zero-or-many** UI actions:
  - `{"type": "CLICK_CARD", "index": 0|1|2}`
  - `{"type": "APPLY_FILTER", "filters": {...}}`
  - `{"type": "SCROLL"}` | `{"type": "STARE"}` | `{"type": "STOP"}`
- **UI model**: Only **top-3 vehicles** (picture, make/model, price, mileage) are visible at a time. To see more details about a car, the user must **click the card**.
- **Stop-score model (optional)**: Three channels in `[0,1]` - `positive`, `neutral`, `negative`. The system:
  - Derives **thresholds** and **initial scores** from persona.
  - **Does not update on the first turn**.
  - Updates scores on later turns.
  - Stops if any score crosses its threshold (and records a structured `stop_result`).
- **Event logging**: Posts to `POST /session/{session_id}/event` with payload:
  `{"event_type":"...", "data":{"details":{...}}}`

## API Contract

### POST `/chat`

**Request** (first key must be `"message"`):

```json
{
  "message": "I want a Jeep around $30k in Colorado",
  "ui_context": {"start": 0, "visible_count": 3, "selection": null},
  "meta": {"step": 0, "actions": []}
}
```

**Response**:

```json
{
  "session_id": "abc123",
  "response": "Here are some options ...",
  "vehicles": [
    {"make":"Toyota","model":"RAV4","price":28500,"mileage":32000,"image_url":"..."},
    {"make":"Subaru","model":"Outback","price":30100,"mileage":29000,"image_url":"..."},
    {"make":"Honda","model":"CR-V","price":29500,"mileage":27000,"image_url":"..."}
  ]
}
```

### POST `/session/{session_id}/event`

**Payload**:

```json
{"event_type":"user_actions_planned", "data":{"details":{"actions":[...], "step":1}}}
```

## Files

- `user_sim_car/adapter.py` — API client.
- `user_sim_car/graph.py` — LangGraph graph & agents.
- `user_sim_car/run_demo.py` — CLI runner example.

## Setup

```bash
pip install langgraph langchain langchain-openai requests
export CARREC_BASE_URL="http://localhost:8000"
export OPENAI_API_KEY="sk-..."
# Windows: make a .env file contain:
# CARREC_BASE_URL="http://localhost:8000"
# OPENAI_API_KEY="sk-..."
```

## Running

**CLI**
```bash
python user_sim_car/run_demo.py
```

**Notebook**
Open `demo_user_sim_car.ipynb` in Jupyter and run the cells.
