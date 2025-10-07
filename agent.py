"""
LangGraph agent for vehicle search with semantic parsing.
"""
from langgraph.graph import StateGraph, END
from state_schema import VehicleSearchState, create_initial_state, add_user_message
from semantic_parser import semantic_parser_node, format_state_summary


def create_vehicle_search_agent() -> StateGraph:
    """
    Create a LangGraph workflow for vehicle search with semantic parsing.

    The workflow:
    1. Starts with user input (already added to conversation history)
    2. Runs semantic parser to extract filters and preferences
    3. Ends (ready for expansion with more nodes)

    Returns:
        Compiled LangGraph workflow
    """
    # Create the graph
    workflow = StateGraph(VehicleSearchState)

    # Add the semantic parser node
    workflow.add_node("semantic_parser", semantic_parser_node)

    # Set entry point
    workflow.set_entry_point("semantic_parser")

    # For now, just end after parsing (we'll add more nodes later)
    workflow.add_edge("semantic_parser", END)

    # Compile the graph
    return workflow.compile()


def run_agent(user_input: str, state: VehicleSearchState = None) -> VehicleSearchState:
    """
    Run the vehicle search agent with user input.

    Args:
        user_input: User's message/query
        state: Optional existing state (for continuing conversations)

    Returns:
        Updated state after processing
    """
    # Create initial state if none provided
    if state is None:
        state = create_initial_state()

    # Add user message to conversation history
    state = add_user_message(state, user_input)

    # Create and run the agent
    agent = create_vehicle_search_agent()
    result = agent.invoke(state)

    return result


if __name__ == "__main__":
    # Simple test
    print("Vehicle Search Agent - Semantic Parser Demo")
    print("=" * 50)

    # Initialize state
    current_state = create_initial_state()

    # Test conversation
    test_inputs = [
        "I'm looking for a reliable family SUV with good safety features",
        "Budget is around $30-35k, and I prefer Toyota or Honda",
        "It should have 3 rows and preferably in white or silver color"
    ]

    for user_msg in test_inputs:
        print(f"\n👤 User: {user_msg}")
        current_state = run_agent(user_msg, current_state)

        print(f"\n🤖 Parsed State:")
        print(format_state_summary(current_state))
        print("-" * 50)
