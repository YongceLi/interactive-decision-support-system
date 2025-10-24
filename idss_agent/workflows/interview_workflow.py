"""
Interview workflow - asks questions to understand user needs before making recommendations.

This workflow runs until the interview is complete (threshold reached or user requests vehicles).
"""
import os
from typing import Any, Optional, Callable
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from idss_agent.logger import get_logger
from idss_agent.state import (
    VehicleSearchState,
    get_latest_user_message,
    VehicleFiltersPydantic,
    ImplicitPreferencesPydantic,
    AgentResponse
)
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.components.discovery import discovery_agent

logger = get_logger("workflows.interview")

# Structured output schema for interview mode
class InterviewResponse(BaseModel):
    """Structured response from interview agent with should_end flag."""
    ai_response: str = Field(description="Your conversational response to the user")
    quick_replies: Optional[list[str]] = Field(
        default=None,
        description=(
            "Short answer options (less than 5 words each) for questions in your response. "
            "Provide less than 5 options if you ask a direct question. "
            "Examples: ['Under $20k', '$20k-$30k', '$30k+'], ['Sedan', 'SUV', 'Truck'], ['Yes', 'No'], ..."
        )
    )
    suggested_followups: list[str] = Field(
        description=(
            "Suggested next queries (short phrases, less than 5 options) to help users continue. "
            "Examples: ['Show me vehicles now', 'I want a safe car', 'I want a sporty car']"
        ),
        max_length=5
    )
    should_end: bool = Field(description="True if interview mode should end, false to continue")


# Structured output schema for extraction
class ExtractionResult(BaseModel):
    """Structured extraction from interview conversation."""
    explicit_filters: VehicleFiltersPydantic = Field(
        default_factory=VehicleFiltersPydantic,
        description="Explicit vehicle filters with specific fields"
    )
    implicit_preferences: ImplicitPreferencesPydantic = Field(
        default_factory=ImplicitPreferencesPydantic,
        description="Implicit preferences with specific fields"
    )


# System prompt for interviewer
INTERVIEW_SYSTEM_PROMPT = """
You are a friendly, knowledgeable, human-like car salesperson.

Your job is to have a natural conversation to understand the customer's situation, needs, and preferences before making any vehicle recommendations.

Follow these principles:
- Be warm, empathetic, and conversational.
- Ask one or two questions at a time—never a long survey.
- Adapt your questions based on the user's previous answers.
- Use intuitive, lifestyle-oriented questions (not just specs).
- Discover necessary information and practical needs (zipcode, new/used, budget, size, usage).
- Discover emotional drivers (status, fun, safety, efficiency).
- DO NOT repeat questions already answered.

Conversational stages to cover:
1. Warm welcome / motivation: Why now? What's happening in their life?
2. Practical constraints: Location(zipcode), budget range, new vs used, body type preferences.
3. Use case & lifestyle: Daily driving? Family? Travel? Commute? Hobbies?
4. Emotional priorities: Safety, efficiency, performance, style, comfort.
5. Context: Location, climate, parking, EV charging, brand feelings.

Your task for each turn:
1. Respond naturally and empathetically to the user's message.
2. Ask 1-2 thoughtful follow-up questions that move the conversation forward.
3. If a stage has already been covered, move to the next relevant stage.
4. Review the conversation history to avoid repeating questions.

When to end the interview (set should_end=true):
- User explicitly asks to see vehicles ("show me", "let's see", "what do you have", "recommendations", etc.)
- You have enough information to make good recommendations
- User seems impatient or ready to move forward

Think like a real human salesperson who builds trust before suggesting options.

Output format:
- ai_response: Your conversational response to the user (IMPORTANT: If setting should_end=true, leave this EMPTY - the system will generate the vehicle recommendation)
- quick_replies: If you ask a direct question, provide less than 5 short answer options (less than 5 words each) that the USER can click to answer. Leave null if no direct question.
- suggested_followups: Provide less than 5 short phrases that represent what the USER might want to say or ask next. These are the user's potential responses/queries, NOT your follow-up questions. Examples of what the USER might say: "I need a family car", "Show me options now", "My budget is $30k", "I want good gas mileage", ...
- should_end: true if interview should end, false to continue
"""


