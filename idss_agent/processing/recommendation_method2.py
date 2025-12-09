"""
Method 2: Web search guidance → Parallel knowledge graph (for PC parts) or local database queries → Vector ranking.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from idss_agent.processing import recommendation as base_recommendation
from idss_agent.processing.vector_ranker import rank_products_by_similarity
from idss_agent.tools.local_electronics_store import LocalElectronicsStore
from idss_agent.tools.kg_compatibility import get_compatibility_tool, is_pc_part
from idss_agent.utils.config import get_config
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.method2")


class WebSearchProductSuggestion(BaseModel):
    """LLM-extracted product suggestions from web search."""

    brands: List[str] = Field(
        description="3-5 electronics brands that match the user's needs (e.g., ['ASUS', 'Dell', 'Lenovo'])"
    )
    product_lines: List[str] = Field(
        description=(
            "4-8 product lines, models, or category keywords (e.g., ['ROG Zephyrus', 'ThinkPad X1', 'gaming laptop'])"
        )
    )
    reasoning: str = Field(description="Brief explanation of why these products match the user's preferences")
    search_query: str = Field(description="Search query used for Tavily web search")


def recommend_method2(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    top_k: Optional[int] = None,
    num_brands: int = 4,
    db_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Method 2: Web search guided brand selection with parallel local database queries.

    Args:
        explicit_filters: Explicit filters describing the desired product.
        implicit_preferences: Implicit preferences inferred from conversation.
        top_k: Number of products to return (defaults to config limit).
        num_brands: Number of brands to explore in parallel.
        db_path: Optional sqlite path for embedding persistence.

    Returns:
        Tuple of (products, reasoning string from LLM suggestions).
    """
    config = get_config()
    if top_k is None:
        top_k = min(
            20,
            config.limits.get("top_products_to_show", 20),
            config.limits.get("max_recommended_items", 20),
        )

    logger.info("=" * 60)
    logger.info("METHOD 2: Web search guidance + parallel local database queries")
    logger.info("=" * 60)
    logger.info("Explicit filters: %s", explicit_filters)
    logger.info("Implicit preferences: %s", implicit_preferences)
    logger.info("Target products: %d across %d brands", top_k, num_brands)

    logger.info("Step 1: Performing web search for brand suggestions...")
    suggestions = web_search_for_product_suggestions(explicit_filters, implicit_preferences)

    if not suggestions or not suggestions.brands:
        logger.warning("Web search suggestions unavailable")
        return [], None

    brands_to_query = suggestions.brands[:num_brands]
    logger.info("Web search suggests brands: %s", brands_to_query)

    per_brand_limit = max(40, top_k)
    brand_results: Dict[str, List[Dict[str, Any]]] = {}

    logger.info("Step 2: Running local database queries in parallel...")
    with ThreadPoolExecutor(max_workers=min(len(brands_to_query), 6)) as executor:
        future_to_brand = {
            executor.submit(
                query_products_for_brand,
                brand,
                explicit_filters,
                implicit_preferences,
                per_brand_limit,
            ): brand
            for brand in brands_to_query
        }

        for future in as_completed(future_to_brand):
            brand = future_to_brand[future]
            try:
                brand_products = future.result()
                # Filter and rank products for consumer/personal use
                consumer_ranked = base_recommendation._rank_products_for_consumer_use(brand_products)
                brand_results[brand] = consumer_ranked
                logger.info("Brand %s: filtered to %d consumer products (from %d total)", 
                           brand, len(consumer_ranked), len(brand_products))
            except Exception as exc:  # pragma: no cover
                logger.error("Brand query failed for %s: %s", brand, exc)
                brand_results[brand] = []

    total_candidates = sum(len(products) for products in brand_results.values())
    logger.info(
        "Step 2 complete: Retrieved %d candidate products across %d brands (consumer-focused)",
        total_candidates,
        len(brands_to_query),
    )

    logger.info("Step 3: Ranking each brand's products by vector similarity...")
    ranked_results: Dict[str, List[Dict[str, Any]]] = {}

    for brand, products in brand_results.items():
        if not products:
            ranked_results[brand] = []
            continue

        ranked = rank_products_by_similarity(
            products,
            explicit_filters,
            implicit_preferences,
            db_path=db_path,
        )
        ranked_results[brand] = ranked
        top_score = ranked[0].get("_vector_score", 0.0) if ranked else 0.0
        logger.info(
            "Brand %s: ranked %d products (top score=%.3f)",
            brand,
            len(ranked),
            top_score,
        )

    logger.info("Step 4: Selecting top products per brand for diversity...")
    products_per_brand = max(1, top_k // max(1, len(brands_to_query)))
    final_selection: List[Dict[str, Any]] = []

    for brand in brands_to_query:
        ranked = ranked_results.get(brand, [])
        # Filter out zero-score items before selecting
        filtered_ranked = [p for p in ranked if p.get("_vector_score", 0.0) > 0.0]
        chosen = filtered_ranked[:products_per_brand]
        final_selection.extend(chosen)
        logger.info("Brand %s: selected %d products", brand, len(chosen))

    if len(final_selection) < top_k:
        logger.info(
            "Need %d more products; collecting remaining high-scoring items...",
            top_k - len(final_selection),
        )

        remaining: List[Dict[str, Any]] = []
        for brand in brands_to_query:
            ranked = ranked_results.get(brand, [])
            # Filter out zero-score items and extend
            filtered = [p for p in ranked[products_per_brand:] if p.get("_vector_score", 0.0) > 0.0]
            remaining.extend(filtered)

        remaining.sort(key=lambda product: product.get("_vector_score", 0.0), reverse=True)
        needed = top_k - len(final_selection)
        final_selection.extend(remaining[:needed])

    final_selection = final_selection[:top_k]

    logger.info(
        "Method 2 complete: returning %d products (reasoning provided)",
        len(final_selection),
    )
    logger.info("=" * 60)
    return final_selection, suggestions.reasoning


def generate_search_query(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
) -> str:
    """
    Generate a web search query tailored to the user's electronics needs.
    """
    parts: List[str] = []

    product_term = (
        explicit_filters.get("product")
        or explicit_filters.get("product_name")
        or explicit_filters.get("category")
        or explicit_filters.get("keywords")
    )
    if product_term:
        parts.append(str(product_term))

    priorities = implicit_preferences.get("priorities", [])
    if priorities:
        parts.extend(priorities[:2])

    budget = implicit_preferences.get("budget_sensitivity")
    if budget:
        parts.append(budget)

    brand = explicit_filters.get("brand")
    if brand:
        parts.append(str(brand))

    max_price = (
        explicit_filters.get("price_max")
        or explicit_filters.get("max_price")
        or explicit_filters.get("price")
    )
    if max_price:
        parts.append(f"under {max_price}")

    if not parts:
        parts = ["best electronics 2024"]

    query = " ".join(str(part) for part in parts if part).strip()
    if "electronics" not in query.lower():
        query = f"{query} electronics"

    logger.info("Generated web search query: %s", query)
    return query


def web_search_for_product_suggestions(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
) -> Optional[WebSearchProductSuggestion]:
    """
    Use web search and an LLM to extract relevant brands and product lines.
    """
    search_query = generate_search_query(explicit_filters, implicit_preferences)

    try:
        from langchain_community.tools.tavily_search import TavilySearchResults

        tavily = TavilySearchResults(max_results=5)
        search_results = tavily.invoke({"query": search_query})
        logger.info("Tavily search returned %d results", len(search_results) if isinstance(search_results, list) else 1)

        if isinstance(search_results, list):
            formatted_results = "\n\n".join(
                f"Title: {item.get('title', 'N/A')}\nContent: {item.get('content', 'N/A')}\nURL: {item.get('url', 'N/A')}"
                for item in search_results
            )
        else:
            formatted_results = str(search_results)
    except Exception as exc:  # pragma: no cover
        logger.error("Tavily search failed: %s", exc)
        return None

    prompt = f"""You are an electronics buying guide expert. Based on the web search results,
recommend the best brands and product lines for the user.

**User Explicit Filters:**
{json.dumps(explicit_filters, indent=2)}

**User Implicit Preferences:**
{json.dumps(implicit_preferences, indent=2)}

**Web Search Results:**
{formatted_results}

Instructions:
1. List 3-5 brands that best match the user's needs.
2. List 4-8 product lines, model families, or category keywords from those brands.
3. Provide a concise reasoning (2-3 sentences).
4. Include the search query used.
"""

    try:
        llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        structured_llm = llm.with_structured_output(WebSearchProductSuggestion)
        result = structured_llm.invoke(
            [
                SystemMessage(content="You are a helpful electronics expert."),
                HumanMessage(content=prompt),
            ]
        )
        logger.info("LLM suggested brands: %s", result.brands)
        logger.info("LLM suggested product lines: %s", result.product_lines)
        return result
    except Exception as exc:  # pragma: no cover
        logger.error("LLM suggestion extraction failed: %s", exc)
        return None


def query_products_for_brand(
    brand: str,
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Query knowledge graph (for PC parts) or local database for a specific brand with user filters.
    """
    try:
        price_bounds = base_recommendation._extract_price_bounds(explicit_filters)
        part_type = explicit_filters.get("category") or explicit_filters.get("part_type")
        if part_type:
            part_type = part_type.lower().strip()
        
        # Build query from product terms
        product_terms = [
            explicit_filters.get("product"),
            explicit_filters.get("product_name"),
            explicit_filters.get("keywords"),
        ]
        query_parts = [term for term in product_terms if term]
        query = " ".join(query_parts) if query_parts else None
        
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
                        query=query,
                        socket=explicit_filters.get("socket"),
                        vram=explicit_filters.get("vram"),
                        capacity=explicit_filters.get("capacity"),
                        wattage=explicit_filters.get("wattage"),
                        form_factor=explicit_filters.get("form_factor"),
                        chipset=explicit_filters.get("chipset"),
                        ram_standard=explicit_filters.get("ram_standard"),
                        storage_type=explicit_filters.get("storage_type"),
                        cooling_type=explicit_filters.get("cooling_type"),
                        certification=explicit_filters.get("certification"),
                        pcie_version=explicit_filters.get("pcie_version"),
                        tdp=explicit_filters.get("tdp"),
                        year=explicit_filters.get("year"),
                        series=explicit_filters.get("series"),
                        seller=explicit_filters.get("seller"),
                        limit=limit,
                    )
                    
                    # Convert KG products to normalized format
                    for kg_product in kg_products:
                        normalized = base_recommendation._normalize_kg_product(kg_product)
                        if normalized:
                            products.append(normalized)
                    
                    # Filter and rank products for consumer/personal use
                    consumer_ranked = base_recommendation._rank_products_for_consumer_use(products)
                    logger.info("Brand %s: gathered %d products from Neo4j KG (filtered to %d consumer products)", 
                               brand, len(products), len(consumer_ranked))
                    products = base_recommendation._deduplicate_products(consumer_ranked)
                    return products[:limit]
                else:
                    logger.warning("Neo4j not available, falling back to local database")
            except Exception as exc:
                logger.error("Neo4j search failed for brand %s: %s, falling back to local database", brand, exc)
        
        # Use local database for non-PC parts or as fallback
        store = LocalElectronicsStore()
        db_products = store.search_products(
            query=query,
            part_type=part_type,
            brand=brand,
            min_price=price_bounds["min_price"],
            max_price=price_bounds["max_price"],
            seller=explicit_filters.get("seller"),
            limit=limit,
        )
        
        # Normalize products
        normalized: List[Dict[str, Any]] = []
        for product in db_products:
            normalized_product = base_recommendation._normalize_product(product)
            if normalized_product:
                normalized.append(normalized_product)
        
        # Filter and rank products for consumer/personal use
        consumer_ranked = base_recommendation._rank_products_for_consumer_use(normalized)
        products = base_recommendation._deduplicate_products(consumer_ranked)
        logger.info("Brand %s: gathered %d products from local database (filtered to %d consumer products)", 
                   brand, len(normalized), len(products))
        return products[:limit]
        
    except Exception as exc:
        logger.error("Product query failed for brand %s: %s", brand, exc)
        return []


__all__ = ["recommend_method2", "web_search_for_product_suggestions", "generate_search_query"]

