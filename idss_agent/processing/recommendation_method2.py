"""
Method 2: Web search guidance → Parallel RapidAPI queries → Vector ranking.
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
from idss_agent.tools.electronics_api import search_products
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
    Method 2: Web search guided brand selection with parallel RapidAPI queries.

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
    logger.info("METHOD 2: Web search guidance + parallel RapidAPI queries")
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

    logger.info("Step 2: Running RapidAPI queries in parallel...")
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
                brand_results[brand] = future.result()
            except Exception as exc:  # pragma: no cover
                logger.error("Brand query failed for %s: %s", brand, exc)
                brand_results[brand] = []

    total_candidates = sum(len(products) for products in brand_results.values())
    logger.info(
        "Step 2 complete: Retrieved %d candidate products across %d brands",
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
        chosen = ranked[:products_per_brand]
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
            remaining.extend(ranked[products_per_brand:])

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
    Query RapidAPI for a specific brand with user filters.
    """
    payload = base_recommendation._build_search_payload(explicit_filters, implicit_preferences)
    brand_query_components = [brand]

    product_terms = [
        explicit_filters.get("product"),
        explicit_filters.get("product_name"),
        explicit_filters.get("keywords"),
        explicit_filters.get("category"),
    ]
    brand_query_components.extend(term for term in product_terms if term)

    payload["query"] = " ".join(str(component) for component in brand_query_components if component)
    payload["page"] = 1

    products: List[Dict[str, Any]] = []
    current_page = 1

    while len(products) < limit and current_page <= 3:
        payload["page"] = current_page
        try:
            response_text = search_products.invoke(payload)
        except Exception as exc:  # pragma: no cover
            logger.error("RapidAPI query failed for brand %s (page %d): %s", brand, current_page, exc)
            break

        raw_products = base_recommendation._parse_product_list(response_text)
        normalized: List[Dict[str, Any]] = []
        for raw_product in raw_products:
            normalized_product = base_recommendation._normalize_product(raw_product)
            if normalized_product:
                normalized.append(normalized_product)

        if not normalized:
            break

        products.extend(normalized)
        current_page += 1

    products = base_recommendation._deduplicate_products(products)
    logger.info("Brand %s: gathered %d products", brand, len(products))
    return products[:limit]


__all__ = ["recommend_method2", "web_search_for_product_suggestions", "generate_search_query"]

