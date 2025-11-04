"""
Verify that vehicles actually have the number of photos listed in photo_count.
"""

import os
import sys
import sqlite3
import requests
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()


def get_vehicle_photos(vin: str, api_key: str) -> dict:
    """Fetch photos for a VIN from Auto.dev API.

    Args:
        vin: 17-character VIN
        api_key: Auto.dev API key

    Returns:
        Dictionary with photo data
    """
    url = f"https://api.auto.dev/photos/{vin}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def verify_photos(db_path: str = "data/test_california_vehicles.db", sample_size: int = 10):
    """Verify photo counts for a sample of vehicles.

    Args:
        db_path: Path to SQLite database
        sample_size: Number of vehicles to check
    """
    api_key = os.getenv("AUTODEV_API_KEY")
    if not api_key:
        print("AUTODEV_API_KEY not found in environment variables")
        return

    db_path = Path(db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    print(f"\n{'='*70}")
    print(f"Photo Verification Test")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    print(f"Sample size: {sample_size} vehicles\n")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get a sample of vehicles with different photo counts
        cursor.execute("""
            SELECT vin, year, make, model, trim, photo_count, dealer_city
            FROM vehicle_listings
            ORDER BY RANDOM()
            LIMIT ?
        """, (sample_size,))

        vehicles = cursor.fetchall()

    if not vehicles:
        print("No vehicles found in database")
        return

    print(f"Fetching photos for {len(vehicles)} random vehicles...\n")

    matches = 0
    mismatches = 0
    errors = 0

    for vin, year, make, model, trim, listed_count, city in vehicles:
        print(f"Checking: {year} {make} {model} {trim or ''} (VIN: {vin})")
        print(f"  Listed photo count: {listed_count}")
        print(f"  Location: {city}")

        # Fetch actual photos
        photo_data = get_vehicle_photos(vin, api_key)

        if "error" in photo_data:
            print(f"  Error fetching photos: {photo_data['error']}\n")
            errors += 1
            continue

        # Count actual photos
        retail_photos = photo_data.get('data', {}).get('retail', [])
        actual_count = len(retail_photos)

        print(f"  Actual photo count: {actual_count}")

        # Compare
        if actual_count == listed_count:
            print(f"  Match! Both show {actual_count} photos")
            matches += 1

            # Show first 3 photo URLs as samples
            if retail_photos:
                print(f"  Sample photo URLs:")
                for i, url in enumerate(retail_photos[:3], 1):
                    print(f"    {i}. {url}")
        else:
            print(f"  Mismatch! Listed: {listed_count}, Actual: {actual_count}")
            mismatches += 1

        print()

    # Summary
    print(f"{'='*70}")
    print(f"Verification Summary")
    print(f"{'='*70}")
    print(f"Total checked: {len(vehicles)}")
    print(f"Matches: {matches} ({matches/len(vehicles)*100:.1f}%)")
    print(f"Mismatches: {mismatches} ({mismatches/len(vehicles)*100:.1f}%)")
    print(f"Errors: {errors}")
    print(f"{'='*70}\n")

    if matches == len(vehicles):
        print("All photo counts verified successfully!")
    elif mismatches > 0:
        print("Some photo counts don't match. This could be due to:")
        print("   - Photos added/removed since initial fetch")
        print("   - API data inconsistencies")


if __name__ == "__main__":
    verify_photos(sample_size=10)
