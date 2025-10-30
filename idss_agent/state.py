"""
State schema for the vehicle search agent.
"""
from typing import TypedDict, Optional, List, Dict, Any, Annotated, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from datetime import datetime


class VehicleFilters(TypedDict, total=False):
    """
    Explicit vehicle search filters extracted from user input.
    Types match AutoDev API tool parameters.
    """
    # Vehicle specification filters
    make: Optional[str]  # e.g., "Toyota" or "Ford,Chevrolet" (comma-separated for multiple)
    model: Optional[str]  # e.g., "Camry" or "F-150,Silverado"
    year: Optional[str]  # e.g., "2018" or "2018-2020" (range format)
    trim: Optional[str]  # e.g., "XLT" or "XLT,Lariat"
    body_style: Optional[str]  # e.g., "sedan" or "suv,truck"
    engine: Optional[str]  # e.g., "2.0L" or "2.0L,3.5L"
    transmission: Optional[str]  # e.g., "automatic" or "automatic,manual"

    # Color filters
    exterior_color: Optional[str]  # e.g., "white" or "white,black,silver"
    interior_color: Optional[str]  # e.g., "black" or "black,beige,gray"

    # Physical attributes
    doors: Optional[int]  # e.g., 2, 4
    seating_capacity: Optional[int]  # e.g., 5, 7, 8

    # Retail listing filters
    price: Optional[str]  # e.g., "10000-30000" (range format)
    state: Optional[str]  # e.g., "CA", "NY"
    miles: Optional[str]  # e.g., "0-50000" (range format)

    # Location filters
    zip: Optional[str]  # 5-digit ZIP code
    distance: Optional[int]  # Search radius in miles from ZIP

    # Additional features
    features: Optional[List[str]]  # e.g., ["sunroof", "leather seats", "navigation"]


class ImplicitPreferences(TypedDict, total=False):
    """Implicit user preferences inferred from conversation."""
    priorities: Optional[List[str]]  # e.g., ["fuel_efficiency", "safety", "reliability", "luxury"]
    lifestyle: Optional[str]  # e.g., "family-oriented", "outdoorsy", "urban commuter", "performance enthusiast"
    budget_sensitivity: Optional[str]  # e.g., "budget-conscious", "moderate", "luxury-focused"
    brand_affinity: Optional[List[str]]  # Brands user seems to prefer based on conversation
    concerns: Optional[List[str]]  # e.g., ["maintenance costs", "resale value", "insurance costs", "reliability"]
    usage_patterns: Optional[str]  # e.g., "daily commuter", "weekend trips", "family road trips"
    notes: Optional[str]  # Any other inferred information


# Pydantic versions for LLM structured output (mirror TypedDict structure)

class VehicleFiltersPydantic(BaseModel):
    """Pydantic version of VehicleFilters for LLM structured output."""
    # Vehicle specification filters
    make: Optional[str] = Field(None, description="e.g., 'Toyota' or 'Ford,Chevrolet' (comma-separated)")
    model: Optional[str] = Field(None, description="e.g., 'Camry' or 'F-150,Silverado'")
    year: Optional[str] = Field(None, description="e.g., '2018' or '2018-2020' (range format)")
    trim: Optional[str] = Field(None, description="e.g., 'XLT' or 'XLT,Lariat'")
    body_style: Optional[str] = Field(None, description="e.g., 'sedan' or 'suv,truck'")
    engine: Optional[str] = Field(None, description="e.g., '2.0L' or '2.0L,3.5L'")
    transmission: Optional[str] = Field(None, description="e.g., 'automatic' or 'automatic,manual'")

    # Color filters
    exterior_color: Optional[str] = Field(None, description="e.g., 'white' or 'white,black,silver'")
    interior_color: Optional[str] = Field(None, description="e.g., 'black' or 'black,beige,gray'")

    # Physical attributes
    doors: Optional[int] = Field(None, description="e.g., 2, 4")
    seating_capacity: Optional[int] = Field(None, description="e.g., 5, 7, 8")

    # Retail listing filters
    price: Optional[str] = Field(None, description="e.g., '10000-30000' (range format)")
    state: Optional[str] = Field(None, description="e.g., 'CA', 'NY'")
    miles: Optional[str] = Field(None, description="e.g., '0-50000' (range format)")

    # Location filters
    zip: Optional[str] = Field(None, description="5-digit ZIP code")
    distance: Optional[int] = Field(None, description="Search radius in miles from ZIP")

    # Additional features
    features: Optional[List[str]] = Field(None, description="e.g., ['sunroof', 'leather seats', 'navigation']")


