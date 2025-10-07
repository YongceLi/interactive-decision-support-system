"""
Complete vehicle search agent workflow using LangGraph.
"""
from langgraph.graph import StateGraph, END
from state_schema import VehicleSearchState, create_initial_state, add_user_message, add_ai_message
from semantic_parser import semantic_parser_node
from recommendation_agent import update_recommendation_list
from mode_router import route_conversation_mode
from discovery_agent import discovery_response_generator
from analytical_agent import analytical_response_generator


def create_vehicle_agent():
    """
    Create the complete vehicle search agent workflow.

    Workflow:
    1. User message → Semantic Parser (extract filters/preferences)
    2. Update Recommendations (ReAct agent gets 20 vehicles)
    3. Route Mode (discovery or analytical)
    4. Discovery: Show vehicles + ask questions
       OR
       Analytical: Answer specific question with tools
    5. Return response

    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(VehicleSearchState)

    # Add all nodes
    workflow.add_node("semantic_parser", semantic_parser_node)
    workflow.add_node("update_recommendations", update_recommendation_list)
    workflow.add_node("discovery_responder", discovery_response_generator)
    workflow.add_node("analytical_responder", analytical_response_generator)

    # Define the flow
    workflow.set_entry_point("semantic_parser")

    # Always update recommendations after parsing
    workflow.add_edge("semantic_parser", "update_recommendations")

    # Route based on message mode after recommendations are updated
    workflow.add_conditional_edges(
        "update_recommendations",
        route_conversation_mode,  # Returns "discovery" or "analytical"
        {
            "discovery": "discovery_responder",
            "analytical": "analytical_responder"
        }
    )

    # Both responders end the workflow
    workflow.add_edge("discovery_responder", END)
    workflow.add_edge("analytical_responder", END)

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
    agent = create_vehicle_agent()
    result = agent.invoke(state)

    # Add AI response to conversation history
    if result.get('ai_response'):
        result = add_ai_message(result, result['ai_response'])

    return result


if __name__ == "__main__":
    # Simple test
    print("Vehicle Search Agent - Full Workflow Test")
    print("=" * 70)

    # Initialize state
    current_state = create_initial_state()

    # Test conversation
    test_inputs = [
        "I want to buy a Jeep",
        "Around $30k, I'm in Colorado",
        "Tell me more about #1"
    ]

    for i, user_msg in enumerate(test_inputs, 1):
        print(f"\n[Turn {i}]")
        print(f"👤 User: {user_msg}")
        print("-" * 70)

        try:
            current_state = run_agent(user_msg, current_state)

            print(f"🤖 Agent: {current_state['ai_response']}")
            print(f"\n📊 Recommendations: {len(current_state['recommended_vehicles'])} vehicles")
            print(f"📝 Questions Asked: {current_state['questions_asked']}")
            print("=" * 70)

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            break
