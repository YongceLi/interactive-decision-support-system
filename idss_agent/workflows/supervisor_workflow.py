"""
Supervisor workflow - orchestrates agents to answer user questions after interview.

This workflow runs after the interview is complete (interviewed=True).

Flow:
    semantic_parser → check_filters → supervisor_decision → [discovery_agent OR analytical_agent] → END
"""
import json
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.components.discovery import discovery_agent
from idss_agent.components.analytical import analytical_agent

logger = get_logger("workflows.supervisor")


# Supervisor decision prompt
SUPERVISOR_DECISION_PROMPT = """
You are a vehicle shopping assistant supervisor. Your job is to decide what action to take based on the user's message.

Current context:
- Vehicles available: {has_vehicles}
- Vehicle count: {vehicle_count}
- Filters: {filters_summary}
- User's message: "{user_message}"

You must always route the user's request to exactly ONE of these tools:
- **discovery_tool**
  - Use when the user wants to browse, see options, or get an overview of listings.
  - Examples: "show me cars", "what do you have", "give me some recommendations", location adjustments, filter tweaks, general browsing requests.
- **analytical_tool**
  - Use when the user asks detailed questions about a specific vehicle, comparisons, specs, or needs deep data lookup.
  - Examples: "tell me about #1", "compare #1 and #3", "what's the safety rating", "does it have heated seats?"

Do not choose "none" or any other option. If the message is chit-chat or outside these instructions, prefer discovery_tool.

Decide what to do:
{{
  "tool": "discovery_tool" | "analytical_tool",
  "reasoning": "Brief explanation of why",
  "params": {{
    "question": "for analytical_tool only - the specific question to answer"
  }}
}}

Output ONLY valid JSON.
"""


def summarize_state(state: VehicleSearchState) -> Dict[str, Any]:
    """
    Create a lightweight summary of state for supervisor decisions.

    Args:
        state: Full state

    Returns:
        Summarized state dict
    """
    filters = state.get("explicit_filters", {})
    vehicles = state.get("recommended_vehicles", [])

    # Create human-readable filter summary
    filter_parts = []
    if filters.get("make"):
        filter_parts.append(filters["make"])
    if filters.get("model"):
        filter_parts.append(filters["model"])
    if filters.get("body_style"):
        filter_parts.append(filters["body_style"])
    if filters.get("price"):
        filter_parts.append(f"${filters['price']}")
    if filters.get("state"):
        filter_parts.append(f"in {filters['state']}")

    filters_summary = ", ".join(filter_parts) if filter_parts else "no specific filters"

    return {
        "has_vehicles": len(vehicles) > 0,
        "vehicle_count": len(vehicles),
        "filters_summary": filters_summary
    }


def supervisor_decide_action(state: VehicleSearchState, user_input: str) -> Dict[str, Any]:
    """
    Supervisor decides what action to take (which tool to call).

    This is a lightweight decision step using summarized state.

    Args:
        state: Current state
        user_input: User's message

    Returns:
        Decision dict with tool and params
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    summary = summarize_state(state)

    prompt = SUPERVISOR_DECISION_PROMPT.format(
        has_vehicles=summary["has_vehicles"],
        vehicle_count=summary["vehicle_count"],
        filters_summary=summary["filters_summary"],
        user_message=user_input
    )

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="Decide what to do.")
    ])

    try:
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        decision = json.loads(content)
        return decision

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse supervisor decision: {e}")
        # Fallback: default to discovery_tool if parsing fails
        return {"tool": "discovery_tool", "reasoning": "Fallback", "params": {}}


def filters_changed(state: VehicleSearchState) -> bool:
    """
    Check if explicit filters have changed since last update.

    Args:
        state: Current state

    Returns:
        True if filters changed
    """
    current = state.get("explicit_filters", {})
    previous = state.get("previous_filters", {})

    # Simple comparison - any difference means changed
    return current != previous


def check_and_update_recommendations(state: VehicleSearchState) -> VehicleSearchState:
    """Node to check if filters changed and update recommendations."""
    if filters_changed(state):
        logger.info("Filters changed, updating recommendations...")
        state = update_recommendation_list(state)
        state["previous_filters"] = state["explicit_filters"].copy()
    return state


def supervisor_decision_node(state: VehicleSearchState) -> VehicleSearchState:
    """Node for supervisor to decide which tool to call."""
    user_input = state.get("conversation_history", [])[-1].content if state.get("conversation_history") else ""
    decision = supervisor_decide_action(state, user_input)

    logger.info(f"Supervisor routing to: {decision.get('tool')} (reason: {decision.get('reasoning')})")

    # Store decision in state for routing
    state["_supervisor_decision"] = decision
    return state


def route_to_agent(state: VehicleSearchState) -> str:
    """Router to decide which agent to call based on supervisor decision."""
    decision = state.get("_supervisor_decision", {})
    tool = decision.get("tool", "discovery_tool")

    if tool == "analytical_tool":
        return "analytical"
    else:
        return "discovery"


def call_discovery_agent(state: VehicleSearchState) -> VehicleSearchState:
    """Node to call discovery agent."""
    state = discovery_agent(state)

    # Clean up temporary fields
    if "_supervisor_decision" in state:
        del state["_supervisor_decision"]

    return state


def call_analytical_agent(state: VehicleSearchState) -> VehicleSearchState:
    """Node to call analytical agent."""
    state = analytical_agent(state)

    # Clean up temporary fields
    if "_supervisor_decision" in state:
        del state["_supervisor_decision"]

    return state


# Create LangGraph StateGraph for supervisor workflow
def create_supervisor_graph():
    """Create the simplified supervisor workflow graph."""
    workflow = StateGraph(VehicleSearchState)

    # Add nodes
    workflow.add_node("semantic_parser", semantic_parser_node)
    workflow.add_node("check_filters", check_and_update_recommendations)
    workflow.add_node("supervisor_decision", supervisor_decision_node)
    workflow.add_node("discovery", call_discovery_agent)
    workflow.add_node("analytical", call_analytical_agent)

    # Add edges
    workflow.set_entry_point("semantic_parser")
    workflow.add_edge("semantic_parser", "check_filters")
    workflow.add_edge("check_filters", "supervisor_decision")

    workflow.add_conditional_edges(
        "supervisor_decision",
        route_to_agent,
        {
            "discovery": "discovery",
            "analytical": "analytical"
        }
    )

    # Both agents route directly to END
    workflow.add_edge("discovery", END)
    workflow.add_edge("analytical", END)

    return workflow.compile()


# Create the compiled graph (singleton)
_supervisor_graph = None

def get_supervisor_graph():
    """Get or create the supervisor workflow graph."""
    global _supervisor_graph
    if _supervisor_graph is None:
        _supervisor_graph = create_supervisor_graph()
    return _supervisor_graph


def run_supervisor_workflow(user_input: str, state: VehicleSearchState) -> VehicleSearchState:
    """
    Main supervisor workflow entry point.

    Simplified Flow:
    1. Semantic parsing (extract filters from user message)
    2. Update recommendations if filters changed
    3. Supervisor routes to discovery or analytical agent
    4. Agent writes response directly to ai_response
    5. End

    Args:
        user_input: User's message
        state: Current state

    Returns:
        Updated state with ai_response
    """
    graph = get_supervisor_graph()
    result = graph.invoke(state)
    return result
