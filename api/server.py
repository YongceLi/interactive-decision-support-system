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

load_dotenv()

from idss_agent import run_agent, create_initial_state, VehicleSearchState
from api.models import (
    ChatRequest,
    ChatResponse,
    SessionResponse,
    ResetRequest,
    ResetResponse
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

# Configure request size limits
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Add gzip compression to reduce response size
app.add_middleware(GZipMiddleware, minimum_size=1000)

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


def create_lightweight_vehicles(vehicles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create lightweight vehicle objects for API response to reduce payload size."""
    lightweight_vehicles = []
    
    for vehicle in vehicles[:10]:  # Limit to 10 vehicles
        # Debug: Print vehicle structure for first vehicle
        if len(lightweight_vehicles) == 0:
            print(f"DEBUG: Vehicle structure: {json.dumps(vehicle, indent=2)[:500]}...")
        
        # Handle auto.dev API nested structure
        vehicle_data = vehicle.get('vehicle', vehicle)
        retail_listing = vehicle.get('retailListing', {})
        
        # Extract price from various possible locations
        price = None
        if retail_listing.get('price'):
            price = retail_listing['price']
        elif retail_listing.get('listPrice'):
            price = retail_listing['listPrice']
        elif vehicle.get('price'):
            price = vehicle['price']
        elif vehicle_data.get('price'):
            price = vehicle_data['price']
        
        # Extract mileage from various possible locations
        mileage = None
        if retail_listing.get('miles'):
            mileage = retail_listing['miles']
        elif vehicle_data.get('mileage'):
            mileage = vehicle_data['mileage']
        elif vehicle.get('mileage'):
            mileage = vehicle['mileage']
        elif retail_listing.get('mileage'):
            mileage = retail_listing['mileage']
        
        # Extract location - prefer city/state over coordinates
        location = None
        if retail_listing.get('city') and retail_listing.get('state'):
            location = f"{retail_listing['city']}, {retail_listing['state']}"
        elif retail_listing.get('state'):
            location = retail_listing['state']
        elif retail_listing.get('city'):
            location = retail_listing['city']
        elif vehicle_data.get('location'):
            location = vehicle_data['location']
        elif vehicle.get('location'):
            location = vehicle['location']
        
        # Skip vehicles with invalid location data
        if location and location.strip() in ['00', '0', '']:
            location = None
        
        # Extract VIN
        vin = vehicle_data.get('vin') or vehicle.get('vin')
        
        lightweight = {
            'id': vehicle_data.get('id', vehicle.get('id', '')),
            'make': vehicle_data.get('make', vehicle.get('make', '')),
            'model': vehicle_data.get('model', vehicle.get('model', '')),
            'year': vehicle_data.get('year', vehicle.get('year', 0)),
            'price': price,
            'mileage': mileage,
            'location': location,
            'vin': vin,
            'trim': vehicle_data.get('trim', vehicle.get('trim')),
            'body_style': vehicle_data.get('bodyStyle', vehicle_data.get('body_style', vehicle.get('body_style'))),
            'exterior_color': vehicle_data.get('exteriorColor', vehicle_data.get('exterior_color', vehicle.get('exterior_color'))),
        }
        
        # Only include fuel economy if available
        if vehicle_data.get('fuel_economy') or vehicle.get('fuel_economy'):
            fuel_data = vehicle_data.get('fuel_economy', vehicle.get('fuel_economy', {}))
            lightweight['fuel_economy'] = {
                'combined': fuel_data.get('combined', 0)
            }
        
        # Only include safety rating if available
        if vehicle_data.get('safety_rating') or vehicle.get('safety_rating'):
            safety_data = vehicle_data.get('safety_rating', vehicle.get('safety_rating', {}))
            lightweight['safety_rating'] = {
                'overall': safety_data.get('overall', 0)
            }
        
        lightweight_vehicles.append(lightweight)
    
    return lightweight_vehicles


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

        # Prepare response with lightweight vehicle data
        recommended_vehicles = updated_state.get('recommended_vehicles', [])
        lightweight_vehicles = create_lightweight_vehicles(recommended_vehicles)
        
        return ChatResponse(
            response=updated_state.get('ai_response', ''),
            vehicles=lightweight_vehicles,
            filters=updated_state.get('explicit_filters', {}),
            preferences=updated_state.get('implicit_preferences', {}),
            session_id=session_id
        )

    except Exception as e:
        import traceback
        error_detail = f"Error processing message: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)  # Print to console for debugging
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """
    Get current session state.

    Returns filters, preferences, vehicles, and conversation history.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id]

    recommended_vehicles = state.get('recommended_vehicles', [])
    lightweight_vehicles = create_lightweight_vehicles(recommended_vehicles)
    
    return SessionResponse(
        session_id=session_id,
        filters=state.get('explicit_filters', {}),
        preferences=state.get('implicit_preferences', {}),
        vehicles=lightweight_vehicles,
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


if __name__ == "__main__":
    import uvicorn

    print("Starting Vehicle Search Agent API Server...")
    print("API Documentation: http://localhost:8000/docs")
    print("=" * 70)

    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        # Increase limits to handle larger requests
        limit_max_requests=1000,
        limit_concurrency=100
    )
