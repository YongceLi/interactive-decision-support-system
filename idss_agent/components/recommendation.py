"""
Recommendation agent node - uses ReAct to build a list of 20 vehicles.
"""
import concurrent.futures
import math
import json
from typing import Dict, Any, List, Optional, Tuple, Callable
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from idss_agent.state import VehicleSearchState
from idss_agent.components.autodev_apis import search_vehicle_listings, get_vehicle_photos_by_vin
from idss_agent.logger import get_logger


logger = get_logger("components.recommendation")


class VehicleSuggestion(BaseModel):
    """Suggested vehicles based on user preferences."""
    makes: List[str] = Field(description="List of 2-4 recommended vehicle makes (e.g., ['Honda', 'Toyota', 'Mazda'])")
    models: List[str] = Field(description="List of 3-6 recommended vehicle models (e.g., ['Civic', 'Corolla', 'Accord', 'Camry', '3', 'CX-5'])")
    reasoning: str = Field(description="Brief explanation (1-2 sentences) of why these vehicles match the preferences")


def suggest_more_vehicles(
    implicit_preferences: Dict[str, Any],
    existing_filters: Dict[str, Any],
    already_tried_makes: List[str],
    already_tried_models: List[str]
) -> Optional[VehicleSuggestion]:
    """
    Suggest ADDITIONAL makes/models (different from what was already tried).

    Args:
        implicit_preferences: User's preferences
        existing_filters: Current filters
        already_tried_makes: Makes already attempted
        already_tried_models: Models already attempted

    Returns:
        VehicleSuggestion with NEW makes/models, or None if no more suggestions
    """
    logger.info(f"Suggesting additional vehicles (avoiding: {already_tried_makes}, {already_tried_models})")

    prompt = f"""You are a vehicle recommendation expert. The previous suggestions didn't find any vehicles in the database.

**User's Preferences:**
{json.dumps(implicit_preferences, indent=2)}

**Existing Filters:**
{json.dumps(existing_filters, indent=2)}

**Already Tried (avoid these):**
- Makes: {already_tried_makes}
- Models: {already_tried_models}

**Instructions:**
1. Suggest 2-4 DIFFERENT vehicle makes (NOT in the already-tried list)
2. Suggest 3-6 DIFFERENT specific models (NOT in the already-tried list)
3. Broaden your suggestions - try less obvious brands/models that still match preferences
4. Consider alternative brands with similar characteristics
5. Provide brief reasoning

**Example:**
If already tried: Honda, Toyota (luxury sedans)
→ Suggest: Mazda, Nissan, Hyundai (similar reliability/value brands)

Generate NEW suggestions:"""

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)  # Higher temp for variety
        structured_llm = llm.with_structured_output(VehicleSuggestion)

        result = structured_llm.invoke([
            SystemMessage(content="You are a vehicle recommendation expert."),
            HumanMessage(content=prompt)
        ])

        # Filter out any duplicates that might have been suggested
        new_makes = [m for m in result.makes if m not in already_tried_makes]
        new_models = [m for m in result.models if m not in already_tried_models]

        if not new_makes and not new_models:
            logger.warning("No new makes/models suggested - all were duplicates")
            return None

        # Return filtered results
        result.makes = new_makes
        result.models = new_models

        logger.info(f"✓ Additional vehicle suggestions: {len(new_makes)} makes, {len(new_models)} models")
        logger.info(f"  New makes: {new_makes}")
        logger.info(f"  New models: {new_models}")

        return result

    except Exception as e:
        logger.error(f"Failed to suggest additional vehicles: {e}")
        return None


