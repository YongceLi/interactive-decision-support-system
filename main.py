#!/usr/bin/env python3
"""Command-line entry point for the interactive plan-execute agent."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict

from dotenv import load_dotenv

from src.agent import build_plan_execute_app


def _format_value(value: Any) -> str:
    """Pretty-print helper for agent events."""

    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


async def _run_once(user_input: str, recursion_limit: int) -> None:
    """Execute a single request against the agent and stream events."""

    app = build_plan_execute_app()
    config = {"recursion_limit": recursion_limit}

    async for event in app.astream({"input": user_input}, config=config):
        if "__end__" in event:
            continue
        for key, value in event.items():
            print(f"[{key}] {_format_value(value)}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the interactive decision support agent from the terminal."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Initial user request (if omitted, you will be prompted).",
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=50,
        help="Maximum recursion depth for the LangGraph execution.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()

    args = parse_args()
    user_input = args.prompt
    if not user_input:
        try:
            user_input = input("Enter your automotive request: ").strip()
        except EOFError:
            raise SystemExit("No input provided.")

    if not user_input:
        raise SystemExit("User request cannot be empty.")

    try:
        asyncio.run(_run_once(user_input, args.recursion_limit))
    except KeyboardInterrupt:
        raise SystemExit("Interrupted by user.")


if __name__ == "__main__":
    main()

