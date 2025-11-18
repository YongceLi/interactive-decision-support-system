"""
Method 2: Proxy Description → Multi-Filter Sets → Dense Ranking + MMR

Flow:
1. Generate proxy item description from user preferences
2. LLM generates 10 distinct filter sets exploring different market segments
3. Execute filter sets as parallel SQL queries
4. Deduplicate results by VIN
5. Dense ranking by semantic similarity
6. MMR diversification
7. Two-tier fallback: explicit_filters → entire database
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.state.schema import VehicleFiltersPydantic
from idss_agent.utils.logger import get_logger
from idss_agent.utils.config import get_config

logger = get_logger("processing.method2")


class MultiFilterSet(BaseModel):
    """Multiple filter sets for diverse search."""
    filter_sets: List[VehicleFiltersPydantic] = Field(
        description="10 distinct filter sets that all match user intent but explore different segments"
    )
    reasoning: str = Field(
        description="Brief explanation of diversity strategy across all filter sets"
    )


def generate_proxy_description(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> str:
    """
    Generate a natural language proxy item description from structured filters.

    This describes the "ideal vehicle" the user wants in natural language,
    which the LLM can then use to generate diverse filter sets.

    Args:
        explicit_filters: User's explicit filters
        implicit_preferences: User's implicit preferences

    Returns:
        Natural language description of ideal vehicle
    """
    parts = []

    # Body style
    body_style = explicit_filters.get("body_style")
    if body_style:
        parts.append(f"{body_style}")

    # Make/Model
    make = explicit_filters.get("make")
    model = explicit_filters.get("model")
    if make and model:
        parts.append(f"from {make} (specifically {model})")
    elif make:
        parts.append(f"from {make}")
    elif model:
        parts.append(f"such as a {model}")

    # Year
    year = explicit_filters.get("year")
    if year:
        if "-" in str(year):
            parts.append(f"from years {year}")
        else:
            parts.append(f"from {year}")

    # Price
    price = explicit_filters.get("price")
    if price:
        if "-" in str(price):
            min_p, max_p = price.split("-")
            parts.append(f"priced between ${min_p} and ${max_p}")
        else:
            parts.append(f"priced around ${price}")

    # Fuel type
    fuel_type = explicit_filters.get("fuel_type")
    if fuel_type:
        parts.append(f"with {fuel_type.lower()} fuel")

    # Drivetrain
    drivetrain = explicit_filters.get("drivetrain")
    if drivetrain:
        parts.append(f"with {drivetrain}")

    # Transmission
    transmission = explicit_filters.get("transmission")
    if transmission:
        parts.append(f"with {transmission.lower()} transmission")

    # Mileage
    mileage = explicit_filters.get("mileage")
    if mileage:
        if "-" in str(mileage):
            parts.append(f"with mileage in range {mileage} miles")

    # Color
    color = explicit_filters.get("exterior_color")
    if color:
        parts.append(f"in {color.lower()} color")

    # Used/New/CPO
    is_used = explicit_filters.get("is_used")
    is_cpo = explicit_filters.get("is_cpo")
    if is_used is True:
        if is_cpo is True:
            parts.append("certified pre-owned")
        else:
            parts.append("used")
    elif is_used is False:
        parts.append("brand new")

    # Avoid vehicles
    avoid = explicit_filters.get("avoid_vehicles", [])
    if avoid:
        avoid_str = ", ".join([
            f"{v.get('make', '')} {v.get('model', '')}".strip()
            for v in avoid
        ])
        parts.append(f"excluding: {avoid_str}")

    # Implicit preferences
    priorities = implicit_preferences.get("priorities", [])
    if priorities:
        parts.append(f"prioritizing {', '.join(priorities[:3])}")

    lifestyle = implicit_preferences.get("lifestyle")
    if lifestyle:
        parts.append(f"for {lifestyle} use")

    budget = implicit_preferences.get("budget_sensitivity")
    if budget:
        parts.append(f"with {budget} budget focus")

    # Combine into description
    if parts:
        description = "A vehicle " + ", ".join(parts) + "."
    else:
        description = "A vehicle matching user preferences."

    return description


def generate_multi_filter_sets(
    proxy_description: str,
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    num_sets: int = 10
) -> MultiFilterSet:
    """
    Use LLM to generate multiple distinct filter sets from proxy description.

    Each filter set explores a different segment of the market while satisfying
    the core user requirements.

    Args:
        proxy_description: Natural language description of ideal vehicle
        explicit_filters: Original explicit filters (for reference)
        implicit_preferences: Original implicit preferences (for reference)
        num_sets: Number of filter sets to generate (default 10)

    Returns:
        MultiFilterSet with 10 distinct filter sets
    """

    # Build prompt with filter schema from semantic_parser.j2
    prompt = f"""You are a vehicle search expert. Generate {num_sets} DISTINCT filter sets
