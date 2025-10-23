"""
Buying mode - Helps user purchase a vehicle through interview and recommendations.

Decision 1 - Option C (Hybrid):
- If not interviewed: Run interview workflow
- If interviewed: Update recommendations with new filters
"""
from idss_agent.state import VehicleSearchState
from idss_agent.components.semantic_parser import semantic_parser_node
from idss_agent.components.discovery import discovery_agent
from idss_agent.components.recommendation import update_recommendation_list
from idss_agent.logger import get_logger

logger = get_logger("modes.buying")


def run_buying_mode(state: VehicleSearchState) -> VehicleSearchState:
    """
    Buying mode handler.

    Behavior:
    - If not interviewed: Run interview workflow (handled by interview_workflow.py)
    - If interviewed: Parse new filters, update recommendations, show options

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with ai_response
    """

    if not state.get("interviewed", False):
        # NOT interviewed yet - interview workflow will be called from main agent
        # This function shouldn't be called in this case, but return state as-is
        logger.info("Buying mode: Interview not complete, should run interview workflow")
        return state

    else:
        # ALREADY interviewed - user is asking for more or updating preferences
        logger.info("Buying mode: Interview complete, updating recommendations")

        # 1. Parse any new filters from latest message
        state = semantic_parser_node(state)

        # 2. Check if filters changed
        filters_changed = state["explicit_filters"] != state.get("previous_filters", {})

        if filters_changed:
            # Filters changed - update recommendations
            logger.info("Buying mode: Filters changed, updating recommendations")
            state = update_recommendation_list(state)
            state["previous_filters"] = state["explicit_filters"].copy()

            # Use discovery agent to present new options
            state = discovery_agent(state)

        else:
            # No filter change - generate conversational response
            logger.info("Buying mode: No filter change, continuing conversation")
            state = discovery_agent(state)

        return state
