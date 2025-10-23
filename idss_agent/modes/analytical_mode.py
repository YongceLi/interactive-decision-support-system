"""
Analytical mode - Answer specific questions with data and analysis.

Triggered by "research" intent - user wants comparisons, specs, ratings.

Decision 2 - Conditional recommendations:
- If query contains vehicle filters: Update recommendations
- If pure analytical question: Just answer, no recommendations
"""
from idss_agent.state import VehicleSearchState, VehicleFilters
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.analytical import analytical_agent
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.logger import get_logger

logger = get_logger("modes.analytical")


def has_vehicle_filters(filters: VehicleFilters) -> bool:
    """
    Check if filters contain actual vehicle search criteria.

    Returns True if any substantive filter is set.
    """
    return any([
        filters.get("make"),
        filters.get("model"),
        filters.get("body_style"),
        filters.get("year"),
        filters.get("price"),
        filters.get("miles"),
        filters.get("state"),
        filters.get("zip"),
        filters.get("transmission"),
        filters.get("exterior_color"),
        filters.get("seating_capacity"),
        filters.get("doors"),
        filters.get("features"),
    ])


def run_analytical_mode(state: VehicleSearchState) -> VehicleSearchState:
    """
    Analytical mode handler - answer questions with data.

    Workflow:
    1. Parse any filters/entities from question
    2. Conditionally update recommendations:
       - If filters detected (e.g., "safest SUV"): Update recommendations
       - If no filters (e.g., "What is ABS?"): Skip recommendations
    3. Use analytical agent to answer question

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with ai_response (± recommended_vehicles)
    """
    logger.info("Analytical mode: Answering analytical question")

    # 1. Parse any filters/entities from question
    state = semantic_parser_node(state)

    # 2. Decision 2: Conditionally update recommendations
    # If filters detected (e.g., "safest SUV"), update recommendations
    # If no filters (e.g., "What is ABS?"), skip recommendations

    filters_detected = (
        state["explicit_filters"] != state.get("previous_filters", {})
        and has_vehicle_filters(state["explicit_filters"])
    )

    if filters_detected:
        # Question includes vehicle criteria → Show vehicles
        logger.info("Analytical mode: Vehicle filters detected, updating recommendations")
        state = update_recommendation_list(state)
        state["previous_filters"] = state["explicit_filters"].copy()
    else:
        logger.info("Analytical mode: No vehicle filters, skipping recommendations")

    # 3. Use analytical agent to answer question
    state = analytical_agent(state)

    return state
