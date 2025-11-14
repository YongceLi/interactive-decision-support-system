"""RapidAPI-backed electronics recommendation pipeline."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from idss_agent.state.schema import ProductSearchState
from idss_agent.tools.electronics_api import search_products
from idss_agent.utils.config import get_config
from idss_agent.utils.logger import get_logger


logger = get_logger("components.recommendation")


DEFAULT_COUNTRY = "us"


def _build_search_query(filters: Dict[str, Any], implicit: Dict[str, Any]) -> str:
    """Create a keyword query for RapidAPI search from filters and preferences."""

    keywords: List[str] = []

    for key in [
        "search_query",
        "query",
        "keywords",
        "product",
        "product_name",
        "category",
        "subcategory",
    ]:
        value = filters.get(key)
        if value:
            keywords.append(str(value))

    brand_affinity = implicit.get("brand_affinity")
    if isinstance(brand_affinity, list):
        keywords.extend(brand_affinity)

    if not keywords and implicit.get("priorities"):
        priorities = implicit["priorities"]
        if isinstance(priorities, list):
            keywords.extend(priorities)

    # Remove duplicates while keeping order
    deduped: List[str] = []
    seen: set[str] = set()
    for word in keywords:
        normalized = word.strip()
        if not normalized or normalized.lower() in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized.lower())

    return " ".join(deduped) if deduped else "electronics"


def _extract_price_bounds(filters: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Pull min/max price values from a variety of filter keys."""

    price_range = filters.get("price") or filters.get("price_range")
    min_price = filters.get("price_min") or filters.get("min_price")
    max_price = filters.get("price_max") or filters.get("max_price")

    if isinstance(price_range, str) and "-" in price_range:
        lower, upper = price_range.split("-", 1)
        if not min_price and lower.strip():
            try:
                min_price = float(lower)
            except ValueError:
                min_price = None
        if not max_price and upper.strip():
            try:
                max_price = float(upper)
            except ValueError:
                max_price = None

    def _coerce(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "min_price": _coerce(min_price),
        "max_price": _coerce(max_price),
    }


def _build_search_payload(
    filters: Dict[str, Any], implicit: Dict[str, Any]
) -> Dict[str, Any]:
    """Prepare parameters for the RapidAPI search tool."""

    price_bounds = _extract_price_bounds(filters)

    payload: Dict[str, Any] = {
        "query": _build_search_query(filters, implicit),
        "page": int(filters.get("page", 1) or 1),
        "country": filters.get("country") or DEFAULT_COUNTRY,
        "language": filters.get("language"),
        "sort_by": filters.get("sort_by") or filters.get("sort"),
        "min_price": price_bounds["min_price"],
        "max_price": price_bounds["max_price"],
        "seller": filters.get("seller") or filters.get("retailer"),
    }

    return payload


