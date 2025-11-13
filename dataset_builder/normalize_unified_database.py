"""Populate normalized body type, fuel type, and usage columns in the unified schema."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Tuple

from dataset_builder.normalization import (
    normalize_body_type,
    normalize_fuel_type,
    normalize_is_used,
)

LOGGER = logging.getLogger("normalize_unified_db")


NORMALIZED_COLUMNS: Dict[str, str] = {
    "norm_body_type": "TEXT",
    "norm_fuel_type": "TEXT",
    "norm_is_used": "INTEGER",
}


def ensure_columns(connection: sqlite3.Connection) -> None:
    cursor = connection.execute("PRAGMA table_info(unified_vehicle_listings)")
    existing = {row[1] for row in cursor.fetchall()}
    for column, definition in NORMALIZED_COLUMNS.items():
        if column not in existing:
            LOGGER.info("Adding missing column %s %s", column, definition)
            connection.execute(
                f"ALTER TABLE unified_vehicle_listings ADD COLUMN {column} {definition}"
            )


def iter_rows(connection: sqlite3.Connection) -> Iterable[Tuple[str, str, str, str, str, object, object]]:
    cursor = connection.execute(
        "SELECT vin, body_style, build_body_type, fuel_type, build_fuel_type, is_used, year "
        "FROM unified_vehicle_listings"
    )
    for row in cursor:
        yield row


def update_records(connection: sqlite3.Connection) -> int:
    updates = []
    for vin, body_style, build_body_type, fuel_type, build_fuel_type, is_used, year in iter_rows(
        connection
    ):
        norm_body = normalize_body_type(body_style, build_body_type)
        norm_fuel = normalize_fuel_type(fuel_type, build_fuel_type)
        norm_used = normalize_is_used(is_used, year)
        updates.append((norm_body, norm_fuel, norm_used, vin))

    if not updates:
        return 0

    connection.executemany(
        "UPDATE unified_vehicle_listings "
        "SET norm_body_type = ?, norm_fuel_type = ?, norm_is_used = ? "
        "WHERE vin = ?",
        updates,
    )
    return len(updates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate normalized body type, fuel type, and usage flags in an existing unified database."
        )
    )
    parser.add_argument(
        "database",
        type=Path,
        help="Path to the SQLite database created with unified_schema.sql.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (e.g. DEBUG, INFO, WARNING).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(message)s")

    if not args.database.exists():
        raise SystemExit(f"Database {args.database} does not exist")

    with sqlite3.connect(args.database) as connection:
        ensure_columns(connection)
        with connection:
            total = update_records(connection)
        LOGGER.info("Updated normalized columns for %d rows", total)


if __name__ == "__main__":
    main()
