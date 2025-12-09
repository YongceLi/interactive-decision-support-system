"""
PC Build Tools - Tools for building complete PC configurations using knowledge graph compatibility.

This module provides tools to:
- Find compatible PC parts using the knowledge graph
- Build complete PC configurations within budget constraints
- Reason about prices and deals
- Generate alternative part options
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from idss_agent.tools.kg_compatibility import get_compatibility_tool
from idss_agent.tools.local_electronics_store import LocalElectronicsStore
from idss_agent.utils.logger import get_logger

logger = get_logger("tools.pc_build")

# Required PC parts for a complete build
REQUIRED_PC_PARTS = {
    "cpu": "CPU",
    "motherboard": "Motherboard",
    "ram": "RAM",
    "storage": "Storage",
    "psu": "Power Supply",
    "case": "Case",
}

# Optional parts
OPTIONAL_PC_PARTS = {
    "gpu": "GPU (Graphics Card)",
    "cooler": "CPU Cooler",
}

# Part selection order (build dependencies)
PART_SELECTION_ORDER = [
    "cpu",      # Start with CPU (determines socket)
    "motherboard",  # Then motherboard (must match CPU socket)
    "ram",      # RAM (must match motherboard)
    "storage",  # Storage (less constrained)
    "psu",      # PSU (must power everything)
    "gpu",      # GPU (optional, but needs PSU power)
    "case",     # Case (must fit motherboard form factor)
    "cooler",   # Cooler (optional, must match CPU socket)
]


class PCBuildTool:
    """Tool for building complete PC configurations."""

    def __init__(self):
        """Initialize PC build tool with compatibility and store tools."""
        self.compatibility_tool = get_compatibility_tool()
        self.store = LocalElectronicsStore()
        logger.info("PC Build Tool initialized")

    def find_compatible_parts_for_build(
        self,
        selected_parts: Dict[str, Dict[str, Any]],
        target_part_type: str,
        budget_remaining: Optional[float] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find compatible parts for a PC build given already selected parts.

        Args:
            selected_parts: Dict mapping part_type -> product dict (with slug)
            target_part_type: Part type to find (e.g., "motherboard", "ram")
            budget_remaining: Remaining budget for this part (optional)
            limit: Maximum number of results

        Returns:
            List of compatible products ordered by price
        """
        if not self.compatibility_tool.is_available():
            logger.warning("Compatibility tool not available, falling back to store search")
            return self._fallback_search(target_part_type, budget_remaining, limit)

        compatible_products = []
        
        # Determine compatibility constraints based on selected parts
        if target_part_type == "motherboard" and "cpu" in selected_parts:
            # Find motherboards compatible with selected CPU
            cpu_slug = selected_parts["cpu"].get("slug")
            if cpu_slug:
                compatible_products = self.compatibility_tool.find_compatible_parts(
                    source_slug=cpu_slug,
                    target_type="motherboard",
                    compatibility_type="SOCKET_COMPATIBLE_WITH",
                    limit=limit * 2  # Get more for filtering
                )
        
        elif target_part_type == "ram" and "motherboard" in selected_parts:
            # Find RAM compatible with selected motherboard
            mb_slug = selected_parts["motherboard"].get("slug")
            if mb_slug:
                compatible_products = self.compatibility_tool.find_compatible_parts(
                    source_slug=mb_slug,
                    target_type="ram",
                    compatibility_type="RAM_COMPATIBLE_WITH",
                    limit=limit * 2
                )
        
        elif target_part_type == "psu":
            # PSU needs to power CPU and GPU
            required_watts = self._calculate_required_psu_watts(selected_parts)
            if required_watts:
                # Search for PSUs with sufficient wattage
                compatible_products = self.store.search_products(
                    part_type="psu",
                    min_price=None,
                    max_price=budget_remaining,
                    limit=limit * 2
                )
                # Filter by wattage requirement
                compatible_products = [
                    p for p in compatible_products
                    if self._psu_meets_requirement(p, required_watts)
                ]
        
        elif target_part_type == "case" and "motherboard" in selected_parts:
            # Find cases compatible with motherboard form factor
            mb_slug = selected_parts["motherboard"].get("slug")
            if mb_slug:
                compatible_products = self.compatibility_tool.find_compatible_parts(
                    source_slug=mb_slug,
                    target_type="case",
                    compatibility_type="FORM_FACTOR_COMPATIBLE_WITH",
                    limit=limit * 2
                )
        
        elif target_part_type == "gpu" and "psu" in selected_parts:
            # Find GPUs compatible with selected PSU
            psu_slug = selected_parts["psu"].get("slug")
            if psu_slug:
                compatible_products = self.compatibility_tool.find_compatible_parts(
                    source_slug=psu_slug,
                    target_type="gpu",
                    compatibility_type="ELECTRICAL_COMPATIBLE_WITH",
                    limit=limit * 2
                )
        
        elif target_part_type == "cooler" and "cpu" in selected_parts:
            # Find coolers compatible with selected CPU
            cpu_slug = selected_parts["cpu"].get("slug")
            if cpu_slug:
                compatible_products = self.compatibility_tool.find_compatible_parts(
                    source_slug=cpu_slug,
                    target_type="cooler",
                    compatibility_type="THERMAL_COMPATIBLE_WITH",
                    limit=limit * 2
                )
        
        else:
            # Fallback to store search for unconstrained parts
            compatible_products = self._fallback_search(target_part_type, budget_remaining, limit)

        # Filter by budget if specified
        if budget_remaining:
            compatible_products = [
                p for p in compatible_products
                if self._get_price(p) <= budget_remaining
            ]

        # Sort by price (ascending)
        compatible_products.sort(key=lambda p: self._get_price(p) or float('inf'))
        
        return compatible_products[:limit]

    def search_products_by_type(
        self,
        part_type: str,
        max_price: Optional[float] = None,
        min_price: Optional[float] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for products of a specific type, optionally filtered by price.
        
        This is a helper method for agents to query the knowledge graph and store
        to find products. The agent should use this iteratively to build configurations.

        Args:
            part_type: Part type (e.g., "cpu", "gpu", "ram", "motherboard", "psu", "storage", "case", "cooler")
            max_price: Maximum price filter
            min_price: Minimum price filter
            limit: Maximum number of results

        Returns:
            List of products with price and compatibility information
        """
        # First try knowledge graph if available
        if self.compatibility_tool.is_available():
            # Query KG for products of this type
            try:
                with self.compatibility_tool.driver.session() as session:
                    query = """
                        MATCH (p:PCProduct)
                        WHERE p.product_type = $part_type
                    """
                    params = {"part_type": part_type}
                    
                    if max_price:
                        query += " AND (p.price_avg IS NULL OR p.price_avg <= $max_price)"
                        params["max_price"] = max_price
                    if min_price:
                        query += " AND (p.price_avg IS NULL OR p.price_avg >= $min_price)"
                        params["min_price"] = min_price
                    
                    query += """
                        RETURN p
                        ORDER BY COALESCE(p.price_avg, p.price_min, 999999) ASC
                        LIMIT $limit
                    """
                    params["limit"] = limit
                    
                    result = session.run(query, **params)
                    products = [dict(record["p"]) for record in result]
                    
                    if products:
                        logger.info(f"[PC Build] Found {len(products)} {part_type} products from KG")
                        return products
            except Exception as e:
                logger.warning(f"[PC Build] Error querying KG for {part_type}: {e}, falling back to store")
        
        # Fallback to store search
        return self.store.search_products(
            part_type=part_type,
            min_price=min_price,
            max_price=max_price,
            limit=limit
        )
    
    def build_pc_configuration(
        self,
        budget: float,
        use_case: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        DEPRECATED: This method uses hardcoded logic. 
        
        Agents should instead use:
        - search_products_by_type() to find initial parts
        - find_compatible_parts_for_build() to find compatible parts iteratively
        - Build the configuration through multiple tool calls
        
        This method is kept for backward compatibility but should not be used.
        It will log a warning and return an error message.
        """
        logger.warning("[PC Build] build_pc_configuration called with hardcoded logic. "
                      "Agents should use search_products_by_type() and find_compatible_parts_for_build() "
                      "iteratively instead.")
        
        return {
            "error": "Hardcoded build logic deprecated",
            "message": "Please use search_products_by_type() and find_compatible_parts_for_build() tools iteratively to build configurations through the knowledge graph.",
            "parts": {},
            "total_price": 0,
            "budget_remaining": budget,
            "alternatives": {},
            "reasoning": ["This method is deprecated. Use iterative tool calls instead."],
            "complete": False
        }

    def get_alternative_parts(
        self,
        current_build: Dict[str, Dict[str, Any]],
        part_type_to_replace: str,
        budget_adjustment: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get alternative parts for a specific part type in a build.

        Args:
            current_build: Current build parts dict
            part_type_to_replace: Part type to find alternatives for
            budget_adjustment: Additional budget for this part (can be negative)

        Returns:
            List of alternative products
        """
        # Remove the part we're replacing
        build_without_part = {
            k: v for k, v in current_build.items()
            if k != part_type_to_replace
        }
        
        # Get current part price
        current_price = self._get_price(current_build.get(part_type_to_replace, {}))
        budget_for_alternatives = current_price + (budget_adjustment or 0)
        
        return self.find_compatible_parts_for_build(
            selected_parts=build_without_part,
            target_part_type=part_type_to_replace,
            budget_remaining=budget_for_alternatives if budget_for_alternatives > 0 else None,
            limit=10
        )

    def _calculate_required_psu_watts(self, selected_parts: Dict[str, Dict[str, Any]]) -> Optional[float]:
        """Calculate required PSU wattage based on selected parts."""
        total_watts = 0
        
        # CPU power
        if "cpu" in selected_parts:
            cpu = selected_parts["cpu"]
            tdp = cpu.get("tdp_watts") or cpu.get("wattage")
            if tdp:
                try:
                    total_watts += float(str(tdp).replace("W", "").strip())
                except (ValueError, AttributeError):
                    pass
        
        # GPU power
        if "gpu" in selected_parts:
            gpu = selected_parts["gpu"]
            gpu_watts = gpu.get("recommended_psu_watts") or gpu.get("tdp_watts") or gpu.get("wattage")
            if gpu_watts:
                try:
                    total_watts += float(str(gpu_watts).replace("W", "").strip())
                except (ValueError, AttributeError):
                    pass
        
        # Add overhead (50W for motherboard, RAM, storage, etc.)
        total_watts += 50
        
        # Add 20% margin for efficiency and headroom
        if total_watts > 0:
            return total_watts * 1.2
        
        return None

    def _psu_meets_requirement(self, psu: Dict[str, Any], required_watts: float) -> bool:
        """Check if PSU meets wattage requirement."""
        psu_wattage = psu.get("wattage") or psu.get("wattage_max")
        if not psu_wattage:
            return False
        
        try:
            psu_watts = float(str(psu_wattage).replace("W", "").strip())
            return psu_watts >= required_watts
        except (ValueError, AttributeError):
            return False

    def _allocate_budget(self, budget: float, use_case: Optional[str] = None) -> Dict[str, float]:
        """Allocate budget across PC parts based on use case."""
        if use_case and "gaming" in use_case.lower():
            # Gaming builds prioritize GPU
            return {
                "cpu": budget * 0.20,
                "motherboard": budget * 0.15,
                "gpu": budget * 0.35,
                "ram": budget * 0.10,
                "storage": budget * 0.10,
                "psu": budget * 0.05,
                "case": budget * 0.03,
                "cooler": budget * 0.02,
            }
        elif use_case and "workstation" in use_case.lower():
            # Workstation builds prioritize CPU and RAM
            return {
                "cpu": budget * 0.30,
                "motherboard": budget * 0.15,
                "gpu": budget * 0.15,
                "ram": budget * 0.20,
                "storage": budget * 0.10,
                "psu": budget * 0.05,
                "case": budget * 0.03,
                "cooler": budget * 0.02,
            }
        elif use_case and "budget" in use_case.lower():
            # Budget builds minimize costs
            return {
                "cpu": budget * 0.25,
                "motherboard": budget * 0.15,
                "gpu": budget * 0.20,
                "ram": budget * 0.12,
                "storage": budget * 0.15,
                "psu": budget * 0.08,
                "case": budget * 0.03,
                "cooler": budget * 0.02,
            }
        else:
            # Balanced allocation
            return {
                "cpu": budget * 0.25,
                "motherboard": budget * 0.15,
                "gpu": budget * 0.25,
                "ram": budget * 0.10,
                "storage": budget * 0.10,
                "psu": budget * 0.08,
                "case": budget * 0.04,
                "cooler": budget * 0.03,
            }

    def _select_best_part(
        self,
        compatible_parts: List[Dict[str, Any]],
        part_type: str,
        use_case: Optional[str],
        budget_remaining: float
    ) -> Optional[Dict[str, Any]]:
        """Select the best part from compatible options."""
        if not compatible_parts:
            return None
        
        # For now, select by price (cheapest that fits budget)
        # Could be enhanced with quality metrics, ratings, etc.
        affordable = [
            p for p in compatible_parts
            if self._get_price(p) <= budget_remaining
        ]
        
        if affordable:
            # Return cheapest affordable option
            return min(affordable, key=lambda p: self._get_price(p) or float('inf'))
        else:
            # Return cheapest overall if nothing fits budget
            return min(compatible_parts, key=lambda p: self._get_price(p) or float('inf'))

    def _get_price(self, product: Dict[str, Any]) -> float:
        """Extract price from product dict."""
        price = (
            product.get("price_avg") or
            product.get("price_min") or
            product.get("price") or
            product.get("sale_price") or
            0.0
        )
        price_float = float(price) if price else 0.0
        
        # Log warning if price is missing or suspiciously low
        if price_float == 0.0:
            product_name = product.get("name") or product.get("title", "Unknown")
            logger.warning(f"[PC Build] Product '{product_name}' has no price data (price_avg={product.get('price_avg')}, price_min={product.get('price_min')}, price={product.get('price')})")
        elif price_float < 1.0:  # Suspiciously low price
            product_name = product.get("name") or product.get("title", "Unknown")
            logger.warning(f"[PC Build] Product '{product_name}' has suspiciously low price: ${price_float:.2f}")
        
        return price_float

    def _fallback_search(
        self,
        part_type: str,
        budget_remaining: Optional[float],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback to store search when compatibility tool unavailable."""
        return self.store.search_products(
            part_type=part_type,
            max_price=budget_remaining,
            limit=limit
        )


# Global instance
_pc_build_tool: Optional[PCBuildTool] = None


def get_pc_build_tool() -> PCBuildTool:
    """Get or create the global PC build tool instance."""
    global _pc_build_tool
    if _pc_build_tool is None:
        _pc_build_tool = PCBuildTool()
    return _pc_build_tool

