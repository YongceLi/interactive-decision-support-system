"""
Local vehicle data access layer backed by SQLite.

Provides filtered queries against the prebuilt uni_vehicles.db dataset
and returns results shaped like the Auto.dev payloads expected by downstream
components.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from idss_agent.utils.logger import get_logger

logger = get_logger("tools.local_vehicle_store")


def _project_root() -> Path:
    """Return project root (parent of idss_agent package)."""
    return Path(__file__).resolve().parent.parent.parent


DEFAULT_DB_PATH = _project_root() / "data" / "car_dataset_idss" / "uni_vehicles.db"


class VehicleStoreError(RuntimeError):
    """Raised when the local vehicle store encounters an error."""


def _format_sql_with_params(sql: str, params: Sequence[Any]) -> str:
    """Return human-readable SQL with positional parameters substituted for logging."""
    formatted = sql
    for value in params:
        replacement = repr(value)
        formatted = formatted.replace("?", replacement, 1)
    return formatted


def _parse_numeric_range(value: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse numeric range strings like "10000-30000" or "2020".

    Returns:
        Tuple[min_value, max_value] where any element can be None.
    """
    if not value:
        return (None, None)

    value = value.strip()
    if "-" not in value:
        try:
            num = float(value)
            return (num, num)
        except ValueError:
            return (None, None)

    lower, upper = value.split("-", 1)
    lower_val = float(lower) if lower.strip() else None
    upper_val = float(upper) if upper.strip() else None
    return (lower_val, upper_val)


def _split_multi_value(text: str) -> List[str]:
    """Split comma-separated filters into individual trimmed values."""
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _haversine_distance_sql(user_lat: float, user_lon: float) -> str:
    """
    Generate SQL expression for haversine distance calculation in miles.

    Returns SQL expression that calculates distance from user location to vehicle's dealer location.
    Formula: https://en.wikipedia.org/wiki/Haversine_formula

    Args:
        user_lat: User's latitude
        user_lon: User's longitude

    Returns:
        SQL expression string for distance calculation in miles
    """
    # Earth's radius in miles
    earth_radius = 3959.0

    # Convert degrees to radians in SQL
    # SQLite uses radians for trig functions
    return f"""
        ({earth_radius} * 2 * ASIN(SQRT(
            POW(SIN((RADIANS(dealer_latitude) - RADIANS({user_lat})) / 2), 2) +
            COS(RADIANS({user_lat})) * COS(RADIANS(dealer_latitude)) *
            POW(SIN((RADIANS(dealer_longitude) - RADIANS({user_lon})) / 2), 2)
        )))
    """


