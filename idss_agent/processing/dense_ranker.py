"""
Dense Embedding Ranker: Ranks vehicles using semantic similarity.

Uses pre-trained sentence transformers to understand semantic meaning
and natural language queries.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional

from idss_agent.processing.dense_embedding_store import DenseEmbeddingStore
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.dense_ranker")

# Module-level cache for DenseEmbeddingStore to avoid reloading model/index
_DENSE_STORE_CACHE: Dict[str, DenseEmbeddingStore] = {}


def get_dense_embedding_store(
    index_dir: Optional[Path] = None,
    model_name: str = "all-mpnet-base-v2",
    version: str = "v1",
    index_type: str = "Flat"
) -> DenseEmbeddingStore:
    """
    Get cached DenseEmbeddingStore instance to avoid reloading model/index.

    This caches the store by configuration so the sentence transformer model
    and FAISS index are only loaded once per configuration.

    Args:
        index_dir: Directory containing FAISS index files
        model_name: Embedding model name
        version: Embedding version
        index_type: Index type (Flat or IVF)

    Returns:
        Cached DenseEmbeddingStore instance
    """
    # Create cache key from configuration
    cache_key = f"{index_dir}:{model_name}:{version}:{index_type}"

    if cache_key not in _DENSE_STORE_CACHE:
        logger.info(f"Creating new DenseEmbeddingStore (cache miss for {cache_key})")
        _DENSE_STORE_CACHE[cache_key] = DenseEmbeddingStore(
            index_dir=index_dir,
            model_name=model_name,
            version=version,
            index_type=index_type
        )
    else:
        logger.debug(f"Using cached DenseEmbeddingStore (cache hit for {cache_key})")

    return _DENSE_STORE_CACHE[cache_key]


def rank_vehicles_by_dense_similarity(
    vehicles: List[Dict[str, Any]],
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    db_path: Optional[Path] = None,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Rank vehicles using dense embedding similarity.

    Args:
        vehicles: List of candidate vehicles to rank
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (priorities, lifestyle, etc.)
        db_path: Path to vehicle database (for loading embeddings)
        top_k: Optional limit on number of results

    Returns:
        List of vehicles ranked by semantic similarity
    """
    if not vehicles:
        return vehicles

    logger.info(f"Ranking {len(vehicles)} vehicles using dense embeddings")

    # Get cached dense embedding store (avoids reloading model for batch processing)
    try:
        store = get_dense_embedding_store()
    except Exception as e:
        logger.error(f"Failed to load dense embedding store: {e}")
        logger.warning("Returning vehicles unranked")
        return vehicles

    # Build natural language query from user preferences
    query_text = build_query_text(explicit_filters, implicit_preferences)
    logger.info(f"Query: {query_text[:150]}{'...' if len(query_text) > 150 else ''}")

    # Get VINs from vehicles
    vin_to_vehicle = {}
    for vehicle in vehicles:
        vin = vehicle.get("vehicle", {}).get("vin") or vehicle.get("vin")
        if vin:
            vin_to_vehicle[vin] = vehicle

    if not vin_to_vehicle:
        logger.warning("No VINs found in vehicles")
        return vehicles

    # Search using dense embeddings
    try:
        vins, scores = store.search_by_vins(
            list(vin_to_vehicle.keys()),
            query_text,
            k=None  # Rank all candidates
        )
    except Exception as e:
        logger.error(f"Dense search failed: {e}")
        return vehicles

    # Build ranked list with scores
    ranked = []
    for vin, score in zip(vins, scores):
        vehicle = vin_to_vehicle[vin]
        vehicle["_vector_score"] = score
        vehicle["_dense_score"] = score
        ranked.append(vehicle)

    # Apply top-k if specified
    if top_k is not None:
        ranked = ranked[:top_k]

    if ranked:
        top_score = ranked[0].get("_dense_score", 0.0)
        logger.info(f"✓ Ranked {len(ranked)} vehicles (top score: {top_score:.3f})")

    return ranked