def should_end_interview(state: VehicleSearchState) -> bool:
    """
    Check if interview should end based on LLM's decision or max turns.

    Returns True if:
    - LLM set should_end=True in last response OR
    - Hit max conversation exchanges (safety limit)
    """
    # Check if LLM decided to end
    if state.get("_interview_should_end", False):
        return True

    # Safety limit - max turns
    max_questions = int(os.getenv("MAX_EXPLORATION_QUESTIONS", "8"))
    conversation = state.get("conversation_history", [])
    turn_count = len([msg for msg in conversation if msg.__class__.__name__ == 'HumanMessage'])

    if turn_count >= max_questions:
        logger.info(f"Hit max turns ({max_questions}), ending interview")
        return True

    return False


def interview_node(state: VehicleSearchState) -> VehicleSearchState:
    """
    Interview node that asks questions like a salesperson.

    Uses structured output with conversation history as user input for optimal prompt caching.

    Args:
        state: Current state

    Returns:
        Updated state with AI response and should_end flag
    """
    # Get progress callback from state if available
    progress_callback = state.get("_progress_callback")

    # Emit progress: Starting interview
    if progress_callback:
        progress_callback({
            "step_id": "interview_questions",
            "description": "Conducting interview",
            "status": "in_progress"
        })

    user_input = get_latest_user_message(state)

    if not user_input:
        # First turn - greeting
        state["ai_response"] = "Hi there! Welcome. What brings you in today? Are you looking to replace a current vehicle or is this your first car?"
        state["quick_replies"] = ["Replacing current", "First car", "Just browsing"]
        state["suggested_followups"] = [
            "Show me vehicles now",
            "Tell me about financing",
            "What's your best deal?",
            "I need help deciding"
        ]
        state["_interview_should_end"] = False

        # Emit progress: Interview question ready
        if progress_callback:
            progress_callback({
                "step_id": "interview_questions",
                "description": "Interview question ready",
                "status": "completed"
            })

        return state

    # Create LLM with structured output
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    structured_llm = llm.with_structured_output(InterviewResponse)

    messages = [SystemMessage(content=INTERVIEW_SYSTEM_PROMPT)]
    messages.extend(state["conversation_history"])

    # Get structured response
    response: InterviewResponse = structured_llm.invoke(messages)

    # Store decision
    state["_interview_should_end"] = response.should_end

    if response.should_end:
        logger.info("LLM decided to end interview")
        state["ai_response"] = ""
        state["quick_replies"] = None
        state["suggested_followups"] = []
    else:
        # Normal conversation - set the response and interactive elements
        state["ai_response"] = response.ai_response
        state["quick_replies"] = response.quick_replies
        state["suggested_followups"] = response.suggested_followups

    # Emit progress: Interview question ready
    if progress_callback:
        progress_callback({
            "step_id": "interview_questions",
            "description": "Interview question ready",
            "status": "completed"
        })

    return state


