"""
CLI interface for testing the Interactive Decision Support System.

This provides a simple command-line interface to test the goal understanding
functionality with the minimal LangGraph implementation.
"""

import sys
import os
import json
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
load_dotenv(os.path.join(project_root, '.env'))

sys.path.insert(0, project_root)

from src.core.agent import IDSSAgent
from src.core.state import AgentState, create_initial_state

class IDSS_CLI:
    """Command-line interface for testing IDSS goal understanding."""

    def __init__(self, debug: bool = False):
        self.agent = IDSSAgent()
        self.debug = debug
        self.state: Optional[AgentState] = None

    def run(self):
        """Run the interactive CLI."""
        print("🚗 Interactive Decision Support System - Complete Workflow Test")
        print("=" * 60)
        print("Type your automotive questions or requests.")
        print("Commands: /debug (toggle debug), /reset (new session), /quit (exit)")
        print("=" * 60)

        self.state = create_initial_state()

        while True:
            try:
                user_input = input("\nYou: ").strip()

                if not user_input:
                    continue

                # Handle special commands
                if user_input.startswith('/'):
                    self._handle_command(user_input)
                    continue

                # Process user message (now synchronous)
                response, self.state = self.agent.chat("default_user", user_input, self.state)

                print(f"\nAgent: {response}")

                # Show debug information if enabled
                if self.debug:
                    self._show_debug_info()

            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"\nError: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()

    def _handle_command(self, command: str):
        """Handle special CLI commands."""
        if command == '/quit':
            print("Goodbye! 👋")
            sys.exit(0)

        elif command == '/debug':
            self.debug = not self.debug
            print(f"Debug mode: {'ON' if self.debug else 'OFF'}")

        elif command == '/reset':
            self.state = create_initial_state()
            print("Session reset. Starting fresh conversation.")

        elif command == '/state':
            self._show_full_state()

        elif command == '/help':
            self._show_help()

        else:
            print("Unknown command. Type /help for available commands.")

    def _show_debug_info(self):
        """Show current state information for debugging."""
        print("\n" + "━" * 60)
        print("🔍 DEBUG: GOAL UNDERSTANDING STATE")
        print("━" * 60)

        # Current Goal
        goal = self.state.get("current_goal", "None")
        print(f"📋 CURRENT GOAL: {goal}")

        # Previous Goal (if exists)
        prev_goal = self.state.get("previous_goal")
        if prev_goal:
            print(f"📝 PREVIOUS GOAL: {prev_goal}")
        print()

        # User-provided information
        information = self.state.get("information", "None")
        print(f"👤 USER INFORMATION: {information}")
        print()

        # Conversation History (simplified)
        messages = self.state.get("messages", [])
        print(f"💬 CONVERSATION ({len(messages)} messages):")
        for i, msg in enumerate(messages[-2:], 1):  # Show last 2 messages
            msg_type = "You" if msg.__class__.__name__ == "HumanMessage" else "Agent"
            content = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
            print(f"   {msg_type}: {content}")
        print()

        # Plan information
        active_plan = self.state.get("active_plan", [])
        next_task_index = self.state.get("next_task_index", 0)

        if active_plan:
            print(f"📋 EXECUTION PLAN ({len(active_plan)} tasks):")
            for i, (action_type, tool_name, description) in enumerate(active_plan):
                # Status indicators
                if i < next_task_index:
                    status = "✅"  # Completed
                elif i == next_task_index:
                    status = "➡️"  # Next to execute
                else:
                    status = "⏳"  # Pending

                # Task info with all three elements
                tool_info = f" | {tool_name}" if tool_name else " | "
                print(f"   {status} {i+1}. {action_type} | {tool_info} | {description}")
            print()

        # Retrieved data information
        retrieved_data = self.state.get("retrieved_data", {})
        if retrieved_data:
            print(f"🗃️ RETRIEVED DATA ({len(retrieved_data)} results):")
            for step_key, data in retrieved_data.items():
                print(f"   📁 {step_key}")
                if isinstance(data, dict):
                    # Show key data points
                    for key, value in list(data.items())[:3]:  # Show first 3 keys
                        if key != "raw_response":
                            if isinstance(value, list):
                                print(f"      {key}: {len(value)} items")
                            else:
                                value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                                print(f"      {key}: {value_str}")
                else:
                    data_str = str(data)[:100] + "..." if len(str(data)) > 100 else str(data)
                    print(f"      {data_str}")
            print()

        print("━" * 60)

    def _show_full_state(self):
        """Show the complete state as JSON."""
        print("\n" + "─" * 40 + " FULL STATE " + "─" * 40)

        # Convert state to JSON-serializable format
        state_copy = dict(self.state)

        # Convert messages to strings for readability
        if "messages" in state_copy:
            state_copy["messages"] = [
                f"{msg.__class__.__name__}: {msg.content}"
                for msg in state_copy["messages"]
            ]

        print(json.dumps(state_copy, indent=2, default=str))
        print("─" * 91)

    def _show_help(self):
        """Show help information."""
        print("\nAvailable commands:")
        print("  /debug  - Toggle debug mode (shows state after each message)")
        print("  /reset  - Reset conversation state")
        print("  /state  - Show full current state")
        print("  /help   - Show this help")
        print("  /quit   - Exit the application")
        print("\nTry asking about cars:")
        print("  'I need a hybrid SUV under $40k'")
        print("  'Find me a reliable family car'")
        print("  'Compare Tesla Model 3 vs Honda Accord'")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="IDSS Goal Understanding Test CLI")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    cli = IDSS_CLI(debug=args.debug)
    cli.run()


if __name__ == "__main__":
    main()