"""
Analytical tool - answers specific questions about vehicles.

Wraps the existing analytical node as a callable tool for the supervisor.
"""
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState
from idss_agent.components.autodev_apis import get_vehicle_listing_by_vin, get_vehicle_photos_by_vin
from idss_agent.components.vehicle_database import get_vehicle_database_tools


def analytical_tool(question: str, state: VehicleSearchState) -> str:
    """
    Tool that answers specific questions about vehicles using available data.

    This creates a ReAct agent with access to:
    - Vehicle details by VIN
    - Vehicle photos
    - Safety database
    - Fuel economy database

    Args:
        question: The specific question to answer
        state: Current state with vehicle context

    Returns:
        String answer to the question
    """
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

User's question: {question}

Available tools:
- get_vehicle_listing_by_vin: Get detailed vehicle information by VIN
- get_vehicle_photos_by_vin: Get photos for a vehicle
- sql_db_query: Query safety_data and feature_data databases
- sql_db_schema: Get database schema
- sql_db_list_tables: List available tables

Instructions:
1. If user references a vehicle by number (e.g., "#1"), use the VIN from the context above
2. Use tools to gather information
3. Provide a comprehensive, helpful answer
4. Format your response clearly

Answer the question.
"""

    try:
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})

        # Extract final response
        messages = result.get("messages", [])
        if messages:
            final_message = messages[-1]
            return final_message.content
        else:
            return "I couldn't find an answer to that question."

    except Exception as e:
        print(f"Error in analytical tool: {e}")
        return f"I encountered an error while trying to answer that question: {str(e)}"
