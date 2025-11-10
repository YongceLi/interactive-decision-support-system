"""
Method 2: Web Search → Parallel SQL → Vector Ranking

Flow:
1. Web search + LLM to find k relevant makes/models
2. Spawn k parallel SQL queries (one per make)
3. Rank each make's results with vector similarity
4. Select top (20/k) from each make for diversity
5. Combine into final list
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.processing.vector_ranker import rank_local_vehicles_by_similarity
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.method2")


class WebSearchVehicleSuggestion(BaseModel):
    """LLM-extracted vehicle suggestions from web search."""
    makes: List[str] = Field(
        description="List of 3-5 recommended vehicle makes (e.g., ['Honda', 'Toyota', 'Mazda'])"
    )
    models: List[str] = Field(
        description="List of 4-8 recommended vehicle models (e.g., ['CR-V', 'RAV4', 'CX-5', 'Forester'])"
    )
    reasoning: str = Field(
        description="Brief explanation of why these vehicles match user preferences"
    )
    search_query: str = Field(
        description="The search query used to find these recommendations"
    )


def generate_search_query(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> str:
    """
    Generate a web search query from user preferences.

    Examples:
    - "best family SUVs 2024 safe reliable"
    - "budget sedans under 20k fuel efficient"
    - "luxury SUVs with 3rd row seating"
    """
    query_parts = []

    # Priorities
    priorities = implicit_preferences.get("priorities", [])
    if priorities:
        query_parts.extend(priorities[:2])  # Top 2 priorities

    # Body style
    body_style = explicit_filters.get("body_style")
    if body_style:
        query_parts.append(body_style)

    # Budget sensitivity
    budget = implicit_preferences.get("budget_sensitivity")
    if budget:
        query_parts.append(budget)

    # Lifestyle
    lifestyle = implicit_preferences.get("lifestyle")
    if lifestyle:
        query_parts.append(lifestyle)

    # Year
    year = explicit_filters.get("year")
    if year:
        # Extract max year from range (e.g., "2020-2024" → "2024")
        if "-" in str(year):
            year = year.split("-")[-1]
        query_parts.append(f"{year}")
    else:
        query_parts.append("2024")  # Default to recent

    # Assemble query
    query = " ".join(query_parts) + " cars"
    if not query.strip():
        query = "best cars 2024"

    logger.info(f"Generated search query: {query}")
    return query


def web_search_for_vehicle_suggestions(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> Optional[WebSearchVehicleSuggestion]:
    """
    Use web search + LLM to find relevant makes/models.

    Args:
        explicit_filters: User's explicit filters
        implicit_preferences: User's implicit preferences

    Returns:
        WebSearchVehicleSuggestion with makes, models, reasoning
    """
    # Generate search query
    search_query = generate_search_query(explicit_filters, implicit_preferences)

    # Perform web search using Tavily
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
        search_tool = TavilySearchResults(max_results=5)
        search_results = search_tool.invoke({"query": search_query})
        logger.info(f"Web search completed: {len(search_results)} results")

        # Format Tavily results into text
        if isinstance(search_results, list):
            formatted_results = "\n\n".join([
                f"Title: {r.get('title', 'N/A')}\nContent: {r.get('content', 'N/A')}\nURL: {r.get('url', 'N/A')}"
                for r in search_results
            ])
        else:
            formatted_results = str(search_results)

        search_results = formatted_results
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return None

    # Use LLM to extract vehicle suggestions from search results
    prompt = f"""You are a vehicle recommendation expert. Based on web search results,
suggest the most relevant vehicle makes and models for this user.

**User's Explicit Filters:**
{json.dumps(explicit_filters, indent=2)}

**User's Implicit Preferences:**
{json.dumps(implicit_preferences, indent=2)}

**Web Search Results:**
{search_results}

**Instructions:**
1. Extract 3-5 vehicle makes that best match the user's needs
2. Extract 4-8 specific models from those makes
3. Focus on vehicles that align with their priorities and lifestyle
4. Explain your reasoning briefly (2-3 sentences)
5. Return the search query used

Be specific with model names (e.g., "CR-V" not just "Honda SUV").
"""

    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        structured_llm = llm.with_structured_output(WebSearchVehicleSuggestion)

        result = structured_llm.invoke([
            SystemMessage(content="You are a vehicle recommendation expert."),
            HumanMessage(content=prompt)
        ])

        logger.info(f"LLM suggested makes: {result.makes}")
        logger.info(f"LLM suggested models: {result.models}")
        logger.info(f"Reasoning: {result.reasoning}")

        return result
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return None


def query_vehicles_for_make(
    store: LocalVehicleStore,
    make: str,
    filters: Dict[str, Any],
    user_latitude: Optional[float],
    user_longitude: Optional[float],
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Query vehicles for a specific make with user's filters.

    Args:
        store: LocalVehicleStore instance
        make: Vehicle make (e.g., "Honda")
        filters: User's explicit filters
        user_latitude: User's latitude
        user_longitude: User's longitude
        limit: Max vehicles to retrieve per make

    Returns:
        List of vehicles for this make
    """
    make_filters = filters.copy()
    make_filters['make'] = make
    # Remove model filter to get variety within the make
    make_filters.pop('model', None)

    try:
        vehicles = store.search_listings(
            make_filters,
            limit=limit,
            order_by="price",
            user_latitude=user_latitude,
            user_longitude=user_longitude
        )
        logger.info(f"Make '{make}': Found {len(vehicles)} vehicles")
        return vehicles
    except Exception as e:
        logger.error(f"Query failed for make '{make}': {e}")
        return []


