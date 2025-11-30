"""Utilities for loading and representing review-derived personas."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pandas as pd


@dataclass
class ProductAffinity:
    """Represents a liked or disliked product configuration."""

    product_brand: Optional[str]
    product_name: Optional[str]
    normalize_product_name: Optional[str]
    rationale: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "ProductAffinity":
        return cls(
            product_brand=data.get("product_brand"),
            product_name=data.get("product_name"),
            normalize_product_name=data.get("normalize_product_name"),
            rationale=data.get("rationale"),
        )


@dataclass
class ReviewPersona:
    """Persona constructed from a single enriched review entry."""

    product_brand: str
    product_name: str
    normalize_product_name: str
    review: str
    rating: Optional[float]
    date: Optional[str]
    liked: List[ProductAffinity] = field(default_factory=list)
    disliked: List[ProductAffinity] = field(default_factory=list)
    intention: str = ""
    mentioned_product_brands: List[str] = field(default_factory=list)
    mentioned_product_names: List[str] = field(default_factory=list)
    mentioned_normalize_product_names: List[str] = field(default_factory=list)
    performance_tier: Optional[str] = None
    newness_preference_score: Optional[int] = None
    newness_preference_notes: Optional[str] = None
    price_range: Optional[str] = None
    alternative_openness: Optional[int] = None
    misc_notes: Optional[str] = None
    upper_price_limit: Optional[float] = None

    @property
    def rating_value(self) -> Optional[float]:
        try:
            return float(self.rating) if self.rating is not None else None
        except (TypeError, ValueError):
            return None


def _parse_affinity_column(value: str) -> List[ProductAffinity]:
    if not value or (isinstance(value, float) and pd.isna(value)):
        return []
    try:
        raw_list = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(raw_list, dict):
        raw_list = [raw_list]
    affinities: List[ProductAffinity] = []
    for item in raw_list:
        if isinstance(item, dict):
            affinities.append(ProductAffinity.from_dict(item))
    return affinities


def _parse_json_list(value: Optional[str]) -> List[str]:
    if not value or (isinstance(value, float) and pd.isna(value)):
        return []
    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, list):
        return [str(item) for item in data if item is not None and str(item).strip()]
    if isinstance(data, (str, int, float)) and str(data).strip():
        return [str(data)]
    return []


def _parse_json_int_list(value: Optional[str]) -> List[int]:
    items = _parse_json_list(value)
    parsed: List[int] = []
    for item in items:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return parsed


def _try_parse_int(value: Optional[object]) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _try_parse_float(value: Optional[object]) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_personas_from_frame(frame: pd.DataFrame) -> List[ReviewPersona]:
    personas: List[ReviewPersona] = []
    for _, row in frame.iterrows():
        personas.append(
            ReviewPersona(
                product_brand=str(row.get("Brand", "")),
                product_name=str(row.get("Product", "")),
                normalize_product_name=str(row.get("Norm_Product", "")),
                review=str(row.get("Review", "")),
                rating=row.get("ratings"),
                date=row.get("date"),
                liked=_parse_affinity_column(row.get("liked_options", "")),
                disliked=_parse_affinity_column(row.get("disliked_options", "")),
                intention=str(row.get("user_intention", "")),
                mentioned_product_brands=_parse_json_list(row.get("mentioned_product_brands")),
                mentioned_product_names=_parse_json_list(row.get("mentioned_product_names")),
                mentioned_normalize_product_names=_parse_json_list(
                    row.get("mentioned_normalize_product_names")
                ),
                performance_tier=(row.get("performance_tier") or None),
                newness_preference_score=_try_parse_int(row.get("newness_preference_score")),
                newness_preference_notes=(row.get("newness_preference_notes") or None),
                price_range=(row.get("price_range") or None),
                alternative_openness=_try_parse_int(row.get("openness_to_alternatives")),
                misc_notes=(row.get("misc_notes") or None),
                upper_price_limit=_try_parse_float(row.get("upper_price_limit")),
            )
        )
    return personas


def load_personas(csv_path: Path) -> List[ReviewPersona]:
    df = pd.read_csv(csv_path)
    return load_personas_from_frame(df)
