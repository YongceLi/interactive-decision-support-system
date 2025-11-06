"""Merge Auto.dev and Marketcheck vehicle listing databases into a unified schema.

This script reads one or more SQLite databases that follow the Auto.dev
(`vehicle_listings`) or Marketcheck (`marketcheck_listings`) schemas, converts
each row into a unified shape, and writes the deduplicated results into a new
SQLite database. When the same VIN exists in multiple sources, the
Marketcheck record is preferred over the Auto.dev record as it usually
contains richer data.

Example usage
-------------

```bash
python dataset_builder/merge_sqlite_datasets.py \
    data/unified_vehicles.db \
    data/california_vehicles.db \
    data/marketcheck_vehicles.db
```

The resulting database will contain a single table named
`unified_vehicle_listings` that matches the schema stored in
`dataset_builder/unified_schema.sql`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

LOGGER = logging.getLogger("merge_datasets")


UNIFIED_COLUMNS = [
    "vin",
    "listing_id",
    "heading",
    "source",
    "price",
    "mileage",
    "msrp",
    "ref_price",
    "price_change_percent",
    "ref_price_dt",
    "ref_miles",
    "ref_miles_dt",
    "listing_created_at",
    "online",
    "first_seen_at",
    "first_seen_at_date",
    "first_seen_at_source",
    "first_seen_at_source_date",
    "first_seen_at_mc",
    "first_seen_at_mc_date",
    "last_seen_at",
    "last_seen_at_date",
    "scraped_at",
    "scraped_at_date",
    "data_fetched_at",
    "year",
    "make",
    "model",
    "trim",
    "body_style",
    "drivetrain",
    "engine",
    "fuel_type",
    "transmission",
    "doors",
    "seats",
    "exterior_color",
    "interior_color",
    "base_ext_color",
    "base_int_color",
    "build_year",
    "build_make",
    "build_model",
    "build_trim",
    "build_version",
    "build_body_type",
    "build_vehicle_type",
    "build_transmission",
    "build_drivetrain",
    "build_fuel_type",
    "build_engine",
    "build_doors",
    "build_cylinders",
    "build_std_seating",
    "build_highway_mpg",
    "build_city_mpg",
    "seller_type",
    "inventory_type",
    "availability_status",
    "is_certified",
    "is_cpo",
    "is_used",
    "in_transit",
    "model_code",
    "stock_number",
    "dealer_name",
    "dealer_city",
    "dealer_state",
    "dealer_zip",
    "dealer_phone",
    "dealer_latitude",
    "dealer_longitude",
    "dealer_country",
    "dealer_type",
    "dealer_msa_code",
    "dist",
    "vdp_url",
    "carfax_url",
    "primary_image_url",
    "photo_count",
    "media_json",
    "financing_options_json",
    "leasing_options_json",
    "dealer_json",
    "mc_dealership_json",
    "build_json",
    "data_source",
    "carfax_one_owner",
    "carfax_clean_title",
    "dom",
    "dom_180",
    "dom_active",
    "dos_active",
    "raw_json",
]


PRIORITY = {"autodev": 1, "marketcheck": 2}


def empty_record() -> Dict[str, Optional[object]]:
    """Create a dictionary with all unified columns set to ``None``."""

    return {column: None for column in UNIFIED_COLUMNS}


def to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_bool(value: object) -> Optional[int]:
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


def load_schema_sql() -> str:
    schema_path = Path(__file__).with_name("unified_schema.sql")
    return schema_path.read_text(encoding="utf-8")


def detect_dataset_type(connection: sqlite3.Connection) -> Optional[str]:
    cursor = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    if "marketcheck_listings" in tables:
        return "marketcheck"
    if "vehicle_listings" in tables:
        return "autodev"
    return None


def normalize_autodev_row(row_dict: Dict[str, object]) -> Dict[str, Optional[object]]:
    record = empty_record()
    record.update(
        {
            "vin": row_dict.get("vin"),
            "source": "autodev",
            "price": to_int(row_dict.get("price")),
            "mileage": to_int(row_dict.get("mileage")),
            "listing_created_at": row_dict.get("listing_created_at"),
            "online": to_bool(row_dict.get("online")),
            "data_fetched_at": row_dict.get("data_fetched_at"),
            "year": to_int(row_dict.get("year")),
            "make": row_dict.get("make"),
            "model": row_dict.get("model"),
            "trim": row_dict.get("trim"),
            "body_style": row_dict.get("body_style"),
            "drivetrain": row_dict.get("drivetrain"),
            "engine": row_dict.get("engine"),
            "fuel_type": row_dict.get("fuel_type"),
            "transmission": row_dict.get("transmission"),
            "doors": to_int(row_dict.get("doors")),
            "seats": to_int(row_dict.get("seats")),
            "exterior_color": row_dict.get("exterior_color"),
            "interior_color": row_dict.get("interior_color"),
            "dealer_name": row_dict.get("dealer_name"),
            "dealer_city": row_dict.get("dealer_city"),
            "dealer_state": row_dict.get("dealer_state"),
            "dealer_zip": row_dict.get("dealer_zip"),
            "dealer_longitude": to_float(row_dict.get("longitude")),
            "dealer_latitude": to_float(row_dict.get("latitude")),
            "primary_image_url": row_dict.get("primary_image_url"),
            "photo_count": to_int(row_dict.get("photo_count")),
            "vdp_url": row_dict.get("vdp_url"),
            "carfax_url": row_dict.get("carfax_url"),
            "is_used": to_bool(row_dict.get("is_used")),
            "is_cpo": to_bool(row_dict.get("is_cpo")),
            "is_certified": to_bool(row_dict.get("is_cpo")),
            "raw_json": row_dict.get("raw_json"),
            "data_source": "autodev",
        }
    )

    # Populate Marketcheck build fields with the best available Auto.dev data.
    record.setdefault("build_year", record["year"])
    record.setdefault("build_make", record["make"])
    record.setdefault("build_model", record["model"])
    record.setdefault("build_trim", record["trim"])
    record.setdefault("build_body_type", record["body_style"])
    record.setdefault("build_fuel_type", record["fuel_type"])
    record.setdefault("build_transmission", record["transmission"])
    record.setdefault("build_drivetrain", record["drivetrain"])
    record.setdefault("build_engine", record["engine"])
    record.setdefault("build_doors", record["doors"])
    seats_value = row_dict.get("seats")
    if seats_value is not None:
        record.setdefault("build_std_seating", str(seats_value))

    return record


def normalize_marketcheck_row(row_dict: Dict[str, object]) -> Dict[str, Optional[object]]:
    record = empty_record()

    inventory_type = row_dict.get("inventory_type")
    is_used = None
    if isinstance(inventory_type, str):
        normalized = inventory_type.strip().lower()
        if normalized == "used":
            is_used = 1
        elif normalized == "new":
            is_used = 0

    record.update(
        {
            "vin": row_dict.get("vin"),
            "listing_id": row_dict.get("listing_id"),
            "heading": row_dict.get("heading"),
            "source": "marketcheck",
            "price": to_int(row_dict.get("price")),
            "mileage": to_int(row_dict.get("miles")),
            "msrp": to_int(row_dict.get("msrp")),
            "ref_price": to_int(row_dict.get("ref_price")),
            "price_change_percent": to_float(row_dict.get("price_change_percent")),
            "ref_price_dt": to_int(row_dict.get("ref_price_dt")),
            "ref_miles": to_int(row_dict.get("ref_miles")),
            "ref_miles_dt": to_int(row_dict.get("ref_miles_dt")),
            "first_seen_at": to_int(row_dict.get("first_seen_at")),
            "first_seen_at_date": row_dict.get("first_seen_at_date"),
            "first_seen_at_source": to_int(row_dict.get("first_seen_at_source")),
            "first_seen_at_source_date": row_dict.get("first_seen_at_source_date"),
            "first_seen_at_mc": to_int(row_dict.get("first_seen_at_mc")),
            "first_seen_at_mc_date": row_dict.get("first_seen_at_mc_date"),
            "last_seen_at": to_int(row_dict.get("last_seen_at")),
            "last_seen_at_date": row_dict.get("last_seen_at_date"),
            "scraped_at": to_int(row_dict.get("scraped_at")),
            "scraped_at_date": row_dict.get("scraped_at_date"),
            "data_fetched_at": row_dict.get("fetched_at"),
            "exterior_color": row_dict.get("exterior_color"),
            "interior_color": row_dict.get("interior_color"),
            "base_ext_color": row_dict.get("base_ext_color"),
            "base_int_color": row_dict.get("base_int_color"),
            "dom": to_int(row_dict.get("dom")),
            "dom_180": to_int(row_dict.get("dom_180")),
            "dom_active": to_int(row_dict.get("dom_active")),
            "dos_active": to_int(row_dict.get("dos_active")),
            "seller_type": row_dict.get("seller_type"),
            "inventory_type": inventory_type,
            "availability_status": row_dict.get("availability_status"),
            "is_certified": to_bool(row_dict.get("is_certified")),
            "is_cpo": to_bool(row_dict.get("is_certified")),
            "is_used": is_used,
            "stock_number": row_dict.get("stock_no"),
            "data_source": row_dict.get("data_source"),
            "vdp_url": row_dict.get("vdp_url"),
            "carfax_one_owner": to_bool(row_dict.get("carfax_1_owner")),
            "carfax_clean_title": to_bool(row_dict.get("carfax_clean_title")),
            "dealer_name": row_dict.get("dealer_name"),
            "dealer_city": row_dict.get("dealer_city"),
            "dealer_state": row_dict.get("dealer_state"),
            "dealer_zip": row_dict.get("dealer_zip"),
            "dealer_phone": row_dict.get("dealer_phone"),
            "dealer_latitude": to_float(row_dict.get("dealer_latitude")),
            "dealer_longitude": to_float(row_dict.get("dealer_longitude")),
            "dealer_country": row_dict.get("dealer_country"),
            "dealer_type": row_dict.get("dealer_type"),
            "dealer_msa_code": row_dict.get("dealer_msa_code"),
            "dist": to_float(row_dict.get("dist")),
            "media_json": row_dict.get("media_json"),
            "financing_options_json": row_dict.get("financing_options_json"),
            "leasing_options_json": row_dict.get("leasing_options_json"),
            "dealer_json": row_dict.get("dealer_json"),
            "mc_dealership_json": row_dict.get("mc_dealership_json"),
            "build_json": row_dict.get("build_json"),
            "build_year": to_int(row_dict.get("build_year")),
            "build_make": row_dict.get("build_make"),
            "build_model": row_dict.get("build_model"),
            "build_trim": row_dict.get("build_trim"),
            "build_version": row_dict.get("build_version"),
            "build_body_type": row_dict.get("build_body_type"),
            "build_vehicle_type": row_dict.get("build_vehicle_type"),
            "build_transmission": row_dict.get("build_transmission"),
            "build_drivetrain": row_dict.get("build_drivetrain"),
            "build_fuel_type": row_dict.get("build_fuel_type"),
            "build_engine": row_dict.get("build_engine"),
            "build_doors": to_int(row_dict.get("build_doors")),
            "build_cylinders": to_int(row_dict.get("build_cylinders")),
            "build_std_seating": row_dict.get("build_std_seating"),
            "build_highway_mpg": to_int(row_dict.get("build_highway_mpg")),
            "build_city_mpg": to_int(row_dict.get("build_city_mpg")),
            "in_transit": to_bool(row_dict.get("in_transit")),
            "model_code": row_dict.get("model_code"),
            "raw_json": row_dict.get("raw_json"),
        }
    )

    # Prefer Marketcheck build data for core vehicle description when available.
    if record["build_year"] is not None:
        record["year"] = record["build_year"]
    if record["build_make"]:
        record["make"] = record["build_make"]
    if record["build_model"]:
        record["model"] = record["build_model"]
    if record["build_trim"]:
        record["trim"] = record["build_trim"]
    if record["build_body_type"]:
        record["body_style"] = record["build_body_type"]
    if record["build_transmission"]:
        record["transmission"] = record["build_transmission"]
    if record["build_drivetrain"]:
        record["drivetrain"] = record["build_drivetrain"]
    if record["build_fuel_type"]:
        record["fuel_type"] = record["build_fuel_type"]
    if record["build_engine"]:
        record["engine"] = record["build_engine"]
    if record["build_doors"] is not None:
        record["doors"] = record["build_doors"]

    return record


def iter_rows(connection: sqlite3.Connection, table_name: str) -> Iterable[Dict[str, object]]:
    connection.row_factory = sqlite3.Row
    cursor = connection.execute(f"SELECT * FROM {table_name}")
    for row in cursor:
        yield dict(row)


def accumulate_records(input_paths: Iterable[Path]) -> Dict[str, Tuple[int, Dict[str, object]]]:
    aggregated: Dict[str, Tuple[int, Dict[str, object]]] = {}
    for path in input_paths:
        LOGGER.info("Processing %s", path)
        with sqlite3.connect(path) as conn:
            dataset_type = detect_dataset_type(conn)
            if dataset_type is None:
                LOGGER.warning("Skipping %s (no known tables)", path)
                continue

            priority = PRIORITY[dataset_type]
            table_name = "marketcheck_listings" if dataset_type == "marketcheck" else "vehicle_listings"
            normalizer = (
                normalize_marketcheck_row
                if dataset_type == "marketcheck"
                else normalize_autodev_row
            )

            for row in iter_rows(conn, table_name):
                normalized = normalizer(row)
                vin = normalized.get("vin")
                if not vin:
                    continue
                if normalized.get("raw_json") is None:
                    # Guarantee raw_json is always populated to satisfy NOT NULL constraint.
                    normalized["raw_json"] = json.dumps(row, ensure_ascii=False)

                current = aggregated.get(vin)
                if current is None or priority >= current[0]:
                    aggregated[vin] = (priority, normalized)

    return aggregated


def write_output(output_path: Path, records: Dict[str, Tuple[int, Dict[str, object]]]) -> None:
    with sqlite3.connect(output_path) as conn:
        conn.executescript(load_schema_sql())
        insert_sql = (
            "INSERT OR REPLACE INTO unified_vehicle_listings ("
            + ", ".join(UNIFIED_COLUMNS)
            + ") VALUES ("
            + ", ".join(["?"] * len(UNIFIED_COLUMNS))
            + ")"
        )
        with conn:
            for _, record in records.values():
                values = [record.get(column) for column in UNIFIED_COLUMNS]
                conn.execute(insert_sql, values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge Auto.dev and Marketcheck SQLite datasets into a unified schema."
    )
    parser.add_argument(
        "output_db",
        type=Path,
        help="Path to the output SQLite database that will contain the unified table.",
    )
    parser.add_argument(
        "input_dbs",
        nargs="+",
        type=Path,
        help="One or more SQLite databases generated by Auto.dev or Marketcheck scripts.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output database if it already exists.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Configure the log level (e.g. DEBUG, INFO, WARNING).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(message)s")

    if args.output_db.exists():
        if args.overwrite:
            LOGGER.info("Overwriting existing output database at %s", args.output_db)
            os.remove(args.output_db)
        else:
            raise SystemExit(
                f"Output database {args.output_db} already exists. Use --overwrite to replace it."
            )

    records = accumulate_records(args.input_dbs)
    LOGGER.info("Writing %d unique VINs to %s", len(records), args.output_db)
    write_output(args.output_db, records)
    LOGGER.info("Done")


if __name__ == "__main__":
    main()