def recommend_method2(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    top_k: int = 20,
    num_makes: int = 4,
    db_path: Optional[Path] = None,
    require_photos: bool = True,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Method 2: Web Search → Parallel SQL → Vector Ranking.

    Flow:
    1. Web search to find k relevant makes
    2. Spawn k parallel SQL queries (one per make)
    3. Rank each result list with vector similarity
    4. Select top (20/k) from each list
    5. Combine into final diverse list of 20

    Args:
        explicit_filters: User's explicit filters
        implicit_preferences: User's implicit preferences
        user_latitude: User's latitude for distance calculation
        user_longitude: User's longitude for distance calculation
        top_k: Number of vehicles to return (default 20)
        num_makes: Number of makes to query in parallel (default 4)
        db_path: Optional path to vehicle database
        require_photos: Whether to require photos

    Returns:
        Tuple of (list of vehicles, reasoning string)
    """
    logger.info("=" * 60)
    logger.info("METHOD 2: Web Search + Parallel SQL")
    logger.info("=" * 60)
    logger.info(f"Filters: {explicit_filters}")
    logger.info(f"Preferences: {implicit_preferences}")
    logger.info(f"Target: {top_k} vehicles from {num_makes} makes")

    # Step 1: Web search for vehicle suggestions
    logger.info("Step 1: Web search for vehicle suggestions...")
    suggestions = web_search_for_vehicle_suggestions(explicit_filters, implicit_preferences)

    if not suggestions or not suggestions.makes:
        logger.warning("Web search failed or returned no suggestions")
        return [], None

    logger.info(f"Step 1: Got {len(suggestions.makes)} makes: {suggestions.makes}")

    # Limit to num_makes
    makes_to_query = suggestions.makes[:num_makes]
    k = len(makes_to_query)

    # Step 2: Initialize local store
    try:
        store = LocalVehicleStore(db_path=db_path, require_photos=require_photos)
    except FileNotFoundError as e:
        logger.error(f"Local store unavailable: {e}")
        return [], None

    # Step 3: Parallel SQL queries for each make
    logger.info(f"Step 2: Querying {k} makes in parallel...")
    per_make_limit = max(30, top_k)  # Query more, rank later

    make_vehicle_lists: Dict[str, List[Dict[str, Any]]] = {}

    with ThreadPoolExecutor(max_workers=min(k, 8)) as executor:
        future_to_make = {
            executor.submit(
                query_vehicles_for_make,
                store,
                make,
                explicit_filters,
                user_latitude,
                user_longitude,
                per_make_limit
            ): make
            for make in makes_to_query
        }

        for future in as_completed(future_to_make):
            make = future_to_make[future]
            try:
                vehicles = future.result()
                make_vehicle_lists[make] = vehicles
            except Exception as e:
                logger.error(f"Failed to query make '{make}': {e}")
                make_vehicle_lists[make] = []

    total_retrieved = sum(len(v) for v in make_vehicle_lists.values())
    logger.info(f"Step 2: Retrieved {total_retrieved} total vehicles across {k} makes")

    # Step 4: Rank each make's vehicle list with vector similarity
    logger.info("Step 3: Ranking each make's vehicles by vector similarity...")

    ranked_make_lists: Dict[str, List[Dict[str, Any]]] = {}

    for make, vehicles in make_vehicle_lists.items():
        if not vehicles:
            ranked_make_lists[make] = []
            continue

        ranked = rank_local_vehicles_by_similarity(
            vehicles,
            explicit_filters,
            implicit_preferences,
            store.db_path,
            top_k=len(vehicles)  # Rank all, select later
        )
        ranked_make_lists[make] = ranked
        top_score = ranked[0].get("_vector_score", 0.0) if ranked else 0.0
        logger.info(f"  Make '{make}': Ranked {len(ranked)} vehicles (top score: {top_score:.3f})")

    # Step 5: Select top (20/k) from each make for diversity
    vehicles_per_make = max(1, top_k // k)
    logger.info(f"Step 4: Selecting top {vehicles_per_make} vehicles from each of {k} makes...")

    final_vehicles = []
    for make, ranked_vehicles in ranked_make_lists.items():
        selected = ranked_vehicles[:vehicles_per_make]
        final_vehicles.extend(selected)
        logger.info(f"  Make '{make}': Selected {len(selected)} vehicles")

    # Step 6: If we don't have enough, fill from remaining
    if len(final_vehicles) < top_k:
        logger.info(f"Only {len(final_vehicles)}/{top_k} vehicles - adding more from remaining...")

        # Collect all remaining vehicles
        remaining = []
        for make, ranked_vehicles in ranked_make_lists.items():
            remaining.extend(ranked_vehicles[vehicles_per_make:])

        # Sort by vector score
        remaining.sort(key=lambda v: v.get("_vector_score", 0.0), reverse=True)

        # Add until we reach top_k
        needed = top_k - len(final_vehicles)
        final_vehicles.extend(remaining[:needed])
        logger.info(f"  Added {min(needed, len(remaining))} more vehicles")

    # Trim to top_k
    final_vehicles = final_vehicles[:top_k]

    # Log final diversity stats
    final_unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in final_vehicles))
    final_unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in final_vehicles))
    logger.info(f"Step 5: Final selection has {final_unique_makes} makes, {final_unique_models} models")

    logger.info("=" * 60)
    logger.info(f"METHOD 2 COMPLETE: {len(final_vehicles)} vehicles returned")
    logger.info("=" * 60)

    return final_vehicles, suggestions.reasoning


__all__ = ["recommend_method2"]