@dataclass
class LocalVehicleStore:
    """
    Thin repository for vehicle listings stored in SQLite.

    Args:
        db_path: Optional override for database location.
        require_photos: Whether to filter listings to those with photo metadata.
    """

    db_path: Optional[Path] = None
    require_photos: bool = True

    def __post_init__(self) -> None:
        path = Path(self.db_path) if self.db_path else DEFAULT_DB_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Local vehicle database not found at {path}. "
                "Build it via dataset_builder/fetch_california_dataset.py."
            )
        self.db_path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def search_listings(
        self,
        filters: Dict[str, Any],
        limit: int = 60,
        offset: int = 0,
        order_by: str = "price",
        order_dir: str = "ASC",
        user_latitude: Optional[float] = None,
        user_longitude: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a filtered search against the local database.

        Args:
            filters: Explicit filter dictionary (VehicleFilters).
            limit: Maximum number of rows to return.
            offset: Offset for pagination.
            order_by: Column to sort by (price, mileage, year).
            order_dir: Sort direction ("ASC" or "DESC").
            user_latitude: Optional user latitude for distance filtering.
            user_longitude: Optional user longitude for distance filtering.

        Returns:
            List of listing payloads shaped like Auto.dev responses.
        """
        sql, params = self._build_query(
            filters,
            limit,
            offset,
            order_by,
            order_dir,
            user_latitude,
            user_longitude,
        )
        sql_single_line = " ".join(sql.split())
        logger.info(
            "Recommendation SQL query: %s",
            _format_sql_with_params(sql_single_line, params),
        )
        logger.debug("Executing local vehicle query: %s | params=%s", sql, params)

        try:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise VehicleStoreError(f"SQLite query failed: {exc}") from exc

        payloads: List[Dict[str, Any]] = []
        for row in rows:
            payload = self._row_to_payload(row)
            if payload:
                payloads.append(payload)

        logger.info("Local vehicle query returned %d listings", len(payloads))
        return payloads

    def get_by_vin(self, vin: str) -> Optional[Dict[str, Any]]:
        """Fetch a single listing by VIN."""
        if not vin:
            return None

        sql = "SELECT raw_json FROM unified_vehicle_listings WHERE vin = ? LIMIT 1"

        try:
            with self._connect() as conn:
                row = conn.execute(sql, (vin.upper(),)).fetchone()
        except sqlite3.Error as exc:
            raise VehicleStoreError(f"Failed to load VIN {vin}: {exc}") from exc

        return self._row_to_payload(row) if row else None

    # ------------------------------------------------------------------ #
    # Query construction helpers
    # ------------------------------------------------------------------ #

    def _build_query(
        self,
        filters: Dict[str, Any],
        limit: int,
        offset: int,
        order_by: str,
        order_dir: str,
        user_latitude: Optional[float] = None,
        user_longitude: Optional[float] = None,
    ) -> Tuple[str, Tuple[Any, ...]]:
        """Construct SQL query and parameter tuple from explicit filters."""
        select_clause = """SELECT raw_json, price, mileage, primary_image_url, photo_count,
            year, make, model, trim, body_style, drivetrain, engine, fuel_type, transmission,
            doors, seats, exterior_color, interior_color,
            dealer_name, dealer_city, dealer_state, dealer_zip, dealer_latitude, dealer_longitude,
            is_used, is_cpo, vdp_url, carfax_url, vin
            FROM unified_vehicle_listings"""
        conditions: List[str] = []
        params: List[Any] = []

        def add_condition(condition: str, values: Iterable[Any]) -> None:
            conditions.append(condition)
            params.extend(values)

        # Make / model / trim support multiple values
        for column, key in [
            ("make", "make"),
            ("model", "model"),
            ("trim", "trim"),
            ("body_style", "body_style"),
            ("engine", "engine"),
            ("transmission", "transmission"),
            ("drivetrain", "drivetrain"),
            ("fuel_type", "fuel_type"),
            ("exterior_color", "exterior_color"),
            ("interior_color", "interior_color"),
        ]:
            value = filters.get(key)
            values = _split_multi_value(value) if isinstance(value, str) else []
            if values:
                placeholders = ",".join(["?"] * len(values))
                add_condition(
                    f"UPPER({column}) IN ({placeholders})",
                    [v.upper() for v in values],
                )

        # Door count
        if filters.get("doors"):
            add_condition("doors = ?", (filters["doors"],))

        # Seating capacity maps to column `seats`
        if filters.get("seating_capacity"):
            add_condition("seats = ?", (filters["seating_capacity"],))

        # State filter (optional, for state-specific searches)
        if filters.get("state"):
            add_condition("UPPER(dealer_state) = ?", (filters["state"].upper(),))

        # Note: ZIP code filter removed - ZIP is now only used to lookup lat/long,
        # then search_radius filter applies geographic distance search

        # Search radius filter (requires user location - lat/long from browser OR ZIP lookup)
        if filters.get("search_radius") and user_latitude is not None and user_longitude is not None:
            radius_miles = filters["search_radius"]
            # Only include vehicles with valid lat/long coordinates
            conditions.append("dealer_latitude IS NOT NULL")
            conditions.append("dealer_longitude IS NOT NULL")
            # Add haversine distance calculation
            distance_expr = _haversine_distance_sql(user_latitude, user_longitude)
            conditions.append(f"({distance_expr}) <= {float(radius_miles)}")

        # Year range
        if filters.get("year"):
            lower, upper = _parse_numeric_range(str(filters["year"]))
            if lower is not None and upper is not None and lower == upper:
                add_condition("year = ?", (int(lower),))
            else:
                if lower is not None:
                    add_condition("year >= ?", (int(lower),))
                if upper is not None:
                    add_condition("year <= ?", (int(upper),))

        # Price range
        if filters.get("price"):
            lower, upper = _parse_numeric_range(str(filters["price"]))
            if lower is not None:
                add_condition("price >= ?", (int(lower),))
            if upper is not None:
                add_condition("price <= ?", (int(upper),))

        # Mileage range (vehicle odometer reading)
        if filters.get("mileage"):
            lower, upper = _parse_numeric_range(str(filters["mileage"]))
            if lower is not None:
                add_condition("mileage >= ?", (int(lower),))
            if upper is not None:
                add_condition("mileage <= ?", (int(upper),))

        # Require photos if configured
        if self.require_photos:
            conditions.append(
                "(COALESCE(photo_count, 0) > 0 OR primary_image_url IS NOT NULL)"
            )

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        order_column = {
            "price": "price",
            "mileage": "mileage",
            "year": "year",
        }.get(order_by.lower(), "price")

        # Fall back to ascending unless explicitly descending
        direction = "DESC" if order_dir.upper() == "DESC" else "ASC"

        sql = (
            f"{select_clause}{where_clause} "
            f"ORDER BY {order_column} {direction}, vin ASC "
            f"LIMIT ? OFFSET ?"
        )

        params.extend([limit, offset])
        return sql, tuple(params)

    @staticmethod
    def _row_to_payload(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        """Convert a SQLite row into the payload expected downstream."""
        if not row:
            return None

        raw_json = row["raw_json"]
        if raw_json:
            try:
                payload = json.loads(raw_json)
            except json.JSONDecodeError:
                logger.warning("Failed to parse raw_json for row")
                payload = {}
        else:
            payload = {}

        # Check if this is the new unified format (flat structure) vs old Auto.dev format (nested)
        # New format has fields like "heading", "data_source" at root level
        # Old format has "vehicle" and "retailListing" as nested objects
        is_unified_format = "data_source" in payload or ("vehicle" not in payload and "retailListing" not in payload)

        if is_unified_format:
            # Transform unified format to Auto.dev format expected by downstream code
            # Prefer database columns over raw_json values (database columns are normalized)
            vehicle_data = {
                "vin": row["vin"],
                "year": row["year"],
                "make": row["make"],
                "model": row["model"],
                "trim": row["trim"],
                "bodyStyle": row["body_style"],
                "drivetrain": row["drivetrain"],
                "engine": row["engine"],
                "fuel": row["fuel_type"],
                "transmission": row["transmission"],
                "doors": row["doors"],
                "seats": row["seats"],
                "exteriorColor": row["exterior_color"],
                "interiorColor": row["interior_color"],
            }

            # Extract retail listing info
            retail_data = {
                "price": row["price"],
                "miles": row["mileage"],
                "dealer": row["dealer_name"],
                "city": row["dealer_city"],
                "state": row["dealer_state"],
                "zip": row["dealer_zip"],
                "vdp": row["vdp_url"],
                "carfaxUrl": row["carfax_url"],
                "primaryImage": row["primary_image_url"],
                "photoCount": row["photo_count"],
                "used": row["is_used"] if row["is_used"] is not None else True,
                "cpo": row["is_cpo"] if row["is_cpo"] is not None else False,
            }

            # Reconstruct in Auto.dev format
            transformed_payload = {
                "@id": payload.get("id", f"unified/{row['vin']}"),
                "vin": row["vin"],
                "online": payload.get("online", True),
                "vehicle": vehicle_data,
                "retailListing": retail_data,
                "wholesaleListing": None,
            }

            # Keep original payload as metadata
            transformed_payload["_original"] = payload

            return transformed_payload
        else:
            # Old Auto.dev format - use existing logic
            retail_listing = payload.setdefault("retailListing", {})
            if row["price"] is not None:
                retail_listing.setdefault("price", row["price"])
            if row["mileage"] is not None:
                retail_listing.setdefault("miles", row["mileage"])

            # Backfill photo hint if missing
            if row["primary_image_url"] and not retail_listing.get("primaryImage"):
                retail_listing["primaryImage"] = row["primary_image_url"]
            if row["photo_count"] is not None and not retail_listing.get("photoCount"):
                retail_listing["photoCount"] = row["photo_count"]

            return payload