def build_query_text(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> str:
    """
    Build a natural language query text from user preferences.
    This will be encoded into a dense embedding for semantic matching.

    Args:
        explicit_filters: Explicit user filters
        implicit_preferences: Implicit user preferences

    Returns:
        Natural language query string
    """
    parts = []

    # Core vehicle identity
    if explicit_filters.get("make"):
        parts.append(str(explicit_filters["make"]))
    if explicit_filters.get("model"):
        parts.append(str(explicit_filters["model"]))
    if explicit_filters.get("trim"):
        parts.append(str(explicit_filters["trim"]))

    # Body style
    if explicit_filters.get("body_style"):
        parts.append(f"{explicit_filters['body_style']} body style")

    # Powertrain
    if explicit_filters.get("engine"):
        parts.append(f"{explicit_filters['engine']} engine")
    if explicit_filters.get("fuel_type"):
        parts.append(f"{explicit_filters['fuel_type']} fuel")
    if explicit_filters.get("drivetrain"):
        parts.append(f"{explicit_filters['drivetrain']} drivetrain")
    if explicit_filters.get("transmission"):
        parts.append(f"{explicit_filters['transmission']} transmission")

    # Colors
    if explicit_filters.get("exterior_color"):
        parts.append(f"{explicit_filters['exterior_color']} exterior")
    if explicit_filters.get("interior_color"):
        parts.append(f"{explicit_filters['interior_color']} interior")

    # Year range
    if explicit_filters.get("year"):
        year_str = str(explicit_filters["year"])
        if "-" in year_str:
            parts.append(f"year range {year_str}")
        else:
            parts.append(f"{year_str} year")

    # Price (semantic, not exact)
    if explicit_filters.get("price"):
        price_str = str(explicit_filters["price"])
        if "-" in price_str:
            parts.append(f"price range ${price_str}")
        else:
            parts.append(f"around ${price_str}")

    # Mileage
    if explicit_filters.get("mileage"):
        mileage_str = str(explicit_filters["mileage"])
        if "-" in mileage_str:
            parts.append(f"{mileage_str} miles")
        else:
            parts.append(f"around {mileage_str} miles")

    # Condition
    if explicit_filters.get("is_used") is False:
        parts.append("new vehicle")
    elif explicit_filters.get("is_used") is True:
        parts.append("used vehicle")

    if explicit_filters.get("is_cpo"):
        parts.append("certified pre-owned")

    # Implicit preferences (this is where dense embeddings shine!)
    priorities = implicit_preferences.get("priorities", []) or []
    for priority in priorities:
        parts.append(str(priority))

    if implicit_preferences.get("usage_patterns"):
        parts.append(str(implicit_preferences["usage_patterns"]))

    if implicit_preferences.get("lifestyle"):
        parts.append(str(implicit_preferences["lifestyle"]))

    concerns = implicit_preferences.get("concerns", []) or []
    for concern in concerns:
        parts.append(str(concern))

    if implicit_preferences.get("brand_affinity"):
        parts.append(str(implicit_preferences["brand_affinity"]))

    if implicit_preferences.get("notes"):
        parts.append(str(implicit_preferences["notes"]))

    # Join into natural language query
    query_text = ". ".join(parts) + "." if parts else "vehicle"
    return query_text


def preload_dense_embedding_store() -> None:
    """
    Preload FAISS index and sentence transformer model at application startup.

    This avoids the ~12-15 second delay on the first user request.
    Call this during application initialization.
    """
    try:
        logger.info("Preloading dense embedding store...")
        store = get_dense_embedding_store()

        # Force model loading by encoding a dummy query
        _ = store.encode_text("preload")

        logger.info("✓ Dense embedding store preloaded successfully")
    except Exception as e:
        logger.warning(f"Failed to preload dense embedding store: {e}")
        logger.warning("First request will be slower as models load on-demand")


__all__ = [
    "rank_vehicles_by_dense_similarity",
    "build_query_text",
    "get_dense_embedding_store",
    "preload_dense_embedding_store",
]
