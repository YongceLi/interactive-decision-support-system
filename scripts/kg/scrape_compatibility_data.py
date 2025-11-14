#!/usr/bin/env python3
"""
Web scraping module for PC component compatibility data.

Scrapes compatibility information from:
- Amazon, Newegg, MicroCenter (product listings)
- Wikipedia (technical specifications)
- Manufacturer official documentation (product pages and PDFs)

Stores scraped data in SQLite database for reuse.
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# PDF parsing libraries
try:
    import pdfplumber
    PDF_PARSING_AVAILABLE = True
except ImportError:
    PDF_PARSING_AVAILABLE = False
    try:
        import PyPDF2
        PDF_PARSING_AVAILABLE = True
    except ImportError:
        PDF_PARSING_AVAILABLE = False

# Import normalization utilities
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.kg.normalize_attributes import normalize_attribute_value
except ImportError:
    # Fallback if import fails
    LOGGER.warning("Failed to import normalize_attribute_value, attribute normalization disabled")
    def normalize_attribute_value(key: str, value: str):
        return None

LOGGER = logging.getLogger("scrape_compatibility")


@dataclass
class CompatibilityFact:
    """Represents a compatibility relationship between products."""
    product_slug: str
    compatible_with_slug: str
    compatibility_type: str  # e.g., "socket", "pcie", "ram_standard", "psu_wattage"
    constraint_value: Optional[str] = None
    source_url: Optional[str] = None
    source_seller: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductAttribute:
    """Represents a product attribute scraped from web."""
    product_slug: str
    attribute_type: str  # e.g., "product_type", "brand", "socket", "pcie_version"
    attribute_value: str
    source_url: Optional[str] = None
    source_seller: Optional[str] = None
    confidence: float = 1.0


class CompatibilityScraper:
    """Main scraper class for compatibility data."""
    
    def __init__(self, db_path: str = "data/compatibility_cache.db", use_llm: bool = False):
        """
        Initialize scraper.
        
        Args:
            db_path: Path to compatibility cache database
            use_llm: Whether to use LLM-based extraction (requires OpenAI API key)
        """
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        self.use_llm = use_llm
        self.llm_extractor = None
        
        if use_llm:
            try:
                from scripts.kg.llm_extractor import LLMExtractor
                self.llm_extractor = LLMExtractor()
                LOGGER.info("LLM extraction enabled")
            except ImportError:
                LOGGER.warning("LLM extraction requested but libraries not available. Install: pip install langchain-openai pydantic")
                self.use_llm = False
            except Exception as e:
                LOGGER.warning("Failed to initialize LLM extractor: %s. Falling back to regex parsing.", e)
                self.use_llm = False
        
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize SQLite database for caching scraped data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Compatibility facts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS compatibility_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_slug TEXT NOT NULL,
                compatible_with_slug TEXT NOT NULL,
                compatibility_type TEXT NOT NULL,
                constraint_value TEXT,
                source_url TEXT,
                source_seller TEXT,
                confidence REAL DEFAULT 1.0,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_slug, compatible_with_slug, compatibility_type)
            )
        """)
        
        # Product attributes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS product_attributes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_slug TEXT NOT NULL,
                attribute_type TEXT NOT NULL,
                attribute_value TEXT NOT NULL,
                source_url TEXT,
                source_seller TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_slug, attribute_type, attribute_value)
            )
        """)
        
        # Scraping cache (URLs already scraped)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scrape_cache (
                url TEXT PRIMARY KEY,
                seller TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN DEFAULT 1
            )
        """)
        
        conn.commit()
        conn.close()
        LOGGER.info("Initialized compatibility cache database at %s", self.db_path)
    
    def _is_scraped(self, url: str) -> bool:
        """Check if URL has already been scraped."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM scrape_cache WHERE url = ?", (url,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def _mark_scraped(self, url: str, seller: Optional[str] = None, success: bool = True) -> None:
        """Mark URL as scraped."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO scrape_cache (url, seller, success) VALUES (?, ?, ?)",
            (url, seller, success)
        )
        conn.commit()
        conn.close()
    
    def scrape_amazon(self, product_name: str, product_slug: str) -> List[ProductAttribute]:
        """Scrape Amazon product page for attributes."""
        # Amazon search URL
        search_url = f"https://www.amazon.com/s?k={product_name.replace(' ', '+')}"
        
        if self._is_scraped(search_url):
            LOGGER.debug("Skipping already scraped Amazon URL: %s", search_url)
            return []
        
        try:
            # Note: In production, you'd want to use Amazon Product Advertising API
            # For now, this is a placeholder that demonstrates the structure
            LOGGER.info("Scraping Amazon for: %s", product_name)
            time.sleep(1)  # Rate limiting
            
            # TODO: Implement actual Amazon scraping
            # This would parse product pages for:
            # - Technical specifications
            # - Compatibility information
            # - Seller information
            
            self._mark_scraped(search_url, seller="amazon", success=True)
            return []
        except Exception as e:
            LOGGER.error("Error scraping Amazon for %s: %s", product_name, e)
            self._mark_scraped(search_url, seller="amazon", success=False)
            return []
    
    def scrape_newegg(self, product_name: str, product_slug: str) -> List[ProductAttribute]:
        """Scrape Newegg product page for attributes."""
        search_url = f"https://www.newegg.com/p/pl?d={product_name.replace(' ', '+')}"
        
        if self._is_scraped(search_url):
            LOGGER.debug("Skipping already scraped Newegg URL: %s", search_url)
            return []
        
        try:
            LOGGER.info("Scraping Newegg for: %s", product_name)
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            attributes = []
            
            # Use LLM extraction if enabled
            if self.use_llm and self.llm_extractor:
                try:
                    from .llm_extractor import convert_to_product_attributes
                    extracted = self.llm_extractor.extract_from_html(
                        str(soup),
                        product_name,
                        product_slug,
                        source="newegg"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_slug,
                        source_url=search_url,
                        source_seller="newegg_llm"
                    )
                    attributes.extend(llm_attrs)
                    LOGGER.info("LLM extracted %d attributes from Newegg", len(llm_attrs))
                except Exception as e:
                    LOGGER.warning("LLM extraction failed, falling back to regex: %s", e)
            
            # Fallback/Supplement with regex-based extraction
            spec_tables = soup.find_all('table', class_='table-horizontal')
            for table in spec_tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        
                        # Normalize and extract attributes
                        normalized = normalize_attribute_value(key, value)
                        if normalized:
                            attr_type, attr_value = normalized
                            # Check if we already have this attribute from LLM
                            if not any(a.attribute_type == attr_type and a.attribute_value == attr_value 
                                     for a in attributes):
                                attributes.append(ProductAttribute(
                                    product_slug=product_slug,
                                    attribute_type=attr_type,
                                    attribute_value=attr_value,
                                    source_url=search_url,
                                    source_seller="newegg",
                                    confidence=0.9
                                ))
            
            self._mark_scraped(search_url, seller="newegg", success=True)
            time.sleep(1)  # Rate limiting
            return attributes
        except Exception as e:
            LOGGER.error("Error scraping Newegg for %s: %s", product_name, e)
            self._mark_scraped(search_url, seller="newegg", success=False)
            return []
    
    def scrape_microcenter(self, product_name: str, product_slug: str) -> List[ProductAttribute]:
        """Scrape MicroCenter product page for attributes."""
        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={product_name.replace(' ', '+')}"
        
        if self._is_scraped(search_url):
            LOGGER.debug("Skipping already scraped MicroCenter URL: %s", search_url)
            return []
        
        try:
            LOGGER.info("Scraping MicroCenter for: %s", product_name)
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            attributes = []
            
            # Extract specifications from MicroCenter
            # Similar pattern to Newegg
            spec_sections = soup.find_all(['div', 'section'], class_=re.compile(r'spec|detail|feature', re.I))
            for section in spec_sections:
                # Parse specification key-value pairs
                # Implementation similar to Newegg
                pass
            
            self._mark_scraped(search_url, seller="microcenter", success=True)
            time.sleep(1)  # Rate limiting
            return attributes
        except Exception as e:
            LOGGER.error("Error scraping MicroCenter for %s: %s", product_name, e)
            self._mark_scraped(search_url, seller="microcenter", success=False)
            return []
    
    def scrape_wikipedia(self, product_name: str, product_slug: str) -> List[ProductAttribute]:
        """Scrape Wikipedia for technical specifications."""
        # Extract series name from product name (e.g., "RTX 3060 Ti" from "Asus Dual NVIDIA GeForce RTX 3060 Ti")
        # Try to find common GPU/CPU series patterns
        series_name = self._extract_series_name(product_name)
        
        # Try direct page first with series name
        search_url = f"https://en.wikipedia.org/wiki/{series_name.replace(' ', '_')}"
        
        # Check if we already have cached attributes for this product from Wikipedia
        # Only skip if we actually found attributes (not just marked as scraped)
        cached_attrs = self.get_cached_attributes(product_slug)
        wikipedia_cached = [a for a in cached_attrs if a.source_seller == "wikipedia"]
        if wikipedia_cached:
            LOGGER.debug("Skipping Wikipedia (already have %d cached attributes)", len(wikipedia_cached))
            return []
        
        # Also check if URL was scraped but found nothing - allow re-scraping with updated normalization
        if self._is_scraped(search_url):
            # Check if the scrape was successful but found no attributes
            # If so, allow re-scraping (normalization might have improved)
            LOGGER.debug("Wikipedia URL was scraped before, but no attributes cached. Re-scraping with updated normalization.")
        
        try:
            LOGGER.info("Scraping Wikipedia for: %s (trying: %s)", product_name, series_name)
            response = self.session.get(search_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            
            # If direct page fails, try Wikipedia search API
            if response.status_code == 404:
                LOGGER.debug("Direct page not found, trying Wikipedia search API")
                search_api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + series_name.replace(' ', '_')
                response = self.session.get(search_api_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                
                if response.status_code == 200:
                    # Use the canonical URL from search results
                    data = response.json()
                    if 'content_urls' in data and 'desktop' in data['content_urls']:
                        search_url = data['content_urls']['desktop']['page']
                        response = self.session.get(search_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            
            if response.status_code != 200:
                LOGGER.debug("Wikipedia page not found for %s (status: %d)", series_name, response.status_code)
                self._mark_scraped(search_url, seller="wikipedia", success=False)
                return []
            
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            attributes = []
            
            # Use LLM extraction if enabled (preferred for Wikipedia - handles varied formats well)
            if self.use_llm and self.llm_extractor:
                try:
                    from scripts.kg.llm_extractor import convert_to_product_attributes
                    extracted = self.llm_extractor.extract_from_html(
                        str(soup),
                        product_name,
                        product_slug,
                        source="wikipedia_llm"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_slug,
                        source_url=search_url,
                        source_seller="wikipedia_llm"
                    )
                    attributes.extend(llm_attrs)
                    LOGGER.info("LLM extracted %d attributes from Wikipedia", len(llm_attrs))
                except Exception as e:
                    LOGGER.warning("LLM extraction from Wikipedia failed, falling back to regex: %s", e)
            
            # Extract from infobox (right sidebar)
            infobox = soup.find('table', class_='infobox')
            if infobox:
                LOGGER.debug("Found infobox, extracting attributes")
                rows = infobox.find_all('tr')
                for row in rows:
                    header = row.find('th')
                    data = row.find('td')
                    if header and data:
                        key = header.get_text(strip=True).lower()
                        value = data.get_text(strip=True)
                        
                        if not value or value == '—' or value == 'N/A':
                            continue
                        
                        normalized = normalize_attribute_value(key, value)
                        if normalized:
                            attr_type, attr_value = normalized
                            # Check if we already have this attribute from LLM
                            if not any(a.attribute_type == attr_type and a.attribute_value == attr_value 
                                     for a in attributes):
                                LOGGER.debug("  Extracted: %s = %s", attr_type, attr_value)
                                attributes.append(ProductAttribute(
                                    product_slug=product_slug,
                                    attribute_type=attr_type,
                                    attribute_value=attr_value,
                                    source_url=search_url,
                                    source_seller="wikipedia",
                                    confidence=0.85
                                ))
                        else:
                            LOGGER.debug("  Skipped unrecognized attribute: %s = %s", key, value)
            else:
                LOGGER.debug("No infobox found on Wikipedia page")
            
            # Extract from specification sections
            spec_sections = soup.find_all(['h2', 'h3'], string=re.compile(r'specification|technical|compatibility', re.I))
            for section in spec_sections:
                content = section.find_next_sibling(['div', 'ul', 'table'])
                if content:
                    # Look for tables with specifications
                    if content.name == 'table':
                        rows = content.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if len(cells) >= 2:
                                key = cells[0].get_text(strip=True).lower()
                                value = cells[1].get_text(strip=True)
                                
                                if not value or value == '—' or value == 'N/A':
                                    continue
                                
                                normalized = normalize_attribute_value(key, value)
                                if normalized:
                                    attr_type, attr_value = normalized
                                    # Check if we already have this attribute
                                    if not any(a.attribute_type == attr_type and a.attribute_value == attr_value 
                                             for a in attributes):
                                        LOGGER.debug("  Extracted from spec section: %s = %s", attr_type, attr_value)
                                        attributes.append(ProductAttribute(
                                            product_slug=product_slug,
                                            attribute_type=attr_type,
                                            attribute_value=attr_value,
                                            source_url=search_url,
                                            source_seller="wikipedia",
                                            confidence=0.8
                                        ))
                    # Look for lists with specifications
                    elif content.name == 'ul':
                        for li in content.find_all('li'):
                            text = li.get_text(strip=True)
                            # Try to parse "Key: Value" or "Key - Value" patterns
                            if ':' in text:
                                parts = text.split(':', 1)
                                if len(parts) == 2:
                                    key = parts[0].strip().lower()
                                    value = parts[1].strip()
                                    normalized = normalize_attribute_value(key, value)
                                    if normalized:
                                        attr_type, attr_value = normalized
                                        if not any(a.attribute_type == attr_type and a.attribute_value == attr_value 
                                                 for a in attributes):
                                            LOGGER.debug("  Extracted from spec list: %s = %s", attr_type, attr_value)
                                            attributes.append(ProductAttribute(
                                                product_slug=product_slug,
                                                attribute_type=attr_type,
                                                attribute_value=attr_value,
                                                source_url=search_url,
                                                source_seller="wikipedia",
                                                confidence=0.75
                                            ))
            
            self._mark_scraped(search_url, seller="wikipedia", success=True)
            LOGGER.info("Wikipedia scraping complete: found %d attributes", len(attributes))
            time.sleep(1)  # Rate limiting
            return attributes
        except Exception as e:
            LOGGER.error("Error scraping Wikipedia for %s: %s", product_name, e, exc_info=True)
            self._mark_scraped(search_url, seller="wikipedia", success=False)
            return []
    
    def _extract_series_name(self, product_name: str) -> str:
        """Extract series name from product name for Wikipedia lookup."""
        # Common GPU series patterns
        gpu_patterns = [
            r'(RTX\s+\d+\s*(?:Ti|Super)?)',
            r'(GTX\s+\d+\s*(?:Ti|Super)?)',
            r'(RX\s+\d+\s*(?:XT|XTX)?)',
            r'(Arc\s+A\d+)',
            r'(Radeon\s+RX\s+\d+)',
            r'(GeForce\s+(?:RTX|GTX)\s+\d+)',
        ]
        
        for pattern in gpu_patterns:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # CPU patterns
        cpu_patterns = [
            r'(Core\s+i\d+\s*-\s*\d+\w*)',
            r'(Ryzen\s+\d+\s*\d+\w*)',
            r'(Threadripper\s+\d+\w*)',
            r'(Xeon\s+\w+)',
        ]
        
        for pattern in cpu_patterns:
            match = re.search(pattern, product_name, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Fallback: try to extract meaningful parts (remove brand/model prefixes)
        # Remove common prefixes
        cleaned = re.sub(r'^(Asus|MSI|Gigabyte|EVGA|Sapphire|PowerColor|XFX|ASRock)\s+', '', product_name, flags=re.IGNORECASE)
        cleaned = re.sub(r'^(Dual|Gaming|OC|Strix|TUF|ROG)\s+', '', cleaned, flags=re.IGNORECASE)
        
        # Return first 50 chars (Wikipedia page names shouldn't be too long)
        return cleaned[:50].strip()
    
    def _get_manufacturer_domain(self, brand: str) -> Optional[str]:
        """Get manufacturer website domain based on brand name."""
        brand_lower = brand.lower().strip()
        manufacturer_domains = {
            "nvidia": "nvidia.com",
            "amd": "amd.com",
            "intel": "intel.com",
            "asus": "asus.com",
            "msi": "msi.com",
            "gigabyte": "gigabyte.com",
            "asrock": "asrock.com",
            "evga": "evga.com",
            "corsair": "corsair.com",
            "g.skill": "gskill.com",
            "gskill": "gskill.com",
            "kingston": "kingston.com",
            "samsung": "samsung.com",
            "crucial": "crucial.com",
            "seasonic": "seasonic.com",
            "be quiet": "bequiet.com",
            "bequiet": "bequiet.com",
            "noctua": "noctua.at",
            "cooler master": "coolermaster.com",
            "coolermaster": "coolermaster.com",
            "nzxt": "nzxt.com",
            "fractal design": "fractal-design.com",
            "fractal": "fractal-design.com",
        }
        return manufacturer_domains.get(brand_lower)
    
    def _find_manufacturer_product_page(self, brand: str, product_name: str) -> Optional[str]:
        """Search manufacturer website for product page."""
        domain = self._get_manufacturer_domain(brand)
        if not domain:
            return None
        
        # Try common product page patterns
        product_slug = re.sub(r'[^a-z0-9]+', '-', product_name.lower()).strip('-')
        search_patterns = [
            f"https://www.{domain}/product/{product_slug}",
            f"https://www.{domain}/products/{product_slug}",
            f"https://www.{domain}/en/product/{product_slug}",
            f"https://www.{domain}/us/en/product/{product_slug}",
        ]
        
        for url in search_patterns:
            try:
                response = self.session.get(url, timeout=10, allow_redirects=False)
                if response.status_code == 200:
                    return url
            except:
                continue
        
        # Try site search
        try:
            search_url = f"https://www.{domain}/search?q={product_name.replace(' ', '+')}"
            response = self.session.get(search_url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # Look for product links
                product_links = soup.find_all('a', href=re.compile(r'/product/|/products/', re.I))
                for link in product_links[:5]:  # Check first 5 results
                    href = link.get('href', '')
                    if product_slug[:10] in href.lower() or any(word in href.lower() for word in product_name.lower().split()[:3]):
                        full_url = urljoin(f"https://www.{domain}", href)
                        return full_url
        except Exception as e:
            LOGGER.debug("Error searching manufacturer site: %s", e)
        
        return None
    
    def scrape_manufacturer_docs(self, product_name: str, product_slug: str, brand: Optional[str] = None) -> List[ProductAttribute]:
        """Scrape official manufacturer documentation and product pages."""
        if not brand:
            # Try to extract brand from product name
            brand_match = re.match(r'^([A-Z][a-z]+)', product_name)
            if brand_match:
                brand = brand_match.group(1)
            else:
                LOGGER.warning("No brand provided for manufacturer doc scraping")
                return []
        
        attributes = []
        
        # Find manufacturer product page
        product_url = self._find_manufacturer_product_page(brand, product_name)
        if product_url and not self._is_scraped(product_url):
            try:
                LOGGER.info("Scraping manufacturer page: %s", product_url)
                response = self.session.get(product_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Use LLM extraction if enabled (preferred for official docs)
                if self.use_llm and self.llm_extractor:
                    try:
                        from .llm_extractor import convert_to_product_attributes, convert_to_compatibility_facts
                        extracted = self.llm_extractor.extract_from_html(
                            str(soup),
                            product_name,
                            product_slug,
                            source=f"{brand}_official"
                        )
                        llm_attrs = convert_to_product_attributes(
                            extracted,
                            product_slug,
                            source_url=product_url,
                            source_seller=f"{brand}_official_llm"
                        )
                        attributes.extend(llm_attrs)
                        
                        # Also extract compatibility relationships
                        compat_facts = convert_to_compatibility_facts(
                            extracted,
                            product_slug,
                            source_url=product_url,
                            source_seller=f"{brand}_official_llm"
                        )
                        if compat_facts:
                            self.save_compatibility(compat_facts)
                        
                        LOGGER.info("LLM extracted %d attributes and %d compatibility facts from manufacturer page",
                                   len(llm_attrs), len(compat_facts))
                    except Exception as e:
                        LOGGER.warning("LLM extraction failed, falling back to regex: %s", e)
                
                # Fallback/Supplement with regex-based extraction
                spec_sections = soup.find_all(['div', 'section', 'table'], 
                                             class_=re.compile(r'spec|specification|technical|detail', re.I))
                for section in spec_sections:
                    # Look for key-value pairs
                    rows = section.find_all(['tr', 'div'], class_=re.compile(r'row|item|spec', re.I))
                    for row in rows:
                        key_elem = row.find(['th', 'dt', 'span', 'div'], class_=re.compile(r'key|label|name', re.I))
                        value_elem = row.find(['td', 'dd', 'span', 'div'], class_=re.compile(r'value|data|content', re.I))
                        
                        if key_elem and value_elem:
                            key = key_elem.get_text(strip=True)
                            value = value_elem.get_text(strip=True)
                            
                            normalized = normalize_attribute_value(key, value)
                            if normalized:
                                attr_type, attr_value = normalized
                                # Check if we already have this attribute from LLM
                                if not any(a.attribute_type == attr_type and a.attribute_value == attr_value 
                                         for a in attributes):
                                    attributes.append(ProductAttribute(
                                        product_slug=product_slug,
                                        attribute_type=attr_type,
                                        attribute_value=attr_value,
                                        source_url=product_url,
                                        source_seller=f"{brand}_official",
                                        confidence=0.95  # High confidence for official docs
                                    ))
                
                # Look for PDF download links
                pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$|download.*pdf|manual.*pdf|spec.*pdf', re.I))
                for link in pdf_links[:3]:  # Limit to first 3 PDFs
                    pdf_url = urljoin(product_url, link.get('href', ''))
                    pdf_attrs = self._parse_pdf(pdf_url, product_slug, brand, product_name=product_name)
                    attributes.extend(pdf_attrs)
                
                self._mark_scraped(product_url, seller=f"{brand}_official", success=True)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                LOGGER.error("Error scraping manufacturer page for %s: %s", product_name, e)
                self._mark_scraped(product_url, seller=f"{brand}_official", success=False)
        
        return attributes
    
    def _parse_pdf(self, pdf_url: str, product_slug: str, brand: str, product_name: Optional[str] = None) -> List[ProductAttribute]:
        """Download and parse PDF to extract compatibility information."""
        if not PDF_PARSING_AVAILABLE:
            LOGGER.warning("PDF parsing libraries not available. Install pdfplumber or PyPDF2.")
            return []
        
        if self._is_scraped(pdf_url):
            LOGGER.debug("Skipping already scraped PDF: %s", pdf_url)
            return []
        
        attributes = []
        
        try:
            LOGGER.info("Downloading and parsing PDF: %s", pdf_url)
            response = self.session.get(pdf_url, timeout=30, stream=True)
            response.raise_for_status()
            
            pdf_content = io.BytesIO(response.content)
            
            # Try pdfplumber first (better text extraction)
            if 'pdfplumber' in sys.modules:
                with pdfplumber.open(pdf_content) as pdf:
                    text = ""
                    for page in pdf.pages[:10]:  # Limit to first 10 pages
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            else:
                # Fallback to PyPDF2
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(pdf_content)
                text = ""
                for page_num in range(min(10, len(pdf_reader.pages))):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n"
            
            # Use LLM extraction if enabled (preferred for PDFs - better at handling unstructured text)
            if self.use_llm and self.llm_extractor:
                try:
                    from .llm_extractor import convert_to_product_attributes, convert_to_compatibility_facts
                    extracted = self.llm_extractor.extract_from_pdf_text(
                        text,
                        product_name or product_slug,  # Use product_name if available, else slug
                        product_slug,
                        source=f"{brand}_official_pdf"
                    )
                    llm_attrs = convert_to_product_attributes(
                        extracted,
                        product_slug,
                        source_url=pdf_url,
                        source_seller=f"{brand}_official_pdf_llm"
                    )
                    attributes.extend(llm_attrs)
                    
                    # Also extract compatibility relationships from PDF
                    compat_facts = convert_to_compatibility_facts(
                        extracted,
                        product_slug,
                        source_url=pdf_url,
                        source_seller=f"{brand}_official_pdf_llm"
                    )
                    if compat_facts:
                        self.save_compatibility(compat_facts)
                    
                    LOGGER.info("LLM extracted %d attributes and %d compatibility facts from PDF",
                               len(llm_attrs), len(compat_facts))
                except Exception as e:
                    LOGGER.warning("LLM extraction from PDF failed, falling back to regex: %s", e)
            
            # Fallback/Supplement with regex-based extraction
            spec_patterns = [
                (r'(?:socket|cpu socket)[\s:]+([A-Z0-9\s]+)', 'socket'),
                (r'(?:pci[-\s]?e|pci express)[\s:]+([0-9.]+)', 'pcie_version'),
                (r'(?:ddr|memory type)[\s:]+(ddr[0-9]+)', 'ram_standard'),
                (r'(?:power|psu|wattage)[\s:]+(\d+)\s*w', 'wattage'),
                (r'(?:form factor|size)[\s:]+([A-Z][a-z]+(?:-[A-Z][a-z]+)?)', 'form_factor'),
            ]
            
            for pattern, attr_type in spec_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    value = match.group(1).strip()
                    normalized = normalize_attribute_value(attr_type, value)
                    if normalized:
                        _, attr_value = normalized
                        # Check if we already have this attribute from LLM
                        if not any(a.attribute_type == attr_type and a.attribute_value == attr_value 
                                 for a in attributes):
                            attributes.append(ProductAttribute(
                                product_slug=product_slug,
                                attribute_type=attr_type,
                                attribute_value=attr_value,
                                source_url=pdf_url,
                                source_seller=f"{brand}_official_pdf",
                                confidence=0.98  # Very high confidence for official PDFs
                            ))
            
            # Extract compatibility tables/sections
            compatibility_section = re.search(
                r'(?:compatibility|compatible|supported)[\s\S]{0,2000}',
                text, re.IGNORECASE
            )
            if compatibility_section:
                compat_text = compatibility_section.group(0)
                # Look for product mentions that might indicate compatibility
                # This is a simplified extraction - could be enhanced with NLP
                pass
            
            self._mark_scraped(pdf_url, seller=f"{brand}_official_pdf", success=True)
            LOGGER.info("Extracted %d attributes from PDF", len(attributes))
            
        except Exception as e:
            LOGGER.error("Error parsing PDF %s: %s", pdf_url, e)
            self._mark_scraped(pdf_url, seller=f"{brand}_official_pdf", success=False)
        
        return attributes
    
    def scrape_product(self, product_name: str, product_slug: str, sellers: Optional[List[str]] = None, brand: Optional[str] = None) -> List[ProductAttribute]:
        """Scrape all sources for a product."""
        if sellers is None:
            sellers = ["newegg", "microcenter", "wikipedia", "manufacturer"]  # Include manufacturer by default
        
        all_attributes = []
        
        for seller in sellers:
            if seller.lower() == "amazon":
                # attrs = self.scrape_amazon(product_name, product_slug)
                continue
            elif seller.lower() == "newegg":
                attrs = self.scrape_newegg(product_name, product_slug)
            elif seller.lower() == "microcenter":
                attrs = self.scrape_microcenter(product_name, product_slug)
            elif seller.lower() == "wikipedia":
                attrs = self.scrape_wikipedia(product_name, product_slug)
            elif seller.lower() in ["manufacturer", "official", "docs"]:
                attrs = self.scrape_manufacturer_docs(product_name, product_slug, brand)
            else:
                LOGGER.warning("Unknown seller: %s", seller)
                continue
            
            all_attributes.extend(attrs)
        
        # Save to database
        self.save_attributes(all_attributes)
        return all_attributes
    
    def save_attributes(self, attributes: List[ProductAttribute]) -> None:
        """Save scraped attributes to database."""
        if not attributes:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for attr in attributes:
            cursor.execute("""
                INSERT OR IGNORE INTO product_attributes
                (product_slug, attribute_type, attribute_value, source_url, source_seller, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                attr.product_slug,
                attr.attribute_type,
                attr.attribute_value,
                attr.source_url,
                attr.source_seller,
                attr.confidence
            ))
        
        conn.commit()
        conn.close()
        LOGGER.info("Saved %d attributes to database", len(attributes))
    
    def save_compatibility(self, compatibilities: List[CompatibilityFact]) -> None:
        """Save compatibility facts to database."""
        if not compatibilities:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for compat in compatibilities:
            import json
            metadata_json = json.dumps(compat.metadata) if compat.metadata else None
            cursor.execute("""
                INSERT OR REPLACE INTO compatibility_facts
                (product_slug, compatible_with_slug, compatibility_type, constraint_value,
                 source_url, source_seller, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                compat.product_slug,
                compat.compatible_with_slug,
                compat.compatibility_type,
                compat.constraint_value,
                compat.source_url,
                compat.source_seller,
                compat.confidence,
                metadata_json
            ))
        
        conn.commit()
        conn.close()
        LOGGER.info("Saved %d compatibility facts to database", len(compatibilities))
    
    def get_cached_attributes(self, product_slug: str) -> List[ProductAttribute]:
        """Retrieve cached attributes from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT attribute_type, attribute_value, source_url, source_seller, confidence
            FROM product_attributes
            WHERE product_slug = ?
        """, (product_slug,))
        
        attributes = []
        for row in cursor.fetchall():
            attributes.append(ProductAttribute(
                product_slug=product_slug,
                attribute_type=row[0],
                attribute_value=row[1],
                source_url=row[2],
                source_seller=row[3],
                confidence=row[4]
            ))
        
        conn.close()
        return attributes
    
    def get_cached_compatibility(self, product_slug: Optional[str] = None) -> List[CompatibilityFact]:
        """Retrieve cached compatibility facts from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if product_slug:
            cursor.execute("""
                SELECT product_slug, compatible_with_slug, compatibility_type, constraint_value,
                       source_url, source_seller, confidence, metadata
                FROM compatibility_facts
                WHERE product_slug = ? OR compatible_with_slug = ?
            """, (product_slug, product_slug))
        else:
            cursor.execute("""
                SELECT product_slug, compatible_with_slug, compatibility_type, constraint_value,
                       source_url, source_seller, confidence, metadata
                FROM compatibility_facts
            """)
        
        compatibilities = []
        import json
        for row in cursor.fetchall():
            metadata = json.loads(row[7]) if row[7] else {}
            compatibilities.append(CompatibilityFact(
                product_slug=row[0],
                compatible_with_slug=row[1],
                compatibility_type=row[2],
                constraint_value=row[3],
                source_url=row[4],
                source_seller=row[5],
                confidence=row[6],
                metadata=metadata
            ))
        
        conn.close()
        return compatibilities


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Scrape compatibility data for PC components")
    parser.add_argument("--db-path", default="data/compatibility_cache.db", help="Path to compatibility cache database")
    parser.add_argument("--product-name", required=True, help="Product name to scrape")
    parser.add_argument("--product-slug", required=True, help="Product slug identifier")
    parser.add_argument("--brand", help="Product brand/manufacturer name")
    parser.add_argument("--sellers", nargs="+", default=["newegg", "microcenter", "wikipedia", "manufacturer"], help="Sellers to scrape")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM-based extraction (requires OpenAI API key)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    scraper = CompatibilityScraper(db_path=args.db_path, use_llm=args.use_llm)
    attributes = scraper.scrape_product(args.product_name, args.product_slug, args.sellers, brand=args.brand)
    
    LOGGER.info("Scraped %d attributes for %s", len(attributes), args.product_name)
    for attr in attributes:
        LOGGER.info("  %s: %s (from %s, confidence: %.2f)", 
                   attr.attribute_type, attr.attribute_value, attr.source_seller, attr.confidence)


if __name__ == "__main__":
    main()