def make_initial_recommendation(state: VehicleSearchState) -> VehicleSearchState:
    """
    Called once at the end of interview to:
    1. Parse entire interview conversation for filters/preferences using structured output
    2. Search for actual available vehicles using Auto.dev API
    3. Use discovery agent to present vehicles conversationally
    4. Mark interview as complete

    Args:
        state: Current state

    Returns:
        Updated state with interviewed=True and initial recommendations
    """
    logger.info("Interview complete! Extracting preferences and searching for available vehicles...")

    # Get progress callback from state if available
    progress_callback = state.get("_progress_callback")

    # Emit progress: Starting extraction
    if progress_callback:
        progress_callback({
            "step_id": "extracting_preferences",
            "description": "Extracting your preferences",
            "status": "in_progress"
        })

    # Step 1: Extract filters/preferences using structured output
    # Get entire interview conversation
    interview_conversation = "\n".join([
        f"{'Customer' if msg.__class__.__name__ == 'HumanMessage' else 'Salesperson'}: {msg.content}"
        for msg in state.get("conversation_history", [])
    ])

    # Create LLM with structured output
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(ExtractionResult)

    extraction_system_prompt = f"""
Analyze this car dealership conversation and extract comprehensive vehicle search criteria.

Extract ALL explicit filters and implicit preferences from this conversation.

Explicit filters are clear, stated requirements:
- Make, model, year, price range, mileage, body style, transmission, colors, features, location, etc.
- Use comma-separated for multiple options: "Toyota,Honda"
- Use ranges for year/price/miles: "2018-2020", "20000-30000"

Implicit preferences are inferred needs and priorities:
- priorities: List of what matters most (safety, fuel efficiency, reliability, performance, etc.)
- lifestyle: Family-oriented, outdoorsy, urban commuter, etc.
- budget_sensitivity: budget-conscious, moderate, luxury-focused
- usage_patterns: Daily commute, weekend trips, family road trips, etc.
- concerns: List of concerns (maintenance costs, resale value, insurance, etc.)
- notes: Any other important context

Be comprehensive - extract EVERYTHING mentioned or clearly implied.
"""

    extraction_prompt = f"""
CONVERSATION:
{interview_conversation}
"""
    messages = [
        SystemMessage(content=extraction_system_prompt),
        HumanMessage(content=extraction_prompt)
    ]

    result: ExtractionResult = structured_llm.invoke(messages)

    state["explicit_filters"] = {**state["explicit_filters"], **result.explicit_filters.model_dump(exclude_none=True)}
    state["implicit_preferences"] = {**state["implicit_preferences"], **result.implicit_preferences.model_dump(exclude_none=True)}

    logger.info(f"Extracted filters: {state['explicit_filters']}")
    logger.info(f"Extracted preferences: {state['implicit_preferences']}")

    # Emit progress: Extraction complete
    if progress_callback:
        progress_callback({
            "step_id": "extracting_preferences",
            "description": "Preferences extracted",
            "status": "completed"
        })

    # Step 2: Search for actual available vehicles using Auto.dev API
    state = update_recommendation_list(state, progress_callback)

    # Step 3: Use discovery agent to present vehicles conversationally
    state = discovery_agent(state, progress_callback)

    # Step 4: Mark interview complete
    state["interviewed"] = True

    # Clean up temporary flag
    if "_interview_should_end" in state:
        del state["_interview_should_end"]

    return state


def decide_next_step(state: VehicleSearchState) -> str:
    """Router to decide if interview should continue or make recommendations."""
    if should_end_interview(state):
        return "make_recommendation"
    return END


# Create wrapper for semantic_parser_node that extracts callback from state
def semantic_parser_wrapper(state: VehicleSearchState) -> VehicleSearchState:
    """Wrapper to pass progress_callback from state to semantic_parser_node."""
    progress_callback = state.get("_progress_callback")
    return semantic_parser_node(state, progress_callback)


# Create LangGraph StateGraph for interview workflow
def create_interview_graph():
    """Create the interview workflow graph."""
    workflow = StateGraph(VehicleSearchState)

    # Add nodes (using wrapper for semantic_parser to pass callback)
    workflow.add_node("semantic_parser", semantic_parser_wrapper)
    workflow.add_node("interview", interview_node)
    workflow.add_node("make_recommendation", make_initial_recommendation)

    # Add edges
    workflow.set_entry_point("semantic_parser")
    workflow.add_edge("semantic_parser", "interview")
    workflow.add_conditional_edges(
        "interview",
        decide_next_step,
        {
            "make_recommendation": "make_recommendation",
            END: END
        }
    )
    workflow.add_edge("make_recommendation", END)

    return workflow.compile()


# Create the compiled graph (singleton)
_interview_graph = None

def get_interview_graph():
    """Get or create the interview workflow graph."""
    global _interview_graph
    if _interview_graph is None:
        _interview_graph = create_interview_graph()
    return _interview_graph


def run_interview_workflow(
    user_input: str,
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Main interview workflow entry point.

    Args:
        user_input: User's message
        state: Current state
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state
    """
    # Store progress callback in state for nodes to access
    # (LangGraph nodes only receive state parameter)
    if progress_callback:
        state["_progress_callback"] = progress_callback

    graph = get_interview_graph()
    result = graph.invoke(state)

    # Clean up progress callback from state
    if "_progress_callback" in result:
        del result["_progress_callback"]

    return result
