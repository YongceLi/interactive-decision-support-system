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
from idss_agent.utils.logger import get_logger
from idss_agent.utils.config import get_config
from idss_agent.utils.prompts import render_prompt
from idss_agent.state.schema import (
    ProductSearchState,
    get_latest_user_message,
    ProductFiltersPydantic,
    ImplicitPreferencesPydantic,
    AgentResponse
)
from idss_agent.processing.semantic_parser import semantic_parser_node
from idss_agent.processing.recommendation import update_recommendation_list
from idss_agent.agents.discovery import discovery_agent

logger = get_logger("workflows.interview")

# Structured output schema for interview mode
class InterviewResponse(BaseModel):
    """Structured response from interview agent with should_end flag."""
    ai_response: str = Field(
        description="Your conversational response to the user (2-3 sentences max)",
        max_length=500
    )
    quick_replies: Optional[list[str]] = Field(
        default=None,
        description=(
            "Short answer options (2-5 words each) for questions in your response. "
            "Provide 2-4 options if you ask a direct question. "
        ),
        max_length=4
    )
    should_end: bool = Field(description="True if interview mode should end, false to continue")


# Structured output schema for extraction
class ExtractionResult(BaseModel):
    """Structured extraction from interview conversation."""
    explicit_filters: ProductFiltersPydantic = Field(
        default_factory=ProductFiltersPydantic,
        description="Explicit product filters with specific fields"
    )
    implicit_preferences: ImplicitPreferencesPydantic = Field(
        default_factory=ImplicitPreferencesPydantic,
        description="Implicit preferences with specific fields"
    )
    questions_asked: list[str] = Field(
        default_factory=list,
        description=(
            "Topics covered during the interview conversation. "
            "Include topics that were asked about OR volunteered by the user. "
            "Possible topics: budget, location, usage, priorities, mileage, "
            "vehicle_type, features, timeline, new_vs_used, etc."
        )
    )


def should_end_interview(state: ProductSearchState) -> bool:
    """
    Check if interview should end based on LLM's decision or max turns.

    Returns True if:
    - LLM set should_end=True in last response OR
    - Hit max conversation exchanges (safety limit)
    """
    # Check if LLM decided to end
    if state.get("_interview_should_end", False):
        return True

    # Safety limit - max turns from config
    config = get_config()
    max_questions = config.limits.get('max_interview_questions', 8)
    conversation = state.get("conversation_history", [])
    turn_count = len([msg for msg in conversation if msg.__class__.__name__ == 'HumanMessage'])

    if turn_count >= max_questions:
        logger.info(f"Hit max turns ({max_questions}), ending interview")
        return True

    return False


def interview_node(state: ProductSearchState) -> ProductSearchState:
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
        state["quick_replies"] = ["Replacing current", "First car", "Adding to household", "Just exploring"]
        state["suggested_followups"] = []  # Interview mode doesn't use suggested followups
        state["_interview_should_end"] = False

        # Emit progress: Interview question ready
        if progress_callback:
            progress_callback({
                "step_id": "interview_questions",
                "description": "Interview question ready",
                "status": "completed"
            })

        return state

    # Get configuration
    config = get_config()
    model_config = config.get_model_config('interview')
    max_history = config.limits.get('max_conversation_history', 10)

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 1000)
    )
    structured_llm = llm.with_structured_output(InterviewResponse)

    # Load system prompt from template
    system_prompt = render_prompt('interview_system.j2')
    messages = [SystemMessage(content=system_prompt)]

    # Limit conversation history to prevent context explosion
    conversation_history = state["conversation_history"]
    if len(conversation_history) > max_history:
        conversation_history = conversation_history[-max_history:]

    messages.extend(conversation_history)

    # Get structured response
    response: InterviewResponse = structured_llm.invoke(messages)

    # Store decision
    state["_interview_should_end"] = response.should_end

    if response.should_end:
        logger.info("LLM decided to end interview")
        state["ai_response"] = ""
        state["quick_replies"] = None
        state["suggested_followups"] = []
        state["comparison_table"] = None
    else:
        # Normal conversation - set the response and interactive elements
        state["ai_response"] = response.ai_response
        # Apply feature flag for quick_replies
        state["quick_replies"] = response.quick_replies if config.features.get('enable_quick_replies', True) else None
        state["suggested_followups"] = []  # Interview mode doesn't use suggested followups
        state["comparison_table"] = None  # Clear comparison table in interview mode

    # Emit progress: Interview question ready
    if progress_callback:
        progress_callback({
            "step_id": "interview_questions",
            "description": "Interview question ready",
            "status": "completed"
        })

    return state


def make_initial_recommendation(state: ProductSearchState) -> ProductSearchState:
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

    # Get configuration
    config = get_config()
    model_config = config.get_model_config('interview_extraction')

    # Create LLM with config parameters
    llm = ChatOpenAI(
        model=model_config['name'],
        temperature=model_config['temperature'],
        max_tokens=model_config.get('max_tokens', 2000)
    )
    structured_llm = llm.with_structured_output(ExtractionResult)

    # Load extraction prompt from template
    extraction_system_prompt = render_prompt('interview_extraction.j2')

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
    state["questions_asked"] = result.questions_asked  # Track topics covered during interview for discovery handoff

    logger.info(f"Extracted filters: {state['explicit_filters']}")
    logger.info(f"Extracted preferences: {state['implicit_preferences']}")
    logger.info(f"Topics covered in interview: {state['questions_asked']}")

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


def decide_next_step(state: ProductSearchState) -> str:
    """Router to decide if interview should continue or make recommendations."""
    if should_end_interview(state):
        return "make_recommendation"
    return END


# Create wrapper for semantic_parser_node that extracts callback from state
def semantic_parser_wrapper(state: ProductSearchState) -> ProductSearchState:
    """
    Wrapper to pass progress_callback from state to semantic_parser_node.

    Optimization: Skip parsing if already done by supervisor to avoid duplicate LLM calls.
    """
    # Check if semantic parsing was already done by supervisor
    if state.get("_semantic_parsing_done", False):
        logger.info("Skipping duplicate semantic parsing (already done by supervisor)")
        # Clear the flag so next turn will parse normally
        state['_semantic_parsing_done'] = False
        return state

    # Otherwise, do semantic parsing
    progress_callback = state.get("_progress_callback")
    return semantic_parser_node(state, progress_callback)


# Create LangGraph StateGraph for interview workflow
def create_interview_graph():
    """Create the interview workflow graph."""
    workflow = StateGraph(ProductSearchState)

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
    state: ProductSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> ProductSearchState:
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
