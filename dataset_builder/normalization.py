"""Helpers for normalizing unified vehicle listing attributes."""

from __future__ import annotations

import re
from typing import Optional

_ALLOWED_BODY_TYPES = {
    "Car Van",
    "Cargo Van",
    "Chassis Cab",
    "Combi",
    "Convertible",
    "Coupe",
    "Cutaway",
    "Hatchback",
    "Micro Car",
    "Mini Mpv",
    "Minivan",
    "Passenger Van",
    "Pickup",
    "SUV",
    "Sedan",
    "Targa",
    "Van",
    "Wagon",
}

_BODY_TYPE_CANONICAL = {value.lower(): value for value in _ALLOWED_BODY_TYPES}

_BODY_TYPE_ALIASES = {
    "crew cab pickup": "Pickup",
    "extended cab pickup": "Pickup",
    "regular cab pickup": "Pickup",
    "4dr suv": "SUV",
    "2dr suv": "SUV",
    "convertible suv": "SUV",
    "4dr hatchback": "Hatchback",
    "2dr hatchback": "Hatchback",
    "passenger minivan": "Minivan",
    "cargo minivan": "Minivan",
    "microcar": "Micro Car",
}

_ALLOWED_FUEL_TYPES = {
    "Gasoline",
    "Electric",
    "Diesel",
    "Hydrogen",
    "Hybrid (Electric + Hydrogen)",
    "Hybrid (Electric + Gasoline)",
}

_FUEL_TYPE_CANONICAL = {value.lower(): value for value in _ALLOWED_FUEL_TYPES}


def _normalize_text(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = cleaned.replace("-", " ")
    cleaned = cleaned.replace("/", " / ")
    cleaned = re.sub(r"[^a-z0-9/\s]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _canonical_body_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = _normalize_text(value)
    if not normalized:
        return None
    alias = _BODY_TYPE_ALIASES.get(normalized)
    if alias:
        return alias
    direct = _BODY_TYPE_CANONICAL.get(normalized)
    if direct:
        return direct
    title = value.strip().lower()
    direct = _BODY_TYPE_CANONICAL.get(re.sub(r"\s+", " ", title))
    if direct:
        return direct
    return None


def normalize_body_type(body_style: Optional[str], build_body_type: Optional[str]) -> Optional[str]:
    for candidate in (build_body_type, body_style):
        canonical = _canonical_body_type(candidate)
        if canonical:
            return canonical
    return None


def _canonical_fuel_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = _normalize_text(value)
    if not normalized:
        return None

    direct = _FUEL_TYPE_CANONICAL.get(normalized)
    if direct:
        return direct

    if "electric" in normalized and "hydrogen" in normalized:
        return "Hybrid (Electric + Hydrogen)"
    if "electric" in normalized and (
        "gas" in normalized
        or "unleaded" in normalized
        or "premium" in normalized
        or "hybrid" in normalized
        or "plug" in normalized
        or "e85" in normalized
        or "flex" in normalized
    ):
        return "Hybrid (Electric + Gasoline)"
    if "hybrid" in normalized:
        if "hydrogen" in normalized:
            return "Hybrid (Electric + Hydrogen)"
        return "Hybrid (Electric + Gasoline)"
    if "electric" in normalized:
        return "Electric"
    if "hydrogen" in normalized:
        return "Hydrogen"
    if "diesel" in normalized:
        return "Diesel"
    return "Gasoline"


def normalize_fuel_type(fuel_type: Optional[str], build_fuel_type: Optional[str]) -> Optional[str]:
    for candidate in (build_fuel_type, fuel_type):
        canonical = _canonical_fuel_type(candidate)
        if canonical:
            return canonical
    return None


def _coerce_bool(value: Optional[object]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return 1 if value != 0 else 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "none", "null"}:
            return None
        if normalized in {"true", "t", "yes", "y", "1"}:
            return 1
        if normalized in {"false", "f", "no", "n", "0"}:
            return 0
        try:
            return 1 if float(normalized) != 0 else 0
        except ValueError:
            return None
    return None


def normalize_is_used(is_used: Optional[object], year: Optional[object]) -> Optional[int]:
    value = _coerce_bool(is_used)
    if value is not None:
        return value

    year_value: Optional[int] = None
    if isinstance(year, int):
        year_value = year
    elif isinstance(year, str):
        try:
            year_value = int(year.strip())
        except ValueError:
            year_value = None
    if year_value in {2025, 2026}:
        return 1
    return 0


__all__ = [
    "normalize_body_type",
    "normalize_fuel_type",
    "normalize_is_used",
]
