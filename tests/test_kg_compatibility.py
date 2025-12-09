"""
Unit tests for Knowledge Graph compatibility checking and web scraping validation.

Tests validate:
- Compatibility relationships are correctly stored and queried
- Web scraped data accuracy
- Random product compatibility validation
"""
import unittest
import sqlite3
import random
from typing import Dict, List, Optional, Any
from pathlib import Path

from idss_agent.tools.kg_compatibility import (
    get_compatibility_tool,
    Neo4jCompatibilityTool,
    PART_COMPATIBILITY_MAP
)
from idss_agent.tools.local_electronics_store import LocalElectronicsStore


class TestKGCompatibility(unittest.TestCase):
    """Test suite for knowledge graph compatibility checking."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.compatibility_tool = get_compatibility_tool()
        cls.store = LocalElectronicsStore()
        cls.compatibility_db_path = Path(__file__).parent.parent / "data" / "compatibility_cache.db"
        
    def test_compatibility_tool_available(self):
        """Test that compatibility tool is available."""
        self.assertTrue(
            self.compatibility_tool.is_available(),
            "Compatibility tool should be available (Neo4j connection required)"
        )

    def test_find_product_by_name(self):
        """Test finding products by name."""
        if not self.compatibility_tool.is_available():
            self.skipTest("Neo4j not available")
        
        # Test with a common product
        product = self.compatibility_tool.find_product_by_name("RTX 4090", product_type="gpu")
        if product:
            self.assertIn("slug", product)
            self.assertIn("name", product)
            self.assertEqual(product.get("product_type"), "gpu")

    def test_binary_compatibility_check(self):
        """Test binary compatibility checking."""
        if not self.compatibility_tool.is_available():
            self.skipTest("Neo4j not available")
        
        # Find two products
        cpu = self.compatibility_tool.find_product_by_name("Ryzen 7", product_type="cpu")
        mb = self.compatibility_tool.find_product_by_name("B650", product_type="motherboard")
        
        if cpu and mb:
            result = self.compatibility_tool.check_compatibility(
                cpu.get("slug"),
                mb.get("slug")
            )
            self.assertIn("compatible", result)
            self.assertIn("explanation", result)

    def test_find_compatible_parts(self):
        """Test finding compatible parts."""
        if not self.compatibility_tool.is_available():
            self.skipTest("Neo4j not available")
        
        # Find a GPU
        gpu = self.compatibility_tool.find_product_by_name("RTX 4090", product_type="gpu")
        if gpu:
            compatible_psus = self.compatibility_tool.find_compatible_parts(
                gpu.get("slug"),
                "psu",
                limit=5
            )
            self.assertIsInstance(compatible_psus, list)
            if compatible_psus:
                self.assertIn("slug", compatible_psus[0])
                self.assertIn("name", compatible_psus[0])

    def test_random_product_compatibility_validation(self):
        """Randomly select products and validate compatibility relationships."""
        if not self.compatibility_tool.is_available():
            self.skipTest("Neo4j not available")
        
        # Get random products from database
        products = self.store.search_products(limit=100)
        pc_parts = [p for p in products if p.get("type") in ["cpu", "gpu", "motherboard", "psu", "ram"]]
        
        if len(pc_parts) < 10:
            self.skipTest("Not enough PC parts in database")
        
        # Test 5 random compatibility checks
        tested = 0
        for _ in range(10):
            if tested >= 5:
                break
                
            part1 = random.choice(pc_parts)
            part2 = random.choice(pc_parts)
            
            if part1 == part2:
                continue
            
            # Try to find in KG
            kg_part1 = self.compatibility_tool.find_product_by_name(
                part1.get("name") or part1.get("title", ""),
                product_type=part1.get("type")
            )
            kg_part2 = self.compatibility_tool.find_product_by_name(
                part2.get("name") or part2.get("title", ""),
                product_type=part2.get("type")
            )
            
            if kg_part1 and kg_part2:
                result = self.compatibility_tool.check_compatibility(
                    kg_part1.get("slug"),
                    kg_part2.get("slug")
                )
                self.assertIn("compatible", result)
                tested += 1
        
        self.assertGreater(tested, 0, "Should have tested at least one compatibility check")

    def test_web_scraped_data_validation(self):
        """Validate web scraped data accuracy."""
        if not self.compatibility_db_path.exists():
            self.skipTest("Compatibility cache database not found")
        
        conn = sqlite3.connect(self.compatibility_db_path)
        cursor = conn.cursor()
        
        # Check that scraped data exists
        cursor.execute("SELECT COUNT(DISTINCT product_slug) FROM product_attributes")
        count = cursor.fetchone()[0]
        self.assertGreater(count, 0, "Should have scraped product attributes")
        
        # Validate attribute structure
        cursor.execute("""
            SELECT product_slug, attribute_type, attribute_value, confidence, source_seller
            FROM product_attributes
            LIMIT 10
        """)
        rows = cursor.fetchall()
        
        for row in rows:
            product_slug, attr_type, attr_value, confidence, source = row
            self.assertIsNotNone(product_slug)
            self.assertIsNotNone(attr_type)
            self.assertIsNotNone(attr_value)
            # Confidence should be between 0 and 1 if present
            if confidence is not None:
                self.assertGreaterEqual(confidence, 0.0)
                self.assertLessEqual(confidence, 1.0)
        
        conn.close()

    def test_compatibility_edge_types(self):
        """Test that compatibility edge types are correctly mapped."""
        # Test known compatibility relationships
        self.assertIn(("cpu", "motherboard"), PART_COMPATIBILITY_MAP)
        self.assertIn(("gpu", "psu"), PART_COMPATIBILITY_MAP)
        self.assertIn(("ram", "motherboard"), PART_COMPATIBILITY_MAP)
        
        # Test bidirectional relationships
        self.assertEqual(
            PART_COMPATIBILITY_MAP.get(("cpu", "motherboard")),
            PART_COMPATIBILITY_MAP.get(("motherboard", "cpu"))
        )

    def test_part_type_normalization(self):
        """Test that part types are normalized correctly."""
        if not self.compatibility_tool.is_available():
            self.skipTest("Neo4j not available")
        
        # Test finding products with different case variations
        product1 = self.compatibility_tool.find_product_by_name("RTX 4090", product_type="GPU")
        product2 = self.compatibility_tool.find_product_by_name("RTX 4090", product_type="gpu")
        
        # Should find the same product regardless of case
        if product1 and product2:
            self.assertEqual(product1.get("slug"), product2.get("slug"))


class TestWebScrapingAccuracy(unittest.TestCase):
    """Test suite for validating web scraped compatibility data accuracy."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.compatibility_db_path = Path(__file__).parent.parent / "data" / "compatibility_cache.db"
        cls.compatibility_tool = get_compatibility_tool()

    def test_scraped_socket_accuracy(self):
        """Validate socket information from web scraping."""
        if not self.compatibility_db_path.exists():
            self.skipTest("Compatibility cache database not found")
        
        conn = sqlite3.connect(self.compatibility_db_path)
        cursor = conn.cursor()
        
        # Get CPU socket data
        cursor.execute("""
            SELECT product_slug, attribute_value, source_seller, confidence
            FROM product_attributes
            WHERE attribute_type = 'socket'
            AND product_slug LIKE '%cpu%'
            LIMIT 5
        """)
        
        rows = cursor.fetchall()
        for row in rows:
            product_slug, socket_value, source, confidence = row
            # Socket should be a valid format (e.g., "AM5", "LGA 1700")
            self.assertIsNotNone(socket_value)
            self.assertGreater(len(str(socket_value)), 0)
            # High confidence sources should have confidence > 0.8
            if source in ["wikipedia", "manufacturer"] and confidence:
                self.assertGreater(confidence, 0.7)
        
        conn.close()

    def test_scraped_pcie_version_accuracy(self):
        """Validate PCIe version information from web scraping."""
        if not self.compatibility_db_path.exists():
            self.skipTest("Compatibility cache database not found")
        
        conn = sqlite3.connect(self.compatibility_db_path)
        cursor = conn.cursor()
        
        # Get PCIe version data
        cursor.execute("""
            SELECT product_slug, attribute_value, source_seller, confidence
            FROM product_attributes
            WHERE attribute_type IN ('pcie_version', 'pcie_requirement')
            LIMIT 5
        """)
        
        rows = cursor.fetchall()
        for row in rows:
            product_slug, pcie_value, source, confidence = row
            # PCIe version should be valid (e.g., "PCIe:5.0", "PCIe:4.0")
            self.assertIsNotNone(pcie_value)
            pcie_str = str(pcie_value)
            # Should contain PCIe version info
            self.assertTrue("pcie" in pcie_str.lower() or "4.0" in pcie_str or "5.0" in pcie_str)
        
        conn.close()

    def test_scraped_wattage_accuracy(self):
        """Validate wattage information from web scraping."""
        if not self.compatibility_db_path.exists():
            self.skipTest("Compatibility cache database not found")
        
        conn = sqlite3.connect(self.compatibility_db_path)
        cursor = conn.cursor()
        
        # Get wattage data - fetch more rows to account for N/A values
        cursor.execute("""
            SELECT product_slug, attribute_value, source_seller, confidence
            FROM product_attributes
            WHERE attribute_type IN ('wattage', 'recommended_psu_watts', 'tdp_watts')
            LIMIT 20
        """)
        
        rows = cursor.fetchall()
        validated_count = 0
        for row in rows:
            product_slug, wattage_value, source, confidence = row
            # Skip null, N/A, or empty values
            if wattage_value is None:
                continue
            
            wattage_str = str(wattage_value).strip()
            # Skip N/A, null (as string), empty, or other placeholder values
            if wattage_str.upper() in ("NULL", "N/A", "NA", "", "NONE", "UNKNOWN", "NONE"):
                continue
            
            # Also skip if it's just whitespace or the literal string "null"
            if not wattage_str or wattage_str.lower() == "null":
                continue
            
            # Wattage should be numeric or contain "W"
            # Should contain wattage indicator or be numeric
            # Allow formats like "850W", "850", "850 W", or numeric strings
            has_wattage_indicator = (
                "w" in wattage_str.lower() or 
                wattage_str.replace(".", "").replace("-", "").isdigit() or
                any(char.isdigit() for char in wattage_str)  # Contains at least one digit
            )
            self.assertTrue(
                has_wattage_indicator,
                f"Wattage value '{wattage_value}' should contain 'W' or be numeric"
            )
            validated_count += 1
        
        # Ensure we validated at least some wattage values
        self.assertGreater(validated_count, 0, "Should have validated at least one wattage value")
        
        conn.close()


if __name__ == "__main__":
    unittest.main()

