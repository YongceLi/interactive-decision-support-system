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
    drivetrain: Optional[str]  # e.g., "AWD" or "AWD,4WD" (comma-separated for multiple)
    fuel_type: Optional[str]  # e.g., "Gasoline" or "Electric,Hybrid" (comma-separated for multiple)

    # Color filters
    exterior_color: Optional[str]  # e.g., "white" or "white,black,silver"
    interior_color: Optional[str]  # e.g., "black" or "black,beige,gray"

    # Physical attributes
    doors: Optional[int]  # e.g., 2, 4
    seating_capacity: Optional[int]  # e.g., 5, 7, 8

    # Retail listing filters
    price: Optional[str]  # e.g., "10000-30000" (range format)
    state: Optional[str]  # e.g., "CA", "NY"
    mileage: Optional[str]  # Vehicle's odometer reading, e.g., "0-50000" (range format)
    highway_mpg: Optional[str]  # Highway fuel economy, e.g., "30" or "30-40" (range format)
    is_used: Optional[bool]  # True for used vehicles, False for new vehicles
    is_cpo: Optional[bool]  # True for Certified Pre-Owned vehicles

    # Location filters
    zip: Optional[str]  # 5-digit ZIP code (only as fallback if browser location denied; gets converted to lat/long)
    search_radius: Optional[int]  # Max distance in miles to travel to dealer location

    # Filter strictness
    must_have_filters: Optional[List[str]]  # List of field names that are strict requirements (used in SQL WHERE clause)


class ImplicitPreferences(TypedDict, total=False):
    """
    Implicit user preferences inferred from conversation.

    Simplified schema optimized for semantic matching with vehicle reviews:
    - liked_features: Vehicle attributes user wants (matched against pros)
    - disliked_features: Vehicle attributes user wants to avoid (matched against cons)
    """
    liked_features: Optional[List[str]]  # e.g., ["fuel efficiency", "reliability", "spacious interior", "smooth ride"]
    disliked_features: Optional[List[str]]  # e.g., ["high maintenance costs", "poor visibility", "stiff suspension"]
    notes: Optional[str]  # Any other contextual information about user preferences


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
    drivetrain: Optional[str] = Field(None, description="e.g., 'AWD' or 'AWD,4WD' (comma-separated)")
    fuel_type: Optional[str] = Field(None, description="e.g., 'Gasoline' or 'Electric,Hybrid' (comma-separated)")

    # Color filters
    exterior_color: Optional[str] = Field(None, description="e.g., 'white' or 'white,black,silver'")
    interior_color: Optional[str] = Field(None, description="e.g., 'black' or 'black,beige,gray'")

    # Physical attributes
    doors: Optional[int] = Field(None, description="e.g., 2, 4")
    seating_capacity: Optional[int] = Field(None, description="e.g., 5, 7, 8")

    # Retail listing filters
    price: Optional[str] = Field(None, description="e.g., '10000-30000' (range format)")
    state: Optional[str] = Field(None, description="e.g., 'CA', 'NY'")
    mileage: Optional[str] = Field(None, description="Vehicle's odometer reading in miles (e.g., '0-50000' for cars with under 50k miles on odometer)")
    highway_mpg: Optional[str] = Field(None, description="Highway fuel economy in miles per gallon (e.g., '30' for at least 30 mpg, '30-40' for 30-40 mpg range). Extract from phrases like 'good gas mileage', 'fuel efficient', '30+ mpg', 'over 35 mpg highway'")
    is_used: Optional[bool] = Field(None, description="True for used/pre-owned vehicles, False for new vehicles. Extract from phrases like 'used car', 'new car', 'pre-owned'")
    is_cpo: Optional[bool] = Field(None, description="True for Certified Pre-Owned (CPO) vehicles. Extract from phrases like 'certified pre-owned', 'CPO', 'certified used'")

    # Location filters
    zip: Optional[str] = Field(None, description="5-digit US ZIP code (only used as fallback if browser geolocation is denied; automatically converted to coordinates for distance search)")
    search_radius: Optional[int] = Field(None, description="Maximum distance in miles you're willing to travel to pick up the vehicle from dealer (e.g., 50 for within 50 miles of your location)")

    # Filter strictness
    must_have_filters: List[str] = Field(
        default_factory=list,
        description="List of filter field names that are hard requirements (relaxed LAST). Example: ['body_style', 'price'] means body_style and price are strict requirements."
    )

    # Inferred filters (relaxed FIRST)
    inferred_filters: List[str] = Field(
        default_factory=list,
        description=(
            "List of filter field names that were INFERRED from context rather than explicitly stated by user. "
            "These are relaxed FIRST during progressive filter relaxation. "
            "Examples of inference: "
            "'newer than 2024 Malibu' → year, make, model filter is inferred; "
            "'low mileage' → mileage filter is inferred. "
            "If user explicitly says 'I want a 2024 car', year is NOT inferred (it's explicit)."
        )
    )

    # Negative filters (vehicles to EXCLUDE)
    avoid_vehicles: Optional[List[Dict[str, str]]] = Field(
        None,
        description=(
            "List of vehicles to EXCLUDE from search results. CRITICAL for user satisfaction. "
            "Extract when user says: 'disappointed with', 'hate', 'avoid', 'never again', 'anything but', 'alternatives to'. "
            "Format: [{'make': 'Toyota', 'model': 'RAV4'}] for specific model, [{'make': 'Honda'}] for entire make. "
            "Example: 'disappointed with my RAV4' → [{'make': 'Toyota', 'model': 'RAV4'}]"
        )
    )


