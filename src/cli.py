#!/usr/bin/env python3
"""Rich interactive CLI for the IDSS agent."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.agent import build_plan_execute_app


class IDSSCli:
    """Interactive CLI for the IDSS agent."""

    def __init__(self, recursion_limit: int = 50, debug: bool = False):
        self.console = Console()
        self.recursion_limit = recursion_limit
        self.debug = debug
        self.app = None  # Will be initialized after env vars are loaded
        self.conversation_history: list[tuple[str, str]] = []

    def print_banner(self) -> None:
        """Display welcome banner."""
        banner = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║     Interactive Decision Support System (IDSS)          ║
║        Automotive Purchase Intelligence Agent           ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
        self.console.print(banner, style="bold cyan")
        mode_text = " [DEBUG MODE]" if self.debug else ""
        self.console.print(
            f"Type your automotive request or 'help' for commands. 'exit' to quit.{mode_text}\n",
            style="dim",
        )

    def print_help(self) -> None:
        """Display help information."""
        help_table = Table(show_header=True, header_style="bold magenta")
        help_table.add_column("Command", style="cyan", width=15)
        help_table.add_column("Description", style="white")

        help_table.add_row("help", "Show this help message")
        help_table.add_row("exit / quit", "Exit the application")
        help_table.add_row("clear / cls", "Clear the screen")
        help_table.add_row("history", "Show conversation history")
        help_table.add_row("new", "Start a new conversation")
        help_table.add_row("debug", "Toggle debug mode on/off")
        help_table.add_row("[any text]", "Submit a request to the agent")

        self.console.print(Panel(help_table, title="Available Commands", border_style="blue"))

    def print_history(self) -> None:
        """Display conversation history."""
        if not self.conversation_history:
            self.console.print("[dim]No conversation history yet.[/dim]")
            return

        history_table = Table(show_header=True, header_style="bold yellow")
        history_table.add_column("#", style="cyan", width=5)
        history_table.add_column("User Request", style="white", width=40)
        history_table.add_column("Agent Response", style="green", width=40)

        for idx, (user_msg, agent_msg) in enumerate(self.conversation_history, 1):
            # Truncate long messages
            user_truncated = (
                user_msg[:80] + "..." if len(user_msg) > 80 else user_msg
            )
            agent_truncated = (
                agent_msg[:80] + "..." if len(agent_msg) > 80 else agent_msg
            )
            history_table.add_row(str(idx), user_truncated, agent_truncated)

        self.console.print(Panel(history_table, title="Conversation History", border_style="yellow"))

    def format_event_value(self, value: Any) -> str:
        """Format event values for display."""
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, indent=2)
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    async def process_request(self, user_input: str) -> str:
        """Process a single user request and return the final response."""
        config = {"recursion_limit": self.recursion_limit}

        final_response = ""
        current_step = ""

        # Process without Live progress to avoid blocking input
        async for event in self.app.astream({"input": user_input}, config=config):
            if "__end__" in event:
                continue

            for node_name, value in event.items():
                # Update based on node
                if node_name == "planner":
                    if self.debug:
                        self.console.print("[cyan]📋 Creating execution plan...[/cyan]")
                    if isinstance(value, dict) and "plan" in value:
                        plan_steps = value.get("plan", [])
                        if self.debug:
                            self._display_plan(plan_steps)

                elif node_name == "agent":
                    if self.debug:
                        self.console.print("[yellow]🤖 Executing task...[/yellow]")
                    if isinstance(value, dict) and "past_steps" in value:
                        past_steps = value.get("past_steps", [])
                        if past_steps:
                            last_step = past_steps[-1]
                            current_step = last_step[0] if len(last_step) > 0 else ""
                            if self.debug:
                                self._display_step_result(last_step)

                elif node_name == "replan":
                    if self.debug:
                        self.console.print("[magenta]🔄 Replanning...[/magenta]")
                    if isinstance(value, dict) and "response" in value:
                        final_response = value.get("response", "")
                        if self.debug:
                            self.console.print("[green]✅ Complete![/green]")

        return final_response or "Task completed successfully."

    def _display_plan(self, plan_steps: list[str]) -> None:
        """Display the execution plan."""
        if not plan_steps:
            return

        plan_table = Table(show_header=False, border_style="cyan", padding=(0, 1))
        plan_table.add_column("Step", style="bold cyan", width=5)
        plan_table.add_column("Description", style="white")

        for idx, step in enumerate(plan_steps, 1):
            plan_table.add_row(f"{idx}.", step)

        self.console.print(Panel(plan_table, title="📋 Execution Plan", border_style="cyan"))

    def _display_step_result(self, step_tuple: tuple) -> None:
        """Display the result of a completed step."""
        if len(step_tuple) != 2:
            return

        task_description, result = step_tuple

        self.console.print(
            Panel(
                f"[bold]Task:[/bold] {task_description}\n\n[bold]Result:[/bold] {result}",
                title="✅ Step Completed",
                border_style="green",
            )
        )

    async def run_interactive(self) -> None:
        """Run the interactive CLI loop."""
        load_dotenv()

        # Initialize the app after loading environment variables
        if self.app is None:
            self.app = build_plan_execute_app()

        self.print_banner()

        while True:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold blue]You[/bold blue]").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ["exit", "quit"]:
                    self.console.print("\n[cyan]Goodbye! 👋[/cyan]\n")
                    break

                if user_input.lower() in ["clear", "cls"]:
                    self.console.clear()
                    self.print_banner()
                    continue

                if user_input.lower() == "help":
                    self.print_help()
                    continue

                if user_input.lower() == "history":
                    self.print_history()
                    continue

                if user_input.lower() == "new":
                    self.conversation_history.clear()
                    self.console.print("[green]Started new conversation.[/green]")
                    continue

                if user_input.lower() == "debug":
                    self.debug = not self.debug
                    status = "enabled" if self.debug else "disabled"
                    self.console.print(f"[cyan]Debug mode {status}.[/cyan]")
                    continue

                # Process the request
                self.console.print()  # Add spacing
                response = await self.process_request(user_input)

                # The agent will continue asking for next steps via ask_human
                # No need to show completion message

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use 'exit' to quit.[/yellow]")
            except EOFError:
                self.console.print("\n[cyan]Goodbye! 👋[/cyan]\n")
                break
            except Exception as e:
                self.console.print(f"\n[bold red]Error:[/bold red] {e}\n")


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Interactive Decision Support System for automotive purchases"
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=50,
        help="Maximum recursion depth for agent execution",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed execution information",
    )
    args = parser.parse_args()

    cli = IDSSCli(recursion_limit=args.recursion_limit, debug=args.debug)
    asyncio.run(cli.run_interactive())


if __name__ == "__main__":
    main()
