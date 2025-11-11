"""
Method 1: RapidAPI search + vector similarity + MMR diversification.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from idss_agent.processing import recommendation as base_recommendation
from idss_agent.processing.diversification import diversify_with_mmr
from idss_agent.processing.vector_ranker import rank_products_by_similarity
from idss_agent.tools.electronics_api import search_products
from idss_agent.utils.config import get_config
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.method1")


def recommend_method1(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    top_k: Optional[int] = None,
    lambda_param: float = 0.7,
    db_path: Optional[Path] = None,
    exploratory: bool = True,
) -> List[Dict[str, Any]]:
    """
    Method 1: Single RapidAPI search with optional exploratory variant, followed by vector
    re-ranking and MMR diversification.

    Args:
        explicit_filters: User's explicit filters (e.g., product, brand, price).
        implicit_preferences: User's implicit preferences (e.g., priorities, brand affinity).
        top_k: Desired number of products (defaults to config limit).
        lambda_param: Diversity trade-off parameter for MMR (0.6-0.8 recommended).
        db_path: Optional sqlite path for embedding persistence.
        exploratory: If True, run an additional exploratory search with relaxed filters.

    Returns:
        List of top_k diverse and relevant products.
    """
    config = get_config()
    if top_k is None:
        top_k = min(
            20,
            config.limits.get("top_products_to_show", 20),
            config.limits.get("max_recommended_items", 20),
        )

    logger.info("=" * 60)
    logger.info("METHOD 1: RapidAPI search + vector ranking + MMR diversification")
    logger.info("=" * 60)
    logger.info("Explicit filters: %s", explicit_filters)
    logger.info("Implicit preferences: %s", implicit_preferences)
    logger.info("Target products: %d (lambda=%.2f)", top_k, lambda_param)

    primary_payload = base_recommendation._build_search_payload(
        explicit_filters, implicit_preferences
    )
    primary_candidates = _fetch_products(primary_payload, label="Primary search")

    exploratory_candidates: List[Dict[str, Any]] = []
    if exploratory:
        relaxed_filters = _build_relaxed_filters(explicit_filters)
        if relaxed_filters != explicit_filters:
            relaxed_payload = base_recommendation._build_search_payload(
                relaxed_filters, implicit_preferences
            )
            exploratory_candidates = _fetch_products(
                relaxed_payload, label="Exploratory search"
            )

    candidates = primary_candidates + exploratory_candidates
    if not candidates:
        logger.warning("Method 1: No candidates returned from RapidAPI search")
        return []

    deduped_candidates = base_recommendation._deduplicate_products(candidates)
    logger.info("Deduplicated to %d unique products", len(deduped_candidates))

    ranked_products = rank_products_by_similarity(
        deduped_candidates,
        explicit_filters,
        implicit_preferences,
        db_path=db_path,
    )

    if not ranked_products:
        logger.warning("Method 1: Vector ranking produced no results, returning candidates")
        return deduped_candidates[:top_k]

    scored_products = [
        (product.get("_vector_score", 0.0), product) for product in ranked_products
    ]

    diversified_products = diversify_with_mmr(
        scored_products,
        top_k=top_k,
        lambda_param=lambda_param,
    )

    if not diversified_products:
        logger.warning("Method 1: Diversification returned empty list, falling back to ranking")
        return ranked_products[:top_k]

    logger.info("Method 1 complete: %d products selected", len(diversified_products))
    logger.info("=" * 60)
    return diversified_products


def _fetch_products(payload: Dict[str, Any], label: str) -> List[Dict[str, Any]]:
    try:
        response_text = search_products.invoke(payload)
    except Exception as exc:  # pragma: no cover - network call wrapper
        logger.error("RapidAPI search failed for %s: %s", label, exc)
        return []

    raw_products = base_recommendation._parse_product_list(response_text)
    normalized: List[Dict[str, Any]] = []

    for raw_product in raw_products:
        normalized_product = base_recommendation._normalize_product(raw_product)
        if normalized_product:
            normalized.append(normalized_product)

    logger.info("%s: retrieved %d products", label, len(normalized))
    return normalized


def _build_relaxed_filters(explicit_filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Relax restrictive filters (brand/title keywords) to surface diverse alternatives.
    """
    relaxed = explicit_filters.copy()

    for key in ("brand", "product", "product_name", "keywords", "search_query"):
        relaxed.pop(key, None)

    if not relaxed.get("category"):
        relaxed["category"] = explicit_filters.get("category") or "electronics"

    return relaxed


__all__ = ["recommend_method1"]