class ImplicitPreferencesPydantic(BaseModel):
    """Pydantic version of ImplicitPreferences for LLM structured output."""
    priorities: Optional[List[str]] = Field(
        None,
        description=(
            "User's top priorities inferred from phrases like 'safe', 'reliable', 'fuel efficient', 'luxurious', 'spacious'. "
            "Extract from: 'safe car' → ['safety'], 'reliable vehicle' → ['reliability'], 'good on gas' → ['fuel_efficiency']. "
            "Common values: 'safety', 'reliability', 'fuel_efficiency', 'luxury', 'performance', 'space', 'technology'"
        )
    )
    lifestyle: Optional[str] = Field(
        None,
        description=(
            "User's lifestyle inferred from context clues like 'family', 'kids', 'outdoor adventures', 'city driving', 'commute'. "
            "Extract from: 'have kids' → 'family-oriented', 'weekend camping' → 'outdoorsy', 'drive to work daily' → 'urban commuter'. "
            "Common values: 'family-oriented', 'outdoorsy', 'urban commuter', 'performance enthusiast', 'business professional'"
        )
    )
    budget_sensitivity: Optional[str] = Field(
        None,
        description=(
            "User's budget consciousness inferred from price mentions and financial language. "
            "Extract from: 'cheapest option' → 'budget-conscious', 'reasonable price' → 'moderate', 'money is not an issue' → 'luxury-focused'. "
            "Common values: 'budget-conscious', 'moderate', 'luxury-focused'"
        )
    )
    brand_affinity: Optional[List[str]] = Field(
        None,
        description=(
            "Brands the user shows preference for through positive mentions or repeated references. "
            "Extract from: 'I love Toyota' → ['Toyota'], 'always driven Honda and Mazda' → ['Honda', 'Mazda']"
        )
    )
    concerns: Optional[List[str]] = Field(
        None,
        description=(
            "User's worries or negative priorities inferred from phrases like 'expensive to maintain', 'high insurance', 'bad resale'. "
            "Extract from: 'low maintenance' → ['maintenance costs'], 'cheap to fix' → ['repair costs'], 'holds value' → ['resale value']. "
            "Common values: 'maintenance costs', 'repair costs', 'insurance costs', 'resale value', 'reliability issues', 'fuel costs'"
        )
    )
    usage_patterns: Optional[str] = Field(
        None,
        description=(
            "How the user plans to use the vehicle, inferred from purpose statements. "
            "Extract from: 'drive to work every day' → 'daily commuter', 'for my teenager' → 'teenage driver', 'road trips with family' → 'family road trips'. "
            "Common values: 'daily commuter', 'weekend trips', 'family road trips', 'teenage driver', 'work vehicle', 'occasional use'"
        )
    )
    notes: Optional[str] = Field(
        None,
        description="Any other contextual information that doesn't fit other fields but seems important for understanding user needs"
    )


class ComparisonTable(BaseModel):
    """
    Structured comparison table for comparing vehicles.

    Used when user asks to compare 2-4 vehicles (e.g., "compare Honda Accord vs Toyota Camry").
    """
    headers: List[str] = Field(
        description="Column headers: first is 'Attribute', rest are vehicle names like 'Honda Accord 2024'"
    )
    rows: List[List[str]] = Field(
        description=(
            "Each row is a list of values. First value is the attribute name, "
            "rest are values for each vehicle. "
            "Example attributes: 'Price Range', 'Safety Rating', 'Fuel Economy (City)', etc."
        )
    )


class AgentResponse(BaseModel):
    """
    Unified response schema for agent modes using structured output.

    Used by: interview, discovery, and general modes.
    Analytical mode generates this separately after ReAct agent completes.
    """
    ai_response: str = Field(
        description="The main conversational response to the user (keep concise, 2-4 sentences)",
        max_length=800
    )
    quick_replies: Optional[List[str]] = Field(
        default=None,
        description=(
            "Short answer options (2-5 words each) for direct questions in ai_response. "
            "Provide 2-4 options. Only include if ai_response asks a direct question. "
            "Examples: ['Under $20k', '$20k-$30k'], ['Yes', 'No'], ['Sedan', 'SUV']"
        ),
        max_length=4
    )
    suggested_followups: List[str] = Field(
        description=(
            "Suggested user's potential next queries to help users continue conversation. "
        ),
        min_length=0,
        max_length=5
    )
    comparison_table: Optional[ComparisonTable] = Field(
        default=None,
        description=(
            "Comparison table for when user asks to compare 2-4 vehicles. "
            "Leave null if not a comparison query. "
            "When provided, include key attributes like price, safety, fuel economy, etc."
        )
    )


# Intent tracking for new architecture
class IntentRecord(BaseModel):
    """Record of an intent classification."""
    intent: Literal["buying", "browsing", "research", "general"] = Field(
        description="Classified user intent"
    )
    confidence: float = Field(
        description="Confidence score between 0 and 1",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(
        description="Brief explanation of classification"
    )
    timestamp: str = Field(
        description="ISO timestamp of classification"
    )
    message_index: int = Field(
        description="Index of message in conversation that triggered this classification"
    )


# Progress tracking for execution visibility
class ProgressStep(TypedDict):
    """A single step in the execution progress."""
    step_id: str  # Unique identifier: "intent_classification", "semantic_parsing", etc.
    description: str  # Human-readable description: "Classifying user intent..."
    status: Literal["pending", "in_progress", "completed", "failed"]  # Current status
    timestamp: float  # Unix timestamp when step started/completed


class ExecutionProgress(TypedDict):
    """Tracks execution progress for streaming to UI."""
    current_step_index: int  # 0-based index of current step
    total_steps: int  # Total number of steps for this mode
    steps: List[ProgressStep]  # All steps with their statuses
    mode: str  # Current mode: "buying", "discovery", "analytical", "general"


class VehicleSearchState(TypedDict):
    """
    Complete state for the vehicle search agent.

    This state is updated throughout the conversation and maintains:
    - Explicit filters from user requests
    - Conversation history using LangChain messages (with add_messages reducer)
    - Implicit preferences inferred from dialogue
    - Recommended vehicles (up to 20, updated each turn)
    - Questions asked to avoid repetition
    - AI response for current turn
    - User interaction events for tracking engagement
    - Interview mode tracking and insights
    """
    # Core data
    explicit_filters: VehicleFilters
    conversation_history: Annotated[List[BaseMessage], add_messages] 
    implicit_preferences: ImplicitPreferences

    # Results (up to MAX_RECOMMENDED_VEHICLES vehicles, updated each turn)
    recommended_vehicles: List[Dict[str, Any]]

    # Metadata
    questions_asked: List[str]  # Track questions to avoid repetition
    previous_filters: VehicleFilters  # Track previous filters to detect changes

    # User interaction tracking
    interaction_events: List[Dict[str, Any]]  # Track user interactions with UI
    favorites: List[Dict[str, Any]]  # List of vehicles favorited by user

    # Interview phase tracking
    interviewed: bool  # False = in interview workflow, True = interview complete
    _interview_should_end: bool  # Internal flag for routing within interview workflow

    # Intent-based routing (NEW)
    current_intent: str  # Latest classified intent (buying/browsing/research/general)
    current_mode: str  # Current operational mode (buying/discovery/analytical/general)
    intent_history: List[Dict[str, Any]]  # All intent classifications (as dicts for TypedDict compatibility)
    mode_switch_count: int  # Track how many times mode has changed

    # Progress tracking for UI streaming
    execution_progress: ExecutionProgress  # Current execution progress for progress bar

    # Output
    ai_response: str
    quick_replies: Optional[List[str]]  # Short answer options (1-3 words, 2-4 options) for direct questions
    suggested_followups: List[str]  # Suggested next queries (short phrases, 3-5 options)
    comparison_table: Optional[Dict[str, Any]]  # Comparison table data when user asks to compare vehicles


def create_initial_state() -> VehicleSearchState:
    """Create an empty initial state for the vehicle search agent."""
    return VehicleSearchState(
        explicit_filters=VehicleFilters(),
        conversation_history=[],
        implicit_preferences=ImplicitPreferences(),
        recommended_vehicles=[],
        questions_asked=[],
        previous_filters=VehicleFilters(),
        interaction_events=[],
        favorites=[],
        interviewed=False,  # Start in interview workflow
        _interview_should_end=False,
        current_intent="general",  # Initial intent
        current_mode="general",  # Initial mode
        intent_history=[],  # Empty intent history
        mode_switch_count=0,  # No mode switches yet
        execution_progress=ExecutionProgress(
            current_step_index=0,
            total_steps=0,
            steps=[],
            mode="general"
        ),  # Initialize empty progress
        ai_response="",
        quick_replies=None,
        suggested_followups=[],
        comparison_table=None
    )


def add_user_message(state: VehicleSearchState, content: str) -> VehicleSearchState:
    """
    Add a user message to the conversation history.
    """
    state["conversation_history"].append(HumanMessage(content=content))
    return state


def add_ai_message(state: VehicleSearchState, content: str) -> VehicleSearchState:
    """
    Add an AI message to the conversation history.
    """
    state["conversation_history"].append(AIMessage(content=content))
    return state


def get_latest_user_message(state: VehicleSearchState) -> Optional[str]:
    """Get the content of the most recent user message."""
    for message in reversed(state["conversation_history"]):
        if isinstance(message, HumanMessage):
            return message.content
    return None
