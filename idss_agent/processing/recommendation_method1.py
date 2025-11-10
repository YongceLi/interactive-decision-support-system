"""
Method 1: SQL + Vector Search + MMR Diversification

Simple approach:
1. SQL query returns candidate vehicles
2. Vector ranking by similarity to user preferences
3. MMR diversification for final top-k selection
"""
from typing import Dict, Any, List, Optional
from pathlib import Path

from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.processing.vector_ranker import rank_local_vehicles_by_similarity
from idss_agent.processing.diversification import diversify_with_mmr
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.method1")


def recommend_method1(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    top_k: int = 20,
    sql_limit: int = 100,
    lambda_param: float = 0.7,
    db_path: Optional[Path] = None,
    require_photos: bool = True,
) -> List[Dict[str, Any]]:
    """
    Method 1: SQL + Vector Ranking + MMR Diversification.

    Flow:
    1. SQL query with user filters (returns up to sql_limit vehicles)
    2. Rank all candidates by vector similarity
    3. Apply MMR to select diverse top_k

    Args:
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (priorities, lifestyle, etc.)
        user_latitude: User's latitude for distance calculation
        user_longitude: User's longitude for distance calculation
        top_k: Number of vehicles to return (default 20)
        sql_limit: Number of candidates to retrieve from SQL (default 100)
        lambda_param: MMR diversity parameter (0.6-0.8 recommended)
        db_path: Optional path to vehicle database
        require_photos: Whether to require photos

    Returns:
        List of top_k diverse and relevant vehicles
    """
    logger.info("=" * 60)
    logger.info("METHOD 1: SQL + Vector + MMR")
    logger.info("=" * 60)
    logger.info(f"Filters: {explicit_filters}")
    logger.info(f"Preferences: {implicit_preferences}")
    logger.info(f"Target: {top_k} vehicles, SQL limit: {sql_limit}, lambda: {lambda_param}")

    # Step 1: Initialize local store
    try:
        store = LocalVehicleStore(db_path=db_path, require_photos=require_photos)
    except FileNotFoundError as e:
        logger.error(f"Local store unavailable: {e}")
        return []

    # Step 2: Hybrid SQL query for diversity
    # Strategy: Get both exact matches AND diverse alternatives
    logger.info("Step 1: Querying database with hybrid diversity strategy...")

    # Query 1: Get exact matches (if make/model specified)
    exact_candidates = []
    if explicit_filters.get('make') or explicit_filters.get('model'):
        exact_limit = int(sql_limit * 0.4)  # 40% exact matches
        exact_candidates = store.search_listings(
            explicit_filters,
            limit=exact_limit,
            order_by="year",
            order_dir="DESC",
            user_latitude=user_latitude,
            user_longitude=user_longitude
        )
        logger.info(f"  Exact matches: {len(exact_candidates)} vehicles")

    # Query 2: Get diverse alternatives (remove make/model filters)
    # Use window function to enforce max 5 vehicles per make/model
    diverse_limit = sql_limit - len(exact_candidates)
    diverse_filters = explicit_filters.copy()
    diverse_filters.pop('make', None)
    diverse_filters.pop('model', None)

    # If no other filters remain, add reasonable defaults
    if not diverse_filters:
        diverse_filters['year'] = '2015-2025'

    diverse_candidates = store.search_listings(
        diverse_filters,
        limit=diverse_limit + len(exact_candidates),  # Query extra to account for overlaps
        order_by="year",
        order_dir="DESC",
        user_latitude=user_latitude,
        user_longitude=user_longitude,
        max_per_make_model=20  # Enforce diversity: max 20 vehicles per make/model
    )
    logger.info(f"  Diverse alternatives: {len(diverse_candidates)} vehicles (max 20 per make/model)")

    # Merge: exact matches first, then diverse (deduplicating by VIN)
    seen_vins = set()
    candidates = []

    # Add exact matches first
    for v in exact_candidates:
        vin = v.get('vin')
        if vin and vin not in seen_vins:
            candidates.append(v)
            seen_vins.add(vin)

    # Add diverse candidates
    for v in diverse_candidates:
        vin = v.get('vin')
        if vin and vin not in seen_vins:
            candidates.append(v)
            seen_vins.add(vin)
        if len(candidates) >= sql_limit:
            break

    if not candidates:
        logger.warning("No vehicles found from SQL query")
        return []

    logger.info(f"Step 1: Retrieved {len(candidates)} total candidate vehicles (hybrid strategy)")

    # Log diversity stats
    unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in candidates))
    unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in candidates))
    unique_make_models = len(set(
        f"{v.get('vehicle', {}).get('make', '')}_{v.get('vehicle', {}).get('model', '')}"
        for v in candidates
    ))
    logger.info(f"  Diversity: {unique_makes} makes, {unique_models} models, {unique_make_models} make/model combinations")

    # Step 3: Vector ranking
    logger.info("Step 2: Ranking by vector similarity...")
    ranked = rank_local_vehicles_by_similarity(
        candidates,
        explicit_filters,
        implicit_preferences,
        store.db_path,
        top_k=len(candidates)  # Rank all candidates
    )

    if not ranked:
        logger.warning("Vector ranking returned no results")
        return []

    logger.info(f"Step 2: Ranked {len(ranked)} vehicles")
    logger.info(f"  Top vehicle score: {ranked[0].get('_vector_score', 0.0):.3f}")

    # Step 4: MMR diversification
    logger.info("Step 3: Applying MMR diversification...")
    scored = [(v.get("_vector_score", 0.0), v) for v in ranked]

    diverse = diversify_with_mmr(
        scored,
        top_k=top_k,
        lambda_param=lambda_param
    )

    logger.info(f"Step 3: Selected {len(diverse)} diverse vehicles")

    # Log final diversity stats
    final_unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in diverse))
    final_unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in diverse))
    final_unique_make_models = len(set(
        f"{v.get('vehicle', {}).get('make', '')}_{v.get('vehicle', {}).get('model', '')}"
        for v in diverse
    ))
    logger.info(f"  Final diversity: {final_unique_makes} makes, {final_unique_models} models, {final_unique_make_models} make/model combinations")

    logger.info("=" * 60)
    logger.info(f"METHOD 1 COMPLETE: {len(diverse)} vehicles returned")
    logger.info("=" * 60)

    return diverse


__all__ = ["recommend_method1"]
