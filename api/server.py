"""
FastAPI server for the IDSS Agent.

Provides REST API endpoints for frontend integration with session management.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional, List, Any
import uuid
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import concurrent.futures
import json
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from idss_agent import run_agent, create_initial_state, VehicleSearchState
from api.models import (
    ChatRequest,
    ChatResponse,
    SessionResponse,
    ResetRequest,
    ResetResponse,
    EventRequest,
    EventResponse,
    EventsResponse
)

required_env_vars = ["OPENAI_API_KEY", "AUTODEV_API_KEY"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    print(f" ERROR: Missing required environment variables: {', '.join(missing_vars)}")
    print("  Please set them in your .env file or environment")
    exit(1)

# Initialize FastAPI app
app = FastAPI(
    title="IDSS API",
    description="IDSS API",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, VehicleSearchState] = {}

# Helper Functions
def get_or_create_session(session_id: Optional[str] = None) -> tuple[str, VehicleSearchState]:
    """Get existing session or create new one."""
    if session_id and session_id in sessions:
        return session_id, sessions[session_id]

    # Create new session
    new_session_id = session_id or str(uuid.uuid4())
    sessions[new_session_id] = create_initial_state()
    return new_session_id, sessions[new_session_id]

def format_conversation_history(state: VehicleSearchState) -> List[Dict[str, Any]]:
    """Format conversation history for API response."""
    history = []
    for msg in state.get('conversation_history', []):
        history.append({
            'role': 'user' if msg.__class__.__name__ == 'HumanMessage' else 'assistant',
            'content': msg.content,
            'timestamp': datetime.now().isoformat()  # Add timestamp if needed
        })
    return history


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "IDSS API",
        "version": "1.0.0"
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main conversation endpoint.

    Handles user messages, updates state, and returns AI response with vehicles.
    """
    try:
        # Get or create session
        session_id, state = get_or_create_session(request.session_id)

        # Run the agent
        updated_state = run_agent(request.message, state)

        # Update session storage
        sessions[session_id] = updated_state

        # Prepare response
        return ChatResponse(
            response=updated_state.get('ai_response', ''),
            vehicles=updated_state.get('recommended_vehicles', [])[:20],
            filters=updated_state.get('explicit_filters', {}),
            preferences=updated_state.get('implicit_preferences', {}),
            session_id=session_id,
            interviewed=updated_state.get('interviewed', False)
        )

    except Exception as e:
        import traceback
        error_detail = f"Error processing message: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)  # Print to console for debugging
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming conversation endpoint with Server-Sent Events.

    Streams progress updates in real-time, then sends final response.

    Events:
    - progress: Progress updates during execution
    - complete: Final response with vehicles and session data
    - error: Error information if something goes wrong
    """
    async def event_generator():
        try:
            # Get or create session
            session_id, state = get_or_create_session(request.session_id)

            # Create progress queue for async communication
            progress_queue = asyncio.Queue()

            # Get the event loop in the async context (before threading)
            loop = asyncio.get_running_loop()

            def progress_callback(update: dict):
                """Thread-safe callback to send progress updates."""
                try:
                    # Use the loop from outer scope
                    asyncio.run_coroutine_threadsafe(
                        progress_queue.put(update),
                        loop
                    )
                except Exception as e:
                    print(f"Error in progress_callback: {e}")

            # Run agent in thread pool to avoid blocking event loop
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Submit agent execution to thread pool
                future = executor.submit(run_agent, request.message, state, progress_callback)

                # Stream progress updates while agent is running
                while not future.done():
                    try:
                        # Wait for progress update with timeout
                        update = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                        yield {
                            "event": "progress",
                            "data": json.dumps(update)
                        }
                    except asyncio.TimeoutError:
                        # No update available, continue waiting
                        continue

                # Drain any remaining progress updates
                while not progress_queue.empty():
                    try:
                        update = progress_queue.get_nowait()
                        yield {
                            "event": "progress",
                            "data": json.dumps(update)
                        }
                    except asyncio.QueueEmpty:
                        break

                # Get final result from agent
                updated_state = future.result()

            # Update session storage
            sessions[session_id] = updated_state

            # Send final response
            yield {
                "event": "complete",
                "data": json.dumps({
                    "response": updated_state.get('ai_response', ''),
                    "vehicles": updated_state.get('recommended_vehicles', [])[:20],
                    "filters": updated_state.get('explicit_filters', {}),
                    "preferences": updated_state.get('implicit_preferences', {}),
                    "session_id": session_id,
                    "interviewed": updated_state.get('interviewed', False)
                })
            }

        except Exception as e:
            import traceback
            error_detail = f"Error processing message: {str(e)}\n{traceback.format_exc()}"
            print(error_detail)  # Print to console for debugging

            # Send error event
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": str(e),
                    "detail": error_detail
                })
            }

    return EventSourceResponse(event_generator())


@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """
    Get current session state.

    Returns filters, preferences, vehicles, and conversation history.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id]

    return SessionResponse(
        session_id=session_id,
        filters=state.get('explicit_filters', {}),
        preferences=state.get('implicit_preferences', {}),
        vehicles=state.get('recommended_vehicles', [])[:10],
        conversation_history=format_conversation_history(state)
    )


@app.post("/session/reset", response_model=ResetResponse)
async def reset_session(request: ResetRequest):
    """
    Reset session or create new one.

    Clears all state and starts fresh conversation.
    """
    session_id = request.session_id

    if not session_id:
        session_id = str(uuid.uuid4())

    # Create fresh state
    sessions[session_id] = create_initial_state()

    return ResetResponse(
        session_id=session_id,
        status="reset"
    )


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session (cleanup)."""
    if session_id in sessions:
        del sessions[session_id]
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/sessions")
async def list_sessions():
    """List all active sessions (for debugging)."""
    return {
        "active_sessions": len(sessions),
        "session_ids": list(sessions.keys())
    }


@app.post("/session/{session_id}/event", response_model=EventResponse)
async def log_event(session_id: str, request: EventRequest):
    """
    Log a user interaction event.

    Tracks user interactions with the UI such as:
    - vehicle_view: User views vehicle details
    - vehicle_click: User clicks on a vehicle
    - photo_view: User views vehicle photos
    - link_click: User clicks external links
    - custom: Any other custom event

    Vehicle-related events (vehicle_view, vehicle_click, photo_view) must include 'vin' in data.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id]

    # Generate timestamp if not provided
    timestamp = request.timestamp or datetime.now().isoformat()

    # Create event record
    event = {
        "event_type": request.event_type,
        "timestamp": timestamp,
        "data": request.data
    }

    # Add to session state
    state['interaction_events'].append(event)
    event_id = len(state['interaction_events']) - 1

    return EventResponse(
        status="logged",
        event_id=event_id,
        timestamp=timestamp
    )


@app.get("/session/{session_id}/events", response_model=EventsResponse)
async def get_events(session_id: str, event_type: Optional[str] = None):
    """
    Get all interaction events for a session.

    Optional query parameter:
    - event_type: Filter events by type (e.g., ?event_type=vehicle_view)
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id]
    events = state.get('interaction_events', [])

    # Filter by event type if specified
    if event_type:
        events = [e for e in events if e.get('event_type') == event_type]

    return EventsResponse(
        session_id=session_id,
        events=events,
        total=len(events)
    )


if __name__ == "__main__":
    import uvicorn

    print("Starting Vehicle Search Agent API Server...")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 70)

    uvicorn.run(app, host="0.0.0.0", port=8000)
