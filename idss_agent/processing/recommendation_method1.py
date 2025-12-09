"""
Method 1: Knowledge graph (for PC parts) or local database search + vector similarity + MMR diversification.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from idss_agent.processing import recommendation as base_recommendation
from idss_agent.processing.diversification import diversify_with_mmr
from idss_agent.processing.vector_ranker import rank_products_by_similarity
from idss_agent.tools.local_electronics_store import LocalElectronicsStore
from idss_agent.tools.kg_compatibility import get_compatibility_tool, is_pc_part
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
    Method 1: Single local database search with optional exploratory variant, followed by vector
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
    logger.info("METHOD 1: Local database search + vector ranking + MMR diversification")
    logger.info("=" * 60)
    logger.info("Explicit filters: %s", explicit_filters)
    logger.info("Implicit preferences: %s", implicit_preferences)
    logger.info("Target products: %d (lambda=%.2f)", top_k, lambda_param)

    primary_candidates = _fetch_products(explicit_filters, implicit_preferences, label="Primary search")

    exploratory_candidates: List[Dict[str, Any]] = []
    if exploratory:
        relaxed_filters = _build_relaxed_filters(explicit_filters)
        if relaxed_filters != explicit_filters:
            exploratory_candidates = _fetch_products(
                relaxed_filters, implicit_preferences, label="Exploratory search"
            )

    candidates = primary_candidates + exploratory_candidates
    if not candidates:
        logger.warning("Method 1: No candidates returned from local database search")
        return []

    # Filter and rank products for consumer/personal use (prioritize consumer over professional)
    consumer_ranked_candidates = base_recommendation._rank_products_for_consumer_use(candidates)
    logger.info("Filtered to %d consumer products (from %d total)", len(consumer_ranked_candidates), len(candidates))
    
    deduped_candidates = base_recommendation._deduplicate_products(consumer_ranked_candidates)
    logger.info("Deduplicated to %d unique products", len(deduped_candidates))

    ranked_products = rank_products_by_similarity(
        deduped_candidates,
        explicit_filters,
        implicit_preferences,
        db_path=db_path,
    )

    if not ranked_products:
        logger.warning("Method 1: Vector ranking produced no results, returning empty list")
        return []

    # Filter out items with zero similarity score
    ranked_products = [p for p in ranked_products if p.get("_vector_score", 0.0) > 0.0]
    
    if not ranked_products:
        logger.warning("Method 1: All products filtered out (zero similarity scores)")
        return []

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


def _fetch_products(
    filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    label: str
) -> List[Dict[str, Any]]:
    """Fetch products from knowledge graph (for PC parts) or local database."""
    try:
        # Build search query
        search_query = base_recommendation._build_search_query(filters, implicit_preferences)
        if search_query == "electronics":
            search_query = None  # Don't search for generic "electronics"
        
        # Extract parameters
        part_type = filters.get("category") or filters.get("part_type") or filters.get("type")
        if part_type:
            part_type = part_type.lower().strip()
        brand = filters.get("brand")
        
        # Try to extract brand from query if not explicitly set
        if not brand and search_query:
            query_parts = search_query.split()
            known_brands = ["ASUS", "Dell", "HP", "Lenovo", "Apple", "Samsung", "LG", "Sony",
                          "Microsoft", "Intel", "AMD", "NVIDIA", "Corsair", "EVGA",
                          "Gigabyte", "MSI", "ASRock"]
            for brand_name in known_brands:
                if search_query.upper().startswith(brand_name.upper()):
                    brand = brand_name
                    search_query = search_query[len(brand_name):].strip()
                    break
        
        price_bounds = base_recommendation._extract_price_bounds(filters)
        
        # Determine if this is a PC part query - use Neo4j if so
        is_pc_part_query = part_type and is_pc_part(part_type)
        products = []
        
        if is_pc_part_query:
            # Use Neo4j knowledge graph for PC parts
            try:
                kg_tool = get_compatibility_tool()
                if kg_tool.is_available():
                    kg_products = kg_tool.search_products(
                        part_type=part_type,
                        brand=brand,
                        min_price=price_bounds["min_price"],
                        max_price=price_bounds["max_price"],
                        query=search_query,
                        socket=filters.get("socket"),
                        vram=filters.get("vram"),
                        capacity=filters.get("capacity"),
                        wattage=filters.get("wattage"),
                        form_factor=filters.get("form_factor"),
                        chipset=filters.get("chipset"),
                        ram_standard=filters.get("ram_standard"),
                        storage_type=filters.get("storage_type"),
                        cooling_type=filters.get("cooling_type"),
                        certification=filters.get("certification"),
                        pcie_version=filters.get("pcie_version"),
                        tdp=filters.get("tdp"),
                        year=filters.get("year"),
                        series=filters.get("series"),
                        seller=filters.get("seller") or filters.get("retailer"),
                        limit=100,
                    )
                    
                    # Convert KG products to normalized format
                    for kg_product in kg_products:
                        normalized = base_recommendation._normalize_kg_product(kg_product)
                        if normalized:
                            products.append(normalized)
                    
                    # Filter and rank products for consumer/personal use
                    consumer_ranked = base_recommendation._rank_products_for_consumer_use(products)
                    logger.info("%s: retrieved %d products from Neo4j KG (filtered to %d consumer products)", 
                               label, len(products), len(consumer_ranked))
                    return consumer_ranked
                else:
                    logger.warning("Neo4j not available, falling back to local database")
            except Exception as exc:
                logger.error("Neo4j search failed for %s: %s, falling back to local database", label, exc)
        
        # Use local database for non-PC parts or as fallback
        store = LocalElectronicsStore()
        db_products = store.search_products(
            query=search_query,
            part_type=part_type,
            brand=brand,
            min_price=price_bounds["min_price"],
            max_price=price_bounds["max_price"],
            seller=filters.get("seller") or filters.get("retailer"),
            limit=100,
        )
        
        # Normalize products
        normalized: List[Dict[str, Any]] = []
        for product in db_products:
            normalized_product = base_recommendation._normalize_product(product)
            if normalized_product:
                normalized.append(normalized_product)
        
        # Filter and rank products for consumer/personal use
        consumer_ranked = base_recommendation._rank_products_for_consumer_use(normalized)
        logger.info("%s: retrieved %d products from local database (filtered to %d consumer products)", 
                   label, len(normalized), len(consumer_ranked))
        return consumer_ranked
        
    except Exception as exc:
        logger.error("Product search failed for %s: %s", label, exc)
        return []


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

