"""Typed definitions for the plan-execute workflow state."""

from __future__ import annotations

import operator
from typing import Annotated, List, Tuple

from typing_extensions import NotRequired, TypedDict


class PlanExecuteState(TypedDict, total=False):
    """State container passed between planner, executor, and replanner nodes."""

    input: str
    plan: List[str]
    past_steps: NotRequired[Annotated[List[Tuple[str, str]], operator.add]]
    response: NotRequired[str]

