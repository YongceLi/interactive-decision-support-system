"""
Method 1: SQL + Dense Vector Search + MMR Diversification

Simple approach:
1. SQL query returns candidate vehicles
2. Dense embedding ranking by semantic similarity to user preferences
3. MMR diversification for final top-k selection
"""
from typing import Dict, Any, List, Optional
from pathlib import Path

from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.processing.dense_ranker import rank_vehicles_by_dense_similarity
from idss_agent.processing.diversification import diversify_with_clustered_mmr
from idss_agent.utils.logger import get_logger
from idss_agent.utils.config import get_config

logger = get_logger("processing.method1")


def recommend_method1(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    top_k: Optional[int] = None,
    sql_limit: int = 100,
    lambda_param: Optional[float] = None,
    cluster_size: Optional[int] = None,
    vector_limit: Optional[int] = None,
    db_path: Optional[Path] = None,
    require_photos: bool = True,
) -> List[Dict[str, Any]]:
    """
    Method 1: SQL + Dense Vector Ranking + Clustered MMR Diversification.

    Flow:
    1. SQL query with strict filters only (returns all matching vehicles)
    2. Rank all candidates by dense embedding similarity
    3. Apply clustered MMR to select diverse clusters of similar vehicles

    Args:
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (priorities, lifestyle, etc.)
        user_latitude: User's latitude for distance calculation
        user_longitude: User's longitude for distance calculation
        top_k: Number of vehicles to return (default 20)
        sql_limit: Number of candidates to retrieve from SQL (default 100) - DEPRECATED
        lambda_param: MMR diversity parameter within clusters (0.6-0.8 recommended)
        cluster_size: Number of similar vehicles per cluster (default 3)
        db_path: Optional path to vehicle database
        require_photos: Whether to require photos

    Returns:
        List of top_k vehicles organized in clusters
    """
    # Load config values if not provided
    config = get_config()
    method1_config = config.recommendation.get('method1', {})

    if top_k is None:
        top_k = method1_config.get('top_k', 20)
    if lambda_param is None:
        lambda_param = method1_config.get('lambda_param', 0.7)
    if cluster_size is None:
        cluster_size = method1_config.get('cluster_size', 3)
    if vector_limit is None:
        vector_limit = method1_config.get('vector_limit', 1000)

    logger.info("=" * 60)
    logger.info("METHOD 1: SQL + Vector + MMR")
    logger.info("=" * 60)
    logger.info(f"Filters: {explicit_filters}")
    logger.info(f"Preferences: {implicit_preferences}")
    logger.info(f"Target: {top_k} vehicles, cluster_size: {cluster_size}, lambda: {lambda_param}, vector_limit: {vector_limit}")

    # Step 1: Initialize local store
    try:
        store = LocalVehicleStore(db_path=db_path, require_photos=require_photos)
    except FileNotFoundError as e:
        logger.error(f"Local store unavailable: {e}")
        return []

    # Step 2: Build strict filters (only must-have fields)
    logger.info("Step 1: Building SQL query with strict filters only...")

    must_have = explicit_filters.get("must_have_filters", [])
    strict_filters = {}

    # Extract only must-have filters for SQL query
    for key in must_have:
        if key in explicit_filters and key != "must_have_filters":
            strict_filters[key] = explicit_filters[key]
            logger.info(f"  Strict filter: {key} = {explicit_filters[key]}")

    # ALWAYS include avoid_vehicles in SQL query (even if not in must_have)
    if explicit_filters.get("avoid_vehicles"):
        strict_filters["avoid_vehicles"] = explicit_filters["avoid_vehicles"]
        logger.info(f"  Excluding vehicles: {explicit_filters['avoid_vehicles']}")

    # Log flexible filters (used only for vector ranking)
    flexible_filters = {k: v for k, v in explicit_filters.items()
                       if k not in must_have and k != "must_have_filters" and k != "avoid_vehicles"}
    if flexible_filters:
        logger.info(f"  Flexible filters (vector only): {list(flexible_filters.keys())}")

    # If no strict filters, add reasonable defaults to prevent querying entire DB
    if not strict_filters:
        logger.warning("No strict filters - adding default year range")
        strict_filters['year'] = '2015-2025'

    # Step 3: Single SQL query with strict filters only (no ORDER BY, no LIMIT)
    logger.info(f"Step 1: Querying database with {len(strict_filters)} strict filters...")
    candidates = store.search_listings(
        strict_filters,
        limit=None,  # No limit - get all matching vehicles
        order_by=None,  # No ordering - let dense ranker handle it
        order_dir="ASC",
        user_latitude=user_latitude,
        user_longitude=user_longitude
        # No max_per_make_model - let MMR handle all diversity
    )

    if not candidates:
        logger.warning("No vehicles found from SQL query - falling back to full database search")
        logger.info("Step 1b: Searching entire database with dense embeddings...")

        # Fallback: Search entire database using dense embeddings
        from idss_agent.processing.dense_ranker import get_dense_embedding_store, build_query_text

        try:
            store_dense = get_dense_embedding_store()
            query_text = build_query_text(explicit_filters, implicit_preferences)
            logger.info(f"Query: {query_text[:150]}{'...' if len(query_text) > 150 else ''}")

            # Search entire database (use configured vector_limit)
            vins, scores = store_dense.search(query_text, k=vector_limit)  # Get top N candidates for MMR

            if not vins:
                logger.warning("Dense search returned no results")
                return []

            logger.info(f"Dense search found {len(vins)} candidates from entire database")

            # Load full vehicle payloads from database
            candidates = []
            for vin, score in zip(vins, scores):
                vehicle = store.get_by_vin(vin)
                if vehicle:
                    vehicle["_dense_score"] = score
                    vehicle["_vector_score"] = score
                    candidates.append(vehicle)

            logger.info(f"Loaded {len(candidates)} vehicle payloads")

            # Skip SQL query stats, go directly to MMR diversification
            scored = [(v.get("_dense_score", 0.0), v) for v in candidates]

            diverse = diversify_with_clustered_mmr(
                scored,
                top_k=top_k,
                cluster_size=cluster_size,
                lambda_param=lambda_param
            )

            logger.info(f"Step 1b: Selected {len(diverse)} vehicles via fallback")

            # Log final diversity stats
            final_unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in diverse))
            final_unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in diverse))
            final_unique_make_models = len(set(
                f"{v.get('vehicle', {}).get('make', '')}_{v.get('vehicle', {}).get('model', '')}"
                for v in diverse
            ))
            logger.info(f"  Fallback diversity: {final_unique_makes} makes, {final_unique_models} models, {final_unique_make_models} make/model combinations")

            logger.info("=" * 60)
            logger.info(f"METHOD 1 COMPLETE (FALLBACK): {len(diverse)} vehicles returned")
            logger.info("=" * 60)

            return diverse

        except Exception as e:
            logger.error(f"Fallback dense search failed: {e}")
            return []

    logger.info(f"Step 1: Retrieved {len(candidates)} candidate vehicles")

    # Log diversity stats
    unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in candidates))
    unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in candidates))
    logger.info(f"  SQL diversity: {unique_makes} makes, {unique_models} models")

    # Step 2: Dense embedding ranking
    logger.info("Step 2: Ranking by dense embedding similarity...")
    # Limit to configured max (or all if fewer candidates)
    effective_limit = min(vector_limit, len(candidates))
    logger.info(f"  Vector ranking limit: {effective_limit} (from {len(candidates)} candidates)")
    ranked = rank_vehicles_by_dense_similarity(
        candidates,
        explicit_filters,
        implicit_preferences,
        db_path=store.db_path,
        top_k=effective_limit  # Rank top N (configured limit or all if < limit)
    )

    if not ranked:
        logger.warning("Dense embedding ranking returned no results")
        return []

    logger.info(f"Step 2: Ranked {len(ranked)} vehicles")
    logger.info(f"  Top vehicle score: {ranked[0].get('_dense_score', 0.0):.3f}")

    # Step 3: Clustered MMR diversification
    logger.info("Step 3: Applying clustered MMR diversification...")
    scored = [(v.get("_dense_score", 0.0), v) for v in ranked]

    diverse = diversify_with_clustered_mmr(
        scored,
        top_k=top_k,
        cluster_size=cluster_size,
        lambda_param=lambda_param
    )

    logger.info(f"Step 3: Selected {len(diverse)} vehicles in clusters")

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
