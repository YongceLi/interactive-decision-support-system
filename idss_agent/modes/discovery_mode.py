"""
Discovery mode - Browse and explore vehicles without commitment.

Triggered by "browsing" intent - user wants to casually explore options.
"""
from typing import Optional, Callable
from idss_agent.state import VehicleSearchState
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.discovery import discovery_agent
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.logger import get_logger

logger = get_logger("modes.discovery")


def run_discovery_mode(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Discovery mode handler - casual browsing without interview.

    Workflow:
    1. Parse filters from conversation
    2. Update recommendations if filters changed
    3. Generate discovery response (shows vehicles + asks questions)

    Args:
        state: Current vehicle search state
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with ai_response and recommended_vehicles
    """
    logger.info("Discovery mode: Browsing vehicles")

    # 1. Parse filters from conversation
    state = semantic_parser_node(state, progress_callback)

    # 2. Update recommendations if filters changed OR no vehicles yet
    filters_changed = state["explicit_filters"] != state.get("previous_filters", {})
    has_vehicles = len(state.get("recommended_vehicles", [])) > 0
    has_preferences = any([
        state.get("implicit_preferences", {}).get("priorities"),
        state.get("implicit_preferences", {}).get("concerns"),
        state.get("implicit_preferences", {}).get("usage_patterns"),
        state.get("implicit_preferences", {}).get("lifestyle")
    ])

    # Update if: filters changed, OR (no vehicles yet AND has preferences for semantic search)
    if filters_changed or (not has_vehicles and has_preferences):
        if filters_changed:
            logger.info("Discovery mode: Filters changed, updating recommendations")
        else:
            logger.info("Discovery mode: No vehicles yet but has preferences, using semantic recommendation")
        state = update_recommendation_list(state, progress_callback)
        state["previous_filters"] = state["explicit_filters"].copy()

    # 3. Generate discovery response
    state = discovery_agent(state, progress_callback)

    return state
