"""
Local electronics data access layer backed by SQLite.

Provides filtered queries against the prebuilt pc_parts.db dataset
and returns results shaped like the RapidAPI payloads expected by downstream
components.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from idss_agent.utils.logger import get_logger

logger = get_logger("tools.local_electronics_store")


def _project_root() -> Path:
    """Return project root (parent of idss_agent package)."""
    return Path(__file__).resolve().parent.parent.parent


DEFAULT_DB_PATH = _project_root() / "data" / "pc_parts.db"


class ElectronicsStoreError(RuntimeError):
    """Raised when the local electronics store encounters an error."""


def _parse_numeric_range(value: Any) -> Tuple[Optional[float], Optional[float]]:
    """Parse numeric range strings like "100-300" or "200"."""
    if not value:
        return (None, None)
    
    value = str(value).strip()
    if "-" not in value:
        try:
            num = float(value)
            return (num, num)
        except ValueError:
            return (None, None)
    
    lower, upper = value.split("-", 1)
    lower_val = float(lower) if lower.strip() else None
    upper_val = float(upper) if upper.strip() else None
    return (lower_val, upper_val)


class LocalElectronicsStore:
    """
    Repository for electronics products stored in SQLite pc_parts.db.
    
    Args:
        db_path: Optional override for database location.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        path = Path(db_path) if db_path else DEFAULT_DB_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Local electronics database not found at {path}. "
                "Build it via dataset_builder/fetch_pc_parts_dataset.py."
            )
        self.db_path = path
    
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def search_products(
        self,
        query: Optional[str] = None,
        part_type: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        seller: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Execute a filtered search against the local database.
        
        Args:
            query: Search keywords (searches product_name, model_number, series).
            part_type: Component category filter.
            brand: Brand filter (searches product_name).
            min_price: Minimum price filter.
            max_price: Maximum price filter.
            seller: Seller/retailer filter.
            limit: Maximum number of rows to return.
            offset: Offset for pagination.
        
        Returns:
            List of product dictionaries shaped like RapidAPI responses.
        """
        sql, params = self._build_query(
            query=query,
            part_type=part_type,
            brand=brand,
            min_price=min_price,
            max_price=max_price,
            seller=seller,
            limit=limit,
            offset=offset,
        )
        
        logger.info("Electronics search SQL: %s | params=%s", sql, params)
        
        try:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise ElectronicsStoreError(f"SQLite query failed: {exc}") from exc
        
        products: List[Dict[str, Any]] = []
        for row in rows:
            product = self._row_to_product(row)
            if product:
                products.append(product)
        
        logger.info("Local electronics query returned %d products", len(products))
        return products
    
    def _build_query(
        self,
        query: Optional[str],
        part_type: Optional[str],
        brand: Optional[str],
        min_price: Optional[float],
        max_price: Optional[float],
        seller: Optional[str],
        limit: int,
        offset: int,
    ) -> Tuple[str, Tuple[Any, ...]]:
        """Construct SQL query and parameter tuple from filters."""
        select_clause = """
            SELECT part_id, source, part_type, product_name, model_number, series,
                   price, currency, availability, stock_status, seller,
                   rating, review_count, url, image_url, description,
                   specs_json, attributes_json, raw_json
            FROM pc_parts
        """
        conditions: List[str] = []
        params: List[Any] = []
        
        # Query search (searches product_name, model_number, series, description)
        if query:
            conditions.append(
                "(product_name LIKE ? OR model_number LIKE ? OR series LIKE ? OR description LIKE ?)"
            )
            query_pattern = f"%{query}%"
            params.extend([query_pattern] * 4)
        
        # Part type filter
        if part_type:
            conditions.append("LOWER(part_type) = LOWER(?)")
            params.append(part_type)
        
        # Brand filter (searches product_name)
        if brand:
            conditions.append("LOWER(product_name) LIKE LOWER(?)")
            params.append(f"%{brand}%")
        
        # Price filters
        if min_price is not None:
            conditions.append("price >= ?")
            params.append(min_price)
        
        if max_price is not None:
            conditions.append("price <= ?")
            params.append(max_price)
        
        # Seller filter
        if seller:
            conditions.append("LOWER(seller) LIKE LOWER(?)")
            params.append(f"%{seller}%")
        
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
        
        sql = f"{select_clause}{where_clause} ORDER BY price ASC, product_name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        return sql, tuple(params)
    
    def _row_to_product(self, row: sqlite3.Row) -> Optional[Dict[str, Any]]:
        """Convert a SQLite row into a product dictionary matching RapidAPI format."""
        try:
            # Parse raw JSON if available
            raw_json = row["raw_json"]
            if raw_json:
                try:
                    product = json.loads(raw_json)
                except json.JSONDecodeError:
                    product = {}
            else:
                product = {}
            
            # Parse specs and attributes JSON
            specs = {}
            if row["specs_json"]:
                try:
                    specs = json.loads(row["specs_json"])
                except json.JSONDecodeError:
                    pass
            
            attributes = {}
            if row["attributes_json"]:
                try:
                    attributes = json.loads(row["attributes_json"])
                except json.JSONDecodeError:
                    pass
            
            # Build normalized product dict matching RapidAPI format
            normalized = {
                "id": row["part_id"],
                "product_id": row["part_id"],
                "title": row["product_name"],
                "name": row["product_name"],
                "product_title": row["product_name"],
                "productName": row["product_name"],
                "brand": self._extract_brand(row["product_name"]),
                "model_number": row["model_number"],
                "series": row["series"],
                "category": row["part_type"],
                "type": row["part_type"],
                "price": row["price"],
                "sale_price": row["price"],
                "salePrice": row["price"],
                "finalPrice": row["price"],
                "currency": row["currency"] or "USD",
                "currencyCode": row["currency"] or "USD",
                "url": row["url"],
                "productUrl": row["url"],
                "link": row["url"],
                "image": row["image_url"],
                "imageUrl": row["image_url"],
                "image_url": row["image_url"],
                "thumbnail": row["image_url"],
                "availability": row["availability"],
                "stock_status": row["stock_status"],
                "stockStatus": row["stock_status"],
                "source": row["seller"],
                "seller": row["seller"],
                "sellerName": row["seller"],
                "store": row["seller"],
                "rating": row["rating"],
                "ratingCount": row["review_count"],
                "rating_count": row["review_count"],
                "reviews": row["review_count"],
                "description": row["description"],
                "attributes": attributes,
                "specs": specs,
                "_source": row["source"] or "local_db",
                "_raw": product,
            }
            
            return normalized
            
        except Exception as exc:
            logger.warning("Failed to convert row to product: %s", exc)
            return None
    
    @staticmethod
    def _extract_brand(product_name: Optional[str]) -> Optional[str]:
        """Extract brand from product name (simple heuristic)."""
        if not product_name:
            return None
        
        # Common brand prefixes
        brands = [
            "ASUS", "Dell", "HP", "Lenovo", "Apple", "Samsung", "LG", "Sony",
            "Microsoft", "Intel", "AMD", "NVIDIA", "Corsair", "EVGA",
            "Gigabyte", "MSI", "ASRock", "Seagate", "Western Digital", "WD",
            "Kingston", "Crucial", "G.Skill", "Thermaltake", "Cooler Master",
            "NZXT", "Fractal Design", "be quiet!", "Noctua", "Logitech",
            "Razer", "SteelSeries", "HyperX", "JBL", "Bose", "Sennheiser",
        ]
        
        product_upper = product_name.upper()
        for brand in brands:
            if product_upper.startswith(brand):
                return brand
        
        # Fallback: first word
        return product_name.split()[0] if product_name.split() else None



