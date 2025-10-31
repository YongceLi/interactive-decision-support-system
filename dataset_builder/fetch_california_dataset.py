"""
Fetch California vehicle dataset from Auto.dev API and store in SQLite.

This script:
1. Reads all unique make/model combinations from safety_data.db
2. Fetches up to 50 vehicles per combination from California
3. Saves data to SQLite database with indexed columns for fast filtering
4. Handles rate limits and errors gracefully
5. Supports resume functionality
"""

import os
import sys
import json
import time
import sqlite3
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class DatasetFetcher:
    """Fetches and manages California vehicle dataset in SQLite."""

    def __init__(self, db_path: str = "data/california_vehicles.db"):
        """Initialize the fetcher.

        Args:
            db_path: Path to SQLite database file
        """
        self.api_key = os.getenv("AUTODEV_API_KEY")
        if not self.api_key:
            raise ValueError("AUTODEV_API_KEY not found in environment variables")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with schema."""
        schema_file = Path(__file__).parent / "schema.sql"

        with sqlite3.connect(self.db_path) as conn:
            # Read and execute schema
            with open(schema_file, 'r') as f:
                schema = f.read()
                conn.executescript(schema)
            conn.commit()

    def _extract_vehicle_data(self, listing: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and flatten vehicle data for database insertion.

        Args:
            listing: Raw listing data from API

        Returns:
            Flattened dict with database column names as keys
        """
        vehicle = listing.get('vehicle', {})
        retail = listing.get('retailListing', {})
        location = listing.get('location', [])

        return {
            'vin': vehicle.get('vin'),
            'year': vehicle.get('year'),
            'make': vehicle.get('make'),
            'model': vehicle.get('model'),
            'trim': vehicle.get('trim'),
            'body_style': vehicle.get('bodyStyle'),
            'drivetrain': vehicle.get('drivetrain'),
            'engine': vehicle.get('engine'),
            'fuel_type': vehicle.get('fuel'),
            'transmission': vehicle.get('transmission'),
            'doors': vehicle.get('doors'),
            'seats': vehicle.get('seats'),
            'exterior_color': vehicle.get('exteriorColor'),
            'interior_color': vehicle.get('interiorColor'),
            'price': retail.get('price'),
            'mileage': retail.get('miles'),
            'is_used': retail.get('used'),
            'is_cpo': retail.get('cpo'),
            'dealer_name': retail.get('dealer'),
            'dealer_city': retail.get('city'),
            'dealer_state': retail.get('state'),
            'dealer_zip': retail.get('zip'),
            'longitude': location[0] if len(location) > 0 else None,
            'latitude': location[1] if len(location) > 1 else None,
            'primary_image_url': retail.get('primaryImage'),
            'photo_count': retail.get('photoCount', 0),
            'vdp_url': retail.get('vdp'),
            'carfax_url': retail.get('carfaxUrl'),
            'listing_created_at': listing.get('createdAt'),
            'online': listing.get('online'),
            'data_fetched_at': datetime.now().isoformat(),
            'raw_json': json.dumps(listing)  # Store complete JSON
        }

    def save_vehicles(self, vehicles: List[Dict[str, Any]]) -> int:
        """Save vehicles to database.

        Args:
            vehicles: List of vehicle listing dictionaries

        Returns:
            Number of vehicles successfully inserted
        """
        if not vehicles:
            return 0

        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for listing in vehicles:
                try:
                    data = self._extract_vehicle_data(listing)

                    # Skip if no VIN
                    if not data['vin']:
                        continue

                    # Insert or replace (upsert)
                    cursor.execute("""
                        INSERT OR REPLACE INTO vehicle_listings (
                            vin, year, make, model, trim, body_style, drivetrain,
                            engine, fuel_type, transmission, doors, seats,
                            exterior_color, interior_color, price, mileage,
                            is_used, is_cpo, dealer_name, dealer_city, dealer_state,
                            dealer_zip, longitude, latitude, primary_image_url,
                            photo_count, vdp_url, carfax_url, listing_created_at,
                            online, data_fetched_at, raw_json
                        ) VALUES (
                            :vin, :year, :make, :model, :trim, :body_style, :drivetrain,
                            :engine, :fuel_type, :transmission, :doors, :seats,
                            :exterior_color, :interior_color, :price, :mileage,
                            :is_used, :is_cpo, :dealer_name, :dealer_city, :dealer_state,
                            :dealer_zip, :longitude, :latitude, :primary_image_url,
                            :photo_count, :vdp_url, :carfax_url, :listing_created_at,
                            :online, :data_fetched_at, :raw_json
                        )
                    """, data)
                    inserted += 1

                except sqlite3.Error as e:
                    print(f"    ✗ Error inserting VIN {data.get('vin', 'unknown')}: {e}")
                    continue

            conn.commit()

        return inserted

    def mark_progress(self, make: str, model: str, count: int, error: Optional[str] = None):
        """Mark fetch progress for a make/model.

        Args:
            make: Vehicle make
            model: Vehicle model
            count: Number of vehicles fetched
            error: Error message if failed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO fetch_progress (make, model, vehicles_fetched, fetched_at, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                make,
                model,
                count,
                datetime.now().isoformat(),
                'failed' if error else 'completed',
                error
            ))
            conn.commit()

    def get_completed_models(self) -> set:
        """Get set of already completed make/model combinations.

        Returns:
            Set of strings in format "MAKE|MODEL"
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT make, model FROM fetch_progress WHERE status = 'completed'")
            return {f"{row[0]}|{row[1]}" for row in cursor.fetchall()}

    def get_make_model_list(self, db_path: str = "data/safety_data.db") -> List[Dict[str, str]]:
        """Get all unique make/model combinations from safety_data.db.

        Args:
            db_path: Path to safety_data.db

        Returns:
            List of dicts with 'make' and 'model' keys, sorted by popularity
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
        SELECT make, model, COUNT(*) as count
        FROM safety_data
        WHERE make IS NOT NULL AND model IS NOT NULL
        GROUP BY make, model
        ORDER BY count DESC
        """

        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()

        return [
            {"make": row[0], "model": row[1], "count": row[2]}
            for row in results
        ]

    def _fetch_with_params(
        self,
        params: Dict[str, Any],
        retry_count: int = 3
    ) -> List[Dict[str, Any]]:
        """Internal method to fetch vehicles with given params.

        Args:
            params: API request parameters
            retry_count: Number of retries on failure

        Returns:
            List of vehicle dictionaries
        """
        url = "https://api.auto.dev/listings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for attempt in range(retry_count):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=60)
                response.raise_for_status()

                data = response.json()
                return data.get('data', [])

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait_time = (attempt + 1) * 5
                    print(f"    ⚠ Rate limit hit. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif e.response.status_code == 500:
                    return []
                else:
                    return []

            except requests.exceptions.Timeout:
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue
                else:
                    return []

            except Exception:
                return []

        return []

    def fetch_vehicles_for_model(
        self,
        make: str,
        model: str,
        limit: int = 50,
        retry_count: int = 3,
        require_photos: bool = True,
        mix_new_used: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch vehicles for a specific make/model from California.

        Args:
            make: Vehicle make
            model: Vehicle model
            limit: Maximum number of vehicles to fetch
            retry_count: Number of retries on failure
            require_photos: If True, only return vehicles with photos
            mix_new_used: If True, fetch 50/50 mix of new and used vehicles

        Returns:
            List of vehicle dictionaries, sorted by year descending (newest first)
        """
        base_params = {
            "vehicle.make": make,
            "vehicle.model": model,
            "vehicle.year": "2023-2026",
            "retailListing.state": "CA",
            "retailListing.miles": "0-150000",
            "retailListing.price": "5000-1000000",
            "page": 1,
        }

        all_vehicles = []

        if mix_new_used:
            # Fetch new vehicles (50% of target)
            half_limit = limit // 2
            new_params = {**base_params, "limit": 100, "retailListing.used": "false"}
            new_vehicles = self._fetch_with_params(new_params, retry_count)

            # Filter for photos
            if require_photos:
                new_vehicles = [
                    v for v in new_vehicles
                    if v.get('retailListing', {}).get('photoCount', 0) > 0
                ]
            new_vehicles = new_vehicles[:half_limit]

            # Fetch used vehicles (50% of target)
            used_params = {**base_params, "limit": 100, "retailListing.used": "true"}
            used_vehicles = self._fetch_with_params(used_params, retry_count)

            # Filter for photos
            if require_photos:
                used_vehicles = [
                    v for v in used_vehicles
                    if v.get('retailListing', {}).get('photoCount', 0) > 0
                ]
            used_vehicles = used_vehicles[:half_limit]

            all_vehicles = new_vehicles + used_vehicles

            # Quiet mode - tqdm will handle output
            # print(f"  ✓ {make} {model}: Found {len(new_vehicles)} new + {len(used_vehicles)} used = {len(all_vehicles)} vehicles")

        else:
            # Fetch all vehicles without used/new filter
            params = {**base_params, "limit": 100 if require_photos else limit}
            all_vehicles = self._fetch_with_params(params, retry_count)

            # Filter for photos
            if require_photos:
                all_vehicles = [
                    v for v in all_vehicles
                    if v.get('retailListing', {}).get('photoCount', 0) > 0
                ]
                all_vehicles = all_vehicles[:limit]

            print(f"  ✓ {make} {model}: Found {len(all_vehicles)} vehicles")

        # Sort by year descending (newest first: 2026 -> 2018)
        all_vehicles.sort(key=lambda v: v.get('vehicle', {}).get('year', 0), reverse=True)

        return all_vehicles

    def fetch_all(self, limit_per_model: int = 100, rate_limit_delay: float = 0.2):
        """Fetch vehicles for all make/model combinations.

        Args:
            limit_per_model: Number of vehicles to fetch per model
            rate_limit_delay: Delay between API calls in seconds
        """
        make_model_list = self.get_make_model_list()
        total_models = len(make_model_list)

        print(f"\n{'='*70}")
        print(f"California Dataset Fetcher (SQLite)")
        print(f"{'='*70}")
        print(f"Total make/model combinations: {total_models}")
        print(f"Target vehicles per model: {limit_per_model}")
        print(f"Database: {self.db_path}")
        print(f"{'='*70}\n")

        # Resume from where we left off
        completed_set = self.get_completed_models()
        remaining = [
            item for item in make_model_list
            if f"{item['make']}|{item['model']}" not in completed_set
        ]

        if completed_set:
            print(f"Resuming from previous session...")
            print(f"Already completed: {len(completed_set)}/{total_models}")
            print(f"Remaining: {len(remaining)}\n")

        start_time = time.time()
        total_vehicles_added = 0

        # Create progress bar
        pbar = tqdm(
            remaining,
            desc="Fetching vehicles",
            initial=len(completed_set),
            total=total_models,
            unit="model",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        )

        for idx, item in enumerate(pbar, start=len(completed_set) + 1):
            make = item['make']
            model = item['model']

            # Update progress bar description
            pbar.set_description(f"Fetching {make} {model}")

            # Fetch vehicles
            vehicles = self.fetch_vehicles_for_model(make, model, limit=limit_per_model)

            # Save to database
            if vehicles:
                inserted = self.save_vehicles(vehicles)
                total_vehicles_added += inserted
                pbar.write(f"  ✓ {make} {model}: Saved {inserted} vehicles (Total: {total_vehicles_added:,})")
            else:
                pbar.write(f"  ⚠ {make} {model}: No vehicles found")

            # Mark progress
            self.mark_progress(make, model, len(vehicles))

            # Rate limiting
            if idx < total_models:
                time.sleep(rate_limit_delay)

            # Update progress bar postfix with stats
            pbar.set_postfix({
                'vehicles': f"{total_vehicles_added:,}",
                'avg/model': f"{total_vehicles_added/idx:.0f}" if idx > 0 else "0"
            })

        pbar.close()

        # Final statistics
        stats = self.generate_stats()

        print(f"\n{'='*70}")
        print(f"Dataset Collection Complete!")
        print(f"{'='*70}")
        print(f"Total models processed: {total_models}")
        print(f"Total vehicles in database: {stats['total_vehicles']}")
        print(f"Unique VINs: {stats['unique_vins']}")
        print(f"Database file: {self.db_path}")
        print(f"Database size: {self.db_path.stat().st_size / (1024*1024):.1f} MB")
        print(f"{'='*70}\n")

    def generate_stats(self) -> Dict[str, Any]:
        """Generate statistics about the dataset.

        Returns:
            Dictionary with dataset statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Total vehicles
            cursor.execute("SELECT COUNT(*), COUNT(DISTINCT vin) FROM vehicle_listings")
            total, unique_vins = cursor.fetchone()

            # By make
            cursor.execute("""
                SELECT make, COUNT(*) as count
                FROM vehicle_listings
                WHERE make IS NOT NULL
                GROUP BY make
                ORDER BY count DESC
                LIMIT 10
            """)
            top_makes = dict(cursor.fetchall())

            # By body style
            cursor.execute("""
                SELECT body_style, COUNT(*) as count
                FROM vehicle_listings
                WHERE body_style IS NOT NULL
                GROUP BY body_style
                ORDER BY count DESC
            """)
            body_styles = dict(cursor.fetchall())

            # Price ranges
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN price < 20000 THEN 1 ELSE 0 END) as under_20k,
                    SUM(CASE WHEN price >= 20000 AND price < 40000 THEN 1 ELSE 0 END) as range_20_40k,
                    SUM(CASE WHEN price >= 40000 AND price < 60000 THEN 1 ELSE 0 END) as range_40_60k,
                    SUM(CASE WHEN price >= 60000 THEN 1 ELSE 0 END) as over_60k
                FROM vehicle_listings
                WHERE price IS NOT NULL
            """)
            price_data = cursor.fetchone()

            stats = {
                'total_vehicles': total,
                'unique_vins': unique_vins,
                'top_makes': top_makes,
                'body_styles': body_styles,
                'price_ranges': {
                    '0-20k': price_data[0] or 0,
                    '20k-40k': price_data[1] or 0,
                    '40k-60k': price_data[2] or 0,
                    '60k+': price_data[3] or 0
                }
            }

            print(f"\nDataset Statistics:")
            print(f"  Total vehicles: {stats['total_vehicles']:,}")
            print(f"  Unique VINs: {stats['unique_vins']:,}")
            print(f"  Top 5 makes: {list(stats['top_makes'].items())[:5]}")
            print(f"  Price distribution:")
            for range_name, count in stats['price_ranges'].items():
                print(f"    ${range_name}: {count:,}")

            return stats


def main():
    """Main entry point."""
    fetcher = DatasetFetcher()
    fetcher.fetch_all(limit_per_model=100, rate_limit_delay=1.0)  # Increased from 0.2 to 1.0 second


if __name__ == "__main__":
    main()
