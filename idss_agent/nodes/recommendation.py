"""
Recommendation agent node - uses ReAct to build a list of 20 vehicles.
"""
import json
import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState
from idss_agent.tools.autodev_apis import search_vehicle_listings, get_vehicle_photos_by_vin


def has_photos(vehicle: Dict[str, Any]) -> bool:
    """
    Check if a vehicle has photos available.

    Args:
        vehicle: Vehicle dictionary with VIN

    Returns:
        True if vehicle has photos, False otherwise
    """
    # Extract VIN from vehicle data
    vin = vehicle.get('vehicle', {}).get('vin') or vehicle.get('vin')

    if not vin or len(vin) != 17:
        return False

    try:
        # Call photo API
        result = get_vehicle_photos_by_vin.invoke({"vin": vin})
        data = json.loads(result)

        # Check if photos exist
        if "error" in data:
            return False

        retail_photos = data.get('data', {}).get('retail', [])
        return len(retail_photos) > 0

    except Exception:
        return False


def filter_vehicles_by_photos(vehicles: List[Dict[str, Any]], target_count: int = 20) -> List[Dict[str, Any]]:
    """
    Filter vehicles to prioritize those with photos.

    Strategy:
    1. First, collect vehicles WITH photos (up to target_count)
    2. If not enough, add vehicles WITHOUT photos to reach target_count

    Args:
        vehicles: List of vehicle dictionaries
        target_count: Target number of vehicles (default: 20)

    Returns:
        List of up to target_count vehicles, prioritizing those with photos
    """
    vehicles_with_photos = []
    vehicles_without_photos = []

    for vehicle in vehicles:
        if has_photos(vehicle):
            vehicles_with_photos.append(vehicle)
        else:
            vehicles_without_photos.append(vehicle)

        # Early exit if we have enough vehicles with photos
        if len(vehicles_with_photos) >= target_count:
            break

    # Combine: prioritize vehicles with photos, then add those without if needed
    result = vehicles_with_photos[:target_count]

    if len(result) < target_count:
        remaining = target_count - len(result)
        result.extend(vehicles_without_photos[:remaining])

    return result


def update_recommendation_list(state: VehicleSearchState) -> VehicleSearchState:
    """
    Use a ReAct agent to build a recommendation list of up to 20 vehicles.

    The agent:
    - Has access to search_vehicle_listings tool
    - Knows current filters and preferences
    - Goal: Return exactly 20 relevant vehicles (or fewer if not available)
    - Can loosen criteria if needed to reach 20

    Args:
        state: Current vehicle search state

    Returns:
        Updated state with recommended_vehicles populated
    """

    filters = state['explicit_filters']
    implicit = state['implicit_preferences']
    
    # Map semantic parser filter names to auto.dev API parameter names
    api_filters = {}
    filter_mapping = {
        'make': 'vehicle_make',
        'model': 'vehicle_model',
        'year': 'vehicle_year',
        'trim': 'vehicle_trim',
        'body_style': 'vehicle_body_style',
        'engine': 'vehicle_engine',
        'transmission': 'vehicle_transmission',
        'exterior_color': 'vehicle_exterior_color',
        'interior_color': 'vehicle_interior_color',
        'doors': 'vehicle_doors',
        'price': 'retail_price',
        'state': 'retail_state',
        'miles': 'retail_miles',
        'zip': 'zip',
        'distance': 'distance'
    }
    
    for key, value in filters.items():
        if key in filter_mapping and value:
            api_filters[filter_mapping[key]] = value

    # Build prompt for recommendation agent
    recommendation_prompt = f"""
You are a vehicle recommendation agent. Your goal is to find up to 20 vehicles for the user.

**Current Filters (mapped to API parameters):**
{json.dumps(api_filters, indent=2)}

**User Preferences:**
{json.dumps(implicit, indent=2)}

**Instructions:**
1. Use search_vehicle_listings tool with the mapped filters above
2. ALWAYS set page=1 and limit=50
3. Once you get the results from the tool, your job is DONE
4. Respond with a simple summary like: "Found X vehicles matching the criteria."

**IMPORTANT:**
- Use the exact parameter names from the filters above (e.g., retail_price, vehicle_make, etc.)
- Call the tool ONCE with current filters, page=1, limit=50
- After you see the tool results, immediately finish with a brief summary
- Do NOT call the tool multiple times
- Do NOT try to list all vehicles in your response
"""

    # Create ReAct agent with search tool
    tools = [search_vehicle_listings]
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = create_react_agent(llm, tools)

    # Run the agent
    result = agent.invoke({"messages": [HumanMessage(content=recommendation_prompt)]})

    # Extract the final response from agent
    final_message = result['messages'][-1].content

    # Parse the search results from the agent's tool calls
    # Look through messages for tool results
    vehicles = []
    for msg in result['messages']:
        # Check if this is a tool message with search results
        if hasattr(msg, 'content') and isinstance(msg.content, str):
            try:
                # Try to parse as JSON
                data = json.loads(msg.content)

                # Check if it's a list of vehicles or has a data field
                if isinstance(data, list):
                    vehicles = data
                    break
                elif isinstance(data, dict):
                    if 'data' in data and isinstance(data['data'], list):
                        vehicles = data['data']
                        break
                    elif 'vehicles' in data and isinstance(data['vehicles'], list):
                        vehicles = data['vehicles']
                        break
            except (json.JSONDecodeError, AttributeError):
                continue

    # Check if photo filtering is enabled via environment variable
    require_photos = os.getenv('REQUIRE_PHOTOS_IN_RECOMMENDATIONS', 'false').lower() == 'true'

    if require_photos and vehicles:
        # Filter vehicles to prioritize those with photos
        filtered_vehicles = filter_vehicles_by_photos(vehicles, target_count=20)
        state['recommended_vehicles'] = filtered_vehicles
    else:
        # Default behavior: just take first 20
        state['recommended_vehicles'] = vehicles[:20]

    # Store current filters as previous for next comparison
    state['previous_filters'] = state['explicit_filters'].copy()

    return state


def parse_vehicle_list(response_content: str) -> list[Dict[str, Any]]:
    """
    Parse vehicle list from agent response.

    Expects JSON format from the agent.

    Args:
        response_content: Agent's response content

    Returns:
        List of vehicle dictionaries
    """
    try:
        # Try to find JSON in the response
        content = response_content.strip()

        # Strip markdown if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Parse JSON
        vehicles = json.loads(content)

        if isinstance(vehicles, list):
            return vehicles[:20]  
        elif isinstance(vehicles, dict) and 'vehicles' in vehicles:
            return vehicles['vehicles'][:20]
        else:
            return []

    except json.JSONDecodeError:
        print(f"Warning: Could not parse vehicle list from response")
        return []
