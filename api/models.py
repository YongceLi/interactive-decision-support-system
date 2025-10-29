"""
Pydantic models for API requests and responses.
"""
from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    session_id: Optional[str] = None
    latitude: Optional[float] = None  # User's location latitude
    longitude: Optional[float] = None  # User's location longitude


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str
    vehicles: List[Dict[str, Any]]
    filters: Dict[str, Any]
    preferences: Dict[str, Any]
    session_id: str
    interviewed: bool = False  # False = in interview, True = interview completed
    quick_replies: Optional[List[str]] = None  # Short answer options (1-3 words, 2-4 options)
    suggested_followups: List[str] = []  # Suggested next queries (short phrases, 3-5 options)
    comparison_table: Optional[Dict[str, Any]] = None  # Comparison table when user asks to compare vehicles


class SessionResponse(BaseModel):
    """Response model for session state endpoint."""
    session_id: str
    filters: Dict[str, Any]
    preferences: Dict[str, Any]
    vehicles: List[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]]


class ResetRequest(BaseModel):
    """Request model for session reset."""
    session_id: Optional[str] = None


class ResetResponse(BaseModel):
    """Response model for session reset."""
    session_id: str
    status: str


class EventRequest(BaseModel):
    """Request model for logging user interaction events."""
    event_type: str
    data: Dict[str, Any] = {}
    timestamp: Optional[str] = None

    @field_validator('data')
    @classmethod
    def validate_vehicle_event(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        """Ensure vehicle-related events include VIN."""
        event_type = info.data.get('event_type', '')
        vehicle_event_types = ['vehicle_view', 'vehicle_click', 'photo_view']

        if event_type in vehicle_event_types:
            if 'vin' not in v or not v['vin']:
                raise ValueError(f"{event_type} events must include 'vin' in data")

        return v


class EventResponse(BaseModel):
    """Response model after logging an event."""
    status: str
    event_id: int
    timestamp: str


class EventsResponse(BaseModel):
    """Response model for retrieving events."""
    session_id: str
    events: List[Dict[str, Any]]
    total: int
