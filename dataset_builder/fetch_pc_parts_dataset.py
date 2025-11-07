"""Build a local SQLite database of PC components.

This script mirrors the California vehicle dataset builder but targets
PC components sourced from:

1. PCPartPicker (HTML scrape)
2. Best Buy (HTML scrape)
3. RapidAPI (configurable, defaults to Newegg data API)

The resulting database matches the normalized structure defined in
``dataset_builder/pc_parts_schema.sql`` and keeps the complete raw payload
for traceability, just like ``california_vehicles.db``.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Ensure project root on sys.path so shared utils are available when needed
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Load environment variables from .env if present
load_dotenv()


logger = logging.getLogger("pc_parts_builder")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CATEGORIES: Dict[str, Dict[str, str]] = {
    "cpu": {
        "pcpartpicker_slug": "cpu",
        "bestbuy_query": "CPU",
        "rapid_query": "desktop cpu",
    },
    "gpu": {
        "pcpartpicker_slug": "video-card",
        "bestbuy_query": "graphics card",
        "rapid_query": "graphics card",
    },
    "motherboard": {
        "pcpartpicker_slug": "motherboard",
        "bestbuy_query": "motherboard",
        "rapid_query": "motherboard",
    },
    "psu": {
        "pcpartpicker_slug": "power-supply",
        "bestbuy_query": "power supply",
        "rapid_query": "power supply",
    },
    "case": {
        "pcpartpicker_slug": "case",
        "bestbuy_query": "pc case",
        "rapid_query": "pc case",
    },
    "cooling": {
        "pcpartpicker_slug": "cpu-cooler",
        "bestbuy_query": "cpu cooler",
        "rapid_query": "cpu cooler",
    },
    "ram": {
        "pcpartpicker_slug": "memory",
        "bestbuy_query": "ram",
        "rapid_query": "ram",
    },
    "storage": {
        "pcpartpicker_slug": "internal-hard-drive",
        "bestbuy_query": "ssd",
        "rapid_query": "ssd",
    },
}


PCPARTPICKER_BASE = "https://pcpartpicker.com"
BESTBUY_SEARCH_URL = "https://www.bestbuy.com/site/searchpage.jsp"


# Defaults for RapidAPI integration (can be overridden via environment)
DEFAULT_RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "product-search-api.p.rapidapi.com")
DEFAULT_RAPIDAPI_ENDPOINT = os.getenv("RAPIDAPI_ENDPOINT", "/shopping")
DEFAULT_RAPIDAPI_COUNTRY = os.getenv("RAPIDAPI_COUNTRY", "us")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")


DEFAULT_TIMEOUT = (5, 25)


def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        try:
            cleaned = (
                value.replace("$", "")
                .replace(",", "")
                .replace("USD", "")
                .strip()
            )
            return float(cleaned) if cleaned else None
        except Exception:
            return None


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            cleaned = (
                value.replace(",", "")
                .replace("reviews", "")
                .replace("ratings", "")
                .strip()
            )
            return int(cleaned) if cleaned else None
        except Exception:
            return None


def _canonical_part_id(source: str, candidate: Optional[str], fallback_fields: Iterable[str]) -> str:
    if candidate is not None:
        candidate_str = str(candidate).strip()
        if candidate_str and candidate_str.lower() != "none":
            return f"{source}:{candidate_str}".lower()

    joined = "|".join(field for field in fallback_fields if field)
    if not joined:
        joined = f"{source}:{_now_iso()}"
    digest = sha1(joined.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"


@dataclass
class PCPartRecord:
    part_id: str
    source: str
    part_type: str
    product_name: str
    data_fetched_at: str

    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    series: Optional[str] = None
    price: Optional[float] = None
    currency: str = "USD"
    availability: Optional[str] = None
    stock_status: Optional[str] = None
    seller: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    specs: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> Dict[str, Any]:
        return {
            "part_id": self.part_id,
            "source": self.source,
            "part_type": self.part_type,
            "manufacturer": self.manufacturer,
            "product_name": self.product_name,
            "model_number": self.model_number,
            "series": self.series,
            "price": self.price,
            "currency": self.currency,
            "availability": self.availability,
            "stock_status": self.stock_status,
            "seller": self.seller,
            "rating": self.rating,
            "review_count": self.review_count,
            "url": self.url,
            "image_url": self.image_url,
            "description": self.description,
            "specs_json": json.dumps(self.specs, ensure_ascii=False) if self.specs else None,
            "attributes_json": json.dumps(self.attributes, ensure_ascii=False) if self.attributes else None,
            "data_fetched_at": self.data_fetched_at,
            "last_seen_at": self.data_fetched_at,
            "raw_json": json.dumps(self.raw, ensure_ascii=False) if self.raw else None,
        }


# ---------------------------------------------------------------------------
# Source-specific collectors
# ---------------------------------------------------------------------------


class PCPartPickerScraper:
    """Scrape component listings directly from PCPartPicker."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://pcpartpicker.com/list/",
        "Cache-Control": "no-cache",
    }

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or _create_session()

    def fetch(self, category: str, slug: str, limit: Optional[int] = 50) -> List[PCPartRecord]:
        logger.info("Scraping PCPartPicker %s (slug=%s, limit=%s)", category, slug, limit or "unlimited")
        records: List[PCPartRecord] = []
        page = 1

        while limit is None or len(records) < limit:
            url = f"{PCPARTPICKER_BASE}/products/{slug}/"
            params = {"page": page, "sort": "price"}
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=self.HEADERS,
                    timeout=DEFAULT_TIMEOUT,
                )
            except requests.RequestException as exc:
                logger.warning("PCPartPicker request error for %s: %s", category, exc)
                break

            if response.status_code != 200:
                logger.warning(
                    "PCPartPicker request failed (%s): %s",
                    response.status_code,
                    response.text[:160],
                )
                break

            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("tr.tr__product")
            if not rows:
                logger.info("No more rows found for %s page %d", category, page)
                break

            for row in rows:
                if limit is not None and len(records) >= limit:
                    break

                data_raw: Dict[str, Any] = {}

                part_key = row.get("data-product-id") or row.get("data-id")
                name_link = row.select_one("td.td__name a")
                if not name_link:
                    continue

                product_name = name_link.get_text(strip=True)
                url_path = name_link.get("href")
                product_url = (
                    f"{PCPARTPICKER_BASE}{url_path}" if url_path and url_path.startswith("/") else url_path
                )

                manufacturer = row.select_one("td.td__name span")
                manufacturer_text = manufacturer.get_text(strip=True) if manufacturer else None

                price_cell = row.select_one("td.td__price span") or row.select_one("td.td__price")
                price_value = _safe_float(price_cell.get_text(strip=True) if price_cell else None)

                rating_cell = row.select_one("td.td__rating span")
                rating_value = _safe_float(rating_cell.get("data-rating")) if rating_cell else None

                reviews_cell = row.select_one("td.td__rating a")
                review_count = _safe_int(reviews_cell.get_text(strip=True) if reviews_cell else None)

                spec_cells = row.select("td.td__spec")
                specs: Dict[str, Any] = {}
                for spec_cell in spec_cells:
                    label = spec_cell.get("data-spec-filter") or spec_cell.get("data-spec-name")
                    value = spec_cell.get_text(strip=True)
                    if label:
                        specs[label] = value

                data_raw = {
                    "product_name": product_name,
                    "manufacturer": manufacturer_text,
                    "price": price_value,
                    "rating": rating_value,
                    "review_count": review_count,
                    "specs": specs,
                    "url": product_url,
                }

                part_id = _canonical_part_id(
                    "pcpartpicker",
                    part_key,
                    (category, product_name, manufacturer_text or ""),
                )

                record = PCPartRecord(
                    part_id=part_id,
                    source="pcpartpicker",
                    part_type=category,
                    product_name=product_name,
                    manufacturer=manufacturer_text,
                    price=price_value,
                    rating=rating_value,
                    review_count=review_count,
                    url=product_url,
                    specs=specs,
                    raw=data_raw,
                    data_fetched_at=_now_iso(),
                )

                records.append(record)

            page += 1
            time.sleep(1.0)  # Respectful crawl rate

        logger.info("PCPartPicker %s: collected %d records", category, len(records))
        return records


