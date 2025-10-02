"""Factories for planner, executor, and replanner nodes."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

from langchain_openai import ChatOpenAI

from .models import Act, Plan, Response
from .prompts import build_planner_prompt, build_replanner_prompt


def create_planner(**kwargs: Any) -> Any:
    """Create structured planner runnable."""

    prompt = build_planner_prompt()
    llm = ChatOpenAI(**kwargs)
    return prompt | llm.with_structured_output(Plan)


def create_replanner(**kwargs: Any) -> Any:
    """Create replanner runnable that can return either plan updates or a response."""

    prompt = build_replanner_prompt()
    llm = ChatOpenAI(**kwargs)
    return prompt | llm.with_structured_output(Act)


def create_agent_executor(tools: Iterable[Any], **kwargs: Any) -> Any:
    """Create the ReAct agent executor with provided tools."""

    from langgraph.prebuilt import create_react_agent

    default_prompt = """You are an automotive decision support agent helping users find the perfect vehicle.

When completing tasks:
1. Use ask_human to gather any missing information you need
2. Use the vehicle search and listing tools to find and analyze vehicles
3. Use present_to_human to share your findings, updates, and recommendations with the user
"""

    prompt = kwargs.pop("prompt", default_prompt)
    llm = ChatOpenAI(**kwargs)
    tools_sequence: Sequence[Any]
    if isinstance(tools, Sequence):
        tools_sequence = tools
    else:
        tools_sequence = tuple(tools)
    return create_react_agent(llm, tools_sequence, prompt=prompt)


def default_planner_config() -> Dict[str, Any]:
    """Default parameters for planner LLM."""

    return {"model": "gpt-4o", "temperature": 0}


def default_replanner_config() -> Dict[str, Any]:
    """Default parameters for replanner LLM."""

    return {"model": "gpt-4o", "temperature": 0}


def default_agent_config() -> Dict[str, Any]:
    """Default parameters for agent executor LLM."""

    return {"model": "gpt-4-turbo-preview"}


__all__ = [
    "create_planner",
    "create_replanner",
    "create_agent_executor",
    "default_planner_config",
    "default_replanner_config",
    "default_agent_config",
]

