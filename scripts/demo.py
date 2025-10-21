"""
Interactive demo for the vehicle search agent.
"""
import os
import sys
# Add parent directory to path to import idss_agent
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from idss_agent import run_agent, create_initial_state
from idss_agent.components.semantic_parser import format_state_summary
from langchain_core.messages import HumanMessage, AIMessage
import json


def print_separator():
    """Print a visual separator."""
    print("\n" + "=" * 70 + "\n")


def print_state(state):
    """Print the current state in a formatted way."""
    print("📊 Current Search State:")
    print(format_state_summary(state))
    print(f"\n🚗 Recommendations: {len(state['recommended_vehicles'])} vehicles")
    print(f"📋 Interview Status: {'Completed ✓' if state.get('interviewed', False) else 'In Progress...'}")
    if not state.get('interviewed', False):
        print(f"❓ Interview Questions Asked: {len(state.get('interview_questions_asked', []))}")


def print_vehicle_listings(vehicles, limit=10):
    """Print vehicle listings in a formatted way."""
    if not vehicles:
        print("\n📋 No vehicles in recommendation list yet.")
        return

    print(f"\n📋 Vehicle Listings (showing {min(limit, len(vehicles))} of {len(vehicles)}):")
    print("=" * 80)

    for i, vehicle in enumerate(vehicles[:limit], 1):
        # Extract vehicle details (handle different possible structures)
        v_info = vehicle.get('vehicle', vehicle)
        retail = vehicle.get('retailListing', {})

        year = v_info.get('year', 'N/A')
        make = v_info.get('make', 'N/A')
        model = v_info.get('model', 'N/A')
        trim = v_info.get('trim', '')

        # Price and location
        price = retail.get('price', 'N/A')
        if isinstance(price, (int, float)) and price > 0:
            price_str = f"${price:,}"
        else:
            price_str = "Contact Dealer"

        # Mileage
        miles = retail.get('miles', v_info.get('mileage', 'N/A'))
        if isinstance(miles, (int, float)):
            miles_str = f"{miles:,} mi"
        else:
            miles_str = str(miles)

        # Location
        city = retail.get('city', 'N/A')
        state = retail.get('state', 'N/A')
        location = f"{city}, {state}" if city != 'N/A' else 'N/A'

        # VIN
        vin = v_info.get('vin', 'N/A')

        # Print formatted listing
        print(f"\n#{i}. {year} {make} {model} {trim}".strip())
        print(f"    💰 Price: {price_str}")
        print(f"    🛣️  Mileage: {miles_str}")
        print(f"    📍 Location: {location}")
        print(f"    🔑 VIN: {vin}")

    print("\n" + "=" * 80)


def print_conversation_history(state):
    """Print the full conversation history."""
    print("\n💬 Conversation History:")
    print("=" * 70)

    if not state.get("conversation_history"):
        print("No conversation history yet.")
        return

    for i, msg in enumerate(state["conversation_history"], 1):
        if isinstance(msg, HumanMessage):
            print(f"\n[{i}] 👤 User:")
            print(f"    {msg.content}")
        elif isinstance(msg, AIMessage):
            print(f"\n[{i}] 🤖 Assistant:")
            print(f"    {msg.content}")

    print("\n" + "=" * 70)


def interactive_demo():
    """Run an interactive demo of the vehicle search agent."""
    # Load environment variables
    load_dotenv()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not found in environment variables.")
        print("Please set it in a .env file or export it as an environment variable.")
        return

    print_separator()
    print("🚗 Vehicle Search Agent - Interactive Demo")
    print_separator()

    print("This is a conversational vehicle shopping assistant.")
    print("The agent will help you find vehicles and answer questions.")
    print("\nCommands:")
    print("  - Type your vehicle search query or questions")
    print("  - Type 'state' to see the current filters and preferences")
    print("  - Type 'reset' to start over")
    print("  - Type 'quit' or 'exit' to end")
    print_separator()

    # Initialize state
    current_state = create_initial_state()

    while True:
        user_input = input("👤 You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ['quit', 'exit']:
            print_conversation_history(current_state)
            print("\n👋 Goodbye!")
            break

        if user_input.lower() == 'reset':
            current_state = create_initial_state()
            print("\n✅ State reset successfully!")
            continue

        if user_input.lower() == 'state':
            print_separator()
            print_state(current_state)
            print_separator()
            continue

        # Process the input
        try:
            current_state = run_agent(user_input, current_state)

            # Display agent response
            print(f"\n🤖 Agent: {current_state['ai_response']}")

            # Display vehicle listings
            if current_state['recommended_vehicles']:
                print_vehicle_listings(current_state['recommended_vehicles'], limit=10)

            print_separator()

        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            print("Please try again with a different query.")
            import traceback
            traceback.print_exc()


def batch_demo():
    """Run a pre-scripted demo with example queries."""
    # Load environment variables
    load_dotenv()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not found in environment variables.")
        print("Please set it in a .env file or export it as an environment variable.")
        return

    print_separator()
    print("🚗 Vehicle Search Agent - Batch Demo")
    print_separator()

    # Initialize state
    current_state = create_initial_state()

    # Example conversation
    test_queries = [
        "I'm looking for a reliable family SUV with good safety features",
        "Budget is around $30-35k, and I prefer Toyota or Honda",
        "It should have 3 rows of seating and preferably in white or silver color",
        "Actually, make that under 50,000 miles and in California"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Query {i}/{len(test_queries)}]")
        print(f"👤 User: {query}")

        try:
            current_state = run_agent(query, current_state)

            print_separator()
            print_state(current_state)
            print_separator()

            # Pause between queries for readability
            if i < len(test_queries):
                input("Press Enter to continue to next query...")

        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            continue

    print("\n✅ Demo completed!")
    print("\n📋 Final State (JSON):")
    print(json.dumps(current_state['explicit_filters'], indent=2))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        batch_demo()
    else:
        interactive_demo()
