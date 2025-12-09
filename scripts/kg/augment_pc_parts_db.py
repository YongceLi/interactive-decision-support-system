#!/usr/bin/env python3
"""
RAG-based augmentation of PC parts database.

This script reads from pc_parts.db and creates pc_parts_augmented.db with
missing compatibility attributes extracted via web scraping and LLM extraction.

Key features:
- Cross-source validation (at least 2 sources must agree)
- Source, URL, timestamp, and confidence tagging
- Manufacturer priority ranking
- Manual review tagging for products without manufacturer data
- Manufacturer documentation link mapping
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Import existing scraping utilities
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / ".env")

try:
    from scripts.kg.llm_extractor import LLMExtractor, convert_to_product_attributes
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    LLMExtractor = None

LOGGER = logging.getLogger("augment_pc_parts_db")


def load_attributes_config() -> Dict[str, Any]:
    """Load attributes configuration from JSON file."""
    config_path = PROJECT_ROOT / "dataset_builder" / "pc_parts_attributes.json"
    if not config_path.exists():
        LOGGER.warning("Attributes config not found at %s, using defaults", config_path)
        return {
            "protected_fields": [
                "product_id", "product_type", "raw_name", "brand", "series",
                "model", "seller", "price", "rating", "rating_count"
            ],
            "part_types": {}
        }
    
    with open(config_path, 'r') as f:
        return json.load(f)


# Load attributes configuration
ATTRIBUTES_CONFIG = load_attributes_config()
PROTECTED_FIELDS = set(ATTRIBUTES_CONFIG.get("protected_fields", [
    "product_id", "product_type", "raw_name", "brand", "series",
    "model", "seller", "price", "rating", "rating_count"
]))


def get_valid_attributes_for_product_type(product_type: str) -> Tuple[List[str], List[str]]:
    """
    Get valid required and optional attributes for a product type.
    
    Args:
        product_type: Product type (e.g., "cpu", "gpu", "motherboard")
    
    Returns:
        Tuple of (required_attributes, optional_attributes)
    """
    part_types = ATTRIBUTES_CONFIG.get("part_types", {})
    product_type_lower = product_type.lower()
    
    # Handle aliases
    if product_type_lower == "internal_storage":
        product_type_lower = "storage"
    
    if product_type_lower in part_types:
        config = part_types[product_type_lower]
        return (
            config.get("required", []),
            config.get("optional", [])
        )
    
    return ([], [])

# Source priority (higher = more trusted)
SOURCE_PRIORITY = {
    "manufacturer": 100,
    "manufacturer_official": 100,
    "manufacturer_official_llm": 95,
    "newegg": 75,  # Higher than Wikipedia - direct product listings, detailed specs
    "newegg_llm": 70,
    "amazon": 70,  # Higher than Wikipedia - product listings, though quality varies
    "amazon_llm": 65,
    "wikipedia": 60,  # Good for general specs but may lack specific model details
    "wikipedia_llm": 55,
    "rapidapi_base": 50,  # Original source, may be incomplete
}

# Minimum sources required for validation
MIN_SOURCES_REQUIRED = 2


@dataclass
class AttributeExtraction:
    """Represents an attribute extraction from a single source."""
    attribute_name: str
    attribute_value: str
    source: str
    source_url: Optional[str]
    timestamp: str
    confidence: float
    is_manufacturer: bool = False


@dataclass
class ValidatedAttribute:
    """Represents a validated attribute with multiple source confirmations."""
    attribute_name: str
    attribute_value: str
    sources: List[AttributeExtraction]
    final_confidence: float
    has_manufacturer_source: bool
    needs_manual_review: bool = False


class ManufacturerMap:
    """Maps manufacturers to their documentation URLs."""
    
    def __init__(self):
        self.manufacturers: Dict[str, Dict[str, Any]] = {}
        self._init_default_manufacturers()
    
    def _init_default_manufacturers(self):
        """Initialize default manufacturer mappings."""
        default_map = {
            "nvidia": {
                "domain": "nvidia.com",
                "product_url_pattern": "https://www.nvidia.com/en-us/geforce/graphics-cards/{model}/",
                "docs_url_pattern": "https://www.nvidia.com/en-us/geforce/graphics-cards/{model}/specifications/",
            },
            "amd": {
                "domain": "amd.com",
                "product_url_pattern": "https://www.amd.com/en/products/processors/{model}",
                "docs_url_pattern": "https://www.amd.com/en/products/processors/{model}/specifications",
            },
            "intel": {
                "domain": "intel.com",
                "product_url_pattern": "https://www.intel.com/content/www/us/en/products/processors/{model}.html",
                "docs_url_pattern": "https://www.intel.com/content/www/us/en/products/processors/{model}/specifications.html",
            },
            "asus": {
                "domain": "asus.com",
                "product_url_pattern": "https://www.asus.com/{category}/{model}/",
                "docs_url_pattern": "https://www.asus.com/{category}/{model}/helpdesk_download/",
            },
            "msi": {
                "domain": "msi.com",
                "product_url_pattern": "https://www.msi.com/{category}/{model}",
                "docs_url_pattern": "https://www.msi.com/{category}/{model}/support",
            },
            "gigabyte": {
                "domain": "gigabyte.com",
                "product_url_pattern": "https://www.gigabyte.com/{category}/{model}",
                "docs_url_pattern": "https://www.gigabyte.com/{category}/{model}/support",
            },
            "asrock": {
                "domain": "asrock.com",
                "product_url_pattern": "https://www.asrock.com/{category}/{model}.asp",
                "docs_url_pattern": "https://www.asrock.com/{category}/{model}.asp#Specification",
            },
            "corsair": {
                "domain": "corsair.com",
                "product_url_pattern": "https://www.corsair.com/us/en/{category}/{model}",
                "docs_url_pattern": "https://www.corsair.com/us/en/{category}/{model}/download",
            },
            "gskill": {
                "domain": "gskill.com",
                "product_url_pattern": "https://www.gskill.com/product/{model}",
                "docs_url_pattern": "https://www.gskill.com/product/{model}",
            },
            "kingston": {
                "domain": "kingston.com",
                "product_url_pattern": "https://www.kingston.com/en/{category}/{model}",
                "docs_url_pattern": "https://www.kingston.com/en/{category}/{model}/specifications",
            },
            "samsung": {
                "domain": "samsung.com",
                "product_url_pattern": "https://www.samsung.com/us/computing/{category}/{model}/",
                "docs_url_pattern": "https://www.samsung.com/us/computing/{category}/{model}/specs/",
            },
            "crucial": {
                "domain": "crucial.com",
                "product_url_pattern": "https://www.crucial.com/products/{category}/{model}",
                "docs_url_pattern": "https://www.crucial.com/products/{category}/{model}/specifications",
            },
            "seasonic": {
                "domain": "seasonic.com",
                "product_url_pattern": "https://www.seasonic.com/{category}/{model}",
                "docs_url_pattern": "https://www.seasonic.com/{category}/{model}",
            },
            "bequiet": {
                "domain": "bequiet.com",
                "product_url_pattern": "https://www.bequiet.com/en/{category}/{model}",
                "docs_url_pattern": "https://www.bequiet.com/en/{category}/{model}",
            },
            "noctua": {
                "domain": "noctua.at",
                "product_url_pattern": "https://noctua.at/en/{category}/{model}",
                "docs_url_pattern": "https://noctua.at/en/{category}/{model}/specification",
            },
            "coolermaster": {
                "domain": "coolermaster.com",
                "product_url_pattern": "https://www.coolermaster.com/us/en-us/{category}/{model}/",
                "docs_url_pattern": "https://www.coolermaster.com/us/en-us/{category}/{model}/specifications/",
            },
            "nzxt": {
                "domain": "nzxt.com",
                "product_url_pattern": "https://www.nzxt.com/products/{model}",
                "docs_url_pattern": "https://www.nzxt.com/products/{model}/specifications",
            },
            "fractal": {
                "domain": "fractal-design.com",
                "product_url_pattern": "https://www.fractal-design.com/products/{category}/{model}/",
                "docs_url_pattern": "https://www.fractal-design.com/products/{category}/{model}/specifications/",
            },
        }
        
        for brand, info in default_map.items():
            self.manufacturers[brand.lower()] = info
    
    def get_manufacturer_info(self, brand: Optional[str]) -> Optional[Dict[str, Any]]:
        """Get manufacturer info for a brand."""
        if not brand:
            return None
        return self.manufacturers.get(brand.lower())
    
    def get_product_url(self, brand: Optional[str], product_name: str, product_type: str) -> Optional[str]:
        """Get manufacturer product URL for a product."""
        info = self.get_manufacturer_info(brand)
        if not info:
            return None
        
        # Map product types to manufacturer categories
        category_map = {
            "gpu": "graphics-cards",
            "cpu": "processors",
            "motherboard": "motherboards",
            "psu": "power-supplies",
            "ram": "memory",
            "cooling": "cooling",
            "case": "cases",
            "storage": "storage",
        }
        
        category = category_map.get(product_type.lower(), product_type.lower())
        model_slug = product_name.lower().replace(" ", "-").replace("_", "-")
        
        try:
            url = info["product_url_pattern"].format(category=category, model=model_slug)
            return url
        except KeyError:
            return None
    
    def save_to_db(self, conn: sqlite3.Connection):
        """Save manufacturer map to database."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manufacturer_map (
                brand TEXT PRIMARY KEY,
                domain TEXT,
                product_url_pattern TEXT,
                docs_url_pattern TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        for brand, info in self.manufacturers.items():
            cursor.execute("""
                INSERT OR REPLACE INTO manufacturer_map 
                (brand, domain, product_url_pattern, docs_url_pattern, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                brand,
                info.get("domain"),
                info.get("product_url_pattern"),
                info.get("docs_url_pattern"),
                datetime.now(timezone.utc).isoformat()
            ))
        
        conn.commit()


class AttributeScraper:
    """Scrapes attributes from multiple sources."""
    
    def __init__(self, use_llm: bool = True):
        self.session = requests.Session()
        # More complete browser headers to avoid anti-scraping detection
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        })
        self.use_llm = use_llm and LLM_AVAILABLE
        self.llm_extractor = None
        
        if self.use_llm:
            try:
                self.llm_extractor = LLMExtractor()
                LOGGER.info("LLM extraction enabled")
            except Exception as e:
                LOGGER.warning("Failed to initialize LLM extractor: %s", e)
                self.use_llm = False
    
    def scrape_newegg(self, product_name: str, brand: Optional[str]) -> List[AttributeExtraction]:
        """Scrape Newegg for product attributes."""
        extractions = []
        search_url = f"https://www.newegg.com/p/pl?d={product_name.replace(' ', '+')}"
        
        try:
            LOGGER.debug("Scraping Newegg: %s", search_url)
            response = self.session.get(search_url, timeout=10, allow_redirects=True)
            # Handle common anti-scraping responses gracefully
            if response.status_code == 403:
                LOGGER.warning("Newegg returned 403 Forbidden (anti-scraping protection). Skipping.")
                return extractions
            if response.status_code == 503:
                LOGGER.warning("Newegg returned 503 Service Unavailable. Skipping.")
                return extractions
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            if self.use_llm and self.llm_extractor:
                try:
                    extracted = self.llm_extractor.extract_from_html(
                        str(soup),
                        product_name,
                        f"{brand}-{product_name}" if brand else product_name,
                        source="newegg"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_name,
                        source_url=search_url,
                        source_seller="newegg_llm"
                    )
                    
                    for attr in llm_attrs:
                        extractions.append(AttributeExtraction(
                            attribute_name=attr["attribute_type"],
                            attribute_value=attr["attribute_value"],
                            source="newegg_llm",
                            source_url=search_url,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            confidence=attr["confidence"],
                            is_manufacturer=False
                        ))
                except Exception as e:
                    LOGGER.warning("LLM extraction from Newegg failed: %s", e)
            
            # Fallback regex extraction
            spec_tables = soup.find_all('table', class_='table-horizontal')
            for table in spec_tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        
                        # Map common keys to attribute names
                        attr_name = self._map_key_to_attribute(key)
                        if attr_name:
                            extractions.append(AttributeExtraction(
                                attribute_name=attr_name,
                                attribute_value=value,
                                source="newegg",
                                source_url=search_url,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                confidence=0.8,
                                is_manufacturer=False
                            ))
            
            time.sleep(1)  # Rate limiting
        except requests.exceptions.HTTPError as e:
            # HTTP errors (403, 503, etc.) are expected due to anti-scraping
            if e.response.status_code in (403, 503, 429):
                LOGGER.debug("Newegg blocked request (status %d): %s", e.response.status_code, e)
            else:
                LOGGER.warning("Newegg HTTP error (status %d): %s", e.response.status_code, e)
        except Exception as e:
            LOGGER.warning("Error scraping Newegg: %s", e)
        
        return extractions
    
    def scrape_amazon(self, product_name: str, brand: Optional[str]) -> List[AttributeExtraction]:
        """Scrape Amazon for product attributes."""
        extractions = []
        search_url = f"https://www.amazon.com/s?k={product_name.replace(' ', '+')}"
        
        try:
            LOGGER.debug("Scraping Amazon: %s", search_url)
            # Note: Amazon has strict anti-scraping measures
            # In production, use Amazon Product Advertising API
            response = self.session.get(search_url, timeout=10, allow_redirects=True)
            # Handle common anti-scraping responses gracefully
            if response.status_code == 403:
                LOGGER.warning("Amazon returned 403 Forbidden (anti-scraping protection). Skipping.")
                return extractions
            if response.status_code == 503:
                LOGGER.warning("Amazon returned 503 Service Unavailable. Skipping.")
                return extractions
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            if self.use_llm and self.llm_extractor:
                try:
                    extracted = self.llm_extractor.extract_from_html(
                        str(soup),
                        product_name,
                        f"{brand}-{product_name}" if brand else product_name,
                        source="amazon"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_name,
                        source_url=search_url,
                        source_seller="amazon_llm"
                    )
                    
                    for attr in llm_attrs:
                        extractions.append(AttributeExtraction(
                            attribute_name=attr["attribute_type"],
                            attribute_value=attr["attribute_value"],
                            source="amazon_llm",
                            source_url=search_url,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            confidence=attr["confidence"],
                            is_manufacturer=False
                        ))
                except Exception as e:
                    LOGGER.warning("LLM extraction from Amazon failed: %s", e)
            
            time.sleep(2)  # Rate limiting for Amazon
        except requests.exceptions.HTTPError as e:
            # HTTP errors (403, 503, etc.) are expected due to anti-scraping
            if e.response.status_code in (403, 503, 429):
                LOGGER.debug("Amazon blocked request (status %d): %s", e.response.status_code, e)
            else:
                LOGGER.warning("Amazon HTTP error (status %d): %s", e.response.status_code, e)
        except Exception as e:
            LOGGER.warning("Error scraping Amazon: %s", e)
        
        return extractions
    
    def scrape_wikipedia(self, product_name: str, brand: Optional[str]) -> List[AttributeExtraction]:
        """Scrape Wikipedia for product attributes.
        
        Note: Wikipedia is searched using SERIES NAME, not individual model names.
        This is because Wikipedia typically has pages for product series (e.g., "RTX 4090", 
        "Ryzen 9 5950X") rather than specific SKUs/models (e.g., "ASUS ROG Strix RTX 4090 OC").
        Series-level information is still valuable for compatibility attributes like socket,
        PCIe version, RAM standard, etc.
        """
        extractions = []
        
        # Extract series name for Wikipedia lookup (not individual model)
        series_name = self._extract_series_name(product_name)
        LOGGER.debug("Wikipedia search: extracted series '%s' from product '%s'", series_name, product_name)
        search_url = f"https://en.wikipedia.org/wiki/{series_name.replace(' ', '_')}"
        
        try:
            LOGGER.debug("Scraping Wikipedia: %s", search_url)
            response = self.session.get(search_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            
            if response.status_code == 404:
                # Try Wikipedia search API
                search_api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{series_name.replace(' ', '_')}"
                response = self.session.get(search_api_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                
                if response.status_code == 200:
                    data = response.json()
                    if 'content_urls' in data and 'desktop' in data['content_urls']:
                        search_url = data['content_urls']['desktop']['page']
                        response = self.session.get(search_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            
            if response.status_code != 200:
                return extractions
            
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            if self.use_llm and self.llm_extractor:
                try:
                    extracted = self.llm_extractor.extract_from_html(
                        str(soup),
                        product_name,
                        f"{brand}-{product_name}" if brand else product_name,
                        source="wikipedia"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_name,
                        source_url=search_url,
                        source_seller="wikipedia_llm"
                    )
                    
                    for attr in llm_attrs:
                        extractions.append(AttributeExtraction(
                            attribute_name=attr["attribute_type"],
                            attribute_value=attr["attribute_value"],
                            source="wikipedia_llm",
                            source_url=search_url,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            confidence=attr["confidence"],
                            is_manufacturer=False
                        ))
                except Exception as e:
                    LOGGER.warning("LLM extraction from Wikipedia failed: %s", e)
            
            # Extract from infobox
            infobox = soup.find('table', class_='infobox')
            if infobox:
                rows = infobox.find_all('tr')
                for row in rows:
                    header = row.find('th')
                    data = row.find('td')
                    if header and data:
                        key = header.get_text(strip=True).lower()
                        value = data.get_text(strip=True)
                        
                        if not value or value in ('—', 'N/A'):
                            continue
                        
                        attr_name = self._map_key_to_attribute(key)
                        if attr_name:
                            extractions.append(AttributeExtraction(
                                attribute_name=attr_name,
                                attribute_value=value,
                                source="wikipedia",
                                source_url=search_url,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                confidence=0.85,
                                is_manufacturer=False
                            ))
            
            time.sleep(1)  # Rate limiting
        except Exception as e:
            LOGGER.error("Error scraping Wikipedia: %s", e)
        
        return extractions
    
    def scrape_manufacturer(self, product_name: str, brand: Optional[str], 
                          product_type: str, manufacturer_map: ManufacturerMap) -> List[AttributeExtraction]:
        """Scrape manufacturer website for product attributes."""
        extractions = []
        
        if not brand:
            return extractions
        
        product_url = manufacturer_map.get_product_url(brand, product_name, product_type)
        if not product_url:
            LOGGER.debug("No manufacturer URL found for %s %s", brand, product_name)
            return extractions
        
        try:
            LOGGER.debug("Scraping manufacturer: %s", product_url)
            response = self.session.get(product_url, timeout=10)
            
            if response.status_code != 200:
                return extractions
            
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            if self.use_llm and self.llm_extractor:
                try:
                    extracted = self.llm_extractor.extract_from_html(
                        str(soup),
                        product_name,
                        f"{brand}-{product_name}",
                        source=f"{brand}_official"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_name,
                        source_url=product_url,
                        source_seller=f"{brand}_official_llm"
                    )
                    
                    for attr in llm_attrs:
                        extractions.append(AttributeExtraction(
                            attribute_name=attr["attribute_type"],
                            attribute_value=attr["attribute_value"],
                            source=f"{brand}_official_llm",
                            source_url=product_url,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            confidence=attr["confidence"],
                            is_manufacturer=True
                        ))
                except Exception as e:
                    LOGGER.warning("LLM extraction from manufacturer failed: %s", e)
            
            # Fallback regex extraction
            spec_sections = soup.find_all(['div', 'section', 'table'], 
                                         class_=lambda x: x and ('spec' in x.lower() or 'detail' in x.lower()))
            for section in spec_sections:
                rows = section.find_all(['tr', 'div'], class_=lambda x: x and ('row' in x.lower() or 'item' in x.lower()))
                for row in rows:
                    key_elem = row.find(['th', 'dt', 'span', 'div'], class_=lambda x: x and ('key' in x.lower() or 'label' in x.lower()))
                    value_elem = row.find(['td', 'dd', 'span', 'div'], class_=lambda x: x and ('value' in x.lower() or 'data' in x.lower()))
                    
                    if key_elem and value_elem:
                        key = key_elem.get_text(strip=True).lower()
                        value = value_elem.get_text(strip=True)
                        
                        attr_name = self._map_key_to_attribute(key)
                        if attr_name:
                            extractions.append(AttributeExtraction(
                                attribute_name=attr_name,
                                attribute_value=value,
                                source=f"{brand}_official",
                                source_url=product_url,
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                confidence=0.95,
                                is_manufacturer=True
                            ))
            
            time.sleep(1)  # Rate limiting
        except Exception as e:
            LOGGER.error("Error scraping manufacturer: %s", e)
        
        return extractions
    
    def _extract_series_name(self, product_name: str) -> str:
        """Extract series name from product name for Wikipedia lookup.
        
        Wikipedia typically has pages for product series (e.g., "GeForce RTX 4090", 
        "Ryzen 9 5950X") rather than specific SKUs. This method extracts the series
        name by removing brand/model prefixes and extracting the core series identifier.
        
        Examples:
        - "ASUS ROG Strix RTX 4090 OC" -> "RTX 4090"
        - "AMD Ryzen 9 5950X" -> "Ryzen 9 5950X"
        - "Intel Core i9-13900K" -> "Core i9-13900K"
        """
        import re
        
        # GPU patterns - extract series (RTX 4090, GTX 1660, RX 7900 XTX, etc.)
        gpu_patterns = [
            r'(GeForce\s+RTX\s+\d+\s*(?:Ti|Super)?)',  # "GeForce RTX 4090"
            r'(RTX\s+\d+\s*(?:Ti|Super)?)',              # "RTX 4090"
            r'(GeForce\s+GTX\s+\d+\s*(?:Ti|Super)?)',   # "GeForce GTX 1660"
            r'(GTX\s+\d+\s*(?:Ti|Super)?)',             # "GTX 1660"
            r'(Radeon\s+RX\s+\d+\s*(?:XT|XTX)?)',       # "Radeon RX 7900 XTX"
            r'(RX\s+\d+\s*(?:XT|XTX)?)',                # "RX 7900 XTX"
            r'(Arc\s+A\d+)',                            # "Arc A770"
        ]
        
        for pattern in gpu_patterns:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # CPU patterns - extract series (Core i9-13900K, Ryzen 9 5950X, etc.)
        cpu_patterns = [
            r'(Intel\s+Core\s+i\d+\s*-\s*\d+\w*)',      # "Intel Core i9-13900K"
            r'(Core\s+i\d+\s*-\s*\d+\w*)',              # "Core i9-13900K"
            r'(AMD\s+Ryzen\s+\d+\s+\d+\w*)',            # "AMD Ryzen 9 5950X"
            r'(Ryzen\s+\d+\s+\d+\w*)',                  # "Ryzen 9 5950X"
            r'(AMD\s+Threadripper\s+\d+\w*)',          # "AMD Threadripper 3990X"
            r'(Threadripper\s+\d+\w*)',                 # "Threadripper 3990X"
            r'(AMD\s+EPYC\s+\d+\w*)',                   # "AMD EPYC 7551P"
            r'(EPYC\s+\d+\w*)',                         # "EPYC 7551P"
            r'(Intel\s+Xeon\s+\w+)',                    # "Intel Xeon W-2295"
            r'(Xeon\s+\w+)',                            # "Xeon W-2295"
        ]
        
        for pattern in cpu_patterns:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Motherboard patterns - extract chipset/series
        motherboard_patterns = [
            r'([ABXZ]\d{3,4}[A-Z]?\s*(?:E|M)?)',       # "Z790", "B650E", "X570"
            r'(TRX40|WRX90)',                           # "TRX40", "WRX90"
        ]
        
        for pattern in motherboard_patterns:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                chipset = match.group(1).strip()
                # Try to construct a series name (e.g., "Intel Z790" or "AMD B650")
                if 'intel' in product_name.lower() or 'core' in product_name.lower():
                    return f"Intel {chipset}"
                elif 'amd' in product_name.lower() or 'ryzen' in product_name.lower():
                    return f"AMD {chipset}"
                return chipset
        
        # Fallback: remove common brand/model prefixes and use first meaningful part
        # Remove GPU/CPU brand prefixes
        cleaned = re.sub(r'^(Asus|MSI|Gigabyte|EVGA|Sapphire|PowerColor|XFX|ASRock|NVIDIA|AMD|Intel)\s+', '', product_name, flags=re.IGNORECASE)
        # Remove common model prefixes
        cleaned = re.sub(r'^(ROG\s+Strix|TUF|Gaming|Dual|OC|AORUS|Gaming\s+X)\s+', '', cleaned, flags=re.IGNORECASE)
        # Take first 50 chars (Wikipedia page names shouldn't be too long)
        return cleaned[:50].strip()
    
    def _map_key_to_attribute(self, key: str) -> Optional[str]:
        """Map a scraped key to a standardized attribute name."""
        key_lower = key.lower()
        
        # Build mapping from attributes config
        # Get all valid attribute names from all part types
        valid_attributes = set()
        part_types = ATTRIBUTES_CONFIG.get("part_types", {})
        for part_type_config in part_types.values():
            valid_attributes.update(part_type_config.get("required", []))
            valid_attributes.update(part_type_config.get("optional", []))
        
        # Map common variations to standard attribute names
        mapping = {
            "socket": "socket",
            "cpu socket": "socket",
            "chipset": "chipset",
            "form factor": "form_factor",
            "formfactor": "form_factor",
            "pcie": "pcie_version",
            "pci express": "pcie_version",
            "pcie version": "pcie_version",
            "ram": "ram_standard",
            "memory type": "ram_standard",
            "ddr": "ram_standard",
            "tdp": "tdp",
            "thermal design power": "tdp",
            "wattage": "wattage",
            "power": "wattage",
            "vram": "vram",
            "video memory": "vram",
            "memory type": "memory_type",
            "cooler type": "cooler_type",
            "cooling type": "cooling_type",
            "interface": "interface",
            "power connector": "power_connector",
            "certification": "certification",
            "efficiency": "certification",
            "modularity": "modularity",
            "modular": "modularity",
            "capacity": "capacity",
            "storage type": "storage_type",
            "year": "year",
            "release year": "year",
            "color": "color",
            "size": "size",
            "architecture": "architecture",
            "variant": "variant",
            "is oc": "is_oc",
            "overclocked": "is_oc",
            "revision": "revision",
            "atx version": "atx_version",
            "atx": "atx_version",
            "noise": "noise",
            "supports pcie5": "supports_pcie5_power",
            "pcie5 power": "supports_pcie5_power",
            "storage": "storage",
        }
        
        # Check exact matches first
        if key_lower in mapping:
            attr_name = mapping[key_lower]
            if attr_name in valid_attributes:
                return attr_name
        
        # Check partial matches
        for pattern, attr_name in mapping.items():
            if pattern in key_lower and attr_name in valid_attributes:
                return attr_name
        
        # Direct check if key matches a valid attribute name
        if key_lower.replace(" ", "_") in valid_attributes:
            return key_lower.replace(" ", "_")
        
        return None


class AttributeValidator:
    """Validates attributes across multiple sources."""
    
    @staticmethod
    def validate_attributes(extractions: List[AttributeExtraction]) -> List[ValidatedAttribute]:
        """Validate attributes by requiring agreement from multiple sources."""
        # Group extractions by attribute name and value
        grouped: Dict[Tuple[str, str], List[AttributeExtraction]] = {}
        
        for ext in extractions:
            key = (ext.attribute_name, ext.attribute_value.lower().strip())
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(ext)
        
        validated = []
        
        for (attr_name, attr_value), sources in grouped.items():
            # Check if we have enough sources
            if len(sources) < MIN_SOURCES_REQUIRED:
                continue
            
            # Check if we have manufacturer source
            has_manufacturer = any(s.is_manufacturer for s in sources)
            
            # Calculate final confidence based on source priority
            source_priorities = [SOURCE_PRIORITY.get(s.source, 50) for s in sources]
            avg_priority = sum(source_priorities) / len(source_priorities)
            base_confidence = min(avg_priority / 100.0, 0.95)
            
            # Boost confidence if manufacturer source exists
            if has_manufacturer:
                base_confidence = min(base_confidence * 1.1, 0.98)
            
            # Determine if manual review is needed
            needs_review = not has_manufacturer
            
            validated.append(ValidatedAttribute(
                attribute_name=attr_name,
                attribute_value=attr_value,
                sources=sources,
                final_confidence=base_confidence,
                has_manufacturer_source=has_manufacturer,
                needs_manual_review=needs_review
            ))
        
        return validated


class DatabaseAugmenter:
    """Augments the PC parts database with scraped attributes."""
    
    def __init__(self, source_db_path: str, target_db_path: str, use_llm: bool = True):
        self.source_db_path = source_db_path
        self.target_db_path = target_db_path
        self.scraper = AttributeScraper(use_llm=use_llm)
        self.validator = AttributeValidator()
        self.manufacturer_map = ManufacturerMap()
        self._init_target_database()
    
    def _ensure_column_exists(self, conn: sqlite3.Connection, table: str, column: str, column_type: str = "TEXT"):
        """Dynamically add a column if it doesn't exist."""
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        if column not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                conn.commit()
                LOGGER.debug("Added column %s to table %s", column, table)
            except sqlite3.OperationalError as e:
                LOGGER.warning("Failed to add column %s to table %s: %s", column, table, e)
    
    def _init_target_database(self):
        """Initialize the augmented database schema with dynamic attribute columns."""
        conn = sqlite3.connect(self.target_db_path)
        cursor = conn.cursor()
        
        # Create main products table - matching source schema with dynamic attribute columns
        # Start with base columns, attributes will be added dynamically
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pc_parts_augmented (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL UNIQUE,
                slug TEXT NOT NULL UNIQUE,
                product_type TEXT NOT NULL,
                series TEXT,
                model TEXT,
                brand TEXT,
                size TEXT,
                color TEXT,
                year INTEGER,
                price REAL,
                price_min REAL,
                price_max REAL,
                price_avg REAL,
                seller TEXT,
                sellers TEXT,
                rating REAL,
                rating_count INTEGER,
                raw_name TEXT,
                imageurl TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                needs_manual_review BOOLEAN DEFAULT 0
            )
        """)
        
        # Add all known attribute columns from the attributes config
        # This ensures all expected attributes have columns from the start
        part_types = ATTRIBUTES_CONFIG.get("part_types", {})
        all_attributes = set()
        for part_type_config in part_types.values():
            all_attributes.update(part_type_config.get("required", []))
            all_attributes.update(part_type_config.get("optional", []))
        
        # Add common attributes that might be shared
        all_attributes.update(["year", "color", "size"])
        
        # Add all attribute columns dynamically
        for attr_name in all_attributes:
            if attr_name not in PROTECTED_FIELDS:
                self._ensure_column_exists(conn, "pc_parts_augmented", attr_name, "TEXT")
        
        # Ensure imageurl column exists
        self._ensure_column_exists(conn, "pc_parts_augmented", "imageurl", "TEXT")
        
        # Create attributes table with source tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_attributes_augmented (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                attribute_name TEXT NOT NULL,
                attribute_value TEXT NOT NULL,
                source TEXT NOT NULL,
                source_url TEXT,
                timestamp TEXT NOT NULL,
                confidence REAL NOT NULL,
                is_manufacturer BOOLEAN DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES pc_parts_augmented(product_id)
            )
        """)
        
        # Create validated attributes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS validated_attributes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                attribute_name TEXT NOT NULL,
                attribute_value TEXT NOT NULL,
                final_confidence REAL NOT NULL,
                has_manufacturer_source BOOLEAN DEFAULT 0,
                needs_manual_review BOOLEAN DEFAULT 0,
                sources_json TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES pc_parts_augmented(product_id),
                UNIQUE(product_id, attribute_name)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_augmented_type ON pc_parts_augmented(product_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_augmented_brand ON pc_parts_augmented(brand)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attrs_product ON product_attributes_augmented(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_validated_product ON validated_attributes(product_id)")
        
        # Save manufacturer map
        self.manufacturer_map.save_to_db(conn)
        
        conn.commit()
        conn.close()
    
    def copy_base_data(self):
        """Copy base product data from source database and parse base_attributes."""
        source_conn = sqlite3.connect(self.source_db_path)
        target_conn = sqlite3.connect(self.target_db_path)
        
        source_cursor = source_conn.cursor()
        target_cursor = target_conn.cursor()
        
        # Read all products from source - select all columns that exist
        # Note: The actual schema has attributes as individual columns, not in base_attributes JSON
        source_cursor.execute("""
            SELECT product_id, slug, product_type, series, model, brand, size, color,
                   price, year, seller, rating, rating_count, raw_name, imageurl, created_at, updated_at,
                   socket, architecture, pcie_version, ram_standard, tdp,
                   vram, memory_type, cooler_type, variant, is_oc, revision, interface, power_connector,
                   chipset, form_factor,
                   wattage, certification, modularity, atx_version, noise, supports_pcie5_power,
                   storage, capacity, storage_type,
                   cooling_type, tdp_support
            FROM pc_parts
        """)
        rows = source_cursor.fetchall()
        
        # Insert into target with explicit column mapping and build base_attributes from individual columns
        parsed_count = 0
        for row in rows:
            try:
                # Unpack row
                (product_id, slug, product_type, series, model, brand, size, color,
                 price, year, seller, rating, rating_count, raw_name, imageurl, created_at, updated_at,
                 socket, architecture, pcie_version, ram_standard, tdp,
                 vram, memory_type, cooler_type, variant, is_oc, revision, interface, power_connector,
                 chipset, form_factor,
                 wattage, certification, modularity, atx_version, noise, supports_pcie5_power,
                 storage, capacity, storage_type,
                 cooling_type, tdp_support) = row
                
                # Build base_attributes JSON from individual attribute columns
                base_attrs = {}
                attribute_columns = {
                    'socket': socket, 'architecture': architecture, 'pcie_version': pcie_version,
                    'ram_standard': ram_standard, 'tdp': tdp,
                    'vram': vram, 'memory_type': memory_type, 'cooler_type': cooler_type,
                    'variant': variant, 'is_oc': is_oc, 'revision': revision,
                    'interface': interface, 'power_connector': power_connector,
                    'chipset': chipset, 'form_factor': form_factor,
                    'wattage': wattage, 'certification': certification, 'modularity': modularity,
                    'atx_version': atx_version, 'noise': noise, 'supports_pcie5_power': supports_pcie5_power,
                    'storage': storage, 'capacity': capacity, 'storage_type': storage_type,
                    'cooling_type': cooling_type, 'tdp_support': tdp_support
                }
                
                for attr_name, attr_value in attribute_columns.items():
                    if attr_value is not None and str(attr_value).strip():
                        base_attrs[attr_name] = attr_value
                
                base_attributes_json = json.dumps(base_attrs) if base_attrs else None
                
                # Set price_min, price_max, price_avg to price (or NULL if price is NULL)
                price_min = price_max = price_avg = price
                sellers = seller  # Use seller as sellers
                
                # Insert product
                target_cursor.execute("""
                    INSERT OR IGNORE INTO pc_parts_augmented
                    (product_id, slug, product_type, series, model, brand, size, color,
                     price, price_min, price_max, price_avg, year, seller, sellers,
                     rating, rating_count, base_attributes, raw_name, imageurl, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (product_id, slug, product_type, series, model, brand, size, color,
                      price, price_min, price_max, price_avg, year, seller, sellers,
                      rating, rating_count, base_attributes_json, raw_name, imageurl, created_at, updated_at))
                
                # Parse base_attributes JSON and extract individual attributes
                if base_attributes_json:
                    try:
                        base_attrs = json.loads(base_attributes_json)
                        if isinstance(base_attrs, dict):
                            timestamp = datetime.now(timezone.utc).isoformat()
                            
                            # Get valid attributes for this product type
                            required_attrs, optional_attrs = get_valid_attributes_for_product_type(product_type)
                            valid_attributes = set(required_attrs + optional_attrs)
                            
                            for attr_name, attr_value in base_attrs.items():
                                # Skip protected fields
                                if attr_name in PROTECTED_FIELDS:
                                    continue
                                
                                # Normalize attribute name to snake_case
                                attr_name_normalized = attr_name.lower().replace(" ", "_").replace("-", "_")
                                
                                # Check if it's a valid attribute for this product type
                                if valid_attributes and attr_name_normalized not in valid_attributes:
                                    # Try to find a match (e.g., "pcie_version" vs "pcie-version")
                                    matched = False
                                    for valid_attr in valid_attributes:
                                        if valid_attr.replace("_", "-") == attr_name_normalized.replace("_", "-"):
                                            attr_name_normalized = valid_attr
                                            matched = True
                                            break
                                    if not matched:
                                        LOGGER.debug("Skipping base attribute '%s' (not valid for %s)", 
                                                   attr_name_normalized, product_type)
                                        continue
                                
                                # Convert value to string
                                attr_value_str = str(attr_value)
                                
                                # Save as extraction with "rapidapi_base" source
                                target_cursor.execute("""
                                    INSERT INTO product_attributes_augmented
                                    (product_id, attribute_name, attribute_value, source, source_url, timestamp, confidence, is_manufacturer)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    product_id,
                                    attr_name_normalized,
                                    attr_value_str,
                                    "rapidapi_base",
                                    None,
                                    timestamp,
                                    0.9,  # High confidence for base attributes from RapidAPI
                                    0  # Not from manufacturer
                                ))
                                
                                # Also save as validated attribute (base attributes are pre-validated)
                                sources_json = json.dumps([{
                                    "source": "rapidapi_base",
                                    "source_url": None,
                                    "timestamp": timestamp,
                                    "confidence": 0.9
                                }])
                                
                                target_cursor.execute("""
                                    INSERT OR IGNORE INTO validated_attributes
                                    (product_id, attribute_name, attribute_value, final_confidence, has_manufacturer_source, needs_manual_review, sources_json)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    product_id,
                                    attr_name_normalized,
                                    attr_value_str,
                                    0.9,
                                    0,  # Not from manufacturer
                                    0,  # No manual review needed for base attributes
                                    sources_json
                                ))
                                
                                # Note: We don't add attributes as columns to avoid sparse tables
                                # Attributes are stored in validated_attributes table and will be
                                # parsed from base_attributes JSON at knowledge graph creation time
                                # Only update common fields that exist in schema (year, color, size)
                                if attr_name_normalized == "year":
                                    try:
                                        import re
                                        numbers = re.findall(r'\d+', attr_value_str)
                                        if numbers:
                                            target_cursor.execute("""
                                                UPDATE pc_parts_augmented
                                                SET year = ?
                                                WHERE product_id = ?
                                            """, (int(numbers[0]), product_id))
                                    except (ValueError, TypeError):
                                        pass
                                elif attr_name_normalized == "color":
                                    target_cursor.execute("""
                                        UPDATE pc_parts_augmented
                                        SET color = ?
                                        WHERE product_id = ?
                                    """, (attr_value_str, product_id))
                                elif attr_name_normalized == "size":
                                    target_cursor.execute("""
                                        UPDATE pc_parts_augmented
                                        SET size = ?
                                        WHERE product_id = ?
                                    """, (attr_value_str, product_id))
                                
                                parsed_count += 1
                    except json.JSONDecodeError as e:
                        LOGGER.warning("Failed to parse base_attributes JSON for product %s: %s", product_id, e)
                    except Exception as e:
                        LOGGER.warning("Error processing base_attributes for product %s: %s", product_id, e)
                        
            except sqlite3.IntegrityError:
                # Product already exists, skip
                pass
        
        target_conn.commit()
        source_conn.close()
        target_conn.close()
        
        LOGGER.info("Copied %d products from source database, parsed %d base attributes", len(rows), parsed_count)
    
    def augment_product(self, product_id: str, product_name: str, product_type: str, 
                       brand: Optional[str], limit_sources: Optional[List[str]] = None) -> bool:
        """Augment a single product with scraped attributes."""
        if limit_sources is None:
            limit_sources = ["newegg", "amazon", "wikipedia", "manufacturer"]
        
        # Scrape from all sources
        all_extractions: List[AttributeExtraction] = []
        
        if "newegg" in limit_sources:
            newegg_extractions = self.scraper.scrape_newegg(product_name, brand)
            all_extractions.extend(newegg_extractions)
        
        if "amazon" in limit_sources:
            amazon_extractions = self.scraper.scrape_amazon(product_name, brand)
            all_extractions.extend(amazon_extractions)
        
        if "wikipedia" in limit_sources:
            wikipedia_extractions = self.scraper.scrape_wikipedia(product_name, brand)
            all_extractions.extend(wikipedia_extractions)
        
        if "manufacturer" in limit_sources:
            manufacturer_extractions = self.scraper.scrape_manufacturer(
                product_name, brand, product_type, self.manufacturer_map
            )
            all_extractions.extend(manufacturer_extractions)
        
        # Filter out protected fields and validate attribute names
        required_attrs, optional_attrs = get_valid_attributes_for_product_type(product_type)
        valid_attributes = set(required_attrs + optional_attrs)
        
        # Filter extractions: remove protected fields and invalid attributes
        filtered_extractions = []
        for e in all_extractions:
            if e.attribute_name in PROTECTED_FIELDS:
                continue
            if valid_attributes and e.attribute_name not in valid_attributes:
                LOGGER.debug("Filtering out invalid attribute '%s' for product type '%s'", 
                           e.attribute_name, product_type)
                continue
            filtered_extractions.append(e)
        
        all_extractions = filtered_extractions
        
        # Validate attributes
        validated = self.validator.validate_attributes(all_extractions)
        
        # Save to database
        conn = sqlite3.connect(self.target_db_path)
        cursor = conn.cursor()
        
        # Save all extractions
        for ext in all_extractions:
            cursor.execute("""
                INSERT INTO product_attributes_augmented
                (product_id, attribute_name, attribute_value, source, source_url, timestamp, confidence, is_manufacturer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id,
                ext.attribute_name,
                ext.attribute_value,
                ext.source,
                ext.source_url,
                ext.timestamp,
                ext.confidence,
                1 if ext.is_manufacturer else 0
            ))
        
        # Save validated attributes
        has_manufacturer = any(v.has_manufacturer_source for v in validated)
        needs_review = not has_manufacturer
        
        for val in validated:
            sources_json = json.dumps([
                {
                    "source": s.source,
                    "source_url": s.source_url,
                    "timestamp": s.timestamp,
                    "confidence": s.confidence
                }
                for s in val.sources
            ])
            
            cursor.execute("""
                INSERT OR REPLACE INTO validated_attributes
                (product_id, attribute_name, attribute_value, final_confidence, has_manufacturer_source, needs_manual_review, sources_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                product_id,
                val.attribute_name,
                val.attribute_value,
                val.final_confidence,
                1 if val.has_manufacturer_source else 0,
                1 if val.needs_manual_review else 0,
                sources_json
            ))
        
        # Update product needs_manual_review flag
        # Note: Attributes are stored in validated_attributes table, not as columns
        # This avoids sparse tables since different product types have different attributes
        # Attributes will be parsed from base_attributes JSON and validated_attributes at KG creation time
        
        # Only update common fields that exist in schema (year, color, size)
        for val in validated:
            if val.attribute_name not in PROTECTED_FIELDS:
                if val.attribute_name == "year":
                    try:
                        import re
                        numbers = re.findall(r'\d+', val.attribute_value)
                        if numbers:
                            cursor.execute("""
                                UPDATE pc_parts_augmented
                                SET year = ?
                                WHERE product_id = ?
                            """, (int(numbers[0]), product_id))
                    except (ValueError, TypeError):
                        pass
                elif val.attribute_name == "color":
                    cursor.execute("""
                        UPDATE pc_parts_augmented
                        SET color = ?
                        WHERE product_id = ?
                    """, (val.attribute_value, product_id))
                elif val.attribute_name == "size":
                    cursor.execute("""
                        UPDATE pc_parts_augmented
                        SET size = ?
                        WHERE product_id = ?
                    """, (val.attribute_value, product_id))
        
        # Update needs_manual_review and updated_at
        cursor.execute("""
            UPDATE pc_parts_augmented
            SET needs_manual_review = ?, updated_at = ?
            WHERE product_id = ?
        """, (
            1 if needs_review else 0,
            datetime.now(timezone.utc).isoformat(),
            product_id
        ))
        
        conn.commit()
        conn.close()
        
        LOGGER.info("Augmented product %s: %d extractions, %d validated attributes, needs_review=%s",
                   product_id, len(all_extractions), len(validated), needs_review)
        
        return len(validated) > 0
    
    def augment_all(self, limit: Optional[int] = None, delay: float = 2.0, limit_sources: Optional[List[str]] = None):
        """Augment all products in the database."""
        conn = sqlite3.connect(self.source_db_path)
        cursor = conn.cursor()
        
        query = "SELECT product_id, raw_name, product_type, brand FROM pc_parts"
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        products = cursor.fetchall()
        conn.close()
        
        LOGGER.info("Augmenting %d products", len(products))
        
        success_count = 0
        skip_count = 0
        
        for idx, (product_id, raw_name, product_type, brand) in enumerate(products, 1):
            LOGGER.info("[%d/%d] Processing %s (%s)", idx, len(products), raw_name, product_type)
            
            try:
                success = self.augment_product(product_id, raw_name, product_type, brand, limit_sources=limit_sources)
                if success:
                    success_count += 1
                else:
                    skip_count += 1
                
                if idx < len(products):
                    time.sleep(delay)
            except Exception as e:
                LOGGER.error("Error augmenting product %s: %s", product_id, e)
                skip_count += 1
        
        LOGGER.info("Augmentation complete: %d successful, %d skipped", success_count, skip_count)


def main():
    parser = argparse.ArgumentParser(description="Augment PC parts database with RAG-extracted attributes")
    parser.add_argument("--source-db", default="data/pc_parts.db", help="Source database path")
    parser.add_argument("--target-db", default="data/pc_parts_augmented.db", help="Target database path")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM extraction")
    parser.add_argument("--limit", type=int, help="Limit number of products to process")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between products (seconds)")
    parser.add_argument("--copy-only", action="store_true", help="Only copy base data, don't augment")
    parser.add_argument("--skip-sources", nargs="+", choices=["newegg", "amazon", "wikipedia", "manufacturer"],
                        help="Skip specific sources (useful if they're blocking requests)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    )
    
    augmenter = DatabaseAugmenter(args.source_db, args.target_db, use_llm=args.use_llm)
    
    # Copy base data
    augmenter.copy_base_data()
    
    if not args.copy_only:
        # Determine which sources to use
        default_sources = ["newegg", "amazon", "wikipedia", "manufacturer"]
        if args.skip_sources:
            sources_to_use = [s for s in default_sources if s not in args.skip_sources]
            LOGGER.info("Skipping sources: %s. Using: %s", args.skip_sources, sources_to_use)
        else:
            sources_to_use = default_sources
        
        # Augment products
        augmenter.augment_all(limit=args.limit, delay=args.delay, limit_sources=sources_to_use)
    
    LOGGER.info("Database augmentation complete: %s", args.target_db)


if __name__ == "__main__":
    main()

