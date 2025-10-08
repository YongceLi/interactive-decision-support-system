"""
Pydantic models for API requests and responses.
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any, List


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str
    vehicles: List[Dict[str, Any]]
    filters: Dict[str, Any]
    preferences: Dict[str, Any]
    session_id: str


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
