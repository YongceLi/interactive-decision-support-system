"""
Method 1: SQL + Dense Vector Search + MMR Diversification

Simple approach:
1. SQL query returns candidate vehicles
2. Dense embedding ranking by semantic similarity to user preferences
3. MMR diversification for final top-k selection
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.processing.dense_ranker import rank_vehicles_by_dense_similarity
from idss_agent.processing.diversification import diversify_with_clustered_mmr
from idss_agent.utils.logger import get_logger
from idss_agent.utils.config import get_config

logger = get_logger("processing.method1")

# Filter importance ranking - filters earlier in list are LESS important (relaxed first)
# Filters later in list are MORE important (kept longest)
FILTER_RELAXATION_ORDER = [
    "search_radius",      # 1 - Willing to travel farther
    "interior_color",     # 2 - Cosmetic
    "exterior_color",     # 3 - Cosmetic
    "is_cpo",             # 4 - Certification is a plus
    "engine",             # 5 - Performance preference
    "trim",               # 6 - Specific variant
    "doors",              # 7 - Practical but flexible
    "year",               # 8 - Age preference (flexible)
    "mileage",            # 9 - Condition indicator (flexible)
    "price",              # 10 - Budget constraint
    "model",              # 11 - Specific model
    "make",               # 12 - Brand identity
    "drivetrain",         # 13 - Climate/terrain needs
    "seating_capacity",   # 14 - Family size
    "transmission",       # 15 - Manual vs automatic
    "fuel_type",          # 16 - Infrastructure/operating cost
    "is_used",            # 17 - New vs used
    "body_style",         # 18 - Fundamental vehicle type (MOST IMPORTANT)
]


def progressive_filter_relaxation(
    store: LocalVehicleStore,
    explicit_filters: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """
    Progressively relax filters from least to most important until we find ANY results.

    Key behavior:
    - If ANY vehicles match all criteria, return them (even if just 1)
    - Only relax filters when 0 results found
    - Track which filters were relaxed so we can inform the user

    Filter Relaxation Hierarchy (3 tiers):
    1. INFERRED filters are relaxed FIRST (least certain - derived from context)
    2. REGULAR filters are relaxed SECOND (explicit but flexible)
    3. MUST-HAVE filters are relaxed LAST (strict requirements)

    Within each tier, filters are relaxed according to FILTER_RELAXATION_ORDER.

    Args:
        store: LocalVehicleStore instance
        explicit_filters: All explicit filters from user
        user_latitude: User latitude for distance calculation
        user_longitude: User longitude for distance calculation

    Returns:
        Tuple of:
        - List of candidate vehicles
        - SQL query string (last executed)
        - Relaxation state dict with:
            - all_criteria_met: True if no relaxation was needed
            - met_filters: List of filters that were satisfied
            - relaxed_filters: List of filters that were removed to find results
            - relaxed_inferred: List of inferred filters that were relaxed
            - relaxed_regular: List of regular filters that were relaxed
            - unmet_must_haves: List of must-have filters that had to be relaxed
            - original_values: Dict of original values for relaxed filters
    """
    # Extract filter categories
    must_have_filter_names = set(explicit_filters.get("must_have_filters", []))
    inferred_filter_names = set(explicit_filters.get("inferred_filters", []))
    avoid_vehicles = explicit_filters.get("avoid_vehicles")

    # Get all actual filter values (exclude metadata fields)
    metadata_fields = {"must_have_filters", "inferred_filters", "avoid_vehicles"}
    all_filters = {k: v for k, v in explicit_filters.items() if k not in metadata_fields}

    if not all_filters:
        logger.warning("No filters to relax - returning empty results")
        return [], None, {
            "all_criteria_met": True,
            "met_filters": [],
            "relaxed_filters": [],
            "relaxed_inferred": [],
            "relaxed_regular": [],
            "unmet_must_haves": [],
            "original_values": {}
        }

    present_filters = set(all_filters.keys())

    # Build priority mapping with 3-tier hierarchy:
    # Tier 0: Inferred filters (priority 0-17) - relaxed FIRST
    # Tier 1: Regular filters (priority 18-35) - relaxed SECOND
    # Tier 2: Must-have filters (priority 36-53) - relaxed LAST
    TIER_SIZE = len(FILTER_RELAXATION_ORDER)

    filter_priorities = {}
    for filter_name in present_filters:
        # Get base priority from FILTER_RELAXATION_ORDER
        if filter_name in FILTER_RELAXATION_ORDER:
            base_priority = FILTER_RELAXATION_ORDER.index(filter_name)
        else:
            # Unranked filters get priority -1 (relaxed first within tier)
            base_priority = -1

        # Determine tier and calculate final priority
        if filter_name in inferred_filter_names:
            # Tier 0: Inferred filters (relaxed FIRST)
            tier_boost = 0
            tier_name = "inferred"
        elif filter_name in must_have_filter_names:
            # Tier 2: Must-have filters (relaxed LAST)
            tier_boost = 2 * TIER_SIZE
            tier_name = "must-have"
        else:
            # Tier 1: Regular filters (relaxed SECOND)
            tier_boost = 1 * TIER_SIZE
            tier_name = "regular"

        filter_priorities[filter_name] = base_priority + tier_boost

    # Sort filters by priority (ascending - lower priority relaxed first)
    ranked_filters = sorted(present_filters, key=lambda f: filter_priorities[f])

    logger.info("=" * 60)
    logger.info("PROGRESSIVE FILTER RELAXATION (3-Tier Hierarchy)")
    logger.info("=" * 60)
    logger.info(f"Starting filters: {list(all_filters.keys())}")
    logger.info(f"Inferred filters (Tier 0 - relaxed FIRST): {list(inferred_filter_names & present_filters)}")
    logger.info(f"Regular filters (Tier 1): {list(present_filters - inferred_filter_names - must_have_filter_names)}")
    logger.info(f"Must-have filters (Tier 2 - relaxed LAST): {list(must_have_filter_names & present_filters)}")
    logger.info(f"Relaxation order: {ranked_filters}")

    # Track relaxation state
    current_filters = all_filters.copy()
    relaxed_filters_list = []  # Track which filters were relaxed, in order
    original_values = {}  # Store original values of relaxed filters
    candidates = []
    sql_query = None

    # Try with all filters first
    iteration = 0
    while True:
        iteration += 1

        # Add avoid_vehicles back if present (never relax this)
        query_filters = current_filters.copy()
        if avoid_vehicles:
            query_filters["avoid_vehicles"] = avoid_vehicles

        logger.info(f"\nIteration {iteration}: Testing with {len(current_filters)} filters: {list(current_filters.keys())}")

        candidates = store.search_listings(
            query_filters,
            limit=None,
            order_by=None,
            order_dir="ASC",
            user_latitude=user_latitude,
            user_longitude=user_longitude
        )

        sql_query = store.last_sql_query

        logger.info(f"  → {len(candidates)} results")

        # Key change: Stop as soon as we find ANY results
        if len(candidates) > 0:
            logger.info(f"✓ Found {len(candidates)} vehicles matching current criteria")
            break

        # Check if we've run out of filters to relax
        if not current_filters:
            logger.info(f"✗ No more filters to relax. No vehicles found.")
            break

        # Find least important filter still present
        least_important = None
        for filter_name in ranked_filters:
            if filter_name in current_filters:
                least_important = filter_name
                break

        if least_important is None:
            # No more filters to relax
            logger.info(f"✗ No more relaxable filters. No vehicles found.")
            break

        # Store the original value before removing
        original_values[least_important] = all_filters[least_important]
        relaxed_filters_list.append(least_important)

        # Remove the least important filter
        logger.info(f"  Relaxing filter: '{least_important}' (was: {all_filters[least_important]})")
        del current_filters[least_important]

    # Calculate relaxation state
    met_filters = list(current_filters.keys())
    all_criteria_met = len(relaxed_filters_list) == 0

    # Categorize relaxed filters by tier
    relaxed_inferred = [f for f in relaxed_filters_list if f in inferred_filter_names]
    relaxed_regular = [f for f in relaxed_filters_list
                       if f not in inferred_filter_names and f not in must_have_filter_names]
    unmet_must_haves = [f for f in relaxed_filters_list if f in must_have_filter_names]

    logger.info("=" * 60)
    logger.info(f"Final result: {len(candidates)} vehicles")
    logger.info(f"All criteria met: {all_criteria_met}")
    logger.info(f"Met filters: {met_filters}")
    logger.info(f"Relaxed filters (total): {relaxed_filters_list}")
    if relaxed_inferred:
        logger.info(f"  ↳ Relaxed inferred (Tier 0): {relaxed_inferred}")
    if relaxed_regular:
        logger.info(f"  ↳ Relaxed regular (Tier 1): {relaxed_regular}")
    if unmet_must_haves:
        logger.warning(f"  ↳ Relaxed must-have (Tier 2): {unmet_must_haves}")
    logger.info("=" * 60)

    # Build relaxation state
    relaxation_state = {
        "all_criteria_met": all_criteria_met,
        "met_filters": met_filters,
        "relaxed_filters": relaxed_filters_list,
        "relaxed_inferred": relaxed_inferred,
        "relaxed_regular": relaxed_regular,
        "unmet_must_haves": unmet_must_haves,
        "original_values": original_values
    }

    return candidates, sql_query, relaxation_state


def recommend_method1(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    top_k: Optional[int] = None,
    lambda_param: Optional[float] = None,
    cluster_size: Optional[int] = None,
    vector_limit: Optional[int] = None,
    db_path: Optional[Path] = None,
    require_photos: bool = True,
) -> Tuple[List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """
    Method 1: SQL + Dense Vector Ranking + Clustered MMR Diversification.

    Flow:
    1. Progressive filter relaxation - SQL query until ANY results found
    2. Rank all candidates by dense embedding similarity
    3. Apply clustered MMR to select diverse clusters of similar vehicles

    Key behavior:
    - If ANY vehicles match all user criteria, return them (even if just 1)
    - Only relax filters when 0 results found
    - No vector similarity backfill - results always match SQL filters
    - Tracks which filters were relaxed for user transparency

    Args:
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (priorities, lifestyle, etc.)
        user_latitude: User's latitude for distance calculation
        user_longitude: User's longitude for distance calculation
        top_k: Number of vehicles to return (default 20)
        lambda_param: MMR diversity parameter within clusters (0.6-0.8 recommended)
        cluster_size: Number of similar vehicles per cluster (default 3)
        db_path: Optional path to vehicle database
        require_photos: Whether to require photos

    Returns:
        Tuple of:
        - List of top_k vehicles organized in clusters
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
        explicit_filters['year'] = '2015-2025'

    # Step 1: Progressive Filter Relaxation
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

    # Note: Dense backfill has been removed. We now rely solely on SQL filtering
    # with progressive relaxation. Even if only 1 vehicle matches all criteria,
    # we use it rather than diluting results with semantically-similar but
    # filter-violating vehicles.

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
        return [], sql_query, relaxation_state

    logger.info(f"Step 2: Ranked {len(ranked)} vehicles")
    top_score = ranked[0].get('_dense_score', 0.0)
    logger.info(f"  Top vehicle score: {top_score:.3f}")

    # Check if dense ranking actually succeeded (has real scores)
    # If all scores are 0, ranking likely failed (e.g., faiss not installed)
    ranking_succeeded = any(v.get('_dense_score', 0.0) > 0 for v in ranked)

    # Step 2.1: Apply similarity threshold filter (only if ranking succeeded)
    min_similarity = method1_config.get('min_similarity', 0.4)
    if min_similarity > 0 and ranking_succeeded:
        pre_filter_count = len(ranked)
        ranked = [v for v in ranked if v.get('_dense_score', 0.0) >= min_similarity]
        filtered_count = pre_filter_count - len(ranked)
        logger.info(f"Step 2.1: Similarity threshold filter (>= {min_similarity})")
        logger.info(f"  Filtered out {filtered_count} vehicles below threshold")
        logger.info(f"  Remaining: {len(ranked)} vehicles")

        if not ranked:
            logger.warning(f"No vehicles met the similarity threshold of {min_similarity}")
            return [], sql_query, relaxation_state
    elif not ranking_succeeded:
        logger.warning("Step 2.1: Skipping similarity threshold (dense ranking failed/unavailable)")
        logger.info(f"  Proceeding with {len(ranked)} unranked vehicles")

    # Step 2.5: BM25 sparse ranking (optional)
    use_bm25 = method1_config.get('use_bm25', False)
    bm25_beta = method1_config.get('bm25_beta', 0.3)

    if use_bm25:
        logger.info(f"Step 2.5: Computing BM25 scores (beta={bm25_beta})...")
        try:
            from idss_agent.processing.bm25_ranker import build_bm25_query, compute_bm25_scores, combine_scores

            # Build BM25 query from filters
            bm25_query = build_bm25_query(explicit_filters, implicit_preferences)
            logger.info(f"  BM25 query: {bm25_query[:100]}{'...' if len(bm25_query) > 100 else ''}")

            # Compute BM25 scores
            bm25_scores = compute_bm25_scores(ranked, bm25_query)

            # Combine dense + BM25 scores
            ranked = combine_scores(ranked, bm25_scores, beta=bm25_beta)

            # Re-sort by combined score
            ranked = sorted(ranked, key=lambda v: v.get("_combined_score", 0.0), reverse=True)

            logger.info(f"Step 2.5: Combined scores computed (top: {ranked[0].get('_combined_score', 0.0):.3f})")

            # Use combined scores for MMR
            score_key = "_combined_score"

        except Exception as e:
            logger.warning(f"BM25 scoring failed: {e}")
            logger.warning("Falling back to dense scores only")
            score_key = "_dense_score"
    else:
        logger.info("Step 2.5: BM25 disabled (use_bm25=False)")
        score_key = "_dense_score"

    # Step 3: Clustered MMR diversification
    logger.info("Step 3: Applying clustered MMR diversification...")
    scored = [(v.get(score_key, 0.0), v) for v in ranked]

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

    # Step 4: Final ranking
    final_ranking_method = method1_config.get('final_ranking_method', 'bm25')

    if final_ranking_method == 'year_value':
        # Option 1: Sort by year (desc) then mileage/price (desc - more miles per dollar is better)
        logger.info("Step 4: Final ranking by year → mileage/price ratio...")

        def get_year_value_key(vehicle):
            """Extract sorting key: (year_desc, mileage_per_price_desc)"""
            v = vehicle.get("vehicle", {})
            year = v.get("year") or vehicle.get("year")
            price = v.get("price") or vehicle.get("price")
            mileage = v.get("mileage") or vehicle.get("mileage")

            year_val = int(year) if year else 0
            price_val = float(price) if price is not None and price > 0 else 1.0
            mileage_val = float(mileage) if mileage is not None else 0.0

            # Mileage per dollar (higher = better value)
            mileage_per_price = mileage_val / price_val

            return (-year_val, -mileage_per_price)  # Both descending

        diverse_sorted = sorted(diverse, key=get_year_value_key)
        logger.info(f"Step 4: Ranked {len(diverse_sorted)} vehicles by year → mileage/price")

        if diverse_sorted:
            top = diverse_sorted[0]
            top_v = top.get("vehicle", {})
            top_r = top.get("retailListing", {})
            year = top_v.get("year")
            price = top_r.get("price", top_v.get("price"))
            mileage = top_r.get("miles", top_v.get("mileage"))
            value_ratio = mileage / price if price and price > 0 else 0
            logger.info(f"  Top vehicle: {year} {top_v.get('make')} {top_v.get('model')} - ${price}, {mileage} mi (value={value_ratio:.4f})")

    elif final_ranking_method == 'bm25':
        # Option 2: Re-rank by BM25 scores (original method)
        logger.info("Step 4: Final ranking by BM25 scores...")

        try:
            from idss_agent.processing.bm25_ranker import build_bm25_query, compute_bm25_scores

            # Build BM25 query from filters and preferences
            bm25_query = build_bm25_query(explicit_filters, implicit_preferences)
            logger.info(f"  BM25 query: {bm25_query[:100]}{'...' if len(bm25_query) > 100 else ''}")

            # Compute BM25 scores for the final 20 vehicles
            bm25_scores = compute_bm25_scores(diverse, bm25_query)

            # Add BM25 scores to vehicles
            for vehicle, score in zip(diverse, bm25_scores):
                vehicle["_final_bm25_score"] = score

            # Sort by BM25 score (highest first)
            diverse_sorted = sorted(diverse, key=lambda v: v.get("_final_bm25_score", 0.0), reverse=True)

            logger.info(f"Step 4: Ranked {len(diverse_sorted)} vehicles by BM25 scores")
            if diverse_sorted:
                top = diverse_sorted[0]
                top_v = top.get("vehicle", {})
                top_r = top.get("retailListing", {})
                top_score = top.get("_final_bm25_score", 0.0)
                price = top_r.get("price", top_v.get("price"))
                mileage = top_r.get("miles", top_v.get("mileage"))
                logger.info(f"  Top vehicle (BM25={top_score:.3f}): {top_v.get('year')} {top_v.get('make')} {top_v.get('model')} - ${price}, {mileage} mi")

        except Exception as e:
            logger.warning(f"BM25 final ranking failed: {e}")
            logger.info("Falling back to MMR order (no reranking)")
            diverse_sorted = diverse

    else:
        # Option 3: Keep original MMR order (no reranking)
        logger.info("Step 4: Keeping original MMR order (no final reranking)")
        diverse_sorted = diverse

    logger.info("=" * 60)
    logger.info(f"METHOD 1 COMPLETE: {len(diverse_sorted)} vehicles returned")
    logger.info("=" * 60)

    return diverse_sorted, sql_query, relaxation_state


__all__ = ["recommend_method1"]
