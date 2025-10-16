"""
Readiness router that determines if we should proceed to recommendations.

This router uses semantic evaluation to decide if the exploration phase
has gathered enough information, mimicking a real dealership sales manager.
"""
import os
from typing import Literal
from idss_agent.state import VehicleSearchState
from idss_agent.nodes.exploration import evaluate_readiness


def check_exploration_readiness(state: VehicleSearchState) -> Literal["explore", "recommend"]:
    """
    Route based on whether we're ready to make recommendations.

    Uses semantic LLM evaluation to determine if we have enough information
    to confidently show vehicles to the customer.

    Also enforces a maximum question threshold to prevent endless exploration.

    Args:
        state: Current vehicle search state

    Returns:
        "explore" to continue exploration, "recommend" to show vehicles
    """
    # If exploration mode is already complete, proceed to recommendations
    if state.get("exploration_mode") == "complete":
        return "recommend"

    # Check if we've hit the maximum question threshold
    max_questions = int(os.getenv("MAX_EXPLORATION_QUESTIONS", "6"))
    questions_asked = len(state.get("exploration_questions_asked", []))

    if questions_asked >= max_questions:
        # Force transition to recommendations
        print(f"🔔 Maximum exploration questions ({max_questions}) reached. Moving to recommendations.")
        state["exploration_mode"] = "complete"
        state["readiness_score"] = 60  # Moderate confidence since forced
        return "recommend"

    # Use semantic evaluation to check readiness
    evaluation = evaluate_readiness(state)

    # Check the recommendation from the evaluation
    recommendation = evaluation.get("recommendation", "explore_more")

    if recommendation == "proceed":
        # Mark exploration as complete
        state["exploration_mode"] = "complete"
        # Store the confidence score for reference
        state["readiness_score"] = evaluation.get("confidence", 70)
        return "recommend"
    else:
        # Continue exploring
        return "explore"


def should_use_web_research(state: VehicleSearchState) -> bool:
    """
    Determine if web research would be helpful before making recommendations.

    Web research is useful when:
    1. User has strong lifestyle/use case insights but NO specific makes/models
    2. User mentions specific needs that benefit from research (e.g., "best for families", "most reliable")
    3. We have rich context and want expert recommendations

    IMPORTANT: Don't use web research for simple/generic cases. Only when we have
    detailed lifestyle insights that would benefit from market research.

    Args:
        state: Current vehicle search state

    Returns:
        True if web research should be performed
    """
    filters = state.get("explicit_filters", {})
    implicit = state.get("implicit_preferences", {})
    insights = state.get("exploration_insights", {})

    # Check if user has specified explicit make/model - if so, NO web research
    has_specific_vehicle = filters.get("make") or filters.get("model")
    if has_specific_vehicle:
        return False

    # Check if we have RICH lifestyle/use case insights (not just generic)
    has_rich_insights = (
        # Must have at least 2 of these:
        sum([
            bool(insights.get("use_cases") and len(insights.get("use_cases", [])) >= 2),
            bool(insights.get("lifestyle_notes")),
            bool(insights.get("must_haves") and len(insights.get("must_haves", [])) >= 2),
            bool(implicit.get("priorities") and len(implicit.get("priorities", [])) >= 2),
            bool(insights.get("current_situation"))
        ]) >= 2
    )

    # Also check for budget (web research is more useful with a budget constraint)
    has_budget = bool(filters.get("price"))

    # Use web research ONLY if we have rich insights AND a budget
    # This prevents generic searches like "commuting car under 40k" from triggering web research
    return has_rich_insights and has_budget