def suggest_vehicles_from_preferences(
    implicit_preferences: Dict[str, Any],
    existing_filters: Dict[str, Any]
) -> Optional[VehicleSuggestion]:
    """
    Use LLM to suggest vehicle makes/models based on user's implicit preferences.

    Args:
        implicit_preferences: User's implicit preferences (priorities, concerns, usage_patterns, etc.)
        existing_filters: Current explicit filters (may have year, price, body_style, etc.)

    Returns:
        VehicleSuggestion with recommended makes/models, or None if no suggestions
    """

    # Only suggest if we have meaningful preferences
    has_preferences = any([
        implicit_preferences.get('priorities'),
        implicit_preferences.get('concerns'),
        implicit_preferences.get('usage_patterns'),
        implicit_preferences.get('lifestyle'),
        implicit_preferences.get('brand_affinity')
    ])

    if not has_preferences:
        logger.info("No implicit preferences found - skipping vehicle suggestion")
        return None

    logger.info("Suggesting vehicles based on implicit preferences")

    prompt = f"""You are a vehicle recommendation expert. Based on the user's preferences, suggest specific vehicle makes and models that would be good matches.

**User's Preferences:**
{json.dumps(implicit_preferences, indent=2)}

**Existing Filters:**
{json.dumps(existing_filters, indent=2)}

**Instructions:**
1. Suggest 2-4 vehicle MAKES (brands like Honda, Toyota, Mazda, etc.)
2. Suggest 3-6 specific MODELS that match the preferences
3. Focus on vehicles known for the user's priorities and concerns
4. Consider usage patterns and lifestyle when making suggestions
5. If existing filters specify year/price/body_style, factor that in
6. Provide a brief reasoning (1-2 sentences)

**Examples:**
- Preferences: priorities=["safety"], concerns=["maintenance costs"], usage_patterns="teenage driver"
  → makes=["Honda", "Toyota", "Mazda"], models=["Civic", "Corolla", "3", "Accord"]

- Preferences: priorities=["fuel_efficiency", "technology"], lifestyle="urban commuter"
  → makes=["Honda", "Toyota", "Hyundai"], models=["Civic", "Accord Hybrid", "Prius", "Ioniq", "Elantra"]

- Preferences: priorities=["space", "family"], usage_patterns="family with kids"
  → makes=["Honda", "Toyota", "Subaru"], models=["CR-V", "Pilot", "Highlander", "RAV4", "Outback"]

Generate your suggestions:"""

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
        structured_llm = llm.with_structured_output(VehicleSuggestion)

        result = structured_llm.invoke([
            SystemMessage(content="You are a vehicle recommendation expert."),
            HumanMessage(content=prompt)
        ])

        logger.info(f"✓ Vehicle suggestions: {len(result.makes)} makes, {len(result.models)} models")
        logger.info(f"  Makes: {result.makes}")
        logger.info(f"  Models: {result.models}")
        logger.info(f"  Reasoning: {result.reasoning}")

        return result

    except Exception as e:
        logger.error(f"Failed to suggest vehicles: {e}")
        return None


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


