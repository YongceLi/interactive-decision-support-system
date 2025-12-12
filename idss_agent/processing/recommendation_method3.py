"""
Method 3: SQL + Coverage-Risk Optimization.

This method combines:
1. Progressive filter relaxation (from Method 1)
2. Coverage-risk optimization ranking (Method 3)

Flow:
1. Progressive filter relaxation - SQL query until ANY results found
2. Rank candidates using coverage-risk optimization with phrase-level semantic alignment
3. Return diversified top-k recommendations

Key differences from Method 1:
- Removes dense vector + MMR diversification
- Uses phrase-level semantic alignment (Pos/Neg scores)
- Greedy selection maximizes coverage while minimizing risk
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from idss_agent.utils.config import get_config
from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.processing.method3_ranker import rank_vehicles_by_method3
from idss_agent.processing.recommendation_method1 import progressive_filter_relaxation
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.recommendation_method3")


def recommend_method3(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    top_k: Optional[int] = None,
    lambda_risk: Optional[float] = None,
    db_path: Optional[Path] = None,
    require_photos: bool = True,
) -> Tuple[List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """
    Method 3: SQL + Coverage-Risk Optimization.

    Flow:
    1. Progressive filter relaxation - SQL query until ANY results found
    2. Rank all candidates using coverage-risk optimization

    Key behavior:
    - If ANY vehicles match all user criteria, return them (even if just 1)
    - Only relax filters when 0 results found
    - Tracks which filters were relaxed for user transparency
    - Uses phrase-level semantic alignment for ranking
    - Greedy selection maximizes coverage while minimizing risk

    Args:
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (liked_features, disliked_features)
        user_latitude: User's latitude for distance calculation
        user_longitude: User's longitude for distance calculation
        top_k: Number of vehicles to return (default 20)
        lambda_risk: Risk penalty weight for coverage-risk optimization (default 0.5)
        db_path: Optional path to vehicle database
        require_photos: Whether to require photos

    Returns:
        Tuple of:
        - List of top_k vehicles ranked by coverage-risk optimization
        - SQL query string (last executed)
        - Relaxation state dict with:
            - all_criteria_met: True if no relaxation was needed
            - met_filters: List of filters that were satisfied
            - relaxed_filters: List of all filters that were removed (in order)
            - relaxed_inferred: List of inferred filters that were relaxed (Tier 0)
            - relaxed_regular: List of regular filters that were relaxed (Tier 1)
            - unmet_must_haves: List of must-have filters that had to be relaxed (Tier 2)
            - original_values: Dict of original values for relaxed filters
    """
    # Load config values if not provided
    config = get_config()
    method3_config = config.recommendation.get('method3', {})

    if top_k is None:
        top_k = method3_config.get('top_k', 20)
    if lambda_risk is None:
        lambda_risk = method3_config.get('lambda_risk', 0.5)

    logger.info("=" * 60)
    logger.info("METHOD 3: SQL + Coverage-Risk Optimization")
    logger.info("=" * 60)
    logger.info(f"Filters: {explicit_filters}")
    logger.info(f"Preferences: {implicit_preferences}")
    logger.info(f"Target: {top_k} vehicles, lambda_risk: {lambda_risk}")

    # Initialize SQL query variable
    sql_query = None

    # Step 1: Initialize local store
    try:
        store = LocalVehicleStore(db_path=db_path, require_photos=require_photos)
    except FileNotFoundError as e:
        logger.error(f"Local store unavailable: {e}")
        return [], None, {}

    # If no filters at all, add default year range
    if not explicit_filters or explicit_filters == {"must_have_filters": []}:
        logger.warning("No explicit filters - adding default year range")
        explicit_filters['year'] = '2020-2025'

    # Step 1: Progressive Filter Relaxation (reuse Method 1's logic)
    # Relax filters until ANY results found (not a target count)
    candidates, sql_query, relaxation_state = progressive_filter_relaxation(
        store=store,
        explicit_filters=explicit_filters,
        user_latitude=user_latitude,
        user_longitude=user_longitude
    )

    # Log diversity stats
    if candidates:
        unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in candidates))
        unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in candidates))
        logger.info(f"  Diversity: {unique_makes} makes, {unique_models} models")

    if not candidates:
        logger.warning("No candidates found after progressive relaxation")
        return [], sql_query, relaxation_state

    # Step 2: Coverage-risk optimization ranking
    logger.info("Step 2: Ranking by coverage-risk optimization...")
    logger.info(f"  Ranking {len(candidates)} candidates")

    # Extract vehicle data for ranking (method3_ranker expects list of dicts)
    vehicles_for_ranking = []
    for candidate in candidates:
        vehicle_data = candidate.get("vehicle", {})
        vehicles_for_ranking.append({
            "make": vehicle_data.get("make"),
            "model": vehicle_data.get("model"),
            "year": vehicle_data.get("year"),
            "price": vehicle_data.get("price"),
            "vin": vehicle_data.get("vin"),
            "_original": candidate  # Keep reference to original candidate
        })

    ranked_vehicles = rank_vehicles_by_method3(
        vehicles=vehicles_for_ranking,
        explicit_filters=explicit_filters,
        implicit_preferences=implicit_preferences,
        db_path=store.db_path,
        top_k=top_k,
        lambda_risk=lambda_risk
    )

    if not ranked_vehicles:
        logger.warning("Coverage-risk optimization returned no results")
        return [], sql_query, relaxation_state

    # Restore original candidate structure
    final_results = []
    for ranked_vehicle in ranked_vehicles:
        original_candidate = ranked_vehicle.pop("_original")
        final_results.append(original_candidate)

    logger.info(f"Step 2: Ranked {len(final_results)} vehicles")

    # Log final diversity stats
    final_unique_makes = len(set(v.get("vehicle", {}).get("make", "") for v in final_results))
    final_unique_models = len(set(v.get("vehicle", {}).get("model", "") for v in final_results))
    final_unique_make_models = len(set(
        f"{v.get('vehicle', {}).get('make', '')}_{v.get('vehicle', {}).get('model', '')}"
        for v in final_results
    ))
    logger.info(f"  Final diversity: {final_unique_makes} makes, {final_unique_models} models, {final_unique_make_models} make/model combinations")

    logger.info("=" * 60)
    logger.info(f"METHOD 3 COMPLETE: {len(final_results)} vehicles returned")
    logger.info("=" * 60)

    return final_results, sql_query, relaxation_state


__all__ = ["recommend_method3"]
