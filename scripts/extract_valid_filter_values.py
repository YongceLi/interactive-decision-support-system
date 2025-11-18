#!/usr/bin/env python3
"""
Extract valid categorical filter values from database and save to JSON.

This script queries the database once to get all distinct values for categorical columns,
then saves them to config/valid_filter_values.json for use in filter validation.

Run this script whenever the database is updated with new data.

Usage:
    python scripts/extract_valid_filter_values.py
"""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

from idss_agent.tools.local_vehicle_store import LocalVehicleStore
from idss_agent.utils.logger import get_logger

logger = get_logger("scripts.extract_valid_filter_values")

# Define categorical columns to extract
# Map: filter_name -> actual_db_column
CATEGORICAL_COLUMNS = {
    "body_style": "norm_body_type",  # Uses normalized column
    "fuel_type": "norm_fuel_type",   # Uses normalized column
    "drivetrain": "drivetrain",      # Direct column
    "transmission": "transmission",  # Direct column
    # Skip colors - too many noisy values (3000+)
    # "exterior_color": "exterior_color",
    # "interior_color": "interior_color",
}


def extract_valid_values():
    """Extract valid values from database for all categorical columns."""
    logger.info("Extracting valid filter values from database...")

    store = LocalVehicleStore()
    valid_values = {}

    # Get database connection
    conn = store._connect()

    for filter_name, db_column in CATEGORICAL_COLUMNS.items():
        logger.info(f"  Querying {filter_name} (from {db_column})...")

        try:
            # Query distinct values for this column
            query = f"""
                SELECT DISTINCT {db_column}
                FROM unified_vehicle_listings
                WHERE {db_column} IS NOT NULL
                  AND {db_column} != ''
                ORDER BY {db_column}
            """

            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            # Extract values (lowercase and stripped)
            values = [row[0].strip().lower() for row in rows if row[0]]
            values = sorted(set(values))  # Remove duplicates and sort

            valid_values[filter_name] = values
            logger.info(f"    Found {len(values)} distinct values")

        except Exception as e:
            logger.error(f"    Error querying {filter_name}: {e}")
            valid_values[filter_name] = []

    # Close connection
    conn.close()

    return valid_values


def save_to_file(valid_values: dict, output_path: Path):
    """Save valid values to JSON file."""
    logger.info(f"Saving to {output_path}...")

    # Create config directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save with pretty formatting
    with open(output_path, 'w') as f:
        json.dump(valid_values, f, indent=2, sort_keys=True)

    logger.info(f"✓ Saved {len(valid_values)} categorical columns to {output_path}")


def main():
    """Main entry point."""
    output_path = project_root / "config" / "valid_filter_values.json"

    print("=" * 80)
    print("EXTRACTING VALID FILTER VALUES FROM DATABASE")
    print("=" * 80)
    print()

    # Extract from database
    valid_values = extract_valid_values()

    # Print summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for column, values in valid_values.items():
        print(f"  {column:20s}: {len(values):4d} values")
        if values:
            print(f"    Examples: {', '.join(values[:5])}")
    print()

    # Save to file
    save_to_file(valid_values, output_path)

    print()
    print("✓ Done! Valid values saved to:")
    print(f"  {output_path}")
    print()
    print("You can now use filter validation in your application.")
    print()


if __name__ == "__main__":
    main()
