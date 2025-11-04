"""
Lightweight vector similarity ranking for local vehicle recommendations.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from idss_agent.utils.logger import get_logger

logger = get_logger("processing.vector_ranker")

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_EMBED_STORE_CACHE: Dict[Path, "VehicleEmbeddingStore"] = {}


class VehicleEmbeddingStore:
    """Persistent embedding cache stored alongside the main vehicle database."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Vehicle embedding store database not found at {self.db_path}"
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
                CREATE TABLE IF NOT EXISTS vehicle_embeddings (
                    vin TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get(self, vin: str) -> Optional[Dict[str, float]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT embedding FROM vehicle_embeddings WHERE vin = ?", (vin,)
            ).fetchone()

        if not row:
            return None

        try:
            data = json.loads(row["embedding"])
            return {token: float(weight) for token, weight in data.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Invalid embedding payload for VIN %s", vin)
            return None

    def upsert(self, vin: str, embedding: Dict[str, float]) -> None:
        payload = json.dumps(embedding)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO vehicle_embeddings (vin, embedding, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(vin) DO UPDATE
                SET embedding = excluded.embedding,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (vin, payload),
            )


def get_embedding_store(db_path: Path) -> VehicleEmbeddingStore:
    """Return cached VehicleEmbeddingStore for a given database path."""
    path = Path(db_path).resolve()
    store = _EMBED_STORE_CACHE.get(path)
    if store is None:
        store = VehicleEmbeddingStore(path)
        _EMBED_STORE_CACHE[path] = store
    return store


def rank_local_vehicles_by_similarity(
    vehicles: List[Dict[str, Any]],
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
    db_path: Path,
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """Rank filtered vehicles by cosine similarity to the user's preference vector."""
    if not vehicles:
        return vehicles

    store = get_embedding_store(db_path)
    user_vector = _build_user_vector(explicit_filters, implicit_preferences)

    if not user_vector:
        logger.info("No preference signal detected; skipping vector ranking")
        return vehicles

    scored: List[Tuple[float, Dict[str, Any]]] = []

    for vehicle in vehicles:
        vin = (
            vehicle.get("vehicle", {}).get("vin")
            or vehicle.get("vin")
        )

        embedding: Optional[Dict[str, float]] = None
        if vin:
            embedding = store.get(vin)

        if embedding is None:
            embedding = _embed_vehicle(vehicle)
            if vin and embedding:
                store.upsert(vin, embedding)

        similarity = _cosine_similarity(user_vector, embedding)
        vehicle["_vector_score"] = similarity
        scored.append((similarity, vehicle))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [item[1] for item in scored]
    top_preview = min(top_k, len(ranked))
    top_score = ranked[0].get("_vector_score", 0.0) if ranked else 0.0
    logger.info(
        "Vector ranking applied to %d vehicles (top%d score=%.3f)",
        len(ranked),
        top_preview,
        top_score,
    )
    return ranked


def _embed_vehicle(vehicle: Dict[str, Any]) -> Dict[str, float]:
    counter = Counter()
    vehicle_data = vehicle.get("vehicle", {})
    retail_data = vehicle.get("retailListing", {})

    _add_tokens(counter, vehicle_data.get("make"), weight=3.0)
    _add_tokens(counter, vehicle_data.get("model"), weight=3.0)
    _add_tokens(counter, vehicle_data.get("trim"), weight=2.0)
    _add_tokens(counter, vehicle_data.get("engine"), weight=1.5)
    _add_tokens(counter, vehicle_data.get("fuel"), weight=1.5)
    _add_tokens(counter, vehicle_data.get("drivetrain"), weight=1.5)
    _add_tokens(counter, vehicle_data.get("transmission"), weight=1.5)
    _add_tokens(counter, vehicle_data.get("exteriorColor"))
    _add_tokens(counter, vehicle_data.get("interiorColor"))
    _add_tokens(counter, vehicle_data.get("bodyStyle"))
    _add_tokens(counter, vehicle.get("body_style"))
    _add_tokens(counter, vehicle_data.get("doors"))
    _add_tokens(counter, vehicle_data.get("seats"))
    _add_tokens(counter, vehicle_data.get("year"), weight=2.0)

    price = retail_data.get("price")
    if price:
        _add_tokens(counter, f"price_bin_{_bin_value(price, 5000)}", weight=1.5)

    miles = retail_data.get("miles")
    if miles:
        _add_tokens(counter, f"miles_bin_{_bin_value(miles, 10000)}", weight=1.5)

    _add_tokens(counter, retail_data.get("state"))
    _add_tokens(counter, retail_data.get("city"))

    # Note: Features not available in Auto.dev API data
    # Future enhancement: Extract features from vehicle descriptions if available

    notes = vehicle.get("raw_json_summary")
    if notes:
        _add_tokens(counter, notes, weight=0.5)

    return _normalize_counter(counter)


def _build_user_vector(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any],
) -> Dict[str, float]:
    counter = Counter()

    def add_filter_tokens(key: str, weight: float = 2.0) -> None:
        value = explicit_filters.get(key)
        if value:
            _add_tokens(counter, value, weight=weight)

    add_filter_tokens("make", weight=3.0)
    add_filter_tokens("model", weight=3.0)
    add_filter_tokens("trim", weight=2.0)
    add_filter_tokens("body_style", weight=2.5)
    add_filter_tokens("engine", weight=2.0)
    add_filter_tokens("transmission", weight=2.0)
    add_filter_tokens("drivetrain", weight=2.0)
    add_filter_tokens("fuel_type", weight=2.0)
    add_filter_tokens("exterior_color", weight=1.5)
    add_filter_tokens("interior_color", weight=1.5)
    add_filter_tokens("state", weight=1.5)
    # Note: ZIP code removed - it's now only used to lookup coordinates, not as a filter

    if explicit_filters.get("price"):
        lower, upper = _parse_numeric_range(explicit_filters["price"])
        if lower is not None:
            _add_tokens(counter, f"price_min_{_bin_value(lower, 5000)}", weight=2.0)
        if upper is not None:
            _add_tokens(counter, f"price_max_{_bin_value(upper, 5000)}", weight=2.0)

    if explicit_filters.get("mileage"):
        lower, upper = _parse_numeric_range(explicit_filters["mileage"])
        if lower is not None:
            _add_tokens(counter, f"miles_min_{_bin_value(lower, 10000)}", weight=1.5)
        if upper is not None:
            _add_tokens(counter, f"miles_max_{_bin_value(upper, 10000)}", weight=1.5)

    if explicit_filters.get("year"):
        lower, upper = _parse_numeric_range(explicit_filters["year"])
        if lower is not None:
            _add_tokens(counter, f"year_min_{int(lower)}", weight=2.0)
        if upper is not None:
            _add_tokens(counter, f"year_max_{int(upper)}", weight=2.0)

    for priority in implicit_preferences.get("priorities", []) or []:
        _add_tokens(counter, priority, weight=2.5)

    if implicit_preferences.get("usage_patterns"):
        _add_tokens(counter, implicit_preferences["usage_patterns"], weight=2.0)

    if implicit_preferences.get("lifestyle"):
        _add_tokens(counter, implicit_preferences["lifestyle"], weight=1.5)

    for concern in implicit_preferences.get("concerns", []) or []:
        _add_tokens(counter, concern, weight=2.0)

    if implicit_preferences.get("brand_affinity"):
        _add_tokens(counter, implicit_preferences["brand_affinity"], weight=2.5)

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

    if isinstance(value, (int, float)):
        counter[str(int(value))] += weight
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
    "VehicleEmbeddingStore",
    "get_embedding_store",
    "rank_local_vehicles_by_similarity",
]
