"""
Compatibility Helper Functions

Helper functions for compatibility checking queries for PC parts using the Neo4j knowledge graph.
"""
import logging
from typing import Dict, List, Optional, Any
from idss_agent.tools.kg_compatibility import get_compatibility_tool
from idss_agent.state.schema import ComparisonTable

logger = logging.getLogger(__name__)


def check_compatibility_binary(
    part1_slug: str,
    part2_slug: str,
    compatibility_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Check if two parts are compatible (binary check).

    Args:
        part1_slug: Slug of first product
        part2_slug: Slug of second product
        compatibility_types: Optional list of compatibility types to check

    Returns:
        Dict with compatibility result
    """
    tool = get_compatibility_tool()
    if not tool.is_available():
        return {
            "compatible": False,
            "error": "Compatibility checking unavailable"
        }

    result = tool.check_compatibility(part1_slug, part2_slug, compatibility_types)
    return result


def find_compatible_parts_recommendations(
    source_slug: str,
    target_type: str,
    compatibility_type: Optional[str] = None,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Find compatible parts recommendations.

    Args:
        source_slug: Slug of source product
        target_type: Product type to find
        compatibility_type: Specific compatibility type
        limit: Number of recommendations

    Returns:
        List of recommended products
    """
    tool = get_compatibility_tool()
    if not tool.is_available():
        return []

    # Get more candidates for reranking
    candidates = tool.find_compatible_parts(source_slug, target_type, compatibility_type, limit=50)
    
    # Simple reranking: by price (ascending), then by name
    # Could be enhanced with user preferences, ratings, etc.
    candidates.sort(key=lambda x: (
        x.get("price_avg") or x.get("price_min") or float('inf'),
        x.get("name", "")
    ))

    return candidates[:limit]


def format_compatibility_recommendations_table(
    products: List[Dict[str, Any]],
    source_product_name: str
) -> ComparisonTable:
    """
    Format compatible products as a comparison table.

    Args:
        products: List of product dictionaries
        source_product_name: Name of source product

    Returns:
        ComparisonTable object
    """
    def strip_brand_and_type(name: str) -> str:
        """Strip first word (brand) and last word (part type) from product name."""
        if not name:
            return name
        words = name.split()
        if len(words) <= 2:
            # If 2 words or less, return as is
            return name
        # Remove first word (brand) and last word (part type, may be in parentheses like "(GPU)")
        return " ".join(words[1:-1])
    
    if not products:
        return ComparisonTable(headers=["Attribute"], rows=[])

    # Build headers - strip brand (first word) and part type (last word)
    headers = ["Attribute"] + [strip_brand_and_type(p.get("name", "Unknown")) for p in products]

    # Build rows
    rows = []

    # Price row
    price_values = []
    for p in products:
        price_avg = p.get("price_avg")
        price_min = p.get("price_min")
        if price_avg:
            price_values.append(f"${price_avg:.2f}")
        elif price_min:
            price_values.append(f"${price_min:.2f}+")
        else:
            price_values.append("N/A")
    rows.append(["Price"] + price_values)

    # Brand row
    rows.append(["Brand"] + [p.get("brand", "N/A") for p in products])

    # Product type specific attributes
    if products and products[0].get("product_type") == "gpu":
        # GPU-specific attributes
        pcie_attrs = []
        for p in products:
            pcie = p.get("pcie_version") or p.get("pcie_requirement") or "N/A"
            pcie_attrs.append(str(pcie))
        rows.append(["PCIe Version"] + pcie_attrs)

        wattage_attrs = []
        for p in products:
            wattage = p.get("recommended_psu_watts") or p.get("tdp_watts") or "N/A"
            wattage_attrs.append(str(wattage))
        rows.append(["Power Requirement"] + wattage_attrs)

    elif products and products[0].get("product_type") == "cpu":
        # CPU-specific attributes
        socket_attrs = []
        for p in products:
            socket = p.get("socket") or "N/A"
            socket_attrs.append(str(socket))
        rows.append(["Socket"] + socket_attrs)

    elif products and products[0].get("product_type") == "ram":
        # RAM-specific attributes
        ddr_attrs = []
        for p in products:
            ddr = p.get("ram_standard") or p.get("ddr") or "N/A"
            ddr_attrs.append(str(ddr))
        rows.append(["DDR Standard"] + ddr_attrs)

        capacity_attrs = []
        for p in products:
            capacity = p.get("capacity") or p.get("size") or "N/A"
            capacity_attrs.append(str(capacity))
        rows.append(["Capacity"] + capacity_attrs)

    return ComparisonTable(headers=headers, rows=rows)

