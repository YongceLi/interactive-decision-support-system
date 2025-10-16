"""
Complete vehicle search agent workflow using LangGraph.
"""
from langgraph.graph import StateGraph, END
from idss_agent.state import VehicleSearchState, create_initial_state, add_user_message, add_ai_message
from idss_agent.nodes.semantic_parser import semantic_parser_node
from idss_agent.nodes.exploration import exploration_node
from idss_agent.nodes.readiness_router import check_exploration_readiness, should_use_web_research
from idss_agent.nodes.web_research_node import web_research_node
from idss_agent.nodes.recommendation import update_recommendation_list
from idss_agent.nodes.mode_router import route_conversation_mode, should_update_recommendations
from idss_agent.nodes.discovery import discovery_response_generator
from idss_agent.nodes.analytical import analytical_response_generator


def web_research_router(state: VehicleSearchState):
    """Route to web research if needed, otherwise go to recommendations."""
    if should_use_web_research(state):
        return "web_research"
    else:
        return "should_update_check"


def create_vehicle_agent():
    """
    Create the complete vehicle search agent workflow.

    New Workflow with Exploration Phase:
    1. User message → Semantic Parser (extract filters/preferences)
    2. Exploration Readiness Check:
       - If not ready → Exploration Node (ask human-like questions)
       - If ready → Proceed to recommendations
    3. (Optional) Web Research (if implicit preferences need enrichment)
    4. Update Recommendations (ReAct agent gets 20 vehicles)
    5. Route Mode (discovery or analytical)
    6. Discovery: Show vehicles + ask questions
       OR
       Analytical: Answer specific question with tools
    7. Return response

    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(VehicleSearchState)

    # Add all nodes
    workflow.add_node("semantic_parser", semantic_parser_node)
    workflow.add_node("exploration", exploration_node)
    workflow.add_node("web_research", web_research_node)
    workflow.add_node("update_recommendations", update_recommendation_list)
    workflow.add_node("discovery_responder", discovery_response_generator)
    workflow.add_node("analytical_responder", analytical_response_generator)

    # Define the flow
    workflow.set_entry_point("semantic_parser")

    # After semantic parsing, check if we should explore or recommend
    workflow.add_conditional_edges(
        "semantic_parser",
        check_exploration_readiness,  # Returns "explore" or "recommend"
        {
            "explore": "exploration",  # Continue asking questions
            "recommend": "web_research_check"  # Proceed to recommendations
        }
    )

    # If exploring, end the turn (user will respond to questions)
    workflow.add_edge("exploration", END)

    # Placeholder node for web research routing
    workflow.add_node("web_research_check", lambda state: state)

    # Check if we should do web research before recommendations
    workflow.add_conditional_edges(
        "web_research_check",
        web_research_router,
        {
            "web_research": "web_research",
            "should_update_check": "should_update_check"
        }
    )

    # After web research, go to update check
    workflow.add_edge("web_research", "should_update_check")

    # Placeholder node for should_update routing
    workflow.add_node("should_update_check", lambda state: state)

    # Conditionally update recommendations only if filters changed
    workflow.add_conditional_edges(
        "should_update_check",
        should_update_recommendations,  # Returns "update" or "skip"
        {
            "update": "update_recommendations",
            "skip": "mode_router"
        }
    )

    # After updating recommendations, route to mode router
    workflow.add_node("mode_router", lambda state: state)  # Pass-through node for routing
    workflow.add_edge("update_recommendations", "mode_router")

    # Route based on message mode
    workflow.add_conditional_edges(
        "mode_router",
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
