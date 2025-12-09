#!/usr/bin/env python3
"""
Build Neo4j Knowledge Graph from Augmented PC Parts Database

This script reads from pc_parts_augmented.db and creates a Neo4j knowledge graph
with product nodes and compatibility relationships.

It replaces the entire graph (purges first), not updates.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None
    print("ERROR: neo4j package not installed. Install with: pip install neo4j")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("build_kg_from_augmented")

# Load environment variables
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class ProductRecord:
    """Represents a product with all its attributes."""
    product_id: str
    slug: str
    product_type: str
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    series: Optional[str] = None
    price: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_avg: Optional[float] = None
    seller: Optional[str] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    raw_name: Optional[str] = None
    imageurl: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


def load_attributes_config() -> Dict[str, Any]:
    """Load attributes configuration from JSON file."""
    config_path = PROJECT_ROOT / "dataset_builder" / "pc_parts_attributes.json"
    if not config_path.exists():
        logger.warning(f"Attributes config not found at {config_path}, using defaults")
        return {"part_types": {}}
    
    with open(config_path, 'r') as f:
        return json.load(f)


def get_valid_attributes_for_product_type(product_type: str, config: Dict[str, Any]) -> Set[str]:
    """Get valid attributes for a product type."""
    part_types = config.get("part_types", {})
    product_type_lower = product_type.lower()
    
    # Handle aliases
    if product_type_lower == "internal_storage":
        product_type_lower = "storage"
    
    if product_type_lower in part_types:
        part_config = part_types[product_type_lower]
        required = part_config.get("required", [])
        optional = part_config.get("optional", [])
        return set(required + optional)
    
    return set()


def normalize_attribute_value(value: Any) -> Any:
    """Normalize attribute values for Neo4j."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in ('none', 'null', ''):
            return None
        # Try to convert numeric strings
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        # Convert boolean strings
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        return value
    return value


def product_type_to_label(product_type: str) -> str:
    """Convert product type to a valid Neo4j label (uppercase, no special chars)."""
    if not product_type:
        return "PCProduct"
    # Normalize: uppercase, replace special chars with underscore, remove underscores at start/end
    label = product_type.upper().replace('-', '_').replace(' ', '_')
    # Remove leading/trailing underscores
    label = label.strip('_')
    # Handle special cases
    if label == 'INTERNAL_STORAGE':
        label = 'STORAGE'
    elif label == 'COOLING':
        label = 'COOLER'
    return label


