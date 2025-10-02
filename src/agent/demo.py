"""Convenience helpers for interacting with the plan-execute agent."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict

from langchain_core.runnables.graph import MermaidDrawMethod

from .workflow import build_plan_execute_app


def create_demo_app(**overrides: Any):
    """Return a compiled plan-execute application with optional configuration overrides."""

    return build_plan_execute_app(**overrides)


def render_graph(app: Any, *, xray: bool = True) -> bytes:
    """Render the workflow graph to PNG bytes for visualization."""

    graph = app.get_graph(xray=xray)
    draw_method = getattr(MermaidDrawMethod, "CLIENT", None)
    if draw_method is not None:
        return graph.draw_mermaid_png(draw_method=draw_method)
    return graph.draw_mermaid_png()


async def run_demo_stream(
    app: Any, user_input: str, *, config: Dict[str, Any] | None = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """Async generator of events from the app for a given input."""

    async for event in app.astream(
        {"input": user_input}, config=config or {"recursion_limit": 50}
    ):
        yield event


__all__ = [
    "create_demo_app",
    "render_graph",
    "run_demo_stream",
]

