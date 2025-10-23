"""
Discovery mode - Browse and explore vehicles without commitment.

Triggered by "browsing" intent - user wants to casually explore options.
"""
from idss_agent.state import VehicleSearchState
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.discovery import discovery_agent
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.logger import get_logger

logger = get_logger("modes.discovery")


def run_discovery_mode(state: VehicleSearchState) -> VehicleSearchState:
    """
    Discovery mode handler - casual browsing without interview.

    Workflow:
    1. Parse filters from conversation
    2. Update recommendations if filters changed
    3. Generate discovery response (shows vehicles + asks questions)

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with ai_response and recommended_vehicles
    """
    logger.info("Discovery mode: Browsing vehicles")

    # 1. Parse filters from conversation
    state = semantic_parser_node(state)

    # 2. Update recommendations if filters changed
    if state["explicit_filters"] != state.get("previous_filters", {}):
        logger.info("Discovery mode: Filters changed, updating recommendations")
        state = update_recommendation_list(state)
        state["previous_filters"] = state["explicit_filters"].copy()

    # 3. Generate discovery response
    state = discovery_agent(state)

    return state
