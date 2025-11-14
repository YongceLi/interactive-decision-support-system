"""
IDSS Product Search Agent

A conversational product shopping assistant built with LangGraph.
"""
from idss_agent.core.agent import run_agent
from idss_agent.state.schema import (
    ProductSearchState,
    ProductFilters,
    ImplicitPreferences,
    create_initial_state,
    add_user_message,
    add_ai_message,
    get_latest_user_message
)

__version__ = "1.0.0"

__all__ = [
    "run_agent",
    "ProductSearchState",
    "ProductFilters",
    "ImplicitPreferences",
    "create_initial_state",
    "add_user_message",
    "add_ai_message",
    "get_latest_user_message",
]