class BestBuyScraper:
    """Scrape Best Buy search results for PC components."""

    SEARCH_URL = BESTBUY_SEARCH_URL
    COMPONENTS_URL = "https://www.bestbuy.com/site/all-computers-tablets-on-sale/computer-components-on-sale/pcmcat1720704931473.c?id=pcmcat1720704931473"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.bestbuy.com/",
        "Cache-Control": "no-cache",
    }

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or _create_session()

    def fetch(self, category: str, query: str, limit: Optional[int] = 40) -> List[PCPartRecord]:
        logger.info("Scraping BestBuy %s (query=%s, limit=%s)", category, query, limit or "unlimited")
        records: List[PCPartRecord] = []
        page = 1

        while limit is None or len(records) < limit:
            params = {"st": query, "cp": page}
            try:
                response = self.session.get(
                    self.SEARCH_URL,
                    params=params,
                    headers=self.HEADERS,
                    timeout=DEFAULT_TIMEOUT,
                )
            except requests.RequestException as exc:
                logger.warning("BestBuy request error for %s: %s", category, exc)
                break

            if response.status_code != 200 or "Access Denied" in response.text:
                logger.warning(
                    "BestBuy request failed (%s): %s",
                    response.status_code,
                    response.text[:160],
                )
                # Fallback to the components sale page if standard search fails
                if page == 1:
                    try:
                        response = self.session.get(
                            self.COMPONENTS_URL,
                            headers=self.HEADERS,
                            timeout=DEFAULT_TIMEOUT,
                        )
                    except requests.RequestException:
                        break
                    if response.status_code != 200:
                        break
                else:
                    break

            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("li.sku-item")
            if not items:
                logger.info("No more BestBuy items for %s page %d", category, page)
                break

            for item in items:
                if limit is not None and len(records) >= limit:
                    break

                sku = item.get("data-sku-id") or item.get("data-sku")
                title_tag = item.select_one("h4.sku-title a")
                if not title_tag:
                    continue
                product_name = title_tag.get_text(strip=True)
                product_url = title_tag.get("href")
                if product_url and product_url.startswith("/"):
                    product_url = f"https://www.bestbuy.com{product_url}"

                price_tag = item.select_one("div.priceView-customer-price span")
                price_value = _safe_float(price_tag.get_text(strip=True) if price_tag else None)

                availability_tag = item.select_one("div.fulfillment-fulfillment-summary")
                availability_text = availability_tag.get_text(" ", strip=True) if availability_tag else None

                rating_tag = item.select_one("div.c-reviews-v4 a, span.c-reviews-v4__rating")
                rating_value = None
                review_count = None
                if rating_tag:
                    rating_value = _safe_float(rating_tag.get("aria-label"))
                    if rating_value is None:
                        rating_value = _safe_float(rating_tag.get_text(strip=True))

                reviews_count_tag = item.select_one("span.c-reviews-v4__count")
                if reviews_count_tag:
                    review_count = _safe_int(reviews_count_tag.get_text(strip=True))

                image_tag = item.select_one("img.product-image")
                image_url = image_tag.get("src") if image_tag else None

                record = PCPartRecord(
                    part_id=_canonical_part_id(
                        "bestbuy",
                        sku,
                        (category, product_name),
                    ),
                    source="bestbuy",
                    part_type=category,
                    product_name=product_name,
                    price=price_value,
                    availability=availability_text,
                    stock_status=self._normalize_stock(availability_text),
                    rating=rating_value,
                    review_count=review_count,
                    seller="Best Buy",
                    url=product_url,
                    image_url=image_url,
                    raw={
                        "sku": sku,
                        "product_name": product_name,
                        "price": price_value,
                        "availability": availability_text,
                        "rating": rating_value,
                        "review_count": review_count,
                        "url": product_url,
                        "image_url": image_url,
                    },
                    data_fetched_at=_now_iso(),
                )

                records.append(record)

            page += 1
            time.sleep(0.75)

        logger.info("BestBuy %s: collected %d records", category, len(records))
        return records

    @staticmethod
    def _normalize_stock(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        lower = text.lower()
        if "available today" in lower or "get it today" in lower or "ready to ship" in lower:
            return "in_stock"
        if "sold out" in lower or "unavailable" in lower:
            return "out_of_stock"
        if "pre-order" in lower or "preorder" in lower:
            return "preorder"
        return "unknown"


class RapidAPISource:
    """Fetch PC part listings via RapidAPI."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        host: str = DEFAULT_RAPIDAPI_HOST,
        endpoint: str = DEFAULT_RAPIDAPI_ENDPOINT,
        country: str = DEFAULT_RAPIDAPI_COUNTRY,
    ) -> None:
        self.session = session or _create_session()
        self.host = host
        self.endpoint = endpoint
        self.country = country
        self.api_key = RAPIDAPI_KEY

    def fetch(self, category: str, query: str, limit: Optional[int] = 40) -> List[PCPartRecord]:
        if not self.api_key:
            logger.warning("Skipping RapidAPI for %s: RAPIDAPI_KEY not configured", category)
            return []

        logger.info(
            "Fetching RapidAPI data for %s (host=%s, endpoint=%s, limit=%s)",
            category,
            self.host,
            self.endpoint,
            limit if limit is not None else "unlimited",
        )

        records: List[PCPartRecord] = []
        url = f"https://{self.host}{self.endpoint}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.host,
        }

        page = 1
        seen_ids: Set[str] = set()

        while True:
            if limit is not None and len(records) >= limit:
                break

            payload = {
                "query": query,
                "page": str(page),
                "country": self.country,
            }

            try:
                response = self.session.post(
                    url,
                    data=payload,
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )
                response.raise_for_status()
                payload_json = response.json()
            except requests.HTTPError as exc:
                logger.error("RapidAPI request failed (%s): %s", category, exc)
                break
            except Exception as exc:
                logger.error("RapidAPI unexpected error for %s: %s", category, exc)
                break

            products = self._extract_products(payload_json)
            if not products:
                logger.info("RapidAPI %s page %d returned no products", category, page)
                break

            new_records = 0
            for product in products:
                raw_identifier = (
                    product.get("productId")
                    or product.get("product_id")
                    or product.get("item_number")
                    or product.get("sku")
                    or product.get("id")
                )

                part_id = _canonical_part_id(
                    "rapidapi",
                    raw_identifier,
                    (
                        category,
                        product.get("title") or product.get("name") or product.get("product_title") or "",
                        product.get("link") or product.get("url") or product.get("productUrl") or "",
                    ),
                )

                if part_id in seen_ids:
                    continue

                name = product.get("title") or product.get("name") or product.get("product_title")
                if not name:
                    continue

                price_value = product.get("price") or product.get("finalPrice") or product.get("salePrice")
                record = PCPartRecord(
                    part_id=part_id,
                    source="rapidapi",
                    part_type=category,
                    product_name=name,
                    manufacturer=product.get("brand") or product.get("manufacturer") or product.get("source"),
                    model_number=product.get("modelNumber") or product.get("model") or product.get("item_number"),
                    price=_safe_float(str(price_value) if price_value is not None else None),
                    availability=product.get("availability"),
                    stock_status=self._normalize_stock(product.get("availability")),
                    seller=product.get("seller") or product.get("sellerName"),
                    rating=_safe_float(str(product.get("rating"))),
                    review_count=_safe_int(str(product.get("reviewCount") or product.get("reviews") or product.get("ratingCount"))),
                    url=product.get("url") or product.get("productUrl"),
                    image_url=product.get("image") or product.get("imageUrl"),
                    specs=product.get("specs") or product.get("attributes") or {},
                    raw=product,
                    data_fetched_at=_now_iso(),
                )
                records.append(record)
                seen_ids.add(part_id)
                new_records += 1

                if limit is not None and len(records) >= limit:
                    break

            if new_records == 0:
                logger.info("RapidAPI %s page %d produced only duplicates", category, page)
                break

            page += 1
            time.sleep(0.5)

        logger.info("RapidAPI %s: collected %d records", category, len(records))
        return records

    @staticmethod
    def _normalize_stock(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        lower = str(value).lower()
        if "in stock" in lower or "available" in lower:
            return "in_stock"
        if "out of stock" in lower or "unavailable" in lower or "sold out" in lower:
            return "out_of_stock"
        if "pre-order" in lower or "preorder" in lower:
            return "preorder"
        return "unknown"

    @staticmethod
    def _extract_products(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload

        for key in (
            "shopping_results",
            "products",
            "items",
            "data",
            "results",
        ):
            if key in payload and isinstance(payload[key], list):
                return payload[key]

        if "main_item" in payload and isinstance(payload["main_item"], dict):
            return [payload["main_item"]]

        return []


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


class PCPartsDatasetBuilder:
    def __init__(
        self,
        db_path: str = "data/pc_parts.db",
        limit_per_source: Optional[int] = 50,
        enabled_sources: Optional[Iterable[str]] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.limit_per_source = limit_per_source if limit_per_source and limit_per_source > 0 else None
        self.enabled_sources: Set[str] = (
            set(enabled_sources) if enabled_sources else {"pcpartpicker", "bestbuy", "rapidapi"}
        )

        self._init_database()

        shared_session = _create_session()
        self.pcpartpicker = PCPartPickerScraper(session=shared_session)
        self.bestbuy = BestBuyScraper(session=shared_session)
        self.rapidapi = RapidAPISource(session=shared_session)
        self._existing_part_ids = self._load_existing_part_ids()

    def _init_database(self) -> None:
        schema_file = PROJECT_ROOT / "dataset_builder" / "pc_parts_schema.sql"
        with sqlite3.connect(self.db_path) as conn:
            with open(schema_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()

    def _load_existing_part_ids(self) -> Set[str]:
        if not self.db_path.exists():
            return set()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT part_id FROM pc_parts")
                return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error:
            return set()

    def build(self) -> None:
        total_inserted = 0

        for part_type, config in CATEGORIES.items():
            logger.info("=== Collecting data for %s ===", part_type)
            collected: List[PCPartRecord] = []

            if "pcpartpicker" in self.enabled_sources:
                try:
                    pcpp_records = self.pcpartpicker.fetch(
                        category=part_type,
                        slug=config["pcpartpicker_slug"],
                        limit=self.limit_per_source,
                    )
                    collected.extend(pcpp_records)
                    self._mark_progress("pcpartpicker", part_type, len(pcpp_records))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("PCPartPicker scrape failed for %s: %s", part_type, exc)
                    self._mark_progress("pcpartpicker", part_type, 0, status="failed", error=str(exc))

            if "bestbuy" in self.enabled_sources:
                try:
                    bestbuy_records = self.bestbuy.fetch(
                        category=part_type,
                        query=config["bestbuy_query"],
                        limit=self.limit_per_source,
                    )
                    collected.extend(bestbuy_records)
                    self._mark_progress("bestbuy", part_type, len(bestbuy_records))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("BestBuy scrape failed for %s: %s", part_type, exc)
                    self._mark_progress("bestbuy", part_type, 0, status="failed", error=str(exc))

            if "rapidapi" in self.enabled_sources:
                try:
                    rapid_records = self.rapidapi.fetch(
                        category=part_type,
                        query=config["rapid_query"],
                        limit=self.limit_per_source,
                    )
                    collected.extend(rapid_records)
                    self._mark_progress("rapidapi", part_type, len(rapid_records))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("RapidAPI fetch failed for %s: %s", part_type, exc)
                    self._mark_progress("rapidapi", part_type, 0, status="failed", error=str(exc))

            inserted = self._save_records(collected)
            total_inserted += inserted

            logger.info(
                "Finished %s: %d collected | %d upserted (db=%s)",
                part_type,
                len(collected),
                inserted,
                self.db_path,
            )

        self._update_stats(total_inserted)
        logger.info("PC parts dataset build complete. Total upserted: %d", total_inserted)

    def _save_records(self, records: List[PCPartRecord]) -> int:
        if not records:
            return 0

        unique_rows: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        seen_name_keys: Set[Tuple[str, str, str]] = set()

        for record in records:
            part_id = record.part_id
            name_key = (
                record.source,
                (record.manufacturer or "").strip().lower(),
                record.product_name.strip().lower(),
            )

            if part_id in seen_ids or part_id in self._existing_part_ids:
                logger.debug("Skipping duplicate part_id %s from %s", part_id, record.source)
                continue

            if name_key in seen_name_keys:
                logger.debug(
                    "Skipping duplicate product %s (%s) from %s due to name match",
                    record.product_name,
                    record.manufacturer,
                    record.source,
                )
                continue

            unique_rows.append(record.to_row())
            seen_ids.add(part_id)
            seen_name_keys.add(name_key)

        if not unique_rows:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO pc_parts (
                    part_id, source, part_type, manufacturer, product_name, model_number,
                    series, price, currency, availability, stock_status, seller, rating,
                    review_count, url, image_url, description, specs_json, attributes_json,
                    data_fetched_at, last_seen_at, raw_json
                ) VALUES (
                    :part_id, :source, :part_type, :manufacturer, :product_name, :model_number,
                    :series, :price, :currency, :availability, :stock_status, :seller, :rating,
                    :review_count, :url, :image_url, :description, :specs_json, :attributes_json,
                    :data_fetched_at, :last_seen_at, :raw_json
                )
                ON CONFLICT(part_id) DO UPDATE SET
                    manufacturer=excluded.manufacturer,
                    product_name=excluded.product_name,
                    model_number=excluded.model_number,
                    series=excluded.series,
                    price=COALESCE(excluded.price, pc_parts.price),
                    availability=COALESCE(excluded.availability, pc_parts.availability),
                    stock_status=COALESCE(excluded.stock_status, pc_parts.stock_status),
                    seller=COALESCE(excluded.seller, pc_parts.seller),
                    rating=COALESCE(excluded.rating, pc_parts.rating),
                    review_count=COALESCE(excluded.review_count, pc_parts.review_count),
                    url=COALESCE(excluded.url, pc_parts.url),
                    image_url=COALESCE(excluded.image_url, pc_parts.image_url),
                    description=COALESCE(excluded.description, pc_parts.description),
                    specs_json=COALESCE(excluded.specs_json, pc_parts.specs_json),
                    attributes_json=COALESCE(excluded.attributes_json, pc_parts.attributes_json),
                    data_fetched_at=excluded.data_fetched_at,
                    last_seen_at=excluded.last_seen_at,
                    raw_json=COALESCE(excluded.raw_json, pc_parts.raw_json)
                """,
                unique_rows,
            )
            conn.commit()
            inserted = cursor.rowcount

        self._existing_part_ids.update(seen_ids)
        return inserted

    def _mark_progress(
        self,
        source: str,
        part_type: str,
        count: int,
        *,
        status: str = "completed",
        error: Optional[str] = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pc_parts_fetch_progress (
                    source, part_type, items_fetched, fetched_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    part_type,
                    count,
                    _now_iso(),
                    status,
                    error,
                ),
            )
            conn.commit()

    def _update_stats(self, total_upserted: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), COUNT(DISTINCT part_id) FROM pc_parts")
            total_records, distinct_parts = cursor.fetchone()

            stats = {
                "last_build": _now_iso(),
                "total_records": str(total_records or 0),
                "unique_parts": str(distinct_parts or 0),
                "upserted_this_run": str(total_upserted),
            }

            for key, value in stats.items():
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pc_parts_dataset_stats (key, value, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (key, value, _now_iso()),
                )

            conn.commit()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the local PC parts SQLite database")
    parser.add_argument(
        "--db-path",
        default="data/pc_parts.db",
        help="Output SQLite database path (default: data/pc_parts.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of records to fetch per source/category (default: 50; use 0 for unlimited)",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["pcpartpicker", "bestbuy", "rapidapi"],
        default=["pcpartpicker", "bestbuy", "rapidapi"],
        help="Subset of data sources to enable (default: all)",
    )

    args = parser.parse_args()

    builder = PCPartsDatasetBuilder(
        db_path=args.db_path,
        limit_per_source=args.limit,
        enabled_sources=args.sources,
    )
    builder.build()


if __name__ == "__main__":
    main()

