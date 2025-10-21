"""
Analytical agent - answers specific questions about vehicles using ReAct.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState
from idss_agent.components.autodev_apis import get_vehicle_listing_by_vin, get_vehicle_photos_by_vin
from idss_agent.components.vehicle_database import get_vehicle_database_tools
from idss_agent.logger import get_logger

logger = get_logger("components.analytical_tool")


def analytical_agent(state: VehicleSearchState) -> VehicleSearchState:
    """
    Agent that answers specific questions about vehicles using available data.

    This creates a ReAct agent with access to:
    - Vehicle details by VIN
    - Vehicle photos
    - Safety database
    - Fuel economy database

    Args:
        state: Current state with vehicle context and user question

    Returns:
        Updated state with ai_response
    """
    # Get user question from conversation history
    user_input = state.get("conversation_history", [])[-1].content if state.get("conversation_history") else ""
    logger.info(f"Analytical query: {user_input}")

    # Get available tools
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    db_tools = get_vehicle_database_tools(llm)
    tools = [
        get_vehicle_listing_by_vin,
        get_vehicle_photos_by_vin
    ] + db_tools

    # Build context from state
    vehicles = state.get("recommended_vehicles", [])

    # Create vehicle reference map (for "#1", "#2" references)
    vehicle_context = ""
    if vehicles:
        vehicle_context = "\n\nAvailable vehicles (user can reference by number):\n"
        for i, vehicle in enumerate(vehicles[:10], 1):
            v = vehicle.get("vehicle", {})
            listing = vehicle.get("retailListing", {})
            vehicle_context += f"#{i}: {v.get('year')} {v.get('make')} {v.get('model')}, ${listing.get('price', 0):,}, VIN: {v.get('vin')}\n"

    # Create analytical agent (reuse llm from above)
    agent = create_react_agent(llm, tools)

    # Build prompt
    prompt = f"""
You are a vehicle information specialist. Answer the user's question using available tools.

Context:
{vehicle_context}

User's question: {user_input}

Available tools:
- get_vehicle_listing_by_vin: Get detailed vehicle information by VIN
- get_vehicle_photos_by_vin: Get photos for a vehicle
- sql_db_query: Query safety_data and feature_data databases
- sql_db_schema: Get database schema
- sql_db_list_tables: List available tables

Instructions:
1. If user references a vehicle by number (e.g., "#1"), use the VIN from the context above
2. Use tools to gather information
3. Provide a concise, helpful answer
4. Format your response clearly

Answer the question.
"""

    try:
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})

        # Extract final response
        messages = result.get("messages", [])
        if messages:
            final_message = messages[-1]
            state["ai_response"] = final_message.content
        else:
            state["ai_response"] = "I couldn't find an answer to that question."
            logger.warning("Analytical agent: No messages returned from ReAct agent")

    except Exception as e:
        logger.error(f"Analytical agent error: {e}", exc_info=True)
        state["ai_response"] = f"I encountered an error while trying to answer that question: {str(e)}"

    return state
