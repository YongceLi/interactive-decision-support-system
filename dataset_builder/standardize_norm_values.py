"""Standardize normalized vehicle attributes to a canonical set of values.

This script cleans ``norm_body_type`` and ``norm_fuel_type`` in the
``unified_vehicle_listings`` table so that only the expected canonical values
remain. Non-canonical values (including lowercase variants) are mapped to their
canonical counterparts; unknown values are set to ``NULL``.

Usage:
    python dataset_builder/standardize_norm_values.py --db data/car_dataset_idss/uni_vehicles.db

"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

LOGGER = logging.getLogger(__name__)

DEFAULT_DB = Path("data/car_dataset_idss/uni_vehicles.db")

CANONICAL_BODY_TYPES = [
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
]

CANONICAL_FUEL_TYPES = [
    "Diesel",
    "Electric",
    "Gasoline",
    "Hybrid (Electric + Gasoline)",
    "Hybrid (Electric + Hydrogen)",
    "Hydrogen",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Standardize norm_body_type and norm_fuel_type values in the"
            " unified_vehicle_listings table."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to the SQLite database to clean.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (e.g. DEBUG, INFO, WARNING).",
    )
    return parser.parse_args()


def build_mapping(canonicals: Iterable[str], aliases: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
    mapping: Dict[str, Optional[str]] = {}
    for value in canonicals:
        mapping[value] = value
        mapping[value.lower()] = value
    if aliases:
        mapping.update(aliases)
    return mapping


def standardize_value(value: str, mapping: Dict[str, Optional[str]]) -> Optional[str]:
    trimmed = value.strip()
    if not trimmed:
        return None
    lowered = trimmed.lower()
    if trimmed in mapping:
        return mapping[trimmed]
    if lowered in mapping:
        return mapping[lowered]
    return None


def standardize_column(
    connection: sqlite3.Connection,
    column: str,
    mapping: Dict[str, Optional[str]],
) -> Tuple[int, int]:
    cursor = connection.execute(
        f"SELECT rowid, {column} FROM unified_vehicle_listings WHERE {column} IS NOT NULL"
    )
    updates = 0
    cleared = 0

    with connection:
        for rowid, value in cursor.fetchall():
            new_value = standardize_value(value, mapping)
            if new_value == value:
                continue
            connection.execute(
                f"UPDATE unified_vehicle_listings SET {column} = ? WHERE rowid = ?",
                (new_value, rowid),
            )
            updates += 1
            if new_value is None:
                cleared += 1

    return updates, cleared


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(message)s")

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    body_aliases = {
        "convertible": "Convertible",
        "coupe": "Coupe",
        "hatchback": "Hatchback",
        "minivan": "Minivan",
        "pickup": "Pickup",
        "sedan": "Sedan",
        "van": "Van",
        "wagon": "Wagon",
    }
    body_mapping = build_mapping(CANONICAL_BODY_TYPES, aliases=body_aliases)

    fuel_aliases = {
        "diesel": "Diesel",
        "electric": "Electric",
        "gasoline": "Gasoline",
        "hybrid": "Hybrid (Electric + Gasoline)",
        "plug-in hybrid": "Hybrid (Electric + Gasoline)",
    }
    fuel_mapping = build_mapping(CANONICAL_FUEL_TYPES, aliases=fuel_aliases)

    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        body_updates, body_cleared = standardize_column(connection, "norm_body_type", body_mapping)
        fuel_updates, fuel_cleared = standardize_column(connection, "norm_fuel_type", fuel_mapping)

    LOGGER.info(
        "Standardized body types: %d updates (%d cleared to NULL)", body_updates, body_cleared
    )
    LOGGER.info(
        "Standardized fuel types: %d updates (%d cleared to NULL)", fuel_updates, fuel_cleared
    )


if __name__ == "__main__":
    main()
