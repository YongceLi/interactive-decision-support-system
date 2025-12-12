"""
Dense Embedding Ranker: Ranks vehicles using semantic similarity.

Uses pre-trained sentence transformers to understand semantic meaning
and natural language queries.

Supports two embedding methods:
1. Concat: Embed entire query as single sentence (legacy)
2. Sum: Embed each feature separately, sum and normalize (recommended)
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
    embedding_method: str = "sum"
) -> List[Dict[str, Any]]:
    """
    Rank vehicles using dense embedding similarity.

    Args:
        vehicles: List of candidate vehicles to rank
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (priorities, lifestyle, etc.)
        db_path: Path to vehicle database (for loading embeddings)
        top_k: Optional limit on number of results
        embedding_method: "sum" (sum-of-features, default) or "concat" (legacy)

    Returns:
        List of vehicles ranked by semantic similarity
    """
    if not vehicles:
        return vehicles

    logger.info(f"Ranking {len(vehicles)} vehicles using dense embeddings (method: {embedding_method})")

    # Get cached dense embedding store (avoids reloading model for batch processing)
    try:
        store = get_dense_embedding_store()
    except Exception as e:
        logger.error(f"Failed to load dense embedding store: {e}")
        logger.warning("Returning vehicles unranked")
        return vehicles

    # Build query based on method
    if embedding_method == "sum":
        # Sum-of-features: Extract individual features
        query_features = extract_query_features(explicit_filters, implicit_preferences)
        logger.info(f"Query features ({len(query_features)}): {', '.join(query_features[:5])}{'...' if len(query_features) > 5 else ''}")
        query_input = query_features
    else:
        # Concat: Build single query text
        query_text = build_query_text(explicit_filters, implicit_preferences)
        logger.info(f"Query: {query_text[:150]}{'...' if len(query_text) > 150 else ''}")
        query_input = query_text

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
            query_input,
            k=None,  # Rank all candidates
            method=embedding_method
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


def extract_query_features(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> List[str]:
    """
    Extract individual query features for sum-of-features embedding.

    Extracts only fields that match vehicle embedding features:
    - make, model, trim
    - body_style
    - engine, fuel_type, drivetrain, transmission
    - doors, seats
    - is_used

    Plus implicit preferences as separate features.

    Args:
        explicit_filters: Explicit user filters
        implicit_preferences: Implicit user preferences

    Returns:
        List of individual feature strings
    """
    features = []

    # Vehicle Identity (make, model, trim)
    identity_parts = []
    if explicit_filters.get("make"):
        identity_parts.append(str(explicit_filters["make"]))
    if explicit_filters.get("model"):
        identity_parts.append(str(explicit_filters["model"]))
    if explicit_filters.get("trim"):
        identity_parts.append(str(explicit_filters["trim"]))
    if identity_parts:
        features.append(" ".join(identity_parts))

    # Body Style
    if explicit_filters.get("body_style"):
        features.append(f"{explicit_filters['body_style']} body style")

    # Engine
    if explicit_filters.get("engine"):
        features.append(f"{explicit_filters['engine']} engine")

    # Fuel Type
    if explicit_filters.get("fuel_type"):
        features.append(f"{explicit_filters['fuel_type']} fuel")

    # Drivetrain
    if explicit_filters.get("drivetrain"):
        features.append(f"{explicit_filters['drivetrain']} drivetrain")

    # Transmission
    if explicit_filters.get("transmission"):
        features.append(f"{explicit_filters['transmission']} transmission")

    # Doors
    if explicit_filters.get("doors"):
        features.append(f"{explicit_filters['doors']} doors")

    # Seats
    if explicit_filters.get("seats"):
        features.append(f"{explicit_filters['seats']} seats")

    # Condition (is_used)
    if explicit_filters.get("is_used") is False:
        features.append("new vehicle")
    elif explicit_filters.get("is_used") is True:
        features.append("used vehicle")

    # Implicit Preferences (each as separate feature)
    priorities = implicit_preferences.get("priorities", []) or []
    for priority in priorities:
        if priority:
            features.append(str(priority))

    if implicit_preferences.get("usage_patterns"):
        features.append(str(implicit_preferences["usage_patterns"]))

    if implicit_preferences.get("lifestyle"):
        features.append(str(implicit_preferences["lifestyle"]))

    concerns = implicit_preferences.get("concerns", []) or []
    for concern in concerns:
        if concern:
            features.append(str(concern))

    if implicit_preferences.get("brand_affinity"):
        features.append(f"Brand preference: {implicit_preferences['brand_affinity']}")

    if implicit_preferences.get("notes"):
        # Notes might contain multiple concepts, add as single feature
        features.append(str(implicit_preferences["notes"]))

    return features


def build_query_text(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> str:
    """
    Build a structured query text from user preferences.
    This will be encoded into a dense embedding for semantic matching.

    Args:
        explicit_filters: Explicit user filters
        implicit_preferences: Implicit user preferences

    Returns:
        Structured query string
    """
    parts = []

    # Vehicle Identity
    identity_parts = []
    if explicit_filters.get("make"):
        identity_parts.append(str(explicit_filters["make"]))
    if explicit_filters.get("model"):
        identity_parts.append(str(explicit_filters["model"]))
    if explicit_filters.get("trim"):
        identity_parts.append(str(explicit_filters["trim"]))
    if identity_parts:
        parts.append(f"Vehicle: {' '.join(identity_parts)}")

    # Body Style
    if explicit_filters.get("body_style"):
        parts.append(f"Body Style: {explicit_filters['body_style']}")

    # Powertrain
    powertrain_parts = []
    if explicit_filters.get("engine"):
        powertrain_parts.append(f"Engine: {explicit_filters['engine']}")
    if explicit_filters.get("fuel_type"):
        powertrain_parts.append(f"Fuel: {explicit_filters['fuel_type']}")
    if explicit_filters.get("drivetrain"):
        powertrain_parts.append(f"Drivetrain: {explicit_filters['drivetrain']}")
    if explicit_filters.get("transmission"):
        powertrain_parts.append(f"Transmission: {explicit_filters['transmission']}")
    if powertrain_parts:
        parts.extend(powertrain_parts)

    # Colors
    if explicit_filters.get("exterior_color"):
        parts.append(f"Exterior Color: {explicit_filters['exterior_color']}")
    if explicit_filters.get("interior_color"):
        parts.append(f"Interior Color: {explicit_filters['interior_color']}")

    # Year
    if explicit_filters.get("year"):
        year_str = str(explicit_filters["year"])
        if "-" in year_str:
            parts.append(f"Year Range: {year_str}")
        else:
            parts.append(f"Year: {year_str}")

    # Price
    if explicit_filters.get("price"):
        price_str = str(explicit_filters["price"])
        if "-" in price_str:
            parts.append(f"Price Range: ${price_str}")
        else:
            parts.append(f"Price: ${price_str}")

    # Mileage
    if explicit_filters.get("mileage"):
        mileage_str = str(explicit_filters["mileage"])
        if "-" in mileage_str:
            parts.append(f"Mileage: {mileage_str} miles")
        else:
            parts.append(f"Mileage: {mileage_str} miles")

    # Condition
    condition_parts = []
    if explicit_filters.get("is_used") is False:
        condition_parts.append("new")
    elif explicit_filters.get("is_used") is True:
        condition_parts.append("used")
    if explicit_filters.get("is_cpo"):
        condition_parts.append("certified pre-owned")
    if condition_parts:
        parts.append(f"Condition: {', '.join(condition_parts)}")

    # Implicit Preferences
    priorities = implicit_preferences.get("priorities", []) or []
    if priorities:
        parts.append(f"Priorities: {', '.join(str(p) for p in priorities)}")

    if implicit_preferences.get("usage_patterns"):
        parts.append(f"Usage: {implicit_preferences['usage_patterns']}")

    if implicit_preferences.get("lifestyle"):
        parts.append(f"Lifestyle: {implicit_preferences['lifestyle']}")

    concerns = implicit_preferences.get("concerns", []) or []
    if concerns:
        parts.append(f"Concerns: {', '.join(str(c) for c in concerns)}")

    if implicit_preferences.get("brand_affinity"):
        parts.append(f"Brand Preference: {implicit_preferences['brand_affinity']}")

    if implicit_preferences.get("budget_sensitivity"):
        parts.append(f"Budget: {implicit_preferences['budget_sensitivity']}")

    if implicit_preferences.get("notes"):
        parts.append(f"Notes: {implicit_preferences['notes']}")

    # Join into structured query
    query_text = ". ".join(parts) + "." if parts else "Vehicle"
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
    "extract_query_features",
    "build_query_text",
    "get_dense_embedding_store",
    "preload_dense_embedding_store",
]