def update_recommendation_list(
    state: VehicleSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> VehicleSearchState:
    """
    Use a ReAct agent to build a recommendation list of up to 20 vehicles.

    The agent:
    - Has access to search_vehicle_listings tool
    - Knows current filters and preferences
    - Goal: Return exactly 20 relevant vehicles (or fewer if not available)
    - Can loosen criteria if needed to reach 20

    Args:
        state: Current vehicle search state
        progress_callback: Optional callback for progress updates

    Returns:
        Updated state with recommended_vehicles populated
    """

    # Emit progress: Starting search
    if progress_callback:
        progress_callback({
            "step_id": "updating_recommendations",
            "description": "Searching for vehicles",
            "status": "in_progress"
        })

    filters = state['explicit_filters'].copy()  # Make a copy to avoid modifying original
    implicit = state['implicit_preferences']

    #If no make/model specified but has preferences, suggest vehicles
    if not filters.get('make') and not filters.get('model'):
        suggestions = suggest_vehicles_from_preferences(implicit, filters)

        if suggestions:
            # Add suggested makes and models to filters
            # Join multiple makes/models with comma for AutoDev API
            filters['make'] = ','.join(suggestions.makes)
            filters['model'] = ','.join(suggestions.models)

            logger.info(f"   Using suggested vehicles: {filters['make']} / {filters['model']}")
            logger.info(f"   Reasoning: {suggestions.reasoning}")

            # Store suggestion reasoning in state for potential use in response
            state['suggestion_reasoning'] = suggestions.reasoning

    # Normalize model name (remove hyphens/underscores) to match Auto.dev API format
    if filters.get('model'):
        filters['model'] = filters['model'].replace('-', ' ').replace('_', ' ')
        logger.info(f"Normalized model name: {filters['model']}")

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
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
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
                    logger.info(f"Found {len(vehicles)} vehicles from search (list format)")
                    break
                elif isinstance(data, dict):
                    if 'data' in data and isinstance(data['data'], list):
                        vehicles = data['data']
                        logger.info(f"Found {len(vehicles)} vehicles from search (data field)")
                        break
                    elif 'vehicles' in data and isinstance(data['vehicles'], list):
                        vehicles = data['vehicles']
                        logger.info(f"Found {len(vehicles)} vehicles from search (vehicles field)")
                        break
            except (json.JSONDecodeError, AttributeError):
                continue

    # If no vehicles found, try iterative search with more makes/models
    retry_count = 0
    max_retries = 2  # Try up to 2 additional times (3 total attempts)
    all_suggested_makes = set(filters.get('make', '').split(',')) if filters.get('make') else set()
    all_suggested_models = set(filters.get('model', '').split(',')) if filters.get('model') else set()

    while not vehicles and retry_count < max_retries:
        retry_count += 1
        logger.warning(f"No vehicles found from search (attempt {retry_count}/{max_retries + 1}) - trying more makes/models")

        # Ask LLM for MORE vehicle suggestions (different from what we already tried)
        retry_suggestions = suggest_more_vehicles(
            implicit,
            filters,
            already_tried_makes=list(all_suggested_makes),
            already_tried_models=list(all_suggested_models)
        )

        if not retry_suggestions:
            logger.warning("No additional vehicle suggestions available - stopping retry")
            break

        # Append new suggestions to existing ones (cumulative)
        all_suggested_makes.update(retry_suggestions.makes)
        all_suggested_models.update(retry_suggestions.models)

        # Update filters with accumulated makes/models
        filters['make'] = ','.join(all_suggested_makes)
        filters['model'] = ','.join(all_suggested_models)

        logger.info(f"Retry {retry_count}: Accumulated makes/models")
        logger.info(f"  Makes: {filters['make']}")
        logger.info(f"  Models: {filters['model']}")

        # Normalize model name
        filters['model'] = filters['model'].replace('-', ' ').replace('_', ' ')

        # Build new prompt for retry
        retry_prompt = f"""
You are a vehicle recommendation agent. Your goal is to find up to 20 vehicles for the user.

**Current Filters (with accumulated makes/models):**
{json.dumps(filters, indent=2)}

**Instructions:**
1. Use search_vehicle_listings tool with the current filters
2. ALWAYS set page=1 and limit=50
3. Once you get the results, respond with a simple summary

**IMPORTANT:**
- Call the tool ONCE with current filters
- After you see the tool results, immediately finish
"""

        # Run the agent again with updated filters
        result = agent.invoke({"messages": [HumanMessage(content=retry_prompt)]})

        # Parse results again
        for msg in result['messages']:
            if hasattr(msg, 'content') and isinstance(msg.content, str):
                try:
                    data = json.loads(msg.content)
                    if isinstance(data, list):
                        vehicles = data
                        logger.info(f"Retry {retry_count}: Found {len(vehicles)} vehicles (list format)")
                        break
                    elif isinstance(data, dict):
                        if 'data' in data and isinstance(data['data'], list):
                            vehicles = data['data']
                            logger.info(f"Retry {retry_count}: Found {len(vehicles)} vehicles (data field)")
                            break
                except (json.JSONDecodeError, AttributeError):
                    continue

    # Final fallback: Progressive filter relaxation if still no vehicles
    fallback_message = None

    if not vehicles:
        logger.warning("No vehicles found after all retry attempts - applying progressive filter relaxation")

        # Fallback 1: Remove MODEL filter (keep make + other filters)
        if filters.get('model'):
            logger.info("Fallback 1: Removing model filter, keeping make")
            fallback_filters = filters.copy()
            removed_models = fallback_filters.pop('model')

            fallback_prompt = f"""
You are a vehicle recommendation agent. Find up to 20 vehicles with relaxed filters.

**Relaxed Filters (model filter removed):**
{json.dumps(fallback_filters, indent=2)}

**Instructions:**
1. Use search_vehicle_listings tool with these filters
2. Set page=1 and limit=50
3. Respond with a simple summary
"""

            result = agent.invoke({"messages": [HumanMessage(content=fallback_prompt)]})

            for msg in result['messages']:
                if hasattr(msg, 'content') and isinstance(msg.content, str):
                    try:
                        data = json.loads(msg.content)
                        if isinstance(data, list):
                            vehicles = data
                            logger.info(f"Fallback 1: Found {len(vehicles)} vehicles (removed model filter)")
                            fallback_message = f"Showing {fallback_filters.get('make', 'available')} vehicles matching your other criteria"
                            break
                        elif isinstance(data, dict) and 'data' in data:
                            vehicles = data['data']
                            logger.info(f"Fallback 1: Found {len(vehicles)} vehicles (removed model filter)")
                            fallback_message = f"Showing {fallback_filters.get('make', 'available')} vehicles matching your other criteria"
                            break
                    except (json.JSONDecodeError, AttributeError):
                        continue

        # Fallback 2: Remove MAKE filter as well (keep body_style, price, etc.)
        if not vehicles and filters.get('make'):
            logger.info("Fallback 2: Removing make filter as well")
            fallback_filters = filters.copy()
            fallback_filters.pop('model', None)
            fallback_filters.pop('make', None)

            fallback_prompt = f"""
You are a vehicle recommendation agent. Find up to 20 vehicles with minimal filters.

**Minimal Filters (make/model removed):**
{json.dumps(fallback_filters, indent=2)}

**Instructions:**
1. Use search_vehicle_listings tool with these filters
2. Set page=1 and limit=50
3. Respond with a simple summary
"""

            result = agent.invoke({"messages": [HumanMessage(content=fallback_prompt)]})

            for msg in result['messages']:
                if hasattr(msg, 'content') and isinstance(msg.content, str):
                    try:
                        data = json.loads(msg.content)
                        if isinstance(data, list):
                            vehicles = data
                            logger.info(f"Fallback 2: Found {len(vehicles)} vehicles (removed make/model filters)")
                            fallback_message = "Showing the closest matches available based on your other criteria"
                            break
                        elif isinstance(data, dict) and 'data' in data:
                            vehicles = data['data']
                            logger.info(f"Fallback 2: Found {len(vehicles)} vehicles (removed make/model filters)")
                            fallback_message = "Showing the closest matches available based on your other criteria"
                            break
                    except (json.JSONDecodeError, AttributeError):
                        continue

    if not vehicles:
        logger.warning("No vehicles found even after progressive filter relaxation")

    # Deduplicate vehicles by VIN (keep lowest price for each)
    vehicles = deduplicate_by_vin(vehicles)
    logger.info(f"After deduplication: {len(vehicles)} unique vehicles")

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

    # Store fallback message if filters were relaxed
    if fallback_message:
        state['fallback_message'] = fallback_message
        logger.info(f"Fallback message set: {fallback_message}")
    logger.info(f"✓ Recommendation complete: {len(state['recommended_vehicles'])} vehicles in state")

    # Store current filters as previous for next comparison
    state['previous_filters'] = state['explicit_filters'].copy()

    # Emit progress: Search complete
    if progress_callback:
        progress_callback({
            "step_id": "updating_recommendations",
            "description": f"Found {len(state['recommended_vehicles'])} vehicles",
            "status": "completed"
        })

    return state
