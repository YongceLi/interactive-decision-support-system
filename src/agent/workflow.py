"""LangGraph workflow assembly for the plan-execute agent."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from langgraph.graph import END, START, StateGraph

from src.tools import (
    ask_human,
    get_vehicle_listing_by_vin,
    get_vehicle_photos_by_vin,
    present_to_human,
    search_vehicle_listings,
)

from .builder import (
    create_agent_executor,
    create_planner,
    create_replanner,
    default_agent_config,
    default_planner_config,
    default_replanner_config,
)
from .models import Plan, Response
from .types import PlanExecuteState


def _should_present_to_human(messages: List[Any], task: str) -> bool:
    """Determine if the executor gathered data that should be presented to the user."""
    # Check if any tool calls were made (excluding ask_human)
    data_gathering_tools = [
        "search_vehicle_listings",
        "get_vehicle_listing_by_vin",
        "get_vehicle_photos_by_vin",
    ]

    for message in messages:
        # Check for tool calls in the message
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.get("name", "")
                if tool_name in data_gathering_tools:
                    return True
        # Also check for ToolMessage (responses from tools)
        if hasattr(message, "type") and message.type == "tool":
            # Check if the content has substantial data (not just confirmations)
            content = getattr(message, "content", "")
            if isinstance(content, str) and len(content) > 100:
                return True

    return False


def _build_presentation_context(
    state: PlanExecuteState, messages: List[Any], task: str
) -> str:
    """Build context string for presentation from state and messages."""
    context_parts = []

    # Add the current task
    context_parts.append(f"Current Task: {task}")

    # Add user's original input
    user_input = state.get("input", "")
    if user_input:
        context_parts.append(f"User Goal: {user_input}")

    # Extract tool results from messages
    context_parts.append("\nTool Results:")
    for message in messages:
        if hasattr(message, "type") and message.type == "tool":
            tool_name = getattr(message, "name", "unknown_tool")
            content = getattr(message, "content", "")
            context_parts.append(f"\n{tool_name}:\n{content}")

    return "\n".join(context_parts)


def create_default_tools() -> List[Any]:
    """Return the default list of tools available to the agent."""

    return [
        search_vehicle_listings,
        get_vehicle_listing_by_vin,
        get_vehicle_photos_by_vin,
        ask_human,
        present_to_human,
    ]


def build_plan_execute_app(
    planner_factory: Callable[..., Any] | None = None,
    replanner_factory: Callable[..., Any] | None = None,
    agent_factory: Callable[..., Any] | None = None,
    tools: Iterable[Any] | None = None,
    planner_config: Mapping[str, Any] | None = None,
    replanner_config: Mapping[str, Any] | None = None,
    agent_config: Mapping[str, Any] | None = None,
) -> Any:
    """Assemble the plan-execute LangGraph workflow."""

    tools_iterable: Sequence[Any]
    if tools is None:
        tools_iterable = create_default_tools()
    else:
        if isinstance(tools, Sequence):
            tools_iterable = tools
        else:
            tools_iterable = tuple(tools)

    planner_factory = planner_factory or _default_planner_factory
    replanner_factory = replanner_factory or _default_replanner_factory
    agent_factory = agent_factory or _default_agent_factory

    planner = planner_factory(**(planner_config or default_planner_config()))
    replanner = replanner_factory(**(replanner_config or default_replanner_config()))
    agent_executor = agent_factory(
        tools_iterable,
        **(agent_config or default_agent_config()),
    )

    async def plan_step(state: PlanExecuteState) -> Dict[str, Any]:
        user_input = state.get("input")
        if not user_input:
            raise ValueError("Planner requires 'input' in state")
        plan_result = await planner.ainvoke({"messages": [("user", user_input)]})
        return {"plan": plan_result.steps}

    async def execute_step(state: PlanExecuteState) -> Dict[str, Any]:
        plan = list(state.get("plan") or [])
        if not plan:
            raise ValueError("Execute step received empty plan")
        plan_str = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(plan))
        task = plan[0]
        task_formatted = (
            f"For the following plan:\n{plan_str}\n\n"
            f"You are tasked with executing step 1, {task}."
        )
        agent_response = await agent_executor.ainvoke({"messages": [("user", task_formatted)]})
        agent_messages = (
            agent_response.get("messages")
            if isinstance(agent_response, dict)
            else getattr(agent_response, "messages", None)
        )
        if not agent_messages:
            raise ValueError("Agent executor returned no messages")
        final_message = agent_messages[-1]
        if hasattr(final_message, "content"):
            result_content = final_message.content
        else:
            result_content = str(final_message)

        # Check if we got meaningful data from tool calls that should be presented
        should_present = _should_present_to_human(agent_messages, task)
        if should_present:
            # Extract tool results and present to human
            presentation_context = _build_presentation_context(state, agent_messages, task)
            from src.tools import present_to_human
            present_to_human.invoke({"context": presentation_context})

        remaining_plan = plan[1:]
        past_steps = list(state.get("past_steps") or [])
        past_steps.append((task, result_content))
        update: Dict[str, Any] = {"past_steps": past_steps}
        if remaining_plan:
            update["plan"] = remaining_plan
        return update

    async def replan_step(state: PlanExecuteState) -> Dict[str, Any]:
        output = await replanner.ainvoke(state)
        action = output.action
        if isinstance(action, Response):
            return {"response": action.response}
        if isinstance(action, Plan):
            return {"plan": action.steps}
        raise ValueError("Unexpected replanner output")

    def should_end(state: PlanExecuteState) -> str:
        if state.get("response"):
            return END
        return "agent"

    workflow = StateGraph(PlanExecuteState)

    workflow.add_node("planner", plan_step)
    workflow.add_node("agent", execute_step)
    workflow.add_node("replan", replan_step)

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "agent")
    workflow.add_edge("agent", "replan")

    workflow.add_conditional_edges(
        "replan",
        should_end,
        ["agent", END],
    )

    return workflow.compile()


def _default_planner_factory(**kwargs: Any) -> Any:
    return create_planner(**kwargs)


def _default_replanner_factory(**kwargs: Any) -> Any:
    return create_replanner(**kwargs)


def _default_agent_factory(tools: List[Any], **kwargs: Any) -> Any:
    return create_agent_executor(tools, **kwargs)


__all__ = [
    "build_plan_execute_app",
    "create_default_tools",
]

