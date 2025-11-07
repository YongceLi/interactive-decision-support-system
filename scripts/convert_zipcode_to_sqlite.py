#!/usr/bin/env python3
"""
Convert zip_code_database.csv to SQLite for efficient lookups.
"""
import csv
import sqlite3
from pathlib import Path

def convert_zipcode_csv_to_sqlite():
    """Convert ZIP code CSV to SQLite database."""
    project_root = Path(__file__).parent.parent
    csv_path = project_root / "data" / "zip_code_database.csv"
    db_path = project_root / "data" / "zipcode_lookup.db"

    print(f"Reading from: {csv_path}")
    print(f"Writing to: {db_path}")

    # Create database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zipcode_coords (
            zip TEXT PRIMARY KEY,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            city TEXT,
            state TEXT,
            county TEXT,
            decommissioned INTEGER DEFAULT 0,
            CHECK (length(zip) = 5)
        )
    """)

    # Create index for fast lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_zip ON zipcode_coords(zip)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_state ON zipcode_coords(state)")

    # Read CSV and insert data
    inserted = 0
    skipped = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            zip_code = row['zip']

            # Skip if missing critical data
            if not zip_code or not row['latitude'] or not row['longitude']:
                skipped += 1
                continue

            try:
                latitude = float(row['latitude'])
                longitude = float(row['longitude'])
                decommissioned = int(row['decommissioned'])

                cursor.execute("""
                    INSERT OR REPLACE INTO zipcode_coords
                    (zip, latitude, longitude, city, state, county, decommissioned)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    zip_code,
                    latitude,
                    longitude,
                    row['primary_city'],
                    row['state'],
                    row['county'],
                    decommissioned
                ))

                inserted += 1

                if inserted % 5000 == 0:
                    print(f"  Inserted {inserted} ZIP codes...")

            except (ValueError, KeyError) as e:
                print(f"  Skipping {zip_code}: {e}")
                skipped += 1

    conn.commit()
    conn.close()

    print(f"\n✓ Conversion complete!")
    print(f"  Inserted: {inserted} ZIP codes")
    print(f"  Skipped: {skipped} ZIP codes")
    print(f"  Database: {db_path}")

    # Test a lookup
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    result = cursor.execute(
        "SELECT zip, city, state, latitude, longitude FROM zipcode_coords WHERE zip = ?",
        ('94043',)
    ).fetchone()
    conn.close()

    if result:
        print(f"\n✓ Test lookup for ZIP 94043:")
        print(f"  City: {result[1]}, {result[2]}")
        print(f"  Coordinates: {result[3]}, {result[4]}")

    return db_path

if __name__ == "__main__":
    convert_zipcode_csv_to_sqlite()
