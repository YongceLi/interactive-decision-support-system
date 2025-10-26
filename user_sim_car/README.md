# User Simulation for Car Recommendation Agent

This repository contains a **LangGraph-based user simulator** that interacts with the car recommendation backend. It simulates realistic shoppers with distinct personalities and interaction styles.

## Key Features

- **Persona pipeline**: A seed persona is expanded in parallel by 4 shaper agents:
  - *Family background* (size, location, preferences)
  - *Writing style* (grammar, spelling, consistency)
  - *Interaction style* (clarification-seeking, topic coherence)
  - *Intent* (market research, checking, comparing)
- **Conversation summary agent**: Maintains an accumulating summary of the dialogue and UI activity. Each new turn is fused with the running memory before the user agent plans its next move.
- **Judge agent**: Scores every simulated reply (0–1 alignment) against persona + intent before it is accepted. If the score drops below `0.75`, the user agent is reminded and re-drafts the turn.
- **User Agent (multi-action)**: Generates the next user message plus **zero-or-many** UI actions such as:
  - `{"type": "CLICK_CARD", "index": 0|1|2}`
  - `{"type": "TOGGLE_FILTER", "id": "suv"}` / `{"type": "SET_MILEAGE", "value": 60000}`
  - `{"type": "REFRESH_FILTERS"}`, `{"type": "SHOW_FAVORITES"}`, `{"type": "CLOSE_DETAIL"}`
  - fallback navigation actions: `SCROLL`, `STARE`, `STOP`
- **Rich UI model**: Mirrors the Next.js front-end — carousel cards, filter drawer (tokens + Refresh button), favorites tray, and detail modal selection state.
- **RL-style stop scorer**: Two channels (`positive`, `negative`) updated **after each assistant response**. The critic returns deltas that are discounted/accumulated (γ ∈ [0.5, 0.99]); thresholds are derived from the persona. Crossing a threshold records a structured `stop_result`.
- **Demo snapshots (optional)**: When `demo_mode=True`, every turn stores a JSON snapshot (scores, judge verdict, summary excerpt) for UI playback.
- **Event logging**: Posts to `POST /session/{session_id}/event` with payload `{"event_type":"...", "data":{"details":{...}}}`.

## API Contract

### POST `/chat`

**Request** (first key must be `"message"`):

```json
{
  "message": "I want a Jeep around $30k in Colorado",
  "ui_context": {
    "start": 0,
    "visible_count": 3,
    "selection": null,
    "filters": {},
    "favorites": [],
    "detail_open": false
  },
  "meta": {
    "step": 0,
    "actions": [],
    "summary": "",
    "judge": null
  }
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
{"event_type":"post_turn_metrics", "data":{"details":{"scores":{"positive":0.41,"negative":0.18}, "step":3}}}
```

## Files

- `user_sim_car/adapter.py` — API client.
- `user_sim_car/graph.py` — LangGraph graph & agents.
- `user_sim_car/run_demo.py` — CLI runner example (supports demo snapshots).

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
python user_sim_car/run_demo.py --demo
```

Use `--persona "..."` to supply a custom seed persona or `--max-steps` to shorten/extend the session.

**JSON feed (for `web_simulation`)**
```bash
python user_sim_car/run_web_simulation.py --max-steps 8 > latest-run.json
```

The script mirrors the CLI runner but always enables demo snapshots and emits a
single JSON document suitable for UI playback. `stdin` can be used to stream a
persona instead of the `--persona` flag.

**Notebook**
Open `demo_user_sim_car.ipynb` in Jupyter and run the cells.
