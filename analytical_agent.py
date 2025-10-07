"""
Analytical agent node - handles specific questions about vehicles using ReAct.
"""
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from state_schema import VehicleSearchState, get_latest_user_message
from discovery_agent import format_vehicles_for_llm
from tools.autodev_apis import get_vehicle_listing_by_vin, get_vehicle_photos_by_vin
from tools.vehicle_database import get_safety_database_tools, get_feature_database_tools


def analytical_response_generator(state: VehicleSearchState) -> VehicleSearchState:
    """
    Handle analytical questions using ReAct agent with tools.

    Examples:
    - "Tell me more about #3"
    - "Compare #1 and #5"
    - "What's the safety rating of this vehicle?"
    - "Is #2 a good deal?"

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
   - safety_data: NHTSA safety ratings, crash tests, safety features (query by make, model, model_yr)
   - feature_db.feature_data: EPA fuel economy, MPG ratings, emissions (query by Make, Model, Year)

**Your Task:**
Answer the user's question using the listings above and tools as needed.

Tips:
- For VIN-based questions: Extract VIN from listings above (e.g., "#1" → find VIN in listing #1)
- For feature/fuel economy questions: Use SQL tools to query feature_db.feature_data by Make, Model, Year
- For safety questions: Use SQL tools to query safety_data by make, model, model_yr
- If VIN API fails, try SQL databases with make/model/year instead

After answering, ask 1-2 follow-up questions.
"""

    # Create ReAct agent with tools
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Gather all tools
    tools = [
        get_vehicle_listing_by_vin,
        get_vehicle_photos_by_vin
    ]

    # Add database tools (safety and feature data)
    safety_tools = get_safety_database_tools(llm)
    feature_tools = get_feature_database_tools(llm)
    tools.extend(safety_tools)
    tools.extend(feature_tools)

    agent = create_react_agent(llm, tools)

    # Run the agent
    result = agent.invoke({"messages": [HumanMessage(content=context)]})

    # Extract final response
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


def extract_vehicle_reference(user_question: str, vehicles: list) -> dict:
    """
    Extract which vehicle the user is referring to.

    Examples:
    - "#3" → vehicles[2]
    - "the first one" → vehicles[0]
    - "the Toyota" → search for Toyota in list

    Args:
        user_question: User's question
        vehicles: List of current vehicles

    Returns:
        Vehicle dict or None
    """
    question_lower = user_question.lower()

    # Check for numeric reference (#1, #3, etc.)
    import re
    match = re.search(r'#(\d+)', user_question)
    if match:
        index = int(match.group(1)) - 1  # Convert to 0-indexed
        if 0 <= index < len(vehicles):
            return vehicles[index]

    # Check for ordinal references (first, second, third)
    ordinals = {
        'first': 0, 'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4,
        'sixth': 5, 'seventh': 6, 'eighth': 7, 'ninth': 8, 'tenth': 9
    }

    for word, index in ordinals.items():
        if word in question_lower and index < len(vehicles):
            return vehicles[index]

    return None
