"""Fetch vehicle listings from the Marketcheck API and store them in SQLite."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv
from tqdm import tqdm

# Ensure repository root on sys.path for shared utilities if needed
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()


class MarketcheckDatasetFetcher:
    """Fetches Marketcheck listings for Bay Area zip codes and stores them locally."""

    API_URL = "https://api.marketcheck.com/v2/search/car/active"
    MAX_ROWS = 50

    def __init__(
        self,
        db_path: str = "data/marketcheck_vehicles.db",
        zip_file: Optional[Path] = None,
        radius: int = 5,
    ) -> None:
        self.api_key = os.getenv("MARKETCHECK_API_KEY")
        if not self.api_key:
            raise ValueError("MARKETCHECK_API_KEY not found in environment variables")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.radius = radius
        self.zip_file = zip_file or Path(__file__).parent / "bay_area_zip.csv"
        self.zip_codes = self._load_zip_codes(self.zip_file)
        if not self.zip_codes:
            raise ValueError("No zip codes found. Check bay_area_zip.csv")

        self._init_database()

    @staticmethod
    def _load_zip_codes(zip_file: Path) -> List[str]:
        if not zip_file.exists():
            raise FileNotFoundError(f"Zip code file not found: {zip_file}")

        zips: List[str] = []
        with zip_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.lower() == "zip":
                    continue
                zips.append(line.zfill(5))
        return zips

    def _init_database(self) -> None:
        schema_path = Path(__file__).parent / "marketcheck_schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError("Marketcheck schema file missing. Expected marketcheck_schema.sql")

        with sqlite3.connect(self.db_path) as conn:
            with schema_path.open("r", encoding="utf-8") as handle:
                conn.executescript(handle.read())
            conn.commit()

    def _prepare_listing_record(self, listing: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        vin = listing.get("vin")
        if not vin:
            return None

        build = listing.get("build") or {}
        dealer = listing.get("dealer") or {}
        mc_dealership = listing.get("mc_dealership") or {}
        financing = listing.get("financing_options") or {}
        leasing = listing.get("leasing_options") or {}
        media = listing.get("media") or {}

        record: Dict[str, Any] = {
            "vin": vin,
            "listing_id": listing.get("id"),
            "heading": listing.get("heading"),
            "price": listing.get("price"),
            "miles": listing.get("miles"),
            "msrp": listing.get("msrp"),
            "data_source": listing.get("data_source") or "mc",
            "vdp_url": listing.get("vdp_url"),
            "carfax_1_owner": listing.get("carfax_1_owner"),
            "carfax_clean_title": listing.get("carfax_clean_title"),
            "exterior_color": listing.get("exterior_color"),
            "interior_color": listing.get("interior_color"),
            "base_int_color": listing.get("base_int_color"),
            "base_ext_color": listing.get("base_ext_color"),
            "dom": listing.get("dom"),
            "dom_180": listing.get("dom_180"),
            "dom_active": listing.get("dom_active"),
            "dos_active": listing.get("dos_active"),
            "seller_type": listing.get("seller_type"),
            "inventory_type": listing.get("inventory_type"),
            "is_certified": listing.get("is_certified"),
            "stock_no": listing.get("stock_no"),
            "last_seen_at": listing.get("last_seen_at"),
            "last_seen_at_date": listing.get("last_seen_at_date"),
            "scraped_at": listing.get("scraped_at"),
            "scraped_at_date": listing.get("scraped_at_date"),
            "first_seen_at": listing.get("first_seen_at"),
            "first_seen_at_date": listing.get("first_seen_at_date"),
            "first_seen_at_source": listing.get("first_seen_at_source"),
            "first_seen_at_source_date": listing.get("first_seen_at_source_date"),
            "first_seen_at_mc": listing.get("first_seen_at_mc"),
            "first_seen_at_mc_date": listing.get("first_seen_at_mc_date"),
            "ref_price": listing.get("ref_price"),
            "price_change_percent": listing.get("price_change_percent"),
            "ref_price_dt": listing.get("ref_price_dt"),
            "ref_miles": listing.get("ref_miles"),
            "ref_miles_dt": listing.get("ref_miles_dt"),
            "source": listing.get("source"),
            "model_code": listing.get("model_code"),
            "in_transit": listing.get("in_transit"),
            "availability_status": listing.get("availability_status"),
            "financing_options_json": json.dumps(financing) if financing else None,
            "leasing_options_json": json.dumps(leasing) if leasing else None,
            "media_json": json.dumps(media) if media else None,
            "dealer_json": json.dumps(dealer) if dealer else None,
            "mc_dealership_json": json.dumps(mc_dealership) if mc_dealership else None,
            "build_json": json.dumps(build) if build else None,
            "build_year": build.get("year"),
            "build_make": build.get("make"),
            "build_model": build.get("model"),
            "build_trim": build.get("trim"),
            "build_version": build.get("version"),
            "build_body_type": build.get("body_type"),
            "build_vehicle_type": build.get("vehicle_type"),
            "build_transmission": build.get("transmission"),
            "build_drivetrain": build.get("drivetrain"),
            "build_fuel_type": build.get("fuel_type"),
            "build_engine": build.get("engine"),
            "build_doors": build.get("doors"),
            "build_cylinders": build.get("cylinders"),
            "build_std_seating": build.get("std_seating"),
            "build_highway_mpg": build.get("highway_mpg"),
            "build_city_mpg": build.get("city_mpg"),
            "dealer_name": dealer.get("name"),
            "dealer_city": dealer.get("city"),
            "dealer_state": dealer.get("state"),
            "dealer_zip": dealer.get("zip"),
            "dealer_phone": dealer.get("phone"),
            "dealer_latitude": self._to_float(dealer.get("latitude")),
            "dealer_longitude": self._to_float(dealer.get("longitude")),
            "dealer_country": dealer.get("country"),
            "dealer_type": dealer.get("dealer_type"),
            "dealer_msa_code": dealer.get("msa_code"),
            "dist": listing.get("dist"),
            "raw_json": json.dumps(listing),
            "fetched_at": datetime.utcnow().isoformat(),
        }
        return record

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def save_listings(self, listings: Iterable[Dict[str, Any]]) -> int:
        if not listings:
            return 0

        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for listing in listings:
                record = self._prepare_listing_record(listing)
                if not record:
                    continue

                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO marketcheck_listings (
                            vin, listing_id, heading, price, miles, msrp,
                            data_source, vdp_url, carfax_1_owner, carfax_clean_title,
                            exterior_color, interior_color, base_int_color, base_ext_color,
                            dom, dom_180, dom_active, dos_active, seller_type, inventory_type,
                            is_certified, stock_no, last_seen_at, last_seen_at_date,
                            scraped_at, scraped_at_date, first_seen_at, first_seen_at_date,
                            first_seen_at_source, first_seen_at_source_date, first_seen_at_mc,
                            first_seen_at_mc_date, ref_price, price_change_percent, ref_price_dt,
                            ref_miles, ref_miles_dt, source, model_code, in_transit,
                            availability_status, financing_options_json, leasing_options_json,
                            media_json, dealer_json, mc_dealership_json, build_json,
                            build_year, build_make, build_model, build_trim, build_version,
                            build_body_type, build_vehicle_type, build_transmission, build_drivetrain,
                            build_fuel_type, build_engine, build_doors, build_cylinders,
                            build_std_seating, build_highway_mpg, build_city_mpg, dealer_name,
                            dealer_city, dealer_state, dealer_zip, dealer_phone,
                            dealer_latitude, dealer_longitude, dealer_country, dealer_type,
                            dealer_msa_code, dist, raw_json, fetched_at
                        ) VALUES (
                            :vin, :listing_id, :heading, :price, :miles, :msrp,
                            :data_source, :vdp_url, :carfax_1_owner, :carfax_clean_title,
                            :exterior_color, :interior_color, :base_int_color, :base_ext_color,
                            :dom, :dom_180, :dom_active, :dos_active, :seller_type, :inventory_type,
                            :is_certified, :stock_no, :last_seen_at, :last_seen_at_date,
                            :scraped_at, :scraped_at_date, :first_seen_at, :first_seen_at_date,
                            :first_seen_at_source, :first_seen_at_source_date, :first_seen_at_mc,
                            :first_seen_at_mc_date, :ref_price, :price_change_percent, :ref_price_dt,
                            :ref_miles, :ref_miles_dt, :source, :model_code, :in_transit,
                            :availability_status, :financing_options_json, :leasing_options_json,
                            :media_json, :dealer_json, :mc_dealership_json, :build_json,
                            :build_year, :build_make, :build_model, :build_trim, :build_version,
                            :build_body_type, :build_vehicle_type, :build_transmission, :build_drivetrain,
                            :build_fuel_type, :build_engine, :build_doors, :build_cylinders,
                            :build_std_seating, :build_highway_mpg, :build_city_mpg, :dealer_name,
                            :dealer_city, :dealer_state, :dealer_zip, :dealer_phone,
                            :dealer_latitude, :dealer_longitude, :dealer_country, :dealer_type,
                            :dealer_msa_code, :dist, :raw_json, :fetched_at
                        )
                        """,
                        record,
                    )
                    inserted += 1
                except sqlite3.Error as exc:
                    print(f"    ✗ Failed to insert VIN {record['vin']}: {exc}")
            conn.commit()
        return inserted

    def mark_progress(self, zip_code: str, count: int, error: Optional[str] = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO marketcheck_zip_progress (
                    zip_code, listings_fetched, fetched_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    zip_code,
                    count,
                    datetime.utcnow().isoformat(),
                    "failed" if error else "completed",
                    error,
                ),
            )
            conn.commit()

    def get_completed_zips(self) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT zip_code FROM marketcheck_zip_progress WHERE status = 'completed'"
            )
            return {row[0] for row in cursor.fetchall()}

    def get_latest_progress(self) -> Optional[tuple[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT zip_code, status
                FROM marketcheck_zip_progress
                ORDER BY fetched_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None
            return row[0], row[1]

    def _request_listings(self, zip_code: str, start: int) -> Dict[str, Any]:
        params = {
            "api_key": self.api_key,
            "zip": zip_code,
            "radius": str(self.radius),
            "rows": str(self.MAX_ROWS),
            "start": str(start),
        }
        headers = {"Accept": "application/json"}

        response = requests.get(
            self.API_URL,
            headers=headers,
            params=params,
            timeout=60,
        )
        if response.status_code == 429:
            raise requests.HTTPError("Rate limit hit", response=response)
        response.raise_for_status()
        return response.json()

    def fetch_zip(self, zip_code: str, limit: Optional[int] = None) -> int:
        start = 0
        total_inserted = 0
        total_seen = 0
        consecutive_failures = 0

        while True:
            if start >= 500:
                break
            try:
                payload = self._request_listings(zip_code, start)
            except requests.HTTPError as exc:
                if exc.response.status_code == 429:
                    wait_time = min(60, 5 * (consecutive_failures + 1))
                    print(f"    ⚠ Rate limit for {zip_code}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    consecutive_failures += 1
                    continue
                raise
            except requests.RequestException as exc:
                wait_time = min(60, 5 * (consecutive_failures + 1))
                print(f"    ⚠ Network error for {zip_code}: {exc}. Retrying in {wait_time}s")
                time.sleep(wait_time)
                consecutive_failures += 1
                continue

            consecutive_failures = 0
            listings = payload.get("listings", []) or []
            if not listings:
                break

            inserted = self.save_listings(listings)
            total_inserted += inserted
            total_seen += len(listings)

            if limit is not None and total_seen >= limit:
                break

            if len(listings) < self.MAX_ROWS:
                break

            start += len(listings)

        return total_inserted

    def fetch_all(
        self,
        limit_per_zip: Optional[int] = None,
        delay: float = 0.2,
        resume: bool = True,
    ) -> None:
        total_zips = len(self.zip_codes)
        completed = self.get_completed_zips() if resume else set()
        resume_zip: Optional[str] = None
        resume_status: Optional[str] = None

        start_index = 0
        if resume:
            latest = self.get_latest_progress()
            if latest:
                resume_zip, resume_status = latest
                if resume_zip in self.zip_codes:
                    start_index = self.zip_codes.index(resume_zip)
                    if resume_status == "completed":
                        start_index += 1

        remaining_sequence = self.zip_codes[start_index:]
        remaining = []
        for zip_code in remaining_sequence:
            if zip_code in completed and not (
                resume_zip == zip_code and resume_status != "completed"
            ):
                continue
            remaining.append(zip_code)

        print(f"\n{'=' * 70}")
        print("Marketcheck Dataset Fetcher")
        print(f"{'=' * 70}")
        print(f"Total zip codes: {total_zips}")
        print(f"Already completed: {len(completed)}")
        print(f"Remaining: {len(remaining)}")
        print(f"Database: {self.db_path}")
        print(f"Rows per call: {self.MAX_ROWS}")
        print(f"Radius: {self.radius} miles")
        print(f"{'=' * 70}\n")

        for zip_code in tqdm(remaining, desc="Fetching zips"):
            try:
                inserted = self.fetch_zip(zip_code, limit=limit_per_zip)
                self.mark_progress(zip_code, inserted)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"    ✗ Failed to fetch zip {zip_code}: {exc}")
                self.mark_progress(zip_code, 0, error=str(exc))

            if delay:
                time.sleep(delay)

        print("\nFetch complete. Run marketcheck_stats.py to explore the data.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Marketcheck listings for Bay Area zips")
    parser.add_argument(
        "--db-path",
        default="data/marketcheck_vehicles.db",
        help="SQLite database path",
    )
    parser.add_argument(
        "--zip-file",
        default=str(Path(__file__).parent / "bay_area_zip.csv"),
        help="CSV file with Bay Area zip codes",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=5,
        help="Search radius in miles for each zip code",
    )
    parser.add_argument(
        "--limit-per-zip",
        type=int,
        default=None,
        help="Optional hard limit of listings to pull per zip",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore previous progress and refetch all zip codes",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delay in seconds between zip code requests",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fetcher = MarketcheckDatasetFetcher(
        db_path=args.db_path,
        zip_file=Path(args.zip_file),
        radius=args.radius,
    )
    fetcher.fetch_all(
        limit_per_zip=args.limit_per_zip,
        delay=args.delay,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
