#!/usr/bin/env python3
"""
Test vehicle description generation to verify format makes sense.
"""
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def generate_vehicle_description(vehicle: Dict[str, Any]) -> str:
    """
    Convert structured vehicle data into natural language description.
    This is what the language model embedding will encode.

    Handles both formats:
    - Unified format (flat with "build" and "dealer" objects)
    - Auto.dev format (nested with "vehicle" and "retailListing" objects)
    """
    # Check which format we have
    is_unified = "data_source" in vehicle or "build" in vehicle

    if is_unified:
        # Unified format: extract from top-level and "build" object
        build = vehicle.get("build", {})
        dealer = vehicle.get("dealer", {})

        v_year = build.get("year") or vehicle.get("year")
        v_make = build.get("make") or vehicle.get("make")
        v_model = build.get("model") or vehicle.get("model")
        v_trim = build.get("trim") or vehicle.get("trim")
        v_body_style = build.get("body_type") or vehicle.get("body_style")
        v_engine = build.get("engine") or vehicle.get("engine")
        v_fuel = build.get("fuel_type") or vehicle.get("fuel_type")
        v_drivetrain = build.get("drivetrain") or vehicle.get("drivetrain")
        v_transmission = build.get("transmission") or vehicle.get("transmission")
        v_doors = build.get("doors") or vehicle.get("doors")
        v_seats = build.get("std_seating") or vehicle.get("seats")
        v_exterior_color = vehicle.get("exterior_color")
        v_interior_color = vehicle.get("interior_color")

        r_price = vehicle.get("price")
        r_miles = vehicle.get("miles") or vehicle.get("mileage")
        r_used = vehicle.get("inventory_type") == "used"
        r_cpo = vehicle.get("is_certified") or False
        r_city = dealer.get("city")
        r_state = dealer.get("state")
    else:
        # Auto.dev format: nested structure
        v = vehicle.get("vehicle", {})
        r = vehicle.get("retailListing", {})

        v_year = v.get("year")
        v_make = v.get("make")
        v_model = v.get("model")
        v_trim = v.get("trim")
        v_body_style = v.get("bodyStyle") or v.get("style")
        v_engine = v.get("engine")
        v_fuel = v.get("fuel")
        v_drivetrain = v.get("drivetrain")
        v_transmission = v.get("transmission")
        v_doors = v.get("doors")
        v_seats = v.get("seats")
        v_exterior_color = v.get("exteriorColor")
        v_interior_color = v.get("interiorColor")

        r_price = r.get("price")
        r_miles = r.get("miles")
        r_used = r.get("used", True)
        r_cpo = r.get("cpo", False)
        r_city = r.get("city")
        r_state = r.get("state")

    # Build description parts
    parts = []

    # Core identity
    if v_year and v_make and v_model:
        identity = f"{v_year} {v_make} {v_model}"
        if v_trim:
            identity += f" {v_trim}"
        parts.append(identity)

    # Body and type
    if v_body_style:
        parts.append(f"{v_body_style} body style")

    # Powertrain
    if v_engine:
        parts.append(f"{v_engine} engine")
    if v_fuel:
        parts.append(f"{v_fuel} fuel")
    if v_drivetrain:
        parts.append(f"{v_drivetrain} drivetrain")
    if v_transmission:
        parts.append(f"{v_transmission} transmission")

    # Capacity
    if v_seats:
        parts.append(f"{v_seats} seats")
    if v_doors:
        parts.append(f"{v_doors} doors")

    # Colors
    if v_exterior_color:
        parts.append(f"{v_exterior_color} exterior")
    if v_interior_color:
        parts.append(f"{v_interior_color} interior")

    # Price and condition
    if r_price:
        parts.append(f"${r_price:,}")
    if r_miles:
        parts.append(f"{r_miles:,} miles")
    if r_used:
        parts.append("used vehicle")
    else:
        parts.append("new vehicle")
    if r_cpo:
        parts.append("certified pre-owned")

    # Location
    if r_city and r_state:
        parts.append(f"located in {r_city}, {r_state}")

    return ". ".join(parts) + "." if parts else "vehicle"


def test_descriptions():
    """Test description generation on sample vehicles."""
    db_path = Path("data/car_dataset_idss/uni_vehicles.db")

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get 10 diverse sample vehicles
    cursor.execute("""
        SELECT vin, raw_json
        FROM unified_vehicle_listings
        ORDER BY RANDOM()
        LIMIT 10
    """)

    print("=" * 80)
    print("Vehicle Description Generation Test")
    print("=" * 80)

    for i, row in enumerate(cursor, 1):
        vin = row["vin"]
        try:
            vehicle_data = json.loads(row["raw_json"])
            description = generate_vehicle_description(vehicle_data)

            print(f"\n{i}. VIN: {vin}")
            print(f"   Description: {description}")
            print(f"   Length: {len(description)} characters")

        except Exception as e:
            print(f"\n{i}. VIN: {vin}")
            print(f"   ERROR: {e}")

    print("\n" + "=" * 80)

    conn.close()


if __name__ == "__main__":
    test_descriptions()