def load_products_from_augmented_db(
    db_path: Path,
    limit: Optional[int] = None
) -> List[ProductRecord]:
    """Load products from augmented database with merged attributes."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Load attributes config
    attrs_config = load_attributes_config()
    
    # Get all products
    query = "SELECT * FROM pc_parts_augmented"
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    products = []
    for row in rows:
        product_id = row['product_id']
        product_type = row['product_type']
        
        # Get valid attributes for this product type
        valid_attrs = get_valid_attributes_for_product_type(product_type, attrs_config)
        
        # Start with base attributes from table columns
        attributes = {}
        
        # First, try to parse base_attributes JSON if it exists
        base_attributes_json = row['base_attributes'] if 'base_attributes' in row.keys() else None
        if base_attributes_json:
            try:
                base_attrs = json.loads(base_attributes_json)
                if isinstance(base_attrs, dict):
                    for attr_name, attr_value in base_attrs.items():
                        if attr_value is not None and str(attr_value).strip():
                            attr_name_normalized = attr_name.lower().replace(" ", "_").replace("-", "_")
                            if not valid_attrs or attr_name_normalized in valid_attrs:
                                normalized = normalize_attribute_value(attr_value)
                                if normalized is not None:
                                    attributes[attr_name_normalized] = normalized
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Get all attribute columns from the row (these override base_attributes JSON)
        for key in row.keys():
            if key in ['id', 'product_id', 'slug', 'product_type', 'raw_name', 
                      'brand', 'model', 'series', 'price', 'price_min', 'price_max', 
                      'price_avg', 'seller', 'rating', 'rating_count', 'imageurl',
                      'created_at', 'updated_at', 'needs_manual_review', 'base_attributes']:
                continue
            
            value = row[key]
            if value is not None and str(value).strip():
                attr_name = key.lower().replace(" ", "_").replace("-", "_")
                if not valid_attrs or attr_name in valid_attrs:
                    normalized = normalize_attribute_value(value)
                    if normalized is not None:
                        attributes[attr_name] = normalized  # Column values override JSON
        
        # Merge with validated attributes
        cursor.execute("""
            SELECT attribute_name, attribute_value
            FROM validated_attributes
            WHERE product_id = ?
        """, (product_id,))
        
        validated_rows = cursor.fetchall()
        for val_row in validated_rows:
            attr_name = val_row['attribute_name']
            attr_value = val_row['attribute_value']
            
            # Only include if it's a valid attribute for this product type
            if not valid_attrs or attr_name in valid_attrs:
                normalized = normalize_attribute_value(attr_value)
                if normalized is not None:
                    # Validated attributes take precedence
                    attributes[attr_name] = normalized
        
        # Create product record
        def get_row_value(key, default=None):
            """Get value from sqlite3.Row with default."""
            return row[key] if key in row.keys() else default
        
        product = ProductRecord(
            product_id=product_id,
            slug=row['slug'],
            product_type=product_type,
            name=row['raw_name'] or row['slug'],
            brand=get_row_value('brand'),
            model=get_row_value('model'),
            series=get_row_value('series'),
            price=get_row_value('price'),
            price_min=get_row_value('price_min'),
            price_max=get_row_value('price_max'),
            price_avg=get_row_value('price_avg'),
            seller=get_row_value('seller'),
            rating=get_row_value('rating'),
            rating_count=get_row_value('rating_count'),
            raw_name=get_row_value('raw_name'),
            imageurl=get_row_value('imageurl'),
            attributes=attributes
        )
        
        products.append(product)
    
    conn.close()
    logger.info(f"Loaded {len(products)} products from augmented database")
    return products


def ensure_driver(uri: str, user: str, password: str):
    """Create and verify Neo4j driver connection."""
    if GraphDatabase is None:
        raise ImportError("neo4j package not installed")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    # Test connection
    with driver.session() as session:
        session.run("RETURN 1")
    return driver


def purge_graph(driver, namespace: str):
    """Delete all nodes and relationships in the namespace."""
    logger.info(f"Purging existing graph for namespace '{namespace}'...")
    with driver.session() as session:
        # Delete product nodes and their relationships
        result = session.run("""
            MATCH (n:PCProduct {namespace: $namespace})
            DETACH DELETE n
        """, namespace=namespace)
        count = result.consume().counters.nodes_deleted
        logger.info(f"Deleted {count} product nodes")
        
        # Delete product type nodes (they don't have namespace, but we'll recreate them)
        result = session.run("""
            MATCH (pt:ProductType)
            DETACH DELETE pt
        """)
        count = result.consume().counters.nodes_deleted
        logger.info(f"Deleted {count} product type nodes")


def create_product_type_nodes(driver, products: List[ProductRecord]):
    """Create ProductType nodes for all unique product types."""
    # Collect unique product types
    product_types = set()
    for product in products:
        if product.product_type:
            product_types.add(product.product_type.lower())
    
    logger.info(f"Creating {len(product_types)} product type nodes: {sorted(product_types)}")
    
    with driver.session() as session:
        for product_type in product_types:
            session.run("""
                MERGE (pt:ProductType {name: $name})
                SET pt.display_name = $display_name
            """, name=product_type, display_name=product_type.capitalize())
    
    logger.info("All product type nodes created")


def create_product_nodes(driver, namespace: str, products: List[ProductRecord]):
    """Create product nodes in Neo4j with product-type-specific labels (e.g., :CPU, :RAM, :GPU)."""
    logger.info(f"Creating {len(products)} product nodes with type-specific labels...")
    
    # Group products by type to create nodes with appropriate labels
    products_by_type: Dict[str, List[ProductRecord]] = {}
    for product in products:
        product_type = product.product_type or "unknown"
        if product_type not in products_by_type:
            products_by_type[product_type] = []
        products_by_type[product_type].append(product)
    
    batch_size = 100
    excluded_keys = ['slug', 'name', 'product_type', 'brand', 'model', 'series',
                     'price', 'price_min', 'price_max', 'price_avg', 'seller', 
                     'rating', 'rating_count', 'raw_name', 'imageurl']
    
    # Create nodes grouped by type (so we can use the correct label)
    with driver.session() as session:
        total_created = 0
        for product_type, type_products in products_by_type.items():
            label = product_type_to_label(product_type)
            logger.info(f"Creating {len(type_products)} nodes with label :{label}...")
            
            # Prepare node data for this type
            nodes_data = []
            for product in type_products:
                node_data = {
                    'slug': product.slug,
                    'name': product.name,
                    'product_type': product.product_type,
                    'brand': product.brand,
                    'model': product.model,
                    'series': product.series,
                    'price': product.price,
                    'price_min': product.price_min,
                    'price_max': product.price_max,
                    'price_avg': product.price_avg,
                    'seller': product.seller,
                    'rating': product.rating,
                    'rating_count': product.rating_count,
                    'raw_name': product.raw_name,
                    'imageurl': product.imageurl,
                }
                
                # Add all attributes
                for key, value in product.attributes.items():
                    if value is not None:
                        node_data[key] = value
                
                nodes_data.append(node_data)
            
            # Create nodes with type-specific label
            for i in range(0, len(nodes_data), batch_size):
                batch = nodes_data[i:i + batch_size]
                # Use dynamic label based on product type
                query = f"""
                UNWIND $nodes AS node
                CREATE (p:PCProduct:{label} {{
                    slug: node.slug,
                    namespace: $namespace,
                    name: node.name,
                    product_type: node.product_type,
                    brand: node.brand,
                    model: node.model,
                    series: node.series,
                    price: node.price,
                    price_min: node.price_min,
                    price_max: node.price_max,
                    price_avg: node.price_avg,
                    seller: node.seller,
                    rating: node.rating,
                    rating_count: node.rating_count,
                    raw_name: node.raw_name,
                    imageurl: node.imageurl
                }})
                WITH p, node
                UNWIND keys(node) AS key
                WITH p, node, key
                WHERE NOT key IN $excluded_keys
                SET p[key] = node[key]
                """
                session.run(query, nodes=batch, namespace=namespace, excluded_keys=excluded_keys)
                total_created += len(batch)
                logger.info(f"Created {total_created}/{len(products)} nodes total")
    
    logger.info("All product nodes created with type-specific labels")
    
    # Create HAS_TYPE relationships (optional - for querying via ProductType nodes)
    logger.info("Creating HAS_TYPE relationships...")
    with driver.session() as session:
        for product_type, type_products in products_by_type.items():
            slugs = [p.slug for p in type_products]
            for i in range(0, len(slugs), batch_size):
                batch_slugs = slugs[i:i + batch_size]
                query = """
                UNWIND $slugs AS slug
                MATCH (p:PCProduct {slug: slug, namespace: $namespace})
                MATCH (pt:ProductType {name: toLower($product_type)})
                MERGE (p)-[:HAS_TYPE {namespace: $namespace}]->(pt)
                """
                session.run(query, slugs=batch_slugs, namespace=namespace, product_type=product_type)
    
    logger.info("All HAS_TYPE relationships created")


def create_compatibility_edges(driver, namespace: str, products: List[ProductRecord]):
    """Create compatibility edges between products based on attributes."""
    logger.info("Creating compatibility edges...")
    
    # Index products by slug and type
    products_by_slug = {p.slug: p for p in products}
    products_by_type: Dict[str, List[ProductRecord]] = {}
    for product in products:
        if product.product_type not in products_by_type:
            products_by_type[product.product_type] = []
        products_by_type[product.product_type].append(product)
    
    edges = []
    
    # 1. SOCKET_COMPATIBLE_WITH: CPU <-> Motherboard
    cpus = products_by_type.get('cpu', [])
    motherboards = products_by_type.get('motherboard', [])
    for cpu in cpus:
        cpu_socket = cpu.attributes.get('socket')
        if not cpu_socket:
            continue
        for mb in motherboards:
            mb_socket = mb.attributes.get('socket')
            if mb_socket and str(cpu_socket).strip().lower() == str(mb_socket).strip().lower():
                edges.append({
                    'type': 'SOCKET_COMPATIBLE_WITH',
                    'from': cpu.slug,
                    'to': mb.slug,
                    'props': {'socket': str(cpu_socket)}
                })
    
    # 2. RAM_COMPATIBLE_WITH: RAM <-> Motherboard
    rams = products_by_type.get('ram', [])
    for ram in rams:
        ram_standard = ram.attributes.get('ram_standard')
        if not ram_standard:
            continue
        for mb in motherboards:
            mb_ram_standard = mb.attributes.get('ram_standard')
            if mb_ram_standard and str(ram_standard).strip().upper() == str(mb_ram_standard).strip().upper():
                edges.append({
                    'type': 'RAM_COMPATIBLE_WITH',
                    'from': ram.slug,
                    'to': mb.slug,
                    'props': {'ram_standard': str(ram_standard)}
                })
    
    # 3. MEMORY_COMPATIBLE_WITH: CPU <-> RAM
    for cpu in cpus:
        cpu_ram_standard = cpu.attributes.get('ram_standard')
        if not cpu_ram_standard:
            continue
        for ram in rams:
            ram_standard = ram.attributes.get('ram_standard')
            if ram_standard and str(cpu_ram_standard).strip().upper() == str(ram_standard).strip().upper():
                edges.append({
                    'type': 'MEMORY_COMPATIBLE_WITH',
                    'from': cpu.slug,
                    'to': ram.slug,
                    'props': {'ram_standard': str(ram_standard)}
                })
    
    # 4. INTERFACE_COMPATIBLE_WITH: GPU <-> Motherboard (PCIe version)
    gpus = products_by_type.get('gpu', [])
    for gpu in gpus:
        gpu_interface = gpu.attributes.get('interface', '')
        # Extract PCIe version from interface (e.g., "PCIe 4.0 x16" -> "4.0")
        gpu_pcie = None
        if gpu_interface:
            match = re.search(r'PCIe\s*(\d+\.\d+)', str(gpu_interface), re.IGNORECASE)
            if match:
                gpu_pcie = match.group(1)
        
        # Also check pcie_version attribute
        if not gpu_pcie:
            gpu_pcie = gpu.attributes.get('pcie_version')
        
        if not gpu_pcie:
            continue
        
        for mb in motherboards:
            mb_pcie = mb.attributes.get('pcie_version')
            if mb_pcie:
                # Check if motherboard supports GPU's PCIe version (backward compatible)
                try:
                    gpu_pcie_float = float(str(gpu_pcie))
                    mb_pcie_float = float(str(mb_pcie))
                    if mb_pcie_float >= gpu_pcie_float:
                        edges.append({
                            'type': 'INTERFACE_COMPATIBLE_WITH',
                            'from': mb.slug,
                            'to': gpu.slug,
                            'props': {
                                'board_pcie': str(mb_pcie),
                                'gpu_requirement': str(gpu_pcie)
                            }
                        })
                except ValueError:
                    pass
    
    # 5. ELECTRICAL_COMPATIBLE_WITH: PSU <-> GPU (and PSU <-> CPU)
    psus = products_by_type.get('psu', [])
    
    # PSU -> GPU
    for psu in psus:
        psu_wattage = psu.attributes.get('wattage')
        if not psu_wattage:
            continue
        try:
            psu_watts = float(str(psu_wattage))
        except (ValueError, TypeError):
            continue
        
        for gpu in gpus:
            # Estimate GPU power requirement (TDP or vram-based estimate)
            gpu_tdp = gpu.attributes.get('tdp')
            gpu_vram = gpu.attributes.get('vram')
            required_watts = None
            
            if gpu_tdp:
                try:
                    required_watts = float(str(gpu_tdp))
                except (ValueError, TypeError):
                    pass
            
            # Rough estimate: 50W per GB VRAM if no TDP
            if required_watts is None and gpu_vram:
                try:
                    vram_gb = float(str(gpu_vram))
                    required_watts = vram_gb * 50  # Rough estimate
                except (ValueError, TypeError):
                    pass
            
            if required_watts and psu_watts >= required_watts * 1.2:  # 20% margin
                margin = psu_watts - required_watts
                edges.append({
                    'type': 'ELECTRICAL_COMPATIBLE_WITH',
                    'from': psu.slug,
                    'to': gpu.slug,
                    'props': {
                        'psu_watts': psu_watts,
                        'required_watts': required_watts,
                        'margin_watts': margin
                    }
                })
    
    # PSU -> CPU
    for psu in psus:
        psu_wattage = psu.attributes.get('wattage')
        if not psu_wattage:
            continue
        try:
            psu_watts = float(str(psu_wattage))
        except (ValueError, TypeError):
            continue
        
        for cpu in cpus:
            cpu_tdp = cpu.attributes.get('tdp')
            if cpu_tdp:
                try:
                    required_watts = float(str(cpu_tdp))
                    if psu_watts >= required_watts * 1.2:  # 20% margin
                        margin = psu_watts - required_watts
                        edges.append({
                            'type': 'ELECTRICAL_COMPATIBLE_WITH',
                            'from': psu.slug,
                            'to': cpu.slug,
                            'props': {
                                'psu_watts': psu_watts,
                                'required_watts': required_watts,
                                'margin_watts': margin
                            }
                        })
                except (ValueError, TypeError):
                    pass
    
    # 6. FORM_FACTOR_COMPATIBLE_WITH: Case <-> Motherboard
    cases = products_by_type.get('case', [])
    for case in cases:
        # Cases might have supported_form_factors or form_factor attribute
        case_form_factors = []
        case_form_factor = case.attributes.get('form_factor')
        if case_form_factor:
            # Parse comma-separated or list
            if isinstance(case_form_factor, str):
                case_form_factors = [f.strip().upper() for f in case_form_factor.split(',')]
            else:
                case_form_factors = [str(case_form_factor).strip().upper()]
        
        for mb in motherboards:
            mb_form_factor = mb.attributes.get('form_factor')
            if mb_form_factor:
                mb_form_factor_upper = str(mb_form_factor).strip().upper()
                # Check if case supports this form factor
                # ATX cases typically support mATX and Mini-ITX too
                if mb_form_factor_upper in case_form_factors:
                    edges.append({
                        'type': 'FORM_FACTOR_COMPATIBLE_WITH',
                        'from': case.slug,
                        'to': mb.slug,
                        'props': {'form_factor': str(mb_form_factor)}
                    })
                elif 'ATX' in case_form_factors and mb_form_factor_upper in ['MICRO-ATX', 'M-ATX', 'MINI-ITX']:
                    # ATX cases typically support smaller form factors
                    edges.append({
                        'type': 'FORM_FACTOR_COMPATIBLE_WITH',
                        'from': case.slug,
                        'to': mb.slug,
                        'props': {'form_factor': str(mb_form_factor)}
                    })
    
    # 7. THERMAL_COMPATIBLE_WITH: Cooler <-> CPU
    coolers = products_by_type.get('cooling', [])
    for cooler in coolers:
        cooler_tdp_support = cooler.attributes.get('tdp_support')
        if not cooler_tdp_support:
            continue
        try:
            cooler_tdp = float(str(cooler_tdp_support))
        except (ValueError, TypeError):
            continue
        
        for cpu in cpus:
            cpu_socket = cpu.attributes.get('socket')
            cpu_tdp = cpu.attributes.get('tdp')
            
            if not cpu_socket or not cpu_tdp:
                continue
            
            try:
                cpu_tdp_float = float(str(cpu_tdp))
            except (ValueError, TypeError):
                continue
            
            # Check if cooler supports CPU socket (simplified - would need socket list from cooler)
            # For now, assume compatibility if TDP is sufficient
            if cooler_tdp >= cpu_tdp_float:
                edges.append({
                    'type': 'THERMAL_COMPATIBLE_WITH',
                    'from': cooler.slug,
                    'to': cpu.slug,
                    'props': {
                        'cooler_support_watts': cooler_tdp,
                        'cpu_requirement_watts': cpu_tdp_float,
                        'margin_watts': cooler_tdp - cpu_tdp_float
                    }
                })
    
    # Create edges in Neo4j
    logger.info(f"Creating {len(edges)} compatibility edges...")
    batch_size = 100
    with driver.session() as session:
        for i in range(0, len(edges), batch_size):
            batch = edges[i:i + batch_size]
            for edge in batch:
                query = f"""
                MATCH (a:PCProduct {{slug: $from_slug, namespace: $namespace}})
                MATCH (b:PCProduct {{slug: $to_slug, namespace: $namespace}})
                MERGE (a)-[r:{edge['type']} {{namespace: $namespace}}]-(b)
                SET r += $props
                """
                session.run(query, 
                          from_slug=edge['from'],
                          to_slug=edge['to'],
                          namespace=namespace,
                          props=edge['props'])
            logger.info(f"Created edges {i+1}-{min(i+batch_size, len(edges))}/{len(edges)}")
    
    logger.info("All compatibility edges created")


def create_indexes(driver, namespace: str):
    """Create indexes on Neo4j nodes for better query performance."""
    logger.info("Creating indexes...")
    with driver.session() as session:
        # Index on slug (most common lookup)
        session.run("CREATE INDEX IF NOT EXISTS FOR (p:PCProduct) ON (p.slug)")
        # Index on product_type (kept for backward compatibility)
        session.run("CREATE INDEX IF NOT EXISTS FOR (p:PCProduct) ON (p.product_type)")
        # Index on namespace
        session.run("CREATE INDEX IF NOT EXISTS FOR (p:PCProduct) ON (p.namespace)")
        # Index on ProductType name
        session.run("CREATE INDEX IF NOT EXISTS FOR (pt:ProductType) ON (pt.name)")
    logger.info("Indexes created")


def main():
    parser = argparse.ArgumentParser(
        description="Build Neo4j knowledge graph from augmented PC parts database"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/pc_parts_augmented.db",
        help="Path to augmented database"
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=None,
        help="Neo4j connection URI (default: from NEO4J_URI env var or bolt://localhost:7687)"
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=None,
        help="Neo4j username (default: from NEO4J_USER env var or 'neo4j')"
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=None,
        help="Neo4j password (default: from NEO4J_PASSWORD env var)"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="pc_parts",
        help="Namespace for nodes (default: 'pc_parts')"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of products to process (for testing)"
    )
    parser.add_argument(
        "--no-purge",
        action="store_true",
        help="Don't purge existing graph (default: purges first)"
    )
    
    args = parser.parse_args()
    
    # Get Neo4j connection details
    uri = args.neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = args.neo4j_user or os.getenv("NEO4J_USER", "neo4j")
    password = args.neo4j_password or os.getenv("NEO4J_PASSWORD", "")
    
    if not password:
        logger.error("Neo4j password not provided. Set NEO4J_PASSWORD env var or use --neo4j-password")
        return 1
    
    # Check database exists
    db_path = PROJECT_ROOT / args.db_path
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return 1
    
    # Connect to Neo4j
    try:
        driver = ensure_driver(uri, user, password)
        logger.info(f"Connected to Neo4j at {uri}")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        return 1
    
    try:
        # Load products
        products = load_products_from_augmented_db(db_path, limit=args.limit)
        
        if not products:
            logger.warning("No products found in database")
            return 0
        
        # Purge existing graph
        if not args.no_purge:
            purge_graph(driver, args.namespace)
        
        # Create product type nodes first
        create_product_type_nodes(driver, products)
        
        # Create product nodes
        create_product_nodes(driver, args.namespace, products)
        
        # Create edges
        create_compatibility_edges(driver, args.namespace, products)
        
        # Create indexes
        create_indexes(driver, args.namespace)
        
        logger.info("Knowledge graph build complete!")
        
        # Print summary
        with driver.session() as session:
            result = session.run("""
                MATCH (p:PCProduct {namespace: $namespace})
                RETURN count(p) as count
            """, namespace=args.namespace)
            node_count = result.single()['count']
            
            result = session.run("""
                MATCH (a:PCProduct {namespace: $namespace})-[r]-(b:PCProduct {namespace: $namespace})
                RETURN count(r) as count
            """, namespace=args.namespace)
            edge_count = result.single()['count']
            
            logger.info(f"Graph summary: {node_count} nodes, {edge_count} relationships")
        
    finally:
        driver.close()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
