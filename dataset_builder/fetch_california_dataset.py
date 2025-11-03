"""
Fetch California Bay Area vehicle dataset from Auto.dev API and store in SQLite.

This script:
1. Loads Bay Area zip codes from bay_area_zip.csv
2. Fetches every available listing for those zip codes from California
3. Saves data to SQLite database with indexed columns for fast filtering
4. Handles rate limits and errors gracefully
5. Supports resume functionality per zip code
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

        # Load Bay Area zip codes for filtering
        self.bay_area_zips = self._load_bay_area_zips()
        if not self.bay_area_zips:
            raise ValueError("No Bay Area zip codes found. Check bay_area_zip.csv")

        # Initialize database
        self._init_database()

    def _load_bay_area_zips(self) -> List[str]:
        """Load Bay Area zip codes from CSV file."""
        zip_file = Path(__file__).parent / "bay_area_zip.csv"

        if not zip_file.exists():
            raise FileNotFoundError(f"Bay Area zip code file not found: {zip_file}")

        zips: List[str] = []
        with open(zip_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.lower() == "zip":
                    continue
                zips.append(line.zfill(5))

        return zips

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

    def mark_progress(self, zip_code: str, count: int, error: Optional[str] = None):
        """Mark fetch progress for a Bay Area zip code.

        Args:
            zip_code: Zip code processed
            count: Number of vehicles fetched
            error: Error message if failed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO zip_fetch_progress (
                    zip_code,
                    vehicles_fetched,
                    fetched_at,
                    status,
                    error_message
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    zip_code,
                    count,
                    datetime.now().isoformat(),
                    'failed' if error else 'completed',
                    error,
                ),
            )
            conn.commit()

    def get_completed_zips(self) -> set:
        """Get set of already completed Bay Area zip codes.

        Returns:
            Set of zip codes that were successfully fetched
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT zip_code FROM zip_fetch_progress WHERE status = 'completed'"
            )
            return {row[0] for row in cursor.fetchall()}

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

    def fetch_vehicles_for_zip(
        self,
        zip_code: str,
        limit: Optional[int] = None,
        retry_count: int = 3,
        require_photos: bool = True,
        mix_new_used: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch vehicles for a specific Bay Area zip code from California.

        Args:
            zip_code: Bay Area zip code
            limit: Maximum number of vehicles to fetch. If None, fetches all available.
            retry_count: Number of retries on failure
            require_photos: If True, only return vehicles with photos
            mix_new_used: If True, fetch new and used listings separately

        Returns:
            List of vehicle dictionaries, sorted by year descending (newest first)
        """
        base_params = {
            "retailListing.state": "CA",
            "retailListing.zip": zip_code,
            "page": 1,
        }

        all_vehicles: List[Dict[str, Any]] = []
        seen_vins: set[str] = set()
        limit_per_request = 100

        def collect_for_condition(used_filter: Optional[str]):
            page = 1
            while True:
                params = {
                    **base_params,
                    "limit": limit_per_request,
                    "page": page,
                }
                if used_filter is not None:
                    params["retailListing.used"] = used_filter

                results = self._fetch_with_params(params, retry_count)

                if require_photos:
                    results = [
                        v for v in results
                        if v.get('retailListing', {}).get('photoCount', 0) > 0
                    ]

                if not results:
                    break

                for listing in results:
                    if limit is not None and len(all_vehicles) >= limit:
                        return

                    vin = listing.get('vehicle', {}).get('vin')
                    if vin and vin in seen_vins:
                        continue
                    if vin:
                        seen_vins.add(vin)
                    all_vehicles.append(listing)

                if limit is not None and len(all_vehicles) >= limit:
                    return

                if len(results) < limit_per_request:
                    break

                page += 1

        if mix_new_used:
            collect_for_condition("false")
            if limit is None or len(all_vehicles) < limit:
                collect_for_condition("true")
        else:
            collect_for_condition(None)

        all_vehicles.sort(key=lambda v: v.get('vehicle', {}).get('year', 0), reverse=True)

        if limit is not None:
            return all_vehicles[:limit]

        return all_vehicles

    def fetch_all(self, limit_per_zip: Optional[int] = None, rate_limit_delay: float = 0.2):
        """Fetch vehicles for all Bay Area zip codes.

        Args:
            limit_per_zip: Number of vehicles to fetch per zip code. If None, fetch all available.
            rate_limit_delay: Delay between API calls in seconds
        """
        total_zips = len(self.bay_area_zips)

        print(f"\n{'='*70}")
        print(f"California Bay Area Dataset Fetcher (SQLite)")
        print(f"{'='*70}")
        print(f"Total Bay Area zip codes: {total_zips}")
        target_display = limit_per_zip if limit_per_zip is not None else "Unlimited"
        print(f"Target vehicles per zip: {target_display}")
        print(f"Database: {self.db_path}")
        print(f"{'='*70}\n")

        # Resume from where we left off
        completed_set = self.get_completed_zips()
        remaining = [
            zip_code for zip_code in self.bay_area_zips
            if zip_code not in completed_set
        ]

        if completed_set:
            print(f"Resuming from previous session...")
            print(f"Already completed: {len(completed_set)}/{total_zips}")
            print(f"Remaining: {len(remaining)}\n")

        total_vehicles_added = 0

        # Create progress bar
        pbar = tqdm(
            remaining,
            desc="Fetching vehicles",
            initial=len(completed_set),
            total=total_zips,
            unit="zip",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        )

        for idx, zip_code in enumerate(pbar, start=len(completed_set) + 1):
            # Update progress bar description
            pbar.set_description(f"Fetching zip {zip_code}")

            # Fetch vehicles
            vehicles = self.fetch_vehicles_for_zip(zip_code, limit=limit_per_zip)

            # Save to database
            if vehicles:
                inserted = self.save_vehicles(vehicles)
                total_vehicles_added += inserted
                pbar.write(f"  ✓ {zip_code}: Saved {inserted} vehicles (Total: {total_vehicles_added:,})")
            else:
                pbar.write(f"  ⚠ {zip_code}: No vehicles found")

            # Mark progress
            self.mark_progress(zip_code, len(vehicles))

            # Rate limiting
            if idx < total_zips:
                time.sleep(rate_limit_delay)

            # Update progress bar postfix with stats
            pbar.set_postfix({
                'vehicles': f"{total_vehicles_added:,}",
                'avg/zip': f"{total_vehicles_added/idx:.0f}" if idx > 0 else "0"
            })

        pbar.close()

        # Final statistics
        stats = self.generate_stats()

        print(f"\n{'='*70}")
        print(f"Dataset Collection Complete!")
        print(f"{'='*70}")
        print(f"Total zip codes processed: {total_zips}")
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
    fetcher.fetch_all(limit_per_zip=None, rate_limit_delay=1.0)  # Fetch all available listings per zip


if __name__ == "__main__":
    main()
