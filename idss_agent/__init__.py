"""
IDSS Vehicle Search Agent

A conversational vehicle shopping assistant built with LangGraph.
"""
from idss_agent.core.agent import run_agent
from idss_agent.state.schema import (
    VehicleSearchState,
    VehicleFilters,
    ImplicitPreferences,
    create_initial_state,
    add_user_message,
    add_ai_message,
    get_latest_user_message
)

__version__ = "1.0.0"

__all__ = [
    "run_agent",
    "VehicleSearchState",
    "VehicleFilters",
    "ImplicitPreferences",
    "create_initial_state",
    "add_user_message",
    "add_ai_message",
    "get_latest_user_message",
]
