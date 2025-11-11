"""
Diversification utilities for electronics product recommendations.

Implements Maximal Marginal Relevance (MMR) for diverse top-k selection.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from idss_agent.utils.logger import get_logger

logger = get_logger("processing.diversification")


def compute_product_similarity(product_a: Dict[str, Any], product_b: Dict[str, Any]) -> float:
    """
    Compute similarity between two products (0.0 = diverse, 1.0 = identical).

    Similarity is based on brand, category, and shared title tokens.
    """
    info_a = product_a.get("product") or {}
    info_b = product_b.get("product") or {}

    identifier_a = (
        product_a.get("id")
        or info_a.get("identifier")
        or info_a.get("id")
        or product_a.get("link")
        or ""
    )
    identifier_b = (
        product_b.get("id")
        or info_b.get("identifier")
        or info_b.get("id")
        or product_b.get("link")
        or ""
    )

    if identifier_a and identifier_b and identifier_a == identifier_b:
        return 0.95

    brand_a = (product_a.get("brand") or info_a.get("brand") or "").lower()
    brand_b = (product_b.get("brand") or info_b.get("brand") or "").lower()

    category_a = _normalize_category(info_a.get("category"))
    category_b = _normalize_category(info_b.get("category"))

    name_tokens_a = _tokenize_title(product_a)
    name_tokens_b = _tokenize_title(product_b)
    shared_tokens = name_tokens_a.intersection(name_tokens_b)

    if brand_a and brand_a == brand_b and shared_tokens:
        return 0.85

    if brand_a and brand_a == brand_b:
        return 0.65

    if category_a and category_b and category_a == category_b:
        if shared_tokens:
            return 0.5
        return 0.35

    if shared_tokens:
        return 0.25

    return 0.0


def diversify_with_mmr(
    scored_products: List[Tuple[float, Dict[str, Any]]],
    top_k: int = 20,
    lambda_param: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Apply Maximal Marginal Relevance (MMR) to select diverse top-k products.

    Args:
        scored_products: List of (relevance_score, product_dict) tuples sorted by relevance.
        top_k: Number of products to select.
        lambda_param: Trade-off between relevance and diversity.

    Returns:
        List of top_k products selected via MMR.
    """
    if len(scored_products) <= top_k:
        return [product for _, product in scored_products]

    selected: List[Tuple[float, Dict[str, Any]]] = [scored_products[0]]
    remaining = list(scored_products[1:])

    while len(selected) < top_k and remaining:
        best_score = -float("inf")
        best_idx = 0

        for idx, (relevance, candidate) in enumerate(remaining):
            max_similarity = max(
                compute_product_similarity(candidate, chosen_product)
                for _, chosen_product in selected
            )
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_similarity

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        selected.append(remaining.pop(best_idx))

    logger.info(
        "MMR diversification selected %d of %d candidates (lambda=%.2f)",
        len(selected),
        len(scored_products),
        lambda_param,
    )

    return [product for _, product in selected]


def _normalize_category(category: Any) -> str:
    if not category:
        return ""

    if isinstance(category, (list, tuple, set)):
        category = next(iter(category), "")

    category_str = str(category).lower()
    if ">" in category_str:
        category_str = category_str.split(">")[0].strip()
    return category_str


def _tokenize_title(product: Dict[str, Any]) -> set[str]:
    title = (
        product.get("title")
        or (product.get("product") or {}).get("title")
        or ""
    )
    tokens = {
        token
        for token in title.lower().replace("-", " ").split()
        if token and len(token) > 2
    }
    return tokens


__all__ = [
    "compute_product_similarity",
    "diversify_with_mmr",
]

