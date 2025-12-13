"""
Method 3 Ranker: Coverage-Risk Optimization for vehicle ranking.

Implements Method 3 using:
- PhraseStore: Pre-computed individual phrase embeddings
- PreferenceAlignment: Pos/Neg alignment scoring with two modes:
  - "max": Original implementation (max over phrases, max over vehicles)
  - "sum": Proposed noisy-or coverage with submodular guarantees
- Greedy selection: Maximizes coverage while minimizing risk
- Soft constraints: Relaxed hard filters become soft bonus terms

This is a drop-in replacement for dense_ranker.rank_vehicles_by_dense_similarity().
"""
from pathlib import Path
from typing import Dict, Any, List, Optional

from idss_agent.processing.phrase_store import PhraseStore
from idss_agent.processing.preference_alignment import rank_vehicles_by_alignment
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.method3_ranker")

# Module-level cache for PhraseStore to avoid reloading model/embeddings
_PHRASE_STORE_CACHE: Optional[PhraseStore] = None


def get_phrase_store(
    reviews_db_path: Optional[Path] = None,
    vehicles_db_path: Optional[Path] = None,
    model_name: str = "all-mpnet-base-v2"
) -> PhraseStore:
    """
    Get cached PhraseStore instance to avoid reloading model/embeddings.

    This caches the phrase store globally so the sentence transformer model
    and phrase embeddings are only loaded once.

    Args:
        reviews_db_path: Path to Tavily reviews database
        vehicles_db_path: Path to unified vehicle listings database
        model_name: Embedding model name

    Returns:
        Cached PhraseStore instance
    """
    global _PHRASE_STORE_CACHE

    if _PHRASE_STORE_CACHE is None:
        logger.info("Creating new PhraseStore (cache miss)")
        _PHRASE_STORE_CACHE = PhraseStore(
            reviews_db_path=reviews_db_path,
            vehicles_db_path=vehicles_db_path,
            model_name=model_name,
            preload=True
        )
    else:
        logger.debug("Using cached PhraseStore (cache hit)")

    return _PHRASE_STORE_CACHE


def rank_vehicles_by_method3(
    vehicles: List[Dict[str, Any]],
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    db_path: Optional[Path] = None,
    top_k: int = 20,
    lambda_risk: float = 0.5,
    mode: str = "max",
    relaxation_state: Optional[Dict[str, Any]] = None,
    min_similarity: float = 0.5,
    tau: float = 0.5,
    alpha: float = 1.0,
    mu: Optional[float] = None,
    rho: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Rank vehicles using Method 3: Coverage-Risk Optimization.

    This is a drop-in replacement for rank_vehicles_by_dense_similarity() that uses
    phrase-level semantic alignment and greedy selection for better diversity.

    Args:
        vehicles: List of candidate vehicles to rank
        explicit_filters: User's explicit filters (make, model, price, etc.)
        implicit_preferences: User's implicit preferences (liked_features, disliked_features)
        db_path: Path to vehicle database (unused, for compatibility)
        top_k: Number of vehicles to recommend (default 20)
        lambda_risk: Risk penalty weight (default 0.5)
        mode: Aggregation mode - "max" (original) or "sum" (noisy-or coverage)
        relaxation_state: Dict with relaxed filters info (for soft constraints)
        min_similarity: Minimum similarity threshold (max mode, default 0.5)
        tau: Similarity threshold φ(t) = max(0, t - τ) at phrase level (default 0.5)
        alpha: g function steepness for coverage mapping (sum mode, default 1.0)
        mu: Soft bonus weight (None = auto-calibrate based on scale matching)
        rho: Scale factor for μ calibration (default 1.0)

    Returns:
        List of top-k vehicles ranked by coverage-risk optimization
    """
    if not vehicles:
        return vehicles

    logger.info(f"Ranking {len(vehicles)} vehicles using Method 3: Coverage-Risk Optimization ({mode} mode)")

    # Get cached phrase store (avoids reloading model for batch processing)
    try:
        phrase_store = get_phrase_store()
    except Exception as e:
        logger.error(f"Failed to load phrase store: {e}")
        logger.warning("Returning vehicles unranked")
        return vehicles[:top_k]

    # Check if we have implicit preferences
    if not implicit_preferences.get("liked_features") and not implicit_preferences.get("disliked_features"):
        logger.warning("No implicit preferences - returning vehicles in original order")
        return vehicles[:top_k]

    # Rank using coverage-risk optimization
    try:
        ranked_vehicles = rank_vehicles_by_alignment(
            vehicles=vehicles,
            phrase_store=phrase_store,
            implicit_preferences=implicit_preferences,
            k=top_k,
            lambda_risk=lambda_risk,
            mode=mode,
            min_similarity=min_similarity,
            tau=tau,
            alpha=alpha,
            relaxation_state=relaxation_state,
            explicit_filters=explicit_filters,
            mu=mu,
            rho=rho
        )

        logger.info(f"✓ Method 3 ranking complete ({mode} mode): returned {len(ranked_vehicles)} vehicles")
        return ranked_vehicles

    except Exception as e:
        logger.error(f"Method 3 ranking failed: {e}")
        logger.warning("Returning vehicles unranked")
        import traceback
        traceback.print_exc()
        return vehicles[:top_k]
