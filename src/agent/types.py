"""Typed definitions for the plan-execute workflow state."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Tuple

from langgraph.graph import MessagesState


class PlanExecuteState(MessagesState):
    """State container passed between planner, executor, and replanner nodes.

    Extends LangGraph's MessagesState to include:
    - messages: Conversation history (inherited from MessagesState with add_messages reducer)
    - plan: Current plan steps
    - past_steps: Executed steps with results (accumulated via operator.add)
    - tool_results: Tool call results (accumulated via operator.add)
    - response: Final response when complete
    """

    input: str
    plan: List[str]
    past_steps: Annotated[List[Tuple[str, str]], operator.add]
    tool_results: Annotated[List[Dict[str, Any]], operator.add]
    response: str