class ImplicitPreferencesPydantic(BaseModel):
    """Pydantic version of ImplicitPreferences for LLM structured output."""
    liked_features: Optional[List[str]] = Field(
        None,
        description=(
            "Vehicle attributes and characteristics the user wants or values (matched against vehicle PROS in reviews). "
            "Extract from phrases indicating positive preferences: "
            "'fuel efficient' → ['fuel efficiency'], "
            "'reliable car' → ['reliability'], "
            "'spacious interior' → ['spacious interior', 'interior space'], "
            "'smooth ride' → ['comfortable ride', 'smooth handling'], "
            "'good safety features' → ['safety features', 'crash test ratings'], "
            "'tech features' → ['technology', 'infotainment system'], "
            "'affordable maintenance' → ['low maintenance costs', 'affordable repairs']. "
            "Be specific and capture the essence of what user wants."
        )
    )
    disliked_features: Optional[List[str]] = Field(
        None,
        description=(
            "Vehicle attributes and characteristics the user wants to avoid (matched against vehicle CONS in reviews). "
            "Extract from phrases indicating negative preferences or concerns: "
            "'expensive to maintain' → ['high maintenance costs', 'expensive repairs'], "
            "'poor visibility' → ['poor visibility', 'blind spots'], "
            "'stiff suspension' → ['harsh ride', 'uncomfortable suspension'], "
            "'bad gas mileage' → ['poor fuel economy', 'low mpg'], "
            "'unreliable' → ['reliability issues', 'frequent breakdowns'], "
            "'cramped interior' → ['limited interior space', 'small cabin']. "
            "Be specific and capture what user wants to avoid."
        )
    )
    notes: Optional[str] = Field(
        None,
        description="Any other contextual information about user preferences that doesn't fit into liked/disliked features"
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

    # User location (from browser geolocation)
    user_latitude: Optional[float]  # User's latitude for distance calculations
    user_longitude: Optional[float]  # User's longitude for distance calculations

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
    _semantic_parsing_done: bool  # Internal flag to skip duplicate semantic parsing in interview workflow

    # Current mode tracking
    current_mode: str  # Current operational mode (supervisor/general)

    # Output
    ai_response: str
    quick_replies: Optional[List[str]]  # Short answer options (1-3 words, 2-4 options) for direct questions
    suggested_followups: List[str]  # Suggested next queries (short phrases, 3-5 options)
    comparison_table: Optional[Dict[str, Any]]  # Comparison table data when user asks to compare vehicles


def create_initial_state() -> VehicleSearchState:
    """Create an empty initial state for the vehicle search agent."""
    return VehicleSearchState(
        explicit_filters=VehicleFilters(must_have_filters=[]),
        conversation_history=[],
        implicit_preferences=ImplicitPreferences(),
        user_latitude=None,
        user_longitude=None,
        recommended_vehicles=[],
        questions_asked=[],
        previous_filters=VehicleFilters(),
        interaction_events=[],
        favorites=[],
        interviewed=False,  # Start in interview workflow
        _interview_should_end=False,
        _semantic_parsing_done=False,  # Semantic parsing not done yet
        current_mode="general",  # Initial mode
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
