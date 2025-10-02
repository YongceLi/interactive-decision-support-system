"""Data models shared across planner and executor nodes."""

from __future__ import annotations

from typing import List, Union

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """Plan to follow in future."""

    steps: List[str] = Field(
        description="A list of executable subtasks, should be in sorted order"
    )


class Response(BaseModel):
    """Response to user."""

    response: str


class Act(BaseModel):
    """Container for replanner action (response or follow-up plan)."""

    action: Union[Response, Plan] = Field(
        description=(
            "Action to perform. If you want to respond to user, use Response. "
            "If you need to change your plan and further use tools to get the answer, use Plan."
        )
    )


__all__ = [
    "Plan",
    "Response",
    "Act",
]

