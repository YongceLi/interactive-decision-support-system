"""
Recommendation agent node - uses ReAct to build a list of 20 vehicles.
"""
import concurrent.futures
import math
import json
import os
from typing import Dict, Any, List, Optional, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from idss_agent.state import VehicleSearchState
from idss_agent.components.autodev_apis import search_vehicle_listings, get_vehicle_photos_by_vin
from idss_agent.logger import get_logger


logger = get_logger("components.recommendation")


def fetch_photos_for_vin(vin: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch photos for a VIN and return the parsed payload if available."""
    if not vin or len(vin) != 17:
        return None

    try:
        result = get_vehicle_photos_by_vin.invoke({"vin": vin})
        data = json.loads(result)
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Photo fetch failed for VIN %s: %s", vin, exc)
        return None

    if "error" in data:
        return None

    retail_photos = data.get("data", {}).get("retail", [])
    if not retail_photos:
        return None

    return {
        "retail": retail_photos,
        "data": data.get("data", {}),
    }


def attach_photo_payload(vehicle: Dict[str, Any], photo_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach a photo payload (if any) onto the vehicle dict."""
    vehicle["photos"] = photo_payload
    return vehicle


def deduplicate_by_vin(vehicles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate vehicles by VIN, keeping the lowest price for each VIN.

    Args:
        vehicles: List of vehicle dictionaries

    Returns:
        List of unique vehicles (one per VIN)
    """
    seen_vins = {}

    for vehicle in vehicles:
        vin = vehicle.get('vehicle', {}).get('vin')
        if not vin:
            continue

        price = vehicle.get('retailListing', {}).get('price', float('inf'))

        # Keep vehicle with lowest price for this VIN
        if vin not in seen_vins or price < seen_vins[vin].get('retailListing', {}).get('price', float('inf')):
            seen_vins[vin] = vehicle

    return list(seen_vins.values())


def enrich_vehicles_with_photos(vehicles: List[Dict[str, Any]], max_workers: int = 8) -> List[Dict[str, Any]]:
    """Fetch photos for vehicles in parallel and attach them to the payload."""
    if not vehicles:
        return vehicles

    vin_to_index: List[Tuple[str, int]] = []
    for idx, vehicle in enumerate(vehicles):
        vin = vehicle.get("vehicle", {}).get("vin") or vehicle.get("vin")
        if vin and len(vin) == 17:
            vin_to_index.append((vin, idx))
        else:
            vehicles[idx]["photos"] = None

    if not vin_to_index:
        return vehicles

    worker_count = min(max(len(vin_to_index), 1), max_workers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_vin = {
            executor.submit(fetch_photos_for_vin, vin): (vin, idx)
            for vin, idx in vin_to_index
        }

        for future in concurrent.futures.as_completed(future_to_vin):
            vin, idx = future_to_vin[future]
            try:
                photo_payload = future.result()
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Error fetching photos for %s: %s", vin, exc)
                photo_payload = None

            vehicles[idx] = attach_photo_payload(vehicles[idx], photo_payload)

    return vehicles


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

    # Build prompt for recommendation agent
    recommendation_prompt = f"""
You are a vehicle recommendation agent. Your goal is to find up to 20 vehicles for the user.

**Current Filters:**
{json.dumps(filters, indent=2)}

**User Preferences:**
{json.dumps(implicit, indent=2)}

**Instructions:**
1. Use search_vehicle_listings tool with the current filters
2. ALWAYS set page=1 and limit=50
3. Once you get the results from the tool, your job is DONE
4. Respond with a simple summary like: "Found X vehicles matching the criteria."

**IMPORTANT:**
- Call the tool ONCE with current filters, page=1, limit=50
- After you see the tool results, immediately finish with a brief summary
- Do NOT call the tool multiple times
- Do NOT try to list all vehicles in your response
"""

    # Create ReAct agent with search tool
    tools = [search_vehicle_listings]
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    agent = create_react_agent(llm, tools)

    # Run the agent
    result = agent.invoke({"messages": [HumanMessage(content=recommendation_prompt)]})

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

    # Deduplicate vehicles by VIN (keep lowest price for each)
    vehicles = deduplicate_by_vin(vehicles)

    vehicles = vehicles[:50]
    vehicles = enrich_vehicles_with_photos(vehicles)

    def vehicle_sort_key(vehicle: Dict[str, Any]) -> Tuple[int, float, float, float]:
        has_photos = 0 if vehicle.get("photos") else 1

        miles_raw = vehicle.get("retailListing", {}).get("miles")
        price_raw = vehicle.get("retailListing", {}).get("price")

        try:
            miles_value = float(miles_raw)
        except (TypeError, ValueError):
            miles_value = float("inf")

        try:
            price_value = float(price_raw)
        except (TypeError, ValueError):
            price_value = float("inf")

        ratio = (
            miles_value / price_value
            if price_value not in (0, float("inf")) and not math.isnan(price_value)
            else float("inf")
        )

        return (has_photos, ratio, miles_value, price_value)

    vehicles.sort(key=vehicle_sort_key)

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