that all satisfy the user's requirements but explore different market segments.

**User's Ideal Vehicle:**
{proxy_description}

**Original Filters (for reference):**
{json.dumps(explicit_filters, indent=2)}

**Implicit Preferences (for reference):**
{json.dumps(implicit_preferences, indent=2)}

**Available Filters:**

- **make**: String or comma-separated (e.g., "Toyota" or "Toyota,Honda")
- **model**: String or comma-separated (e.g., "Camry" or "Camry,Accord") - BASE MODEL ONLY, no trims
- **year**: Single year "2020" or range "2018-2020"
- **price**: Range format "15000-25000"
- **mileage**: Range format "0-50000"
- **body_style**: One of: "Sedan", "SUV", "Pickup", "Coupe", "Hatchback", "Wagon", "Convertible", "Van", "Minivan"
- **fuel_type**: One of: "Gasoline", "Electric", "Hybrid (Electric + Gasoline)", "Diesel", "Hydrogen"
- **drivetrain**: One of: "FWD", "RWD", "AWD", "4WD"
- **transmission**: One of: "Automatic", "Manual", "CVT", "Automated Manual"
- **exterior_color**: String (e.g., "White", "Black")
- **is_used**: true (used), false (new), or null (don't care)
- **is_cpo**: true (certified pre-owned), false (not CPO), or null (don't care)
- **search_radius**: Integer (miles from user location)
- **avoid_vehicles**: List of {{make, model}} to exclude
- **must_have_filters**: List of field names that are STRICT requirements (will be enforced by SQL)

**Diversity Strategies:**

Generate {num_sets} filter sets using DIFFERENT approaches:

1. **Brand diversity**: Different make combinations
   - Set 1: Toyota/Honda (mainstream reliable)
   - Set 2: Mazda/Subaru (alternative reliable)
   - Set 3: Ford/Chevrolet (American brands)
   - Set 4: BMW/Audi (luxury European)

2. **Price segments**: Different budget ranges
   - Budget: Lower end of user's range
   - Mid-range: Middle of user's range
   - Premium: Higher end of user's range

3. **Feature focus**: Different attribute priorities
   - Efficiency: Hybrid/electric, good MPG
   - Capability: AWD/4WD, towing
   - Luxury: Premium brands, features
   - Value: Best price/mileage ratio

4. **Age segments**: Different year ranges
   - Brand new: 2024-2025
   - Recent: 2022-2023
   - Slightly used: 2020-2021

5. **Specificity**: Vary how restrictive
   - Narrow: Specific make+model
   - Medium: Specific make, any model
   - Broad: Any make, just body_style/price

**CRITICAL RULES:**

1. **ALL sets must satisfy core requirements**:
   - If user says "SUV", ALL sets must have body_style="SUV"
   - If user says "under $40k", ALL sets must have price ending at or below 40000
   - If user says "2022 or newer", ALL sets must have year starting at or after 2022

2. **Preserve avoid_vehicles in ALL sets**:
   - If user avoids a vehicle, include avoid_vehicles in EVERY filter set

3. **Preserve must_have_filters in ALL sets**:
   - If user has strict requirements, include them in EVERY filter set
   - Fields in must_have_filters should appear in ALL sets

4. **Multi-dimensional exploration**:
   - Explore different dimensions: make, price, year, mileage
   - If user mentions signals (modern, luxury, budget, recent), infer appropriate ranges
   - Even if not specified, VARY year and price across sets for better coverage
   - You CAN vary makes/models ONLY if they're NOT in must_have_filters

5. **Make sets DISTINCT - NO overlaps allowed**:
   - Each filter set must be UNIQUE - no duplicates
   - Vary across multiple dimensions (make, price, year, mileage)
   - Different make combinations (ONLY if make not in must_have_filters)
   - Different year ranges to explore newer vs slightly older vehicles
   - Different price segments
   - CRITICAL: Review all 10 sets before returning to ensure no duplicates or heavy overlaps

6. **Aim for 50-200 vehicles per set**:
   - Don't make sets too restrictive (would get < 10 results)
   - Don't make sets too broad (would get > 1000 results)

7. **Only use valid values**:
   - Use exact values from the available filters list above
   - For multiple values, use comma-separated strings

**Example:**

User wants: "Reliable family SUV under $40k, avoiding Toyota RAV4"

Filter Set 1 (Honda/Mazda - alternative reliable):
{{
  "body_style": "SUV",
  "make": "Honda,Mazda",
  "price": "25000-40000",
  "year": "2020-2024",
  "avoid_vehicles": [{{"make": "Toyota", "model": "RAV4"}}],
  "must_have_filters": ["body_style", "price"]
}}

Filter Set 2 (Subaru - AWD capability):
{{
  "body_style": "SUV",
  "make": "Subaru",
  "drivetrain": "AWD",
  "price": "25000-40000",
  "year": "2020-2024",
  "avoid_vehicles": [{{"make": "Toyota", "model": "RAV4"}}],
  "must_have_filters": ["body_style", "price"]
}}

Filter Set 3 (Budget segment - any make):
{{
  "body_style": "SUV",
  "price": "20000-30000",
  "year": "2018-2024",
  "avoid_vehicles": [{{"make": "Toyota", "model": "RAV4"}}],
  "must_have_filters": ["body_style", "price"]
}}

Filter Set 4 (Hybrid efficiency - any make):
{{
  "body_style": "SUV",
  "fuel_type": "Hybrid (Electric + Gasoline)",
  "price": "25000-40000",
  "year": "2020-2024",
  "avoid_vehicles": [{{"make": "Toyota", "model": "RAV4"}}],
  "must_have_filters": ["body_style", "price"]
}}

Filter Set 5 (Newest models - any make):
{{
  "body_style": "SUV",
  "year": "2023-2024",
  "price": "25000-40000",
  "avoid_vehicles": [{{"make": "Toyota", "model": "RAV4"}}],
  "must_have_filters": ["body_style", "price"]
}}

... (5 more distinct sets exploring other segments)

Now generate {num_sets} distinct filter sets for the user's requirements.
"""

    # Call LLM with structured output
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
    structured_llm = llm.with_structured_output(MultiFilterSet)

    try:
        result: MultiFilterSet = structured_llm.invoke([
            SystemMessage(content="You are a vehicle search expert specializing in diverse market exploration."),
            HumanMessage(content=prompt)
        ])

        logger.info(f"LLM generated {len(result.filter_sets)} filter sets")
        logger.info(f"Strategy: {result.reasoning}")

        return result

    except Exception as e:
        logger.error(f"Failed to generate filter sets: {e}")
        # Fallback: create simple filter sets from original filters
        logger.warning("Falling back to simple filter generation")

        fallback_sets = []
        base_filters = VehicleFiltersPydantic(**explicit_filters)

        # Just duplicate the base filters 10 times (not ideal, but safe)
        for i in range(num_sets):
            fallback_sets.append(base_filters)

        return MultiFilterSet(
            filter_sets=fallback_sets,
            reasoning="Fallback: Using original filters"
        )


def recommend_method2(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    top_k: Optional[int] = None,
    num_filter_sets: Optional[int] = None,
    db_path: Optional[Path] = None,
    require_photos: bool = True,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Method 2: Proxy Description → Multi-Filter Sets → Dense Ranking + MMR.

    Flow:
    1. Generate proxy item description from user preferences
    2. LLM generates N distinct filter sets
    3. Execute filter sets as parallel SQL queries
    4. Deduplicate results by VIN
    5. Dense ranking by semantic similarity
    6. MMR diversification
    7. Two-tier fallback if no results

    Args:
        explicit_filters: User's explicit filters
        implicit_preferences: User's implicit preferences
        user_latitude: User's latitude for distance calculation
        user_longitude: User's longitude for distance calculation
        top_k: Number of vehicles to return (default from config)
        num_filter_sets: Number of filter sets to generate (default 10)
        db_path: Optional path to vehicle database
        require_photos: Whether to require photos

    Returns:
        Tuple of (list of top_k vehicles, proxy description)
    """
    # Load config values if not provided
    config = get_config()
    method2_config = config.recommendation.get('method2', {})

    if top_k is None:
        top_k = method2_config.get('top_k', 20)
    if num_filter_sets is None:
        num_filter_sets = method2_config.get('num_filter_sets', 10)

    logger.info("=" * 60)
    logger.info("METHOD 2: Multi-Filter Strategy")
    logger.info("=" * 60)
    logger.info(f"Filters: {explicit_filters}")
    logger.info(f"Preferences: {implicit_preferences}")
    logger.info(f"Target: {top_k} vehicles from {num_filter_sets} filter sets")

    # Step 1: Generate proxy description
    logger.info("=" * 60)
    logger.info("STEP 1: Generate Proxy Description")
    logger.info("=" * 60)

    proxy_description = generate_proxy_description(explicit_filters, implicit_preferences)
    logger.info(f"Proxy: {proxy_description}")

    # Step 2: LLM generates distinct filter sets
    logger.info("=" * 60)
    logger.info(f"STEP 2: Generate {num_filter_sets} Distinct Filter Sets")
    logger.info("=" * 60)

    multi_filter_set = generate_multi_filter_sets(
        proxy_description,
        explicit_filters,
        implicit_preferences,
        num_filter_sets
    )

    filter_sets = multi_filter_set.filter_sets
    logger.info(f"Generated {len(filter_sets)} filter sets")
    logger.info(f"Strategy: {multi_filter_set.reasoning}")

    # Log each filter set (show ALL non-None fields)
    for i, fs in enumerate(filter_sets, 1):
        fs_dict = fs.model_dump(exclude_none=True)
        # Remove must_have_filters and avoid_vehicles from display for brevity
        display_dict = {k: v for k, v in fs_dict.items()
                       if k not in ['must_have_filters', 'avoid_vehicles']}
        logger.info(f"  Set {i}: {display_dict}")

    # Step 3: Initialize local store
    try:
        store = LocalVehicleStore(db_path=db_path, require_photos=require_photos)
    except FileNotFoundError as e:
        logger.error(f"Local store unavailable: {e}")
        return [], None

    # Step 4: Execute queries in parallel
    logger.info("=" * 60)
    logger.info("STEP 3: Execute SQL Queries in Parallel")
    logger.info("=" * 60)

    all_candidates = []

    with ThreadPoolExecutor(max_workers=min(num_filter_sets, 8)) as executor:
        futures = []

        for i, filter_set in enumerate(filter_sets):
            # Convert Pydantic to dict
            filters_dict = filter_set.model_dump(exclude_none=True)

            # Apply filter validation (categorical value correction)
            from idss_agent.processing.filter_validator import validate_and_correct_filters
            filters_dict = validate_and_correct_filters(filters_dict)

            # Submit query
            future = executor.submit(
                store.search_listings,
                filters_dict,
                limit=None,  # Get all matching vehicles
                user_latitude=user_latitude,
                user_longitude=user_longitude
            )
            futures.append((future, i + 1))

        # Collect results
        for future, query_idx in futures:
            try:
                vehicles = future.result()
                logger.info(f"  Filter Set {query_idx}: {len(vehicles)} vehicles")
                all_candidates.extend(vehicles)
            except Exception as e:
                logger.error(f"  Filter Set {query_idx} failed: {e}")

    logger.info(f"Step 3: Retrieved {len(all_candidates)} total vehicles (with duplicates)")

    # Step 5: Deduplicate by VIN
    logger.info("=" * 60)
    logger.info("STEP 4: Deduplicate by VIN")
    logger.info("=" * 60)

    seen_vins = set()
    unique_candidates = []

    for vehicle in all_candidates:
        vin = vehicle.get("vehicle", {}).get("vin") or vehicle.get("vin")
        if vin and vin not in seen_vins:
            seen_vins.add(vin)
            unique_candidates.append(vehicle)

    logger.info(f"Step 4: {len(unique_candidates)} unique vehicles")

    # Two-tier fallback if no results
    if not unique_candidates:
        logger.warning("=" * 60)
        logger.warning("FALLBACK TIER 1: No results from filter sets")
        logger.warning("=" * 60)
        logger.warning("Trying with original explicit_filters...")

        try:
            unique_candidates = store.search_listings(
                explicit_filters,
                limit=None,
                user_latitude=user_latitude,
                user_longitude=user_longitude
            )
            logger.info(f"Fallback Tier 1: {len(unique_candidates)} vehicles")
        except Exception as e:
            logger.error(f"Fallback Tier 1 failed: {e}")

        # If still no results, search entire database
        if not unique_candidates:
            logger.warning("=" * 60)
            logger.warning("FALLBACK TIER 2: Still no results")
            logger.warning("=" * 60)
            logger.warning("Searching entire database (no filters)...")

            try:
                unique_candidates = store.search_listings(
                    {},  # No filters
                    limit=1000,  # Limit to 1000 for performance
                    user_latitude=user_latitude,
                    user_longitude=user_longitude
                )
                logger.info(f"Fallback Tier 2: {len(unique_candidates)} vehicles")
            except Exception as e:
                logger.error(f"Fallback Tier 2 failed: {e}")
                return [], proxy_description

    if not unique_candidates:
        logger.error("No vehicles found after all fallbacks")
        return [], proxy_description

    # Step 6: Dense ranking
    logger.info("=" * 60)
    logger.info("STEP 5: Dense Embedding Ranking")
    logger.info("=" * 60)

    from idss_agent.processing.dense_ranker import rank_vehicles_by_dense_similarity

    # Limit to top 1000 for ranking efficiency
    candidates_to_rank = unique_candidates[:1000] if len(unique_candidates) > 1000 else unique_candidates
    logger.info(f"Ranking {len(candidates_to_rank)} vehicles...")

    ranked = rank_vehicles_by_dense_similarity(
        candidates_to_rank,
        explicit_filters,
        implicit_preferences,
        db_path=store.db_path,
        top_k=min(1000, len(candidates_to_rank))
    )

    if not ranked:
        logger.warning("Dense ranking returned no results")
        return [], proxy_description

    logger.info(f"Step 5: Ranked {len(ranked)} vehicles")
    if ranked:
        logger.info(f"  Top score: {ranked[0].get('_dense_score', 0.0):.3f}")

    # Step 7: MMR diversification
    logger.info("=" * 60)
    logger.info("STEP 6: Clustered MMR Diversification")
    logger.info("=" * 60)

    from idss_agent.processing.diversification import diversify_with_clustered_mmr

    # Get config params
    lambda_param = method2_config.get('lambda_param', 0.85)
    cluster_size = method2_config.get('cluster_size', 5)

    scored = [(v.get("_dense_score", 0.0), v) for v in ranked]
    diverse = diversify_with_clustered_mmr(
        scored,
        top_k=top_k,
        cluster_size=cluster_size,
        lambda_param=lambda_param
    )

    logger.info(f"Step 6: Selected {len(diverse)} final vehicles")

    # Log diversity stats
    unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in diverse))
    unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in diverse))
    unique_make_models = len(set(
        f"{v.get('vehicle', {}).get('make', '')}_{v.get('vehicle', {}).get('model', '')}"
        for v in diverse
    ))

    logger.info(f"  Final diversity: {unique_makes} makes, {unique_models} models, {unique_make_models} make/model combos")

    logger.info("=" * 60)
    logger.info(f"METHOD 2 COMPLETE: {len(diverse)} vehicles returned")
    logger.info("=" * 60)

    return diverse, proxy_description


__all__ = ["recommend_method2"]
