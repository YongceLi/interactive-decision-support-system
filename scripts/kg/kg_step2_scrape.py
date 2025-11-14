#!/usr/bin/env python3
"""
Step 2: Scrape compatibility data for all products.

Reads product information from ComponentRecord objects and scrapes compatibility
data from multiple sources (Newegg, MicroCenter, Wikipedia, Manufacturer docs).

This step is separate from graph building so that:
1. Step 1 can complete even if scraping fails
2. Scraping can be run incrementally/retried
3. Scraped data is cached for reuse
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.kg.scrape_compatibility_data import CompatibilityScraper
from scripts.kg.build_pc_parts_kg import ComponentRecord

LOGGER = logging.getLogger("kg_step2_scrape")


def scrape_all_products(
    components: List[ComponentRecord],
    compatibility_db: str = "data/compatibility_cache.db",
    use_llm: bool = False,
    limit: Optional[int] = None,
    delay_between_products: float = 2.0
) -> None:
    """
    Scrape compatibility data for all products.
    
    Args:
        components: List of ComponentRecord objects to scrape
        compatibility_db: Path to compatibility cache database
        use_llm: Whether to use LLM-based extraction
        limit: Maximum number of products to scrape (None for all)
        delay_between_products: Seconds to wait between scraping products (rate limiting)
    """
    scraper = CompatibilityScraper(db_path=compatibility_db, use_llm=use_llm)
    
    # Filter components if limit specified
    components_to_scrape = components[:limit] if limit else components
    
    LOGGER.info("Starting to scrape %d products (out of %d total)", 
                len(components_to_scrape), len(components))
    
    # Group by product type for better logging
    by_type = {}
    for comp in components_to_scrape:
        comp_type = comp.component_type
        if comp_type not in by_type:
            by_type[comp_type] = []
        by_type[comp_type].append(comp)
    
    LOGGER.info("Products by type:")
    for comp_type, comps in sorted(by_type.items()):
        LOGGER.info("  %s: %d products", comp_type, len(comps))
    
    # Scrape each product
    total_scraped = 0
    total_skipped = 0
    total_errors = 0
    
    for idx, component in enumerate(components_to_scrape, 1):
        # Check if already scraped - but allow re-scraping if no attributes found
        # (normalization might have improved)
        cached = scraper.get_cached_attributes(component.slug)
        if cached and len(cached) > 0:
            LOGGER.debug("Skipping %s (already has %d cached attributes)", 
                        component.slug, len(cached))
            total_skipped += 1
            continue
        elif cached and len(cached) == 0:
            LOGGER.info("Re-scraping %s (previously found 0 attributes, normalization may have improved)", 
                       component.slug)
        
        # Extract brand from component
        brand = component.manufacturer or component.metadata.get("brand")
        
        # Get product name (use base name from metadata if available)
        product_name = component.metadata.get("base_name") or component.name
        
        # Determine sellers based on component type and available sellers
        sellers = list(component.sellers) if component.sellers else []
        if not sellers:
            # Default sellers if none specified
            sellers = ["newegg", "microcenter", "wikipedia", "manufacturer"]
        
        LOGGER.info("[%d/%d] Scraping %s (%s)", 
                   idx, len(components_to_scrape), component.name, component.component_type)
        
        try:
            # Scrape product
            attributes = scraper.scrape_product(
                product_name=product_name,
                product_slug=component.slug,
                sellers=sellers,
                brand=brand
            )
            
            if attributes:
                LOGGER.info("  ✓ Scraped %d attributes", len(attributes))
                total_scraped += 1
            else:
                LOGGER.warning("  ⚠ No attributes scraped")
                total_skipped += 1
            
            # Rate limiting
            if idx < len(components_to_scrape):
                time.sleep(delay_between_products)
                
        except Exception as e:
            LOGGER.error("  ✗ Error scraping %s: %s", component.slug, e)
            total_errors += 1
            # Continue with next product even if this one fails
            continue
    
    # Summary
    LOGGER.info("=" * 60)
    LOGGER.info("Scraping Summary:")
    LOGGER.info("  Total products: %d", len(components_to_scrape))
    LOGGER.info("  Successfully scraped: %d", total_scraped)
    LOGGER.info("  Skipped (cached): %d", total_skipped)
    LOGGER.info("  Errors: %d", total_errors)
    LOGGER.info("=" * 60)
    LOGGER.info("Scraped data saved to: %s", compatibility_db)
    LOGGER.info("Next: Run step 3 to update graph with scraped data")


if __name__ == "__main__":
    import argparse
    import sqlite3
    
    from scripts.kg.build_pc_parts_kg import load_components
    
    parser = argparse.ArgumentParser(description="Step 2: Scrape compatibility data for all products")
    parser.add_argument("--db-path", default="data/pc_parts.db", help="Path to pc_parts SQLite database")
    parser.add_argument("--compatibility-db", default="data/compatibility_cache.db", help="Path to compatibility cache database")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM-based extraction")
    parser.add_argument("--limit", type=int, help="Maximum number of products to scrape")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between products")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    )
    
    # Load components from database
    LOGGER.info("Loading components from %s", args.db_path)
    conn = sqlite3.connect(args.db_path)
    try:
        components_dict = load_components(conn, args.limit)
        all_components = [comp for comp_list in components_dict.values() for comp in comp_list]
    finally:
        conn.close()
    
    # Scrape all products
    scrape_all_products(
        components=all_components,
        compatibility_db=args.compatibility_db,
        use_llm=args.use_llm,
        limit=args.limit,
        delay_between_products=args.delay
    )

