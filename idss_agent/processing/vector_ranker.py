"""
Lightweight vector similarity ranking for electronics product recommendations.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from idss_agent.utils.logger import get_logger

logger = get_logger("processing.vector_ranker")

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_EMBED_STORE_CACHE: Dict[Path, "ProductEmbeddingStore"] = {}


class ProductEmbeddingStore:
    """
    Persistent embedding cache stored alongside a local electronics product database.

    The store is optional—if no database path is provided, embeddings are computed on the fly
    without persistence.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Product embedding store database not found at {self.db_path}"
            )
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_embeddings (
                    product_id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get(self, product_id: str) -> Optional[Dict[str, float]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT embedding FROM product_embeddings WHERE product_id = ?",
                (product_id,),
            ).fetchone()

        if not row:
            return None

        try:
            data = json.loads(row["embedding"])
            return {token: float(weight) for token, weight in data.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Invalid embedding payload for product %s", product_id)
            return None

    def upsert(self, product_id: str, embedding: Dict[str, float]) -> None:
        payload = json.dumps(embedding)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO product_embeddings (product_id, embedding, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(product_id) DO UPDATE
                SET embedding = excluded.embedding,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (product_id, payload),
            )


def get_embedding_store(db_path: Path) -> ProductEmbeddingStore:
    """Return cached ProductEmbeddingStore for a given database path."""
    path = Path(db_path).resolve()
    store = _EMBED_STORE_CACHE.get(path)
    if store is None:
        store = ProductEmbeddingStore(path)
        _EMBED_STORE_CACHE[path] = store
    return store


def rank_products_by_similarity(
    products: List[Dict[str, Any]],
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    db_path: Optional[Path] = None,
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Rank electronics products by cosine similarity to the user's preference vector.

    Args:
        products: Candidate product dictionaries.
        explicit_filters: Explicit filters extracted from the conversation.
        implicit_preferences: Implicit preferences inferred from the conversation.
        db_path: Optional sqlite path for embedding cache persistence.
        top_k: Optional number of items to keep (defaults to len(products)).

    Returns:
        Ranked list of products (highest similarity first).
    """
    if not products:
        return products

    store: Optional[ProductEmbeddingStore] = None
    if db_path is not None:
        try:
            store = get_embedding_store(db_path)
        except FileNotFoundError as exc:
            logger.warning("Embedding store unavailable: %s", exc)

    user_vector = _build_user_vector(explicit_filters, implicit_preferences)

    if not user_vector:
        logger.info("No preference signal detected; skipping vector ranking")
        return products

    scored: List[Tuple[float, Dict[str, Any]]] = []

    for product in products:
        product_id = _get_product_identifier(product)
        embedding: Optional[Dict[str, float]] = None

        if store and product_id:
            embedding = store.get(product_id)

        if embedding is None:
            embedding = _embed_product(product)
            if store and product_id and embedding:
                store.upsert(product_id, embedding)

        similarity = _cosine_similarity(user_vector, embedding)
        product["_vector_score"] = similarity
        scored.append((similarity, product))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [item[1] for item in scored]

    # Filter out items with similarity score of 0
    ranked = [product for product in ranked if product.get("_vector_score", 0.0) > 0.0]

    if top_k is not None and top_k < len(ranked):
        ranked = ranked[:top_k]

    top_score = ranked[0].get("_vector_score", 0.0) if ranked else 0.0
    logger.info(
        "Vector ranking applied to %d products (top score=%.3f)",
        len(ranked),
        top_score,
    )
    return ranked


def _get_product_identifier(product: Dict[str, Any]) -> Optional[str]:
    product_info = product.get("product") or {}
    return (
        product.get("id")
        or product_info.get("identifier")
        or product_info.get("id")
        or product.get("link")
    )


def _embed_product(product: Dict[str, Any]) -> Dict[str, float]:
    counter = Counter()

    product_info = product.get("product") or {}
    offer = product.get("offer") or {}

    _add_tokens(counter, product.get("title"), weight=3.5)
    _add_tokens(counter, product_info.get("title"), weight=3.0)
    _add_tokens(counter, product.get("brand") or product_info.get("brand"), weight=2.5)
    _add_tokens(counter, product_info.get("category"), weight=2.0)
    _add_tokens(counter, product_info.get("type"), weight=2.0)
    _add_tokens(counter, product_info.get("series"), weight=1.8)
    _add_tokens(counter, product.get("source"), weight=1.0)

    for attribute_value in _iter_attribute_values(product_info.get("attributes")):
        _add_tokens(counter, attribute_value, weight=1.5)

    for spec_value in _iter_attribute_values(product.get("specs")):
        _add_tokens(counter, spec_value, weight=1.4)

    _add_tokens(counter, product.get("feature_bullets"), weight=1.2)
    _add_tokens(counter, product.get("description"), weight=1.0)

    rating = product.get("rating") or product_info.get("rating")
    if rating:
        _add_tokens(counter, f"rating_{rating}", weight=1.0)

    price = offer.get("price") or product.get("price_text")
    if price:
        _add_tokens(counter, f"price_bin_{_bin_value(price, 50)}", weight=1.8)

    return _normalize_counter(counter)


def _iter_attribute_values(attributes: Any) -> List[str]:
    values: List[str] = []

    if isinstance(attributes, dict):
        for value in attributes.values():
            if isinstance(value, (list, tuple)):
                values.extend(str(item) for item in value)
            elif value is not None:
                values.append(str(value))
    elif isinstance(attributes, list):
        for item in attributes:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    values.append(str(name))
                attr_values = item.get("values")
                if isinstance(attr_values, list):
                    values.extend(str(v) for v in attr_values if v is not None)
                elif attr_values is not None:
                    values.append(str(attr_values))
            elif item is not None:
                values.append(str(item))
    elif attributes is not None:
        values.append(str(attributes))

    return values


def _build_user_vector(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
) -> Dict[str, float]:
    counter = Counter()

    def add_filter_tokens(key: str, weight: float = 2.0) -> None:
        value = explicit_filters.get(key)
        if value:
            _add_tokens(counter, value, weight=weight)

    add_filter_tokens("product", weight=3.0)
    add_filter_tokens("product_name", weight=3.0)
    add_filter_tokens("search_query", weight=2.5)
    add_filter_tokens("keywords", weight=2.5)
    add_filter_tokens("category", weight=2.5)
    add_filter_tokens("subcategory", weight=2.0)
    add_filter_tokens("type", weight=2.0)
    add_filter_tokens("brand", weight=2.5)
    add_filter_tokens("series", weight=1.8)
    add_filter_tokens("seller", weight=1.5)
    add_filter_tokens("retailer", weight=1.5)
    add_filter_tokens("features", weight=2.0)

    if explicit_filters.get("price"):
        lower, upper = _parse_numeric_range(explicit_filters["price"])
        if lower is not None:
            _add_tokens(counter, f"price_min_{_bin_value(lower, 50)}", weight=2.0)
        if upper is not None:
            _add_tokens(counter, f"price_max_{_bin_value(upper, 50)}", weight=2.0)

    for key in ("min_price", "price_min"):
        if explicit_filters.get(key) is not None:
            _add_tokens(counter, f"price_min_{_bin_value(explicit_filters[key], 50)}", weight=2.0)

    for key in ("max_price", "price_max"):
        if explicit_filters.get(key) is not None:
            _add_tokens(counter, f"price_max_{_bin_value(explicit_filters[key], 50)}", weight=2.0)

    if explicit_filters.get("rating_min"):
        _add_tokens(counter, f"rating_min_{explicit_filters['rating_min']}", weight=1.5)

    if explicit_filters.get("rating"):
        _add_tokens(counter, f"rating_target_{explicit_filters['rating']}", weight=1.3)

    if explicit_filters.get("stores"):
        _add_tokens(counter, explicit_filters["stores"], weight=1.4)

    for priority in implicit_preferences.get("priorities", []) or []:
        _add_tokens(counter, priority, weight=2.5)

    if implicit_preferences.get("usage_patterns"):
        _add_tokens(counter, implicit_preferences["usage_patterns"], weight=2.0)

    if implicit_preferences.get("lifestyle"):
        _add_tokens(counter, implicit_preferences["lifestyle"], weight=1.5)

    if implicit_preferences.get("budget_sensitivity"):
        _add_tokens(counter, implicit_preferences["budget_sensitivity"], weight=1.5)

    for concern in implicit_preferences.get("concerns", []) or []:
        _add_tokens(counter, concern, weight=2.0)

    for brand in implicit_preferences.get("brand_affinity", []) or []:
        _add_tokens(counter, brand, weight=2.5)

    if implicit_preferences.get("notes"):
        _add_tokens(counter, implicit_preferences["notes"], weight=1.0)

    return _normalize_counter(counter)


def _add_tokens(counter: Counter, value: Any, weight: float = 1.0) -> None:
    if value is None:
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            _add_tokens(counter, item, weight)
        return

    if isinstance(value, dict):
        for item in value.values():
            _add_tokens(counter, item, weight)
        return

    if isinstance(value, (int, float)):
        counter[str(value)] += weight
        return

    text = str(value).lower()
    for token in _TOKEN_PATTERN.findall(text):
        counter[token] += weight


def _normalize_counter(counter: Counter) -> Dict[str, float]:
    if not counter:
        return {}
    norm = math.sqrt(sum(weight * weight for weight in counter.values()))
    if norm == 0:
        return {token: float(weight) for token, weight in counter.items()}
    return {token: float(weight) / norm for token, weight in counter.items()}


def _cosine_similarity(
    vec_a: Optional[Dict[str, float]],
    vec_b: Optional[Dict[str, float]],
) -> float:
    if not vec_a or not vec_b:
        return 0.0

    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a

    return float(
        sum(weight * vec_b.get(token, 0.0) for token, weight in vec_a.items())
    )


def _parse_numeric_range(value: Any) -> Tuple[Optional[float], Optional[float]]:
    if value is None:
        return (None, None)

    text = str(value).strip()
    if "-" not in text:
        try:
            num = float(text)
            return (num, num)
        except ValueError:
            return (None, None)

    lower_text, upper_text = text.split("-", 1)
    lower = float(lower_text) if lower_text.strip() else None
    upper = float(upper_text) if upper_text.strip() else None
    return (lower, upper)


def _bin_value(value: Any, step: int) -> int:
    try:
        num = int(float(value))
    except (TypeError, ValueError):
        return 0
    if step <= 0:
        return num
    return (num // step) * step


__all__ = [
    "ProductEmbeddingStore",
    "get_embedding_store",
    "rank_products_by_similarity",
]
