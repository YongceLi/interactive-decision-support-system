"""Fetch Auto.dev or Marketcheck listings directly into the unified schema."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests
from dotenv import load_dotenv

from dataset_builder.merge_sqlite_datasets import (
    PRIORITY,
    UNIFIED_COLUMNS,
    empty_record,
    to_bool,
    to_float,
    to_int,
)

load_dotenv()

LOGGER = logging.getLogger("fetch_unified")

SCHEMA_PATH = Path(__file__).with_name("unified_schema.sql")
DEFAULT_DB_PATH = Path("data/unified_vehicles.db")
AUTODEV_URL = "https://api.auto.dev/listings"
MARKETCHECK_URL = "https://api.marketcheck.com/v2/search/car/active"


class UnifiedWriter:
    """Handle inserts into the unified schema with VIN precedence rules."""

    def __init__(self, db_path: Path, overwrite: bool = False) -> None:
        self.db_path = db_path
        if overwrite and self.db_path.exists():
            self.db_path.unlink()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if not SCHEMA_PATH.exists():
            raise FileNotFoundError("unified_schema.sql not found next to fetch_unified_dataset.py")

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")

        placeholders = ",".join(["?"] * len(UNIFIED_COLUMNS))
        columns_sql = ",".join(UNIFIED_COLUMNS)
        self.insert_sql = f"INSERT OR REPLACE INTO unified_vehicle_listings ({columns_sql}) VALUES ({placeholders})"

    def upsert(self, record: Dict[str, Any]) -> bool:
        vin = record.get("vin")
        if not vin:
            return False

        source = record.get("source")
        if not source:
            return False

        existing = self.conn.execute(
            "SELECT source FROM unified_vehicle_listings WHERE vin = ?",
            (vin,),
        ).fetchone()
        if existing:
            existing_source = existing[0]
            if PRIORITY.get(existing_source, 0) > PRIORITY.get(source, 0):
                return False

        values = [record.get(column) for column in UNIFIED_COLUMNS]
        self.conn.execute(self.insert_sql, values)
        return True

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


def parse_base_params(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    candidate = Path(raw)
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(raw)


def normalize_autodev_listing(listing: Dict[str, Any], fetched_at: str) -> Optional[Dict[str, Any]]:
    vehicle = listing.get("vehicle") or {}
    retail = listing.get("retailListing") or {}
    dealer_details = retail.get("dealerDetails") or {}
    location = listing.get("location") or []
    photos = retail.get("photos") or []

    vin = vehicle.get("vin")
    if not vin:
        return None

    record = empty_record()
    record.update(
        {
            "vin": vin,
            "listing_id": listing.get("id") or listing.get("listingId"),
            "heading": retail.get("title") or vehicle.get("model"),
            "source": "autodev",
            "price": to_int(retail.get("price")),
            "mileage": to_int(retail.get("miles")),
            "msrp": to_int(retail.get("msrp")),
            "listing_created_at": listing.get("createdAt"),
            "online": to_bool(listing.get("online")),
            "data_fetched_at": fetched_at,
            "year": to_int(vehicle.get("year")),
            "make": vehicle.get("make"),
            "model": vehicle.get("model"),
            "trim": vehicle.get("trim"),
            "body_style": vehicle.get("bodyStyle"),
            "drivetrain": vehicle.get("drivetrain"),
            "engine": vehicle.get("engine"),
            "fuel_type": vehicle.get("fuel"),
            "transmission": vehicle.get("transmission"),
            "doors": to_int(vehicle.get("doors")),
            "seats": to_int(vehicle.get("seats")),
            "exterior_color": vehicle.get("exteriorColor"),
            "interior_color": vehicle.get("interiorColor"),
            "inventory_type": "used" if retail.get("used") is True else ("new" if retail.get("used") is False else None),
            "is_used": to_bool(retail.get("used")),
            "is_cpo": to_bool(retail.get("cpo")),
            "is_certified": to_bool(retail.get("cpo")),
            "stock_number": retail.get("stockNumber"),
            "dealer_name": retail.get("dealer") or dealer_details.get("name"),
            "dealer_city": retail.get("city") or dealer_details.get("city"),
            "dealer_state": retail.get("state") or dealer_details.get("state"),
            "dealer_zip": retail.get("zip") or dealer_details.get("zip"),
            "dealer_phone": retail.get("phone") or dealer_details.get("phone"),
            "dealer_latitude": to_float(location[1] if len(location) > 1 else dealer_details.get("latitude")),
            "dealer_longitude": to_float(location[0] if location else dealer_details.get("longitude")),
            "primary_image_url": retail.get("primaryImage") or (photos[0] if photos else None),
            "photo_count": to_int(retail.get("photoCount")) or (len(photos) if photos else None),
            "vdp_url": retail.get("vdp"),
            "carfax_url": retail.get("carfaxUrl"),
            "dealer_json": json.dumps(dealer_details) if dealer_details else None,
            "build_json": json.dumps(vehicle) if vehicle else None,
            "data_source": "autodev",
            "carfax_one_owner": to_bool(retail.get("carfaxOneOwner")),
            "carfax_clean_title": to_bool(retail.get("carfaxCleanTitle")),
            "raw_json": json.dumps(listing, ensure_ascii=False),
        }
    )

    if photos:
        record["media_json"] = json.dumps({"photos": photos}, ensure_ascii=False)

    record.setdefault("build_year", record.get("year"))
    record.setdefault("build_make", record.get("make"))
    record.setdefault("build_model", record.get("model"))
    record.setdefault("build_trim", record.get("trim"))
    record.setdefault("build_body_type", record.get("body_style"))
    record.setdefault("build_fuel_type", record.get("fuel_type"))
    record.setdefault("build_transmission", record.get("transmission"))
    record.setdefault("build_drivetrain", record.get("drivetrain"))
    record.setdefault("build_engine", record.get("engine"))
    record.setdefault("build_doors", record.get("doors"))
    seats = record.get("seats")
    if seats is not None:
        record.setdefault("build_std_seating", str(seats))

    return record


def normalize_marketcheck_listing(listing: Dict[str, Any], fetched_at: str) -> Optional[Dict[str, Any]]:
    vin = listing.get("vin")
    if not vin:
        return None

    build = listing.get("build") or {}
    dealer = listing.get("dealer") or {}
    mc_dealership = listing.get("mc_dealership") or {}
    financing = listing.get("financing_options") or {}
    leasing = listing.get("leasing_options") or {}
    media = listing.get("media") or {}
    photo_links = media.get("photo_links") or []

    inventory_type = listing.get("inventory_type")
    is_used = None
    if isinstance(inventory_type, str):
        normalized = inventory_type.strip().lower()
        if normalized == "used":
            is_used = 1
        elif normalized == "new":
            is_used = 0

    record = empty_record()
    record.update(
        {
            "vin": vin,
            "listing_id": listing.get("id"),
            "heading": listing.get("heading"),
            "source": "marketcheck",
            "price": to_int(listing.get("price")),
            "mileage": to_int(listing.get("miles")),
            "msrp": to_int(listing.get("msrp")),
            "ref_price": to_int(listing.get("ref_price")),
            "price_change_percent": to_float(listing.get("price_change_percent")),
            "ref_price_dt": to_int(listing.get("ref_price_dt")),
            "ref_miles": to_int(listing.get("ref_miles")),
            "ref_miles_dt": to_int(listing.get("ref_miles_dt")),
            "first_seen_at": to_int(listing.get("first_seen_at")),
            "first_seen_at_date": listing.get("first_seen_at_date"),
            "first_seen_at_source": to_int(listing.get("first_seen_at_source")),
            "first_seen_at_source_date": listing.get("first_seen_at_source_date"),
            "first_seen_at_mc": to_int(listing.get("first_seen_at_mc")),
            "first_seen_at_mc_date": listing.get("first_seen_at_mc_date"),
            "last_seen_at": to_int(listing.get("last_seen_at")),
            "last_seen_at_date": listing.get("last_seen_at_date"),
            "scraped_at": to_int(listing.get("scraped_at")),
            "scraped_at_date": listing.get("scraped_at_date"),
            "data_fetched_at": fetched_at,
            "exterior_color": listing.get("exterior_color"),
            "interior_color": listing.get("interior_color"),
            "base_ext_color": listing.get("base_ext_color"),
            "base_int_color": listing.get("base_int_color"),
            "dom": to_int(listing.get("dom")),
            "dom_180": to_int(listing.get("dom_180")),
            "dom_active": to_int(listing.get("dom_active")),
            "dos_active": to_int(listing.get("dos_active")),
            "seller_type": listing.get("seller_type"),
            "inventory_type": inventory_type,
            "availability_status": listing.get("availability_status"),
            "is_certified": to_bool(listing.get("is_certified")),
            "is_cpo": to_bool(listing.get("is_certified")),
            "is_used": is_used,
            "in_transit": to_bool(listing.get("in_transit")),
            "model_code": listing.get("model_code"),
            "stock_number": listing.get("stock_no"),
            "dealer_name": dealer.get("name"),
            "dealer_city": dealer.get("city"),
            "dealer_state": dealer.get("state"),
            "dealer_zip": dealer.get("zip"),
            "dealer_phone": dealer.get("phone"),
            "dealer_latitude": to_float(dealer.get("latitude")),
            "dealer_longitude": to_float(dealer.get("longitude")),
            "dealer_country": dealer.get("country"),
            "dealer_type": dealer.get("dealer_type"),
            "dealer_msa_code": dealer.get("msa_code"),
            "dist": to_float(listing.get("dist")),
            "vdp_url": listing.get("vdp_url"),
            "carfax_one_owner": to_bool(listing.get("carfax_1_owner")),
            "carfax_clean_title": to_bool(listing.get("carfax_clean_title")),
            "primary_image_url": photo_links[0] if photo_links else None,
            "photo_count": len(photo_links) if photo_links else to_int(listing.get("photo_count")),
            "financing_options_json": json.dumps(financing, ensure_ascii=False) if financing else None,
            "leasing_options_json": json.dumps(leasing, ensure_ascii=False) if leasing else None,
            "media_json": json.dumps(media, ensure_ascii=False) if media else None,
            "dealer_json": json.dumps(dealer, ensure_ascii=False) if dealer else None,
            "mc_dealership_json": json.dumps(mc_dealership, ensure_ascii=False) if mc_dealership else None,
            "build_json": json.dumps(build, ensure_ascii=False) if build else None,
            "data_source": listing.get("data_source") or "marketcheck",
            "raw_json": json.dumps(listing, ensure_ascii=False),
        }
    )

    record.update(
        {
            "build_year": to_int(build.get("year")),
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
            "build_doors": to_int(build.get("doors")),
            "build_cylinders": to_int(build.get("cylinders")),
            "build_std_seating": build.get("std_seating"),
            "build_highway_mpg": to_int(build.get("highway_mpg")),
            "build_city_mpg": to_int(build.get("city_mpg")),
        }
    )

    record.setdefault("year", record.get("build_year"))
    record.setdefault("make", record.get("build_make"))
    record.setdefault("model", record.get("build_model"))
    record.setdefault("trim", record.get("build_trim"))
    record.setdefault("body_style", record.get("build_body_type"))
    record.setdefault("drivetrain", record.get("build_drivetrain"))
    record.setdefault("engine", record.get("build_engine"))
    record.setdefault("fuel_type", record.get("build_fuel_type"))
    record.setdefault("transmission", record.get("build_transmission"))
    record.setdefault("doors", record.get("build_doors"))

    return record


class BaseFetcher:
    def __init__(
        self,
        writer: UnifiedWriter,
        base_params: Dict[str, Any],
        page_size: int,
        max_records: Optional[int],
        delay: float,
        timeout: float,
        retries: int,
    ) -> None:
        self.writer = writer
        self.base_params = base_params
        self.page_size = page_size
        self.max_records = max_records
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def _request(self, method: str, url: str, *, headers: Dict[str, str], params: Dict[str, Any]) -> requests.Response:
        attempt = 0
        while True:
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                attempt += 1
                if attempt > self.retries:
                    raise
                wait = min(60.0, self.delay * (attempt + 1))
                LOGGER.warning("Network error: %s. Retrying in %.1fs", exc, wait)
                time.sleep(wait)
                continue

            if response.status_code == 429 and attempt < self.retries:
                attempt += 1
                wait = min(120.0, self.delay * (attempt + 1) * 2)
                LOGGER.warning("Rate limit hit. Waiting %.1fs", wait)
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

    def insert_many(self, listings: Iterable[Dict[str, Any]], normalizer) -> int:
        inserted = 0
        for listing in listings:
            fetched_at = datetime.utcnow().isoformat()
            record = normalizer(listing, fetched_at)
            if not record:
                continue
            if self.writer.upsert(record):
                inserted += 1
        self.writer.commit()
        return inserted

    def run(self) -> int:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError


class AutoDevFetcher(BaseFetcher):
    def __init__(
        self,
        writer: UnifiedWriter,
        base_params: Dict[str, Any],
        page_size: int,
        max_records: Optional[int],
        delay: float,
        timeout: float,
        retries: int,
    ) -> None:
        super().__init__(writer, base_params, page_size, max_records, delay, timeout, retries)
        self.api_key = os.getenv("AUTODEV_API_KEY")
        if not self.api_key:
            raise ValueError("AUTODEV_API_KEY environment variable is required for Auto.dev fetches")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def run(self) -> int:
        total_inserted = 0
        page = 1
        while True:
            params = dict(self.base_params)
            params.update({"limit": self.page_size, "page": page})
            try:
                response = self._request("GET", AUTODEV_URL, headers=self.headers, params=params)
            except requests.HTTPError as exc:
                LOGGER.error("Auto.dev request failed: %s", exc)
                break

            payload = response.json()
            listings = payload.get("data") or []
            if not isinstance(listings, list) or not listings:
                break

            inserted = self.insert_many(listings, normalize_autodev_listing)
            total_inserted += inserted
            LOGGER.info("Auto.dev page %d: %d inserted (%d total)", page, inserted, total_inserted)

            if self.max_records is not None and total_inserted >= self.max_records:
                break
            if len(listings) < self.page_size:
                break

            page += 1
            if self.max_records is not None and page * self.page_size >= self.max_records + self.page_size:
                break
            time.sleep(self.delay)
        return total_inserted


class MarketcheckFetcher(BaseFetcher):
    def __init__(
        self,
        writer: UnifiedWriter,
        base_params: Dict[str, Any],
        page_size: int,
        max_records: Optional[int],
        delay: float,
        timeout: float,
        retries: int,
    ) -> None:
        super().__init__(writer, base_params, page_size, max_records, delay, timeout, retries)
        self.api_key = os.getenv("MARKETCHECK_API_KEY")
        if not self.api_key:
            raise ValueError("MARKETCHECK_API_KEY environment variable is required for Marketcheck fetches")
        self.headers = {"Accept": "application/json"}

    def run(self) -> int:
        total_inserted = 0
        start = 0
        while True:
            params = dict(self.base_params)
            params.setdefault("rows", str(self.page_size))
            params.update({"api_key": self.api_key, "start": str(start)})
            try:
                response = self._request("GET", MARKETCHECK_URL, headers=self.headers, params=params)
            except requests.HTTPError as exc:
                LOGGER.error("Marketcheck request failed: %s", exc)
                break

            payload = response.json()
            listings = payload.get("listings") or []
            if not isinstance(listings, list) or not listings:
                break

            inserted = self.insert_many(listings, normalize_marketcheck_listing)
            total_inserted += inserted
            LOGGER.info("Marketcheck start=%d: %d inserted (%d total)", start, inserted, total_inserted)

            if self.max_records is not None and total_inserted >= self.max_records:
                break
            if len(listings) < int(params.get("rows", self.page_size)):
                break

            start += len(listings)
            if self.max_records is not None and start >= self.max_records:
                break
            time.sleep(self.delay)
        return total_inserted


def build_fetcher(args: argparse.Namespace, writer: UnifiedWriter, base_params: Dict[str, Any]):
    common_kwargs = {
        "writer": writer,
        "base_params": base_params,
        "page_size": args.page_size,
        "max_records": args.max_records,
        "delay": args.delay,
        "timeout": args.timeout,
        "retries": args.retries,
    }
    if args.api == "autodev":
        return AutoDevFetcher(**common_kwargs)
    return MarketcheckFetcher(**common_kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch vehicle listings into the unified schema")
    parser.add_argument(
        "api",
        choices=["autodev", "marketcheck"],
        help="Which upstream API to call",
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database that stores unified_vehicle_listings",
    )
    parser.add_argument(
        "--base-params",
        help="JSON string or file with default request parameters passed to the API",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=250,
        help="Number of records to request per page (Auto.dev max 500, Marketcheck max 50)",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        help="Optional cap on the total number of inserted records",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to sleep between consecutive API requests",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Maximum number of retries for rate limits or transient failures",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Drop the existing database before fetching",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    args = parser.parse_args()
    if args.api == "marketcheck" and args.page_size > 50:
        LOGGER.warning("Marketcheck rows capped at 50. Reducing page size to 50.")
        args.page_size = 50
    if args.api == "autodev" and args.page_size > 500:
        LOGGER.warning("Auto.dev page limit is 500. Reducing page size to 500.")
        args.page_size = 500
    return args


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    base_params = parse_base_params(args.base_params)
    writer = UnifiedWriter(args.output_db, overwrite=args.overwrite)
    try:
        fetcher = build_fetcher(args, writer, base_params)
        inserted = fetcher.run()
        LOGGER.info("Inserted %d unified records", inserted)
    finally:
        writer.close()


if __name__ == "__main__":
    main()
