"""
Neo4j Knowledge Graph Compatibility Tool

Provides functions to query Neo4j for PC parts compatibility information.
"""
import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

logger = logging.getLogger(__name__)

# Compatibility relationship types
COMPATIBILITY_TYPES = {
    "ELECTRICAL_COMPATIBLE_WITH": "Power supply compatibility (PSU wattage requirements)",
    "SOCKET_COMPATIBLE_WITH": "Socket compatibility (CPU and motherboard socket matching)",
    "INTERFACE_COMPATIBLE_WITH": "PCIe interface compatibility (GPU and motherboard)",
    "RAM_COMPATIBLE_WITH": "RAM standard compatibility (RAM and motherboard DDR standard)",
    "MEMORY_COMPATIBLE_WITH": "Memory controller compatibility (CPU and RAM)",
    "FORM_FACTOR_COMPATIBLE_WITH": "Form factor compatibility (case and motherboard physical size)",
    "THERMAL_COMPATIBLE_WITH": "Thermal compatibility (cooler socket and TDP capacity)",
}

# Part type to compatibility type mapping
PART_COMPATIBILITY_MAP = {
    ("cpu", "motherboard"): ["SOCKET_COMPATIBLE_WITH"],
    ("motherboard", "cpu"): ["SOCKET_COMPATIBLE_WITH"],
    ("gpu", "psu"): ["ELECTRICAL_COMPATIBLE_WITH"],
    ("psu", "gpu"): ["ELECTRICAL_COMPATIBLE_WITH"],
    ("cpu", "psu"): ["ELECTRICAL_COMPATIBLE_WITH"],
    ("psu", "cpu"): ["ELECTRICAL_COMPATIBLE_WITH"],
    ("motherboard", "gpu"): ["INTERFACE_COMPATIBLE_WITH"],
    ("gpu", "motherboard"): ["INTERFACE_COMPATIBLE_WITH"],
    ("ram", "motherboard"): ["RAM_COMPATIBLE_WITH"],
    ("motherboard", "ram"): ["RAM_COMPATIBLE_WITH"],
    ("cpu", "ram"): ["MEMORY_COMPATIBLE_WITH"],
    ("ram", "cpu"): ["MEMORY_COMPATIBLE_WITH"],
    ("case", "motherboard"): ["FORM_FACTOR_COMPATIBLE_WITH"],
    ("motherboard", "case"): ["FORM_FACTOR_COMPATIBLE_WITH"],
    ("cooler", "cpu"): ["THERMAL_COMPATIBLE_WITH"],
    ("cpu", "cooler"): ["THERMAL_COMPATIBLE_WITH"],
}

# Supported PC part types
PC_PART_TYPES = {
    "cpu", "gpu", "motherboard", "psu", "ram", "storage", "case", "cooler"
}


