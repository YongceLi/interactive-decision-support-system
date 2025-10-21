"""
Supervisor workflow - orchestrates tools to answer user questions after interview.

This workflow runs after the interview is complete (interviewed=True).
"""
from langgraph.graph import StateGraph, END
from idss_agent.logger import get_logger
from idss_agent.state import VehicleSearchState
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.workflows.supervisor_agent import supervisor_decide_action, supervisor_generate_response
from idss_agent.components.discovery import discovery_tool
from idss_agent.components.analytical_tool import analytical_tool

logger = get_logger("workflows.supervisor")


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

    logger.info(f"Supervisor decision: tool={decision.get('tool')}, reasoning={decision.get('reasoning')}")

    # Store decision in state for routing
    state["_supervisor_decision"] = decision
    return state


def route_to_tool(state: VehicleSearchState) -> str:
    """Router to decide which tool to call based on supervisor decision."""
    decision = state.get("_supervisor_decision", {})
    tool = decision.get("tool", "none")

    if tool == "discovery_tool":
        return "discovery"
    elif tool == "analytical_tool":
        return "analytical"
    else:
        return "response"


def call_discovery_tool(state: VehicleSearchState) -> VehicleSearchState:
    """Node to call discovery tool."""
    tool_result = discovery_tool(state)
    state["_tool_result"] = tool_result
    return state


def call_analytical_tool(state: VehicleSearchState) -> VehicleSearchState:
    """Node to call analytical tool."""
    decision = state.get("_supervisor_decision", {})
    user_input = state.get("conversation_history", [])[-1].content if state.get("conversation_history") else ""
    question = decision.get("params", {}).get("question", user_input)

    tool_result = analytical_tool(question, state)
    state["_tool_result"] = tool_result
    return state


def generate_response_node(state: VehicleSearchState) -> VehicleSearchState:
    """Node to generate final response."""
    decision = state.get("_supervisor_decision", {})
    user_input = state.get("conversation_history", [])[-1].content if state.get("conversation_history") else ""
    tool_result = state.get("_tool_result")
    chosen_tool = decision.get("tool", "none")

    if chosen_tool in {"discovery_tool", "analytical_tool"}:
        if isinstance(tool_result, str) and tool_result.strip():
            response = tool_result.strip()
        else:
            response = "I wasn't able to retrieve the details just now. Could you try again?"
    else:
        response = supervisor_generate_response(
            state=state,
            user_input=user_input,
            tool_used=chosen_tool,
            tool_result=tool_result
        )

    state["ai_response"] = response

    # Clean up temporary fields
    if "_supervisor_decision" in state:
        del state["_supervisor_decision"]
    if "_tool_result" in state:
        del state["_tool_result"]

    return state


# Create LangGraph StateGraph for supervisor workflow
def create_supervisor_graph():
    """Create the supervisor workflow graph."""
    workflow = StateGraph(VehicleSearchState)

    # Add nodes
    workflow.add_node("semantic_parser", semantic_parser_node)
    workflow.add_node("check_filters", check_and_update_recommendations)
    workflow.add_node("supervisor_decision", supervisor_decision_node)
    workflow.add_node("discovery", call_discovery_tool)
    workflow.add_node("analytical", call_analytical_tool)
    workflow.add_node("response", generate_response_node)

    # Add edges
    workflow.set_entry_point("semantic_parser")
    workflow.add_edge("semantic_parser", "check_filters")
    workflow.add_edge("check_filters", "supervisor_decision")

    workflow.add_conditional_edges(
        "supervisor_decision",
        route_to_tool,
        {
            "discovery": "discovery",
            "analytical": "analytical",
            "response": "response"
        }
    )

    workflow.add_edge("discovery", "response")
    workflow.add_edge("analytical", "response")
    workflow.add_edge("response", END)

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

    Flow:
    1. Semantic parsing (this message only)
    2. Update recommendations if filters changed
    3. Supervisor decides which tool to call
    4. Call tool (if any)
    5. Supervisor generates response

    Args:
        user_input: User's message
        state: Current state

    Returns:
        Updated state with response
    """
    graph = get_supervisor_graph()
    result = graph.invoke(state)
    return result
