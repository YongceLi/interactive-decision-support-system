"""
Export PC parts database to CSV format for visual inspection.
"""

import sqlite3
import csv
import sys
from pathlib import Path


def export_to_csv(db_path: str, csv_path: str, limit: int = None):
    """Export PC parts listings to CSV.

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
        cursor.execute("SELECT COUNT(*) FROM pc_parts")
        total = cursor.fetchone()[0]
        print(f"Total PC parts in database: {total}")

        # Query data (exclude JSON fields for readability, but include key fields)
        query = """
        SELECT
            product_id, slug, product_type, brand, series, model,
            size, color, price, year, seller,
            rating, rating_count,
            raw_name,
            created_at, updated_at
        FROM pc_parts
        ORDER BY product_type, brand, series, model, price
        """

        if limit:
            query += " LIMIT ?"
            cursor.execute(query, (limit,))
        else:
            cursor.execute(query)

        # Get column names
        columns = [description[0] for description in cursor.description]

        # Write to CSV
        csv_path.parent.mkdir(parents=True, exist_ok=True)
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
    import argparse
    
    parser = argparse.ArgumentParser(description="Export PC parts database to CSV")
    parser.add_argument(
        "--db-path",
        default="data/pc_parts.db",
        help="Path to SQLite database (default: data/pc_parts.db)",
    )
    parser.add_argument(
        "--csv-path",
        default=None,
        help="Output CSV file path (default: data/pc_parts.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of rows to export",
    )
    
    args = parser.parse_args()
    
    db_path = args.db_path
    csv_path = args.csv_path or db_path.replace(".db", ".csv") if db_path.endswith(".db") else "data/pc_parts.csv"
    
    export_to_csv(db_path, csv_path, limit=args.limit)

    print(f"\nYou can now open the CSV file in:")
    print(f"  - Excel")
    print(f"  - Google Sheets")
    print(f"  - Any text editor")
    print(f"\nUsage examples:")
    print(f"  python dataset_builder/export_to_csv.py")
    print(f"  python dataset_builder/export_to_csv.py --db-path data/pc_parts.db --csv-path output.csv")
    print(f"  python dataset_builder/export_to_csv.py --limit 100")


if __name__ == "__main__":
    main()