class Neo4jCompatibilityTool:
    """Tool for querying Neo4j knowledge graph for compatibility information."""

    def __init__(self):
        """Initialize Neo4j connection."""
        self.driver = None
        self._connect()

    def _connect(self) -> None:
        """Connect to Neo4j database."""
        if GraphDatabase is None:
            logger.warning("Neo4j driver not installed. Compatibility checking unavailable.")
            return

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")

        if not password:
            logger.warning("NEO4J_PASSWORD not set. Compatibility checking unavailable.")
            return

        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Connected to Neo4j successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.driver = None

    def is_available(self) -> bool:
        """Check if Neo4j connection is available."""
        return self.driver is not None

    def find_product_by_name(self, product_name: str, product_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find a product in the knowledge graph by name (fuzzy matching).

        Args:
            product_name: Product name to search for
            product_type: Optional product type filter

        Returns:
            Product node data or None if not found
        """
        if not self.is_available():
            return None

        try:
            with self.driver.session() as session:
                # Try exact slug match first
                slug = product_name.lower().replace(" ", "-").replace("_", "-")
                query = """
                    MATCH (p:PCProduct {slug: $slug})
                    RETURN p
                    LIMIT 1
                """
                result = session.run(query, slug=slug)
                record = result.single()
                if record:
                    return dict(record["p"])

                # Try fuzzy name matching
                query = """
                    MATCH (p:PCProduct)
                    WHERE toLower(p.name) CONTAINS toLower($name)
                       OR toLower(p.slug) CONTAINS toLower($name)
                """
                if product_type:
                    query += " AND p.product_type = $product_type"
                query += """
                    RETURN p
                    ORDER BY p.name
                    LIMIT 5
                """
                params = {"name": product_name}
                if product_type:
                    params["product_type"] = product_type

                result = session.run(query, **params)
                records = list(result)
                if records:
                    # Return the first match (could be improved with better ranking)
                    return dict(records[0]["p"])

                return None
        except Exception as e:
            logger.error(f"Error finding product: {e}")
            return None

    def check_compatibility(
        self, 
        part1_slug: str, 
        part2_slug: str, 
        compatibility_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Check if two parts are compatible.

        Args:
            part1_slug: Slug of first product
            part2_slug: Slug of second product
            compatibility_types: Optional list of compatibility types to check

        Returns:
            Dict with 'compatible', 'compatibility_types', 'explanation'
        """
        if not self.is_available():
            return {
                "compatible": False,
                "error": "Neo4j connection unavailable"
            }

        try:
            with self.driver.session() as session:
                # Get product types
                query = """
                    MATCH (p1:PCProduct {slug: $slug1})
                    MATCH (p2:PCProduct {slug: $slug2})
                    RETURN p1.product_type AS type1, p2.product_type AS type2, p1.name AS name1, p2.name AS name2
                """
                result = session.run(query, slug1=part1_slug, slug2=part2_slug)
                record = result.single()
                if not record:
                    return {
                        "compatible": False,
                        "error": "One or both products not found"
                    }

                type1 = record["type1"]
                type2 = record["type2"]
                name1 = record["name1"]
                name2 = record["name2"]

                # Determine compatibility types to check
                # Check both directions since compatibility is symmetric
                if not compatibility_types:
                    key = (type1, type2)
                    compatibility_types = PART_COMPATIBILITY_MAP.get(key, [])
                    # Try reverse direction if not found
                    if not compatibility_types:
                        key = (type2, type1)
                        compatibility_types = PART_COMPATIBILITY_MAP.get(key, [])

                if not compatibility_types:
                    return {
                        "compatible": False,
                        "error": f"Compatibility checking not supported for {type1} and {type2}"
                    }

                # Check each compatibility type (bidirectional - compatibility is symmetric)
                found_types = []
                for rel_type in compatibility_types:
                    # Check both directions since compatibility is symmetric
                    query = f"""
                        MATCH (p1:PCProduct {{slug: $slug1}})-[r:{rel_type}]-(p2:PCProduct {{slug: $slug2}})
                        RETURN r
                        LIMIT 1
                    """
                    logger.info(f"[KG Query] Checking compatibility: {name1} <-> {name2} via {rel_type}")
                    logger.debug(f"[KG Query] Cypher: {query}")
                    logger.debug(f"[KG Query] Parameters: slug1={part1_slug}, slug2={part2_slug}")
                    result = session.run(query, slug1=part1_slug, slug2=part2_slug)
                    record = result.single()
                    if record:
                        found_types.append(rel_type)
                        logger.info(f"[KG Result] ✓ Compatible via {rel_type}")
                    else:
                        logger.debug(f"[KG Result] ✗ No relationship found for {rel_type}")

                compatible = len(found_types) > 0

                # Build explanation
                if compatible:
                    explanation = f"{name1} is compatible with {name2}."
                    if len(found_types) == 1:
                        explanation += f" They are compatible via {COMPATIBILITY_TYPES.get(found_types[0], found_types[0])}."
                    else:
                        types_desc = [COMPATIBILITY_TYPES.get(t, t) for t in found_types]
                        explanation += f" They are compatible via: {', '.join(types_desc)}."
                else:
                    explanation = f"{name1} is not compatible with {name2} based on the checked compatibility types."

                result_data = {
                    "compatible": compatible,
                    "compatibility_types": found_types,
                    "explanation": explanation,
                    "part1_name": name1,
                    "part2_name": name2
                }
                logger.info(f"[KG Result] Compatibility check complete: {name1} <-> {name2} = {compatible} (types: {found_types})")
                return result_data
        except Exception as e:
            logger.error(f"Error checking compatibility: {e}")
            return {
                "compatible": False,
                "error": str(e)
            }

    def find_compatible_parts(
        self,
        source_slug: str,
        target_type: str,
        compatibility_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find parts compatible with a source part.

        Args:
            source_slug: Slug of source product
            target_type: Product type to find (e.g., "gpu", "cpu")
            compatibility_type: Specific compatibility type to check (optional)
            limit: Maximum number of results

        Returns:
            List of compatible product nodes
        """
        if not self.is_available():
            return []

        try:
            with self.driver.session() as session:
                # Get source product type
                query = """
                    MATCH (source:PCProduct {slug: $slug})
                    RETURN source.product_type AS source_type
                """
                result = session.run(query, slug=source_slug)
                record = result.single()
                if not record:
                    return []

                source_type = record["source_type"]

                # Determine compatibility type if not provided
                # Check both (source_type, target_type) and (target_type, source_type) since compatibility is symmetric
                if not compatibility_type:
                    key = (source_type, target_type)
                    types = PART_COMPATIBILITY_MAP.get(key, [])
                    if not types:
                        # Try reverse direction
                        key = (target_type, source_type)
                        types = PART_COMPATIBILITY_MAP.get(key, [])
                    if not types:
                        return []
                    compatibility_type = types[0]  # Use first matching type

                # Query compatible parts (bidirectional - check both directions)
                # First try: source -> target (normal direction)
                # Second try: target -> source (reverse direction, since compatibility is symmetric)
                query = f"""
                    MATCH (source:PCProduct {{slug: $slug}})-[r:{compatibility_type}]-(target:PCProduct)
                    WHERE target.product_type = $target_type
                    RETURN target, r
                    ORDER BY target.price_avg ASC
                    LIMIT $limit
                """
                logger.info(f"[KG Query] Finding compatible parts: source={source_slug} ({source_type}) -> target_type={target_type} via {compatibility_type}")
                logger.debug(f"[KG Query] Cypher: {query}")
                logger.debug(f"[KG Query] Parameters: slug={source_slug}, target_type={target_type}, limit={limit}")
                result = session.run(query, slug=source_slug, target_type=target_type, limit=limit)
                
                products = []
                for record in result:
                    product_data = dict(record["target"])
                    rel_data = dict(record["r"])
                    product_data["_compatibility_relationship"] = rel_data
                    products.append(product_data)

                logger.info(f"[KG Result] Found {len(products)} compatible {target_type} parts for {source_slug}")
                if products:
                    logger.debug(f"[KG Result] Products: {[p.get('name', 'Unknown') for p in products[:5]]}")
                return products
        except Exception as e:
            logger.error(f"Error finding compatible parts: {e}")
            return []

    def get_product_info(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Get full product information from knowledge graph.

        Args:
            slug: Product slug

        Returns:
            Product node data or None
        """
        if not self.is_available():
            return None

        try:
            with self.driver.session() as session:
                query = """
                    MATCH (p:PCProduct {slug: $slug})
                    RETURN p
                """
                result = session.run(query, slug=slug)
                record = result.single()
                if record:
                    return dict(record["p"])
                return None
        except Exception as e:
            logger.error(f"Error getting product info: {e}")
            return None

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None


# Global instance
_compatibility_tool: Optional[Neo4jCompatibilityTool] = None


def get_compatibility_tool() -> Neo4jCompatibilityTool:
    """Get or create the global compatibility tool instance."""
    global _compatibility_tool
    if _compatibility_tool is None:
        _compatibility_tool = Neo4jCompatibilityTool()
    return _compatibility_tool


def is_pc_part(product_type: str) -> bool:
    """Check if a product type is a PC part."""
    return product_type.lower() in PC_PART_TYPES


def get_compatibility_types_for_parts(part1_type: str, part2_type: str) -> List[str]:
    """Get compatibility types for two part types."""
    key = (part1_type.lower(), part2_type.lower())
    return PART_COMPATIBILITY_MAP.get(key, [])