def _parse_product_list(response_text: str) -> List[Dict[str, Any]]:
    """Parse RapidAPI response text into a list of product dictionaries."""

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        logger.error("RapidAPI returned non-JSON response: %s", response_text[:200])
        return []

    if isinstance(payload, dict):
        if payload.get("error"):
            logger.error("RapidAPI error: %s", payload["error"])
            return []

        for key in ("items", "products", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

        # Some APIs nest under 'response' or 'payload'
        for key in ("response", "payload"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                for sub_key in ("items", "products", "data", "results"):
                    value = nested.get(sub_key)
                    if isinstance(value, list):
                        return value

        return []

    if isinstance(payload, list):
        return payload

    return []


def _normalize_product(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert raw product dict into a structure expected by downstream code."""

    product_id = (
        product.get("product_id")
        or product.get("productId")
        or product.get("id")
        or product.get("itemId")
        or product.get("item_number")
    )
    title = (
        product.get("title")
        or product.get("name")
        or product.get("product_title")
        or product.get("productName")
    )

    if not title:
        return None

    brand = product.get("brand") or product.get("manufacturer")
    price = (
        product.get("price")
        or product.get("sale_price")
        or product.get("salePrice")
        or product.get("finalPrice")
    )
    currency = product.get("currency") or product.get("currencyCode") or "USD"
    url = product.get("url") or product.get("productUrl") or product.get("link")
    image_url = (
        product.get("image")
        or product.get("imageUrl")
        or product.get("image_url")
        or product.get("thumbnail")
    )
    availability = (
        product.get("availability")
        or product.get("stock_status")
        or product.get("stockStatus")
    )

    def parse_price_value(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            # Extract numeric portion from price string (handles $123.45/mo and similar)
            match = re.findall(r"[0-9]+(?:[.,][0-9]+)?", value)
            if match:
                try:
                    return float(match[0].replace(",", ""))
                except ValueError:
                    return None

        return None

    price_value = parse_price_value(price)

    source = (
        product.get("source")
        or product.get("seller")
        or product.get("sellerName")
        or product.get("store")
    )

    normalized = {
        "id": str(product_id or url or title),
        "title": title,
        "brand": brand,
        "source": source,
        "price_text": str(price) if price is not None else None,
        "price_value": price_value,
        "price_currency": currency,
        "link": url,
        "image_url": image_url,
        "rating": product.get("rating"),
        "rating_count": product.get("ratingCount") or product.get("rating_count") or product.get("reviews"),
        "product": {
            "id": product_id,
            "title": title,
            "brand": brand,
            "category": product.get("category") or product.get("type"),
            "attributes": product.get("attributes") or product.get("specs"),
        },
        "offer": {
            "price": price,
            "currency": currency,
            "seller": source,
            "url": url,
            "availability": availability,
        },
        "rating": product.get("rating"),
        "reviewCount": product.get("reviewCount") or product.get("reviews"),
        "photos": {"retail": [{"url": image_url}]} if image_url else None,
        "_source": product.get("source") or "rapidapi",
        "_raw": product,
    }

    if product_id:
        normalized["product"]["identifier"] = product_id

    # Set standard electronics product fields
    product_brand = brand or source or "Unknown"
    product_name = title

    normalized.setdefault("brand", product_brand)
    normalized.setdefault("product_brand", product_brand)
    normalized.setdefault("product_name", product_name)

    if price_value is not None and "price" not in normalized:
        normalized["price"] = price_value

    if image_url and not normalized.get("photos"):
        normalized["photos"] = {"retail": [{"url": image_url}]}

    return normalized


def _deduplicate_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate products based on product id or URL."""

    seen: Dict[str, Dict[str, Any]] = {}

    for product in products:
        identifier = (
            product.get("product", {}).get("identifier")
            or product.get("product", {}).get("id")
            or product.get("offer", {}).get("url")
        )

        if not identifier:
            identifier = product.get("product", {}).get("title")

        if not identifier:
            continue

        # Prefer lower priced offer when duplicate ids appear
        existing = seen.get(identifier)
        current_price = product.get("offer", {}).get("price")
        existing_price = existing.get("offer", {}).get("price") if existing else None

        def _price_to_float(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return float("inf")

        if not existing or _price_to_float(current_price) < _price_to_float(existing_price):
            seen[identifier] = product

    return list(seen.values())


def update_recommendation_list(
    state: ProductSearchState,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> ProductSearchState:
    """Populate recommendation slots in state with RapidAPI electronics products."""

    if progress_callback:
        progress_callback(
            {
            "step_id": "updating_recommendations",
                "description": "Searching for products",
                "status": "in_progress",
            }
        )

    filters = state["explicit_filters"].copy()
    implicit = state["implicit_preferences"].copy()

    search_params = _build_search_payload(filters, implicit)
    logger.info("RapidAPI product search params: %s", search_params)

    try:
        response_text = search_products.invoke(search_params)
    except Exception as exc:  # pragma: no cover - tool invocation wrapper
        logger.error("RapidAPI search invocation failed: %s", exc)
        state["recommended_products"] = []
        state["search_error"] = str(exc)
        return state

    raw_products = _parse_product_list(response_text)
    normalized_products = []

    for product in raw_products:
        normalized = _normalize_product(product)
        if normalized:
            normalized_products.append(normalized)

    if not normalized_products:
        logger.warning("RapidAPI search returned no products for params: %s", search_params)

    deduped_products = _deduplicate_products(normalized_products)
    config = get_config()
    max_items = config.limits.get("max_recommended_items", 20)

    top_products = deduped_products[:max_items]
    state["recommended_products"] = top_products
    state["fallback_message"] = None
    state["previous_filters"] = filters
    state.pop("suggestion_reasoning", None)
    state.pop("search_error", None)

    logger.info(
        "✓ Recommendation complete: %d products in state",
        len(top_products),
    )

    if progress_callback:
        progress_callback(
            {
            "step_id": "updating_recommendations",
                "description": (
                    f"Found {len(top_products)} products"
                ),
                "status": "completed",
            }
        )

    return state
