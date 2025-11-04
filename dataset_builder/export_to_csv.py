"""
Export vehicle listings database to CSV format for visual inspection.
"""

import sqlite3
import csv
import sys
from pathlib import Path


def export_to_csv(db_path: str, csv_path: str, limit: int = None):
    """Export vehicle listings to CSV.

    Args:
        db_path: Path to SQLite database
        csv_path: Output CSV file path
        limit: Optional limit on number of rows to export
    """
    db_path = Path(db_path)
    csv_path = Path(csv_path)

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    print(f"Exporting {db_path} to {csv_path}...")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get total count
        cursor.execute("SELECT COUNT(*) FROM vehicle_listings")
        total = cursor.fetchone()[0]
        print(f"Total vehicles in database: {total}")

        # Query data (exclude raw_json for readability)
        query = """
        SELECT
            vin, year, make, model, trim, body_style,
            drivetrain, engine, fuel_type, transmission,
            doors, seats, exterior_color, interior_color,
            price, mileage, is_used, is_cpo,
            dealer_name, dealer_city, dealer_state, dealer_zip,
            longitude, latitude,
            primary_image_url, photo_count,
            vdp_url, carfax_url,
            listing_created_at, online, data_fetched_at
        FROM vehicle_listings
        ORDER BY make, model, year, price
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)

        # Get column names
        columns = [description[0] for description in cursor.description]

        # Write to CSV
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Write header
            writer.writerow(columns)

            # Write data
            row_count = 0
            for row in cursor:
                writer.writerow(row)
                row_count += 1

            print(f"Exported {row_count} rows to {csv_path}")
            print(f"File size: {csv_path.stat().st_size / 1024:.1f} KB")


def main():
    """Main entry point."""
    # Default: export test database
    db_path = "data/test_california_vehicles.db"
    csv_path = "data/test_california_vehicles.csv"

    # Check if user specified different paths
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    if len(sys.argv) > 2:
        csv_path = sys.argv[2]

    export_to_csv(db_path, csv_path)

    print(f"\nYou can now open the CSV file in:")
    print(f"  - Excel")
    print(f"  - Google Sheets")
    print(f"  - Any text editor")
    print(f"\nTo export the full database later:")
    print(f"  python dataset_builder/export_to_csv.py data/california_vehicles.db data/california_vehicles.csv")


if __name__ == "__main__":
    main()
