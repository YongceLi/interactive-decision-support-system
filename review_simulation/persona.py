"""Utilities for loading and representing review-derived personas."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pandas as pd


@dataclass
class VehicleAffinity:
    """Represents a liked or disliked vehicle configuration."""

    make: Optional[str]
    model: Optional[str]
    year: Optional[int]
    condition: Optional[str]
    rationale: Optional[str]

    @classmethod
    def from_dict(cls, data: dict) -> "VehicleAffinity":
        return cls(
            make=data.get("make"),
            model=data.get("model"),
            year=data.get("year"),
            condition=(data.get("condition") or None),
            rationale=data.get("rationale"),
        )


@dataclass
class ReviewPersona:
    """Persona constructed from a single enriched review entry."""

    make: str
    model: str
    review: str
    rating: Optional[float]
    date: Optional[str]
    liked: List[VehicleAffinity] = field(default_factory=list)
    disliked: List[VehicleAffinity] = field(default_factory=list)
    intention: str = ""

    @property
    def rating_value(self) -> Optional[float]:
        try:
            return float(self.rating) if self.rating is not None else None
        except (TypeError, ValueError):
            return None


def _parse_affinity_column(value: str) -> List[VehicleAffinity]:
    if not value or (isinstance(value, float) and pd.isna(value)):
        return []
    try:
        raw_list = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(raw_list, dict):
        raw_list = [raw_list]
    affinities: List[VehicleAffinity] = []
    for item in raw_list:
        if isinstance(item, dict):
            affinities.append(VehicleAffinity.from_dict(item))
    return affinities


def load_personas(csv_path: Path) -> List[ReviewPersona]:
    df = pd.read_csv(csv_path)
    personas: List[ReviewPersona] = []
    for _, row in df.iterrows():
        personas.append(
            ReviewPersona(
                make=str(row.get("Make", "")),
                model=str(row.get("Model", "")),
                review=str(row.get("Review", "")),
                rating=row.get("ratings"),
                date=row.get("date"),
                liked=_parse_affinity_column(row.get("liked_options", "")),
                disliked=_parse_affinity_column(row.get("disliked_options", "")),
                intention=str(row.get("user_intention", "")),
            )
        )
    return personas
