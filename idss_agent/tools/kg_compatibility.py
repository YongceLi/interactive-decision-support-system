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

                result = session.run(query, parameters=params)
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

    def search_products(
        self,
        part_type: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        query: Optional[str] = None,
        socket: Optional[str] = None,
        vram: Optional[str] = None,
        capacity: Optional[str] = None,
        wattage: Optional[str] = None,
        form_factor: Optional[str] = None,
        chipset: Optional[str] = None,
        ram_standard: Optional[str] = None,
        storage_type: Optional[str] = None,
        cooling_type: Optional[str] = None,
        certification: Optional[str] = None,
        pcie_version: Optional[str] = None,
        tdp: Optional[str] = None,
        year: Optional[str] = None,
        series: Optional[str] = None,
        seller: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        namespace: str = "pc_parts"
    ) -> List[Dict[str, Any]]:
        """
        Search for products in the knowledge graph with various filters.

        Args:
            part_type: Product type filter (e.g., "cpu", "gpu", "motherboard")
            brand: Brand filter (comma-separated for multiple)
            min_price: Minimum price filter
            max_price: Maximum price filter
            query: Text search in product name/slug
            socket: Socket filter (for CPU/motherboard)
            vram: VRAM filter (for GPU)
            capacity: Capacity filter (for storage/RAM)
            wattage: Wattage filter (for PSU)
            form_factor: Form factor filter (for motherboard/case)
            chipset: Chipset filter (for motherboard)
            ram_standard: RAM standard filter (DDR4, DDR5)
            storage_type: Storage type filter (NVMe, SSD, HDD)
            cooling_type: Cooling type filter
            certification: PSU certification filter
            pcie_version: PCIe version filter
            tdp: TDP filter
            year: Year filter (can be range like "2022-2024")
            series: Series filter
            seller: Seller filter
            limit: Maximum number of results
            offset: Offset for pagination
            namespace: Namespace for nodes (default: "pc_parts")

        Returns:
            List of product dictionaries
        """
        if not self.is_available():
            return []

        try:
            with self.driver.session() as session:
                # Build dynamic query with filters
                query_parts = ["MATCH (p:PCProduct {namespace: $namespace})"]
                where_conditions = []
                params = {"namespace": namespace, "limit": limit, "offset": offset}

                # Product type filter
                if part_type:
                    # Normalize part type
                    part_type_normalized = part_type.lower().strip()
                    if part_type_normalized == "internal_storage":
                        part_type_normalized = "storage"
                    where_conditions.append("p.product_type = $part_type")
                    params["part_type"] = part_type_normalized

                # Brand filter (supports comma-separated)
                if brand:
                    brands = [b.strip() for b in brand.split(",")]
                    if len(brands) == 1:
                        where_conditions.append("toLower(p.brand) = toLower($brand)")
                        params["brand"] = brands[0]
                    else:
                        brand_conditions = []
                        for i, b in enumerate(brands):
                            param_name = f"brand_{i}"
                            brand_conditions.append(f"toLower(p.brand) = toLower(${param_name})")
                            params[param_name] = b.strip()
                        where_conditions.append(f"({' OR '.join(brand_conditions)})")

                # Price filters
                if min_price is not None:
                    where_conditions.append(
                        "(p.price_avg IS NOT NULL AND p.price_avg >= $min_price) OR "
                        "(p.price_avg IS NULL AND p.price_min IS NOT NULL AND p.price_min >= $min_price)"
                    )
                    params["min_price"] = min_price
                if max_price is not None:
                    where_conditions.append(
                        "(p.price_avg IS NOT NULL AND p.price_avg <= $max_price) OR "
                        "(p.price_avg IS NULL AND p.price_max IS NOT NULL AND p.price_max <= $max_price)"
                    )
                    params["max_price"] = max_price

                # Text search in name/slug
                if query:
                    where_conditions.append(
                        "(toLower(p.name) CONTAINS toLower($query) OR "
                        "toLower(p.slug) CONTAINS toLower($query) OR "
                        "toLower(p.raw_name) CONTAINS toLower($query))"
                    )
                    params["query"] = query

                # Attribute filters
                if socket:
                    where_conditions.append("toLower(p.socket) = toLower($socket)")
                    params["socket"] = socket
                if vram:
                    where_conditions.append("p.vram = $vram")
                    params["vram"] = vram
                if capacity:
                    where_conditions.append("p.capacity = $capacity")
                    params["capacity"] = capacity
                if wattage:
                    where_conditions.append("p.wattage = $wattage")
                    params["wattage"] = wattage
                if form_factor:
                    where_conditions.append("toLower(p.form_factor) = toLower($form_factor)")
                    params["form_factor"] = form_factor
                if chipset:
                    where_conditions.append("toLower(p.chipset) = toLower($chipset)")
                    params["chipset"] = chipset
                if ram_standard:
                    where_conditions.append("toUpper(p.ram_standard) = toUpper($ram_standard)")
                    params["ram_standard"] = ram_standard
                if storage_type:
                    where_conditions.append("toLower(p.storage_type) = toLower($storage_type)")
                    params["storage_type"] = storage_type
                if cooling_type:
                    where_conditions.append("toLower(p.cooling_type) = toLower($cooling_type)")
                    params["cooling_type"] = cooling_type
                if certification:
                    where_conditions.append("toLower(p.certification) CONTAINS toLower($certification)")
                    params["certification"] = certification
                if pcie_version:
                    where_conditions.append("p.pcie_version = $pcie_version")
                    params["pcie_version"] = pcie_version
                if tdp:
                    where_conditions.append("p.tdp = $tdp")
                    params["tdp"] = tdp
                if year:
                    # Handle year ranges like "2022-2024"
                    if "-" in str(year):
                        try:
                            year_parts = str(year).split("-")
                            year_min = int(year_parts[0].strip())
                            year_max = int(year_parts[1].strip()) if len(year_parts) > 1 else year_min
                            where_conditions.append("p.year >= $year_min AND p.year <= $year_max")
                            params["year_min"] = year_min
                            params["year_max"] = year_max
                        except ValueError:
                            pass
                    else:
                        try:
                            year_val = int(year)
                            where_conditions.append("p.year = $year")
                            params["year"] = year_val
                        except ValueError:
                            pass
                if series:
                    where_conditions.append("toLower(p.series) CONTAINS toLower($series)")
                    params["series"] = series
                if seller:
                    where_conditions.append("toLower(p.seller) CONTAINS toLower($seller)")
                    params["seller"] = seller

                # Build WHERE clause
                if where_conditions:
                    query_parts.append("WHERE " + " AND ".join(where_conditions))

                # Return and ordering
                # Note: Professional/workstation products are filtered out in Python
                # (see _rank_products_for_consumer_use in recommendation.py)
                # to prioritize consumer/personal use products
                query_parts.append("RETURN p")
                query_parts.append(
                    "ORDER BY COALESCE(p.price_avg, p.price_min, 999999) ASC"
                )
                query_parts.append("SKIP $offset LIMIT $limit")

                cypher_query = "\n".join(query_parts)
                logger.debug(f"[KG Search] Query: {cypher_query}")
                logger.debug(f"[KG Search] Params: {params}")

                result = session.run(cypher_query, parameters=params)
                products = []
                for record in result:
                    product_data = dict(record["p"])
                    products.append(product_data)

                logger.info(f"[KG Search] Found {len(products)} products matching filters")
                return products

        except Exception as e:
            logger.error(f"Error searching products in KG: {e}")
            return []

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

