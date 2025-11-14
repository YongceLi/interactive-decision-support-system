#!/usr/bin/env python3
"""
Test script for quick replies feature.

Usage:
    python scripts/test_quick_replies.py "I want a reliable SUV"
    python scripts/test_quick_replies.py "What's the safety rating of the first one?" --state previous_state.json
"""
import argparse
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

from idss_agent.core.supervisor import run_supervisor
from idss_agent.state.schema import VehicleSearchState


def print_separator(char="=", length=80):
    """Print a separator line."""
    print(char * length)


def print_response(state: VehicleSearchState):
    """Pretty print the agent's response and interactive elements."""
    print_separator()
    print("AGENT RESPONSE:")
    print_separator("-")
    print(state.get('ai_response', ''))
    print()

    # Quick replies
    quick_replies = state.get('quick_replies')
    if quick_replies:
        print_separator("-")
        print("QUICK REPLIES (answer options for questions):")
        for i, reply in enumerate(quick_replies, 1):
            print(f"  [{i}] {reply}")
        print()

    # Suggested followups
    suggested_followups = state.get('suggested_followups', [])
    if suggested_followups:
        print_separator("-")
        print("SUGGESTED FOLLOW-UPS (predicted next queries):")
        for i, followup in enumerate(suggested_followups, 1):
            print(f"  [{i}] {followup}")
        print()

    print_separator()


def save_state(state: VehicleSearchState, output_path: str):
    """Save state to JSON file for multi-turn testing."""
    # Convert to serializable dict
    state_dict = dict(state)

    # Remove non-serializable items
    if 'messages' in state_dict:
        state_dict['messages'] = [
            {
                'role': 'user' if msg.__class__.__name__ == 'HumanMessage' else 'assistant',
                'content': msg.content
            }
            for msg in state_dict['messages']
        ]

    with open(output_path, 'w') as f:
        json.dump(state_dict, f, indent=2, default=str)

    print(f"✓ State saved to {output_path}")


def load_state(input_path: str) -> VehicleSearchState:
    """Load state from JSON file."""
    from langchain_core.messages import HumanMessage, AIMessage

    with open(input_path, 'r') as f:
        state_dict = json.load(f)

    # Convert messages back to LangChain format
    if 'messages' in state_dict:
        messages = []
        for msg in state_dict['messages']:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            else:
                messages.append(AIMessage(content=msg['content']))
        state_dict['messages'] = messages

    return state_dict


def main():
    parser = argparse.ArgumentParser(
        description="Test quick replies with a single query",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single turn
  python scripts/test_quick_replies.py "I want a reliable SUV under $30k"

  # Save state for multi-turn testing
  python scripts/test_quick_replies.py "Show me Honda Accords" --save state.json

  # Continue from saved state
  python scripts/test_quick_replies.py "What's the safety rating?" --state state.json
        """
    )
    parser.add_argument(
        "query",
        type=str,
        help="User query to test"
    )
    parser.add_argument(
        "--state",
        type=str,
        help="Path to load previous state from (for multi-turn testing)"
    )
    parser.add_argument(
        "--save",
        type=str,
        help="Path to save resulting state to (for multi-turn testing)"
    )
    parser.add_argument(
        "--show-state",
        action="store_true",
        help="Show full state at the end (verbose)"
    )

    args = parser.parse_args()

    print_separator()
    print("QUICK REPLIES TEST")
    print_separator()
    print(f"Query: {args.query}")
    print()

    # Initialize or load state
    if args.state:
        print(f"Loading state from {args.state}...")
        state = load_state(args.state)
        print(f"✓ Loaded (conversation has {len(state.get('messages', []))} messages)")
        print()
    else:
        print("Initializing new conversation...")
        state = VehicleSearchState(
            messages=[],
            conversation_history=[],  # Add conversation_history
            explicit_filters={},
            implicit_preferences={},
            recommended_vehicles=[],
            favorited_vehicles=[],
            ai_response="",
            quick_replies=None,
            suggested_followups=[],
            comparison_table=None,
            interviewed=False,
            questions_asked=[],
            current_mode="supervisor"
        )
        print("✓ New state initialized")
        print()

    # Run supervisor
    print("Running agent...")
    print_separator("-")

    try:
        result_state = run_supervisor(
            user_input=args.query,
            state=state
        )

        print()
        print("✓ Agent completed")
        print()

        # Print response
        print_response(result_state)

        # Show filters if updated
        if result_state.get('explicit_filters'):
            print_separator("-")
            print("EXTRACTED FILTERS:")
            print(json.dumps(result_state['explicit_filters'], indent=2))
            print()

        # Show vehicle count
        vehicles = result_state.get('recommended_vehicles', [])
        if vehicles:
            print_separator("-")
            print(f"VEHICLES FOUND: {len(vehicles)}")
            print()

        # Save state if requested
        if args.save:
            save_state(result_state, args.save)
            print()

        # Show full state if requested
        if args.show_state:
            print_separator()
            print("FULL STATE:")
            print_separator("-")
            state_copy = dict(result_state)
            # Remove large fields for readability
            state_copy.pop('messages', None)
            state_copy.pop('recommended_vehicles', None)
            print(json.dumps(state_copy, indent=2, default=str))
            print()

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
