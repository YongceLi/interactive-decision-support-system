"""
Analytical agent node - handles specific questions about vehicles using ReAct.
"""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState, get_latest_user_message
from idss_agent.nodes.discovery import format_vehicles_for_llm
from idss_agent.tools.autodev_apis import get_vehicle_listing_by_vin, get_vehicle_photos_by_vin
from idss_agent.tools.vehicle_database import get_vehicle_database_tools


def analytical_response_generator(state: VehicleSearchState) -> VehicleSearchState:
    """
    Handle analytical questions using ReAct agent with tools.
    
    The ReAct agent has access to:
    - get_vehicle_listing_by_vin
    - get_vehicle_photos_by_vin
    - search_vehicle_listings
    (More tools can be added later)

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with ai_response
    """

    user_question = get_latest_user_message(state)
    vehicles = state['recommended_vehicles']
    implicit = state['implicit_preferences']

    # Format current vehicle list with VINs for context
    vehicles_context = format_vehicles_with_vins(vehicles, limit=20)

    # Build context for the ReAct agent
    context = f"""
You are a helpful vehicle shopping assistant with access to tools.

**User's Question:**
{user_question}

**Current Vehicle Listings:**
{vehicles_context}

**User's Preferences:**
{json.dumps(implicit, indent=2)}

**Available Tools:**
1. API Tools (for current listings):
   - get_vehicle_listing_by_vin(vin): Get detailed listing for a 17-character VIN
   - get_vehicle_photos_by_vin(vin): Get photo URLs for a 17-character VIN

2. SQL Database Tools (for additional vehicle data):
   - sql_db_list_tables: List all available tables
   - sql_db_schema: Get schema for specific tables
   - sql_db_query: Execute SQL queries
   - sql_db_query_checker: Verify query syntax

   Available tables:
   - safety_data: NHTSA safety ratings, crash tests, safety features
   - feature_db.feature_data: EPA fuel economy, MPG ratings, emissions

**Your Task:**
Answer the user's question using the listings above and tools as needed.

Tips:
- For VIN-based questions: Extract VIN from listings above (e.g., "#1" → find VIN in listing #1)
- For feature/fuel economy questions: Use SQL tools to query feature_db.feature_data by Make, Model, Year
- For safety questions: Use SQL tools to query safety_data by make, model, model_yr
- If VIN API fails, try SQL databases with make/model/year instead

After answering, ask 1-2 follow-up questions.
"""

    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    tools = [
        get_vehicle_listing_by_vin,
        get_vehicle_photos_by_vin
    ]

    # Add database tools (combined safety and feature data)
    db_tools = get_vehicle_database_tools(llm)
    tools.extend(db_tools)

    agent = create_react_agent(llm, tools)

    result = agent.invoke({"messages": [HumanMessage(content=context)]})

    state['ai_response'] = result['messages'][-1].content

    return state


def format_vehicles_with_vins(vehicles: list, limit: int = 20) -> str:
    """
    Format vehicle list with VINs visible for the agent to extract.

    Args:
        vehicles: List of vehicle dictionaries
        limit: Maximum number to format

    Returns:
        Formatted string with vehicle details including VINs
    """
    if not vehicles:
        return "No vehicles in current list."

    formatted = []
    for i, vehicle in enumerate(vehicles[:limit], 1):
        # Extract vehicle info
        v_info = vehicle.get('vehicle', vehicle)
        retail = vehicle.get('retailListing', {})

        year = v_info.get('year', 'N/A')
        make = v_info.get('make', 'N/A')
        model = v_info.get('model', 'N/A')
        trim = v_info.get('trim', '')
        vin = v_info.get('vin', 'N/A')

        price = retail.get('price', 'N/A')
        if isinstance(price, (int, float)) and price > 0:
            price_str = f"${price:,}"
        else:
            price_str = "Contact Dealer"

        miles = retail.get('miles', v_info.get('mileage', 'N/A'))
        if isinstance(miles, (int, float)):
            miles_str = f"{miles:,} mi"
        else:
            miles_str = str(miles)

        city = retail.get('city', 'N/A')
        state = retail.get('state', 'N/A')
        location = f"{city}, {state}" if city != 'N/A' else 'N/A'

        # Format with VIN clearly visible
        vehicle_line = f"#{i}. {year} {make} {model} {trim}".strip()
        vehicle_line += f"\n    VIN: {vin}"
        vehicle_line += f"\n    Price: {price_str} | Mileage: {miles_str} | Location: {location}"

        formatted.append(vehicle_line)

    return "\n\n".join(formatted)
