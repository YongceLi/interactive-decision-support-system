"""
IDSS Vehicle Search Agent

A conversational vehicle shopping assistant built with LangGraph.
"""
from idss_agent.agent import create_vehicle_agent, run_agent
from idss_agent.state import (
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
    "create_vehicle_agent",
    "run_agent",
    "VehicleSearchState",
    "VehicleFilters",
    "ImplicitPreferences",
    "create_initial_state",
    "add_user_message",
    "add_ai_message",
    "get_latest_user_message",
]
