"""
State management for Interactive Decision Support System.

Simplified approach with just goal and information strings that get merged at each turn.
"""

from typing import TypedDict, List, Optional, Dict, Any
from typing_extensions import Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Simplified state structure for the IDSS agent."""
    # Core conversation data
    messages: Annotated[List[BaseMessage], add_messages]

    # Simplified state - just two main strings
    current_goal: Optional[str]
    previous_goal: Optional[str]
    information: Optional[str]  # All gathered information as a string
    previous_information: Optional[str]

    # Minimal execution context
    active_plan: List[tuple[str, str, str]]  # [(action_type, tool_name, description), ...]
    next_task_index: int  # Pointer to next task to execute
    needs_user_input: bool

    # Retrieved data storage - preserves full tool results
    retrieved_data: Dict[str, Any]  # Key: "step_X: description", Value: full tool result


def create_initial_state() -> AgentState:
    """Create a fresh state for new conversation."""
    return AgentState(
        messages=[],
        current_goal=None,
        previous_goal=None,
        information=None,
        previous_information=None,
        active_plan=[],
        next_task_index=0,
        needs_user_input=False,
        retrieved_data={}
    )