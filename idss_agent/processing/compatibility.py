"""
Compatibility Handler

Handles compatibility checking queries for PC parts using the Neo4j knowledge graph.
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from idss_agent.tools.kg_compatibility import (
    get_compatibility_tool,
    is_pc_part,
    get_compatibility_types_for_parts,
    PC_PART_TYPES
)
from idss_agent.state.schema import ComparisonTable

logger = logging.getLogger(__name__)

# Natural language descriptions for compatibility types
COMPATIBILITY_DESCRIPTIONS = {
    "ELECTRICAL_COMPATIBLE_WITH": "power supply compatibility",
    "SOCKET_COMPATIBLE_WITH": "socket compatibility",
    "INTERFACE_COMPATIBLE_WITH": "PCIe interface compatibility",
    "RAM_COMPATIBLE_WITH": "RAM standard compatibility",
    "MEMORY_COMPATIBLE_WITH": "memory controller compatibility",
    "FORM_FACTOR_COMPATIBLE_WITH": "form factor compatibility",
    "THERMAL_COMPATIBLE_WITH": "thermal compatibility",
}

# Natural language part type names
PART_TYPE_NAMES = {
    "cpu": "processors (CPUs)",
    "gpu": "graphics cards (GPUs)",
    "motherboard": "motherboards",
    "psu": "power supplies (PSUs)",
    "ram": "memory (RAM)",
    "storage": "storage drives",
    "case": "PC cases",
    "cooler": "CPU coolers",
}


class CompatibilityHandler:
    """Handler for compatibility checking queries."""

    def __init__(self):
        self.kg_tool = get_compatibility_tool()

    def is_compatibility_query(self, user_query: str) -> bool:
        """
        Check if user query is about compatibility.

        Args:
            user_query: User's query text

        Returns:
            True if query is about compatibility
        """
        if not self.kg_tool.is_available():
            return False

        query_lower = user_query.lower()
        compatibility_keywords = [
            "compatible", "compatibility", "works with", "fits", "supports",
            "will work", "can i use", "does it work", "compatible with"
        ]
        return any(keyword in query_lower for keyword in compatibility_keywords)

    def classify_intent(self, user_query: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Classify compatibility query intent.

        Returns:
            Tuple of (intent_type, extracted_info)
            intent_type: "compare" or "recommend" or "unknown"
            extracted_info: Dict with part names/types if extracted
        """
        query_lower = user_query.lower()

        # Check for binary comparison pattern: "is X compatible with Y"
        comparison_patterns = [
            "is", "are", "will", "does", "can"
        ]
        for pattern in comparison_patterns:
            if pattern in query_lower and "compatible" in query_lower:
                # Likely a comparison query
                return "compare", None

        # Check for recommendation pattern: "what", "show me", "find"
        recommendation_patterns = [
            "what", "show me", "find", "recommend", "suggest", "list"
        ]
        for pattern in recommendation_patterns:
            if pattern in query_lower and ("compatible" in query_lower or "work" in query_lower):
                return "recommend", None

        return "unknown", None

    def extract_part_info(self, user_query: str, cached_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract part information from user query and cached products.

        Args:
            user_query: User's query
            cached_products: List of cached products from state

        Returns:
            Dict with extracted part information
        """
        # Try to match products from cached recommendations
        # This is a simplified version - could be enhanced with LLM extraction
        extracted = {
            "part1": None,
            "part2": None,
            "part1_type": None,
            "part2_type": None,
            "target_type": None,  # For recommendation queries
        }

        # Check cached products for matches
        query_lower = user_query.lower()
        for product in cached_products:
            product_info = product.get("product") or {}
            title = (product.get("title") or product_info.get("title") or "").lower()
            if title and any(word in query_lower for word in title.split()[:3]):
                if not extracted["part1"]:
                    extracted["part1"] = product
                    # Try to infer type from product info
                    if "cpu" in title or "processor" in title:
                        extracted["part1_type"] = "cpu"
                    elif "gpu" in title or "graphics" in title or "rtx" in title or "rx" in title:
                        extracted["part1_type"] = "gpu"
                    elif "motherboard" in title or "board" in title:
                        extracted["part1_type"] = "motherboard"
                    elif "psu" in title or "power" in title:
                        extracted["part1_type"] = "psu"
                    elif "ram" in title or "memory" in title:
                        extracted["part1_type"] = "ram"
                    elif "case" in title:
                        extracted["part1_type"] = "case"
                    elif "cooler" in title:
                        extracted["part1_type"] = "cooler"

        return extracted

    def handle_compatibility_query(
        self,
        user_query: str,
        cached_products: List[Dict[str, Any]],
        intent_type: str
    ) -> Dict[str, Any]:
        """
        Handle a compatibility query.

        Args:
            user_query: User's query
            cached_products: Cached products from state
            intent_type: "compare" or "recommend"

        Returns:
            Dict with response data
        """
        if not self.kg_tool.is_available():
            return {
                "ai_response": "The compatibility checking system is temporarily unavailable. Please try again later.",
                "compatibility_result": None,
                "comparison_table": None,
            }

        if intent_type == "compare":
            return self._handle_compare_query(user_query, cached_products)
        elif intent_type == "recommend":
            return self._handle_recommend_query(user_query, cached_products)
        else:
            return {
                "ai_response": "I can help you check compatibility between PC parts. Could you clarify what you'd like to know? For example, 'Is X compatible with Y?' or 'What GPUs work with my motherboard?'",
                "compatibility_result": None,
                "comparison_table": None,
            }

    def _handle_compare_query(
        self,
        user_query: str,
        cached_products: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle binary compatibility comparison query."""
        # Extract part information
        part_info = self.extract_part_info(user_query, cached_products)

        # Try to find products in KG
        if not part_info["part1"]:
            return {
                "ai_response": "I need to know which specific products you're asking about. Could you provide the exact model names, or reference products from your previous search results?",
                "compatibility_result": None,
                "comparison_table": None,
            }

        # For now, return a message asking for more information
        # In full implementation, would look up products in KG and check compatibility
        return {
            "ai_response": "I can check compatibility between two specific PC parts. Please provide the exact model names of both products, or reference them from your search results (e.g., '#1 and #2').",
            "compatibility_result": None,
            "comparison_table": None,
        }

    def _handle_recommend_query(
        self,
        user_query: str,
        cached_products: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle compatibility recommendation query."""
        # Extract part information
        part_info = self.extract_part_info(user_query, cached_products)

        # Determine target type from query
        query_lower = user_query.lower()
        target_type = None
        for part_type, keywords in [
            ("gpu", ["gpu", "graphics", "video card", "graphics card"]),
            ("cpu", ["cpu", "processor"]),
            ("ram", ["ram", "memory"]),
            ("psu", ["psu", "power supply"]),
            ("motherboard", ["motherboard", "board"]),
            ("case", ["case", "chassis"]),
            ("cooler", ["cooler", "cooling"]),
        ]:
            if any(keyword in query_lower for keyword in keywords):
                target_type = part_type
                break

        if not target_type:
            return {
                "ai_response": "I can help you find compatible parts. Which type of part are you looking for? I support: processors (CPUs), graphics cards (GPUs), motherboards, power supplies (PSUs), memory (RAM), storage drives, PC cases, and CPU coolers.",
                "compatibility_result": None,
                "comparison_table": None,
            }

        if not part_info["part1"]:
            return {
                "ai_response": f"I can help you find compatible {PART_TYPE_NAMES.get(target_type, target_type)}. Which specific product are you checking compatibility with? Please provide the exact model name or reference a product from your search results.",
                "compatibility_result": None,
                "comparison_table": None,
            }

        # For now, return a message asking for more information
        # In full implementation, would query KG and return recommendations
        return {
            "ai_response": f"I can help you find compatible {PART_TYPE_NAMES.get(target_type, target_type)}. Please provide the exact model name of the product you're checking compatibility with, or reference it from your search results.",
            "compatibility_result": None,
            "comparison_table": None,
        }

    def check_pc_parts_only(self, user_query: str, cached_products: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        Check if query is about PC parts only.

        Returns:
            Tuple of (is_pc_parts, error_message)
        """
        # Check cached products for product types
        for product in cached_products:
            product_info = product.get("product") or {}
            # Check if product type is in PC parts
            # This is a simplified check - could be enhanced
            pass

        # For now, assume PC parts if compatibility query detected
        # Could be enhanced with LLM classification
        return True, None

    def get_supported_compatibility_info(self) -> str:
        """Get natural language description of supported compatibility types."""
        types_list = [
            "socket compatibility (CPU and motherboard)",
            "PCIe compatibility (GPU and motherboard)",
            "power supply compatibility (GPU/CPU and PSU)",
            "memory compatibility (RAM with motherboard or CPU)",
            "form factor compatibility (case and motherboard)",
            "thermal compatibility (cooler and CPU)",
        ]
        return "I can check compatibility for: " + ", ".join(types_list) + "."


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
    if not products:
        return ComparisonTable(headers=["Attribute"], rows=[])

    # Build headers
    headers = ["Attribute"] + [p.get("name", "Unknown") for p in products]

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

