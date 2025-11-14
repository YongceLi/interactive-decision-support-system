"""
BM25 Sparse Ranker: Ranks vehicles using keyword-based BM25 algorithm.

Complements dense embeddings by boosting exact keyword matches.
Uses pre-built BM25 index for fast inference.
"""
import pickle
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from idss_agent.utils.logger import get_logger
from idss_agent.utils.config import get_config

logger = get_logger("processing.bm25_ranker")

# Module-level cache for BM25 index to avoid reloading
_BM25_CACHE: Dict[str, Tuple[Any, List[str]]] = {}


def get_bm25_index(index_dir: Optional[Path] = None) -> Tuple[Any, List[str]]:
    """
    Get cached BM25 index and VIN list.

    The index is pre-built by scripts/build_bm25_index.py.

    Args:
        index_dir: Directory containing BM25 index files

    Returns:
        Tuple of (BM25Okapi index, list of VINs)
    """
    if index_dir is None:
        index_dir = Path('data/car_dataset_idss')

    index_path = index_dir / "bm25_index.pkl"
    vins_path = index_dir / "bm25_vins.pkl"

    cache_key = str(index_dir)

    if cache_key not in _BM25_CACHE:
        logger.info(f"Loading BM25 index from {index_path}")

        if not index_path.exists():
            raise FileNotFoundError(
                f"BM25 index not found at {index_path}. "
                f"Run scripts/build_bm25_index.py to create it."
            )

        with open(index_path, "rb") as f:
            bm25_index = pickle.load(f)

        with open(vins_path, "rb") as f:
            vin_list = pickle.load(f)

        logger.info(f"✓ Loaded BM25 index with {len(vin_list)} vehicles")

        _BM25_CACHE[cache_key] = (bm25_index, vin_list)
    else:
        logger.debug(f"Using cached BM25 index (cache hit for {cache_key})")

    return _BM25_CACHE[cache_key]


def build_bm25_query(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> str:
    """
    Build BM25 query string from user preferences.

    Extracts keywords from filters to create a query that boosts
    exact matches in vehicle descriptions.

    Args:
        explicit_filters: User's explicit filters
        implicit_preferences: User's implicit preferences

    Returns:
        Query string with keywords for BM25 search
    """
    keywords = []

    # Core vehicle identity (high priority)
    if explicit_filters.get("make"):
        keywords.extend(explicit_filters["make"].split(","))
    if explicit_filters.get("model"):
        keywords.extend(explicit_filters["model"].split(","))
    if explicit_filters.get("trim"):
        keywords.append(explicit_filters["trim"])

    # Body style
    if explicit_filters.get("body_style"):
        keywords.append(explicit_filters["body_style"])

    # Powertrain
    if explicit_filters.get("engine"):
        keywords.append(explicit_filters["engine"])
    if explicit_filters.get("fuel_type"):
        keywords.append(explicit_filters["fuel_type"])
    if explicit_filters.get("drivetrain"):
        keywords.append(explicit_filters["drivetrain"])
    if explicit_filters.get("transmission"):
        keywords.append(explicit_filters["transmission"])

    # Colors
    if explicit_filters.get("exterior_color"):
        keywords.extend(explicit_filters["exterior_color"].split(","))
    if explicit_filters.get("interior_color"):
        keywords.extend(explicit_filters["interior_color"].split(","))

    # Condition keywords
    if explicit_filters.get("is_cpo"):
        keywords.extend(["certified", "pre-owned", "cpo"])
    if explicit_filters.get("is_used") is False:
        keywords.append("new")
    elif explicit_filters.get("is_used") is True:
        keywords.append("used")

    # Implicit preferences (top priorities only)
    priorities = implicit_preferences.get("priorities", []) or []
    keywords.extend(priorities[:3])  # Top 3 priorities

    # Join and normalize
    query = " ".join(str(k).lower() for k in keywords if k)

    return query


def compute_bm25_scores(
    vehicles: List[Dict[str, Any]],
    query: str,
    index_dir: Optional[Path] = None
) -> List[float]:
    """
    Compute BM25 scores for a list of vehicles.

    Args:
        vehicles: List of vehicles to score
        query: BM25 query string (space-separated keywords)
        index_dir: Optional directory containing BM25 index

    Returns:
        List of BM25 scores (same order as vehicles)
    """
    if not vehicles:
        return []

    logger.info(f"Computing BM25 scores for {len(vehicles)} vehicles")

    # Load pre-built BM25 index
    try:
        bm25_index, vin_list = get_bm25_index(index_dir)
    except FileNotFoundError as e:
        logger.warning(f"BM25 index not found: {e}")
        logger.warning("Returning zero scores - run scripts/build_bm25_index.py")
        return [0.0] * len(vehicles)

    if not query.strip():
        logger.warning("Empty BM25 query - no keywords extracted")
        return [0.0] * len(vehicles)

    # Create VIN to index mapping
    vin_to_idx = {vin: idx for idx, vin in enumerate(vin_list)}

    # Get BM25 scores for all documents
    query_tokens = query.lower().split()
    all_scores = bm25_index.get_scores(query_tokens)

    # Map scores to vehicles by VIN
    scores = []
    for vehicle in vehicles:
        vin = vehicle.get("vehicle", {}).get("vin") or vehicle.get("vin")
        if vin and vin in vin_to_idx:
            idx = vin_to_idx[vin]
            scores.append(float(all_scores[idx]))
        else:
            scores.append(0.0)

    if scores:
        max_score = max(scores) if max(scores) > 0 else 1.0
        logger.info(f"✓ BM25 scores computed (max: {max_score:.3f})")

    return scores


def combine_scores(
    vehicles: List[Dict[str, Any]],
    bm25_scores: List[float],
    beta: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Combine dense and BM25 scores.

    Formula: final_score = (1 - beta) * dense_score + beta * bm25_score_normalized

    Args:
        vehicles: List of vehicles with _dense_score field
        bm25_scores: List of BM25 scores
        beta: Weight for BM25 (0-1). Dense weight = 1 - beta

    Returns:
        List of vehicles with _bm25_score and _combined_score fields
    """
    # Normalize BM25 scores to [0, 1]
    max_bm25 = max(bm25_scores) if bm25_scores and max(bm25_scores) > 0 else 1.0
    bm25_normalized = [s / max_bm25 for s in bm25_scores]

    # Combine scores
    alpha = 1.0 - beta  # Dense weight

    for vehicle, bm25_score in zip(vehicles, bm25_normalized):
        dense_score = vehicle.get("_dense_score", 0.0)
        vehicle["_bm25_score"] = bm25_score
        vehicle["_combined_score"] = alpha * dense_score + beta * bm25_score

    return vehicles


__all__ = [
    "get_bm25_index",
    "build_bm25_query",
    "compute_bm25_scores",
    "combine_scores",
]
