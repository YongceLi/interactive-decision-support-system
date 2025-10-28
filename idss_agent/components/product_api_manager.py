"""
Product API Manager - Handles product-agnostic API selection and routing.

This module provides a unified interface for different product types (vehicles, electronics, PCs)
and routes API calls to the appropriate endpoints based on the product type.
"""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from langchain_core.tools import tool
from idss_agent.components.autodev_apis import search_vehicle_listings, get_vehicle_photos_by_vin
from idss_agent.logger import get_logger

logger = get_logger("components.product_api_manager")


class ProductType(Enum):
    """Supported product types."""
    VEHICLES = "vehicles"
    ELECTRONICS = "electronics"
    PCS = "pcs"


class ProductAPIManager:
    """Manages product-agnostic API access."""
    
    def __init__(self):
        self.product_type = ProductType.VEHICLES  # Default to vehicles
        self._api_handlers = {
            ProductType.VEHICLES: self._get_vehicle_api_handler,
            # Will add electronics and PCs later
        }
    
    def set_product_type(self, product_type: str):
        """Set the current product type based on user intent."""
        try:
            self.product_type = ProductType(product_type.lower())
            logger.info(f"Product type set to: {self.product_type.value}")
        except ValueError:
            logger.warning(f"Unknown product type: {product_type}, defaulting to vehicles")
            self.product_type = ProductType.VEHICLES
    
    def detect_product_type(self, user_query: str) -> ProductType:
        """Detect product type from user query."""
        query_lower = user_query.lower()
        
        # Vehicle keywords
        vehicle_keywords = [
            'car', 'vehicle', 'automobile', 'truck', 'suv', 'sedan', 'coupe',
            'hatchback', 'convertible', 'van', 'minivan', 'vin', 'mileage',
            'drivetrain', 'engine', 'transmission', 'dealer', 'listing'
        ]
        
        # PC keywords (will be expanded when PC API is added)
        pc_keywords = [
            'pc', 'computer', 'laptop', 'desktop', 'cpu', 'gpu', 'ram',
            'hard drive', 'ssd', 'motherboard', 'gaming pc', 'workstation'
        ]
        
        # Electronics keywords (will be expanded when electronics API is added)
        electronics_keywords = [
            'phone', 'smartphone', 'tablet', 'tv', 'television', 'headphones',
            'speaker', 'camera', 'electronics'
        ]
        
        # Count matches
        vehicle_matches = sum(1 for keyword in vehicle_keywords if keyword in query_lower)
        pc_matches = sum(1 for keyword in pc_keywords if keyword in query_lower)
        electronics_matches = sum(1 for keyword in electronics_keywords if keyword in query_lower)
        
        # Log detection results
        logger.info(f"[Product Detection] Vehicle matches: {vehicle_matches}, PC matches: {pc_matches}, Electronics matches: {electronics_matches}")
        
        # Return the type with most matches, default to vehicles
        if pc_matches > vehicle_matches and pc_matches > electronics_matches:
            product_type = ProductType.PCS
        elif electronics_matches > vehicle_matches and electronics_matches > pc_matches:
            product_type = ProductType.ELECTRONICS
        else:
            product_type = ProductType.VEHICLES
        
        logger.info(f"[Product Detection] Selected product type: {product_type.value}")
        return product_type
    
    def _get_vehicle_api_handler(self):
        """Get API handler for vehicles."""
        return {
            'search_listings': search_vehicle_listings,
            'get_photos': get_vehicle_photos_by_vin,
        }
    
    def get_api_handler(self, api_name: str):
        """Get a specific API handler for the current product type."""
        handler = self._api_handlers.get(self.product_type)
        if not handler:
            logger.error(f"No API handler found for product type: {self.product_type}")
            return None
        
        handlers = handler()
        return handlers.get(api_name)
    
    def get_all_tools(self) -> List:
        """Get all tools for the current product type via MCP."""
        tools = []
        
        logger.info(f"[Product API Manager] Getting tools for product type: {self.product_type.value}")
        
        if self.product_type == ProductType.VEHICLES:
            from idss_agent.components.mcp_tools import search_vehicles_mcp
            from idss_agent.components.autodev_apis import (
                get_vehicle_listing_by_vin,
                get_vehicle_photos_by_vin
            )
            tools = [
                search_vehicles_mcp,  # Use MCP tool
                get_vehicle_listing_by_vin,
                get_vehicle_photos_by_vin
            ]
            logger.info(f"[Product API Manager] Returning {len(tools)} vehicle tools (including MCP tool)")
        elif self.product_type == ProductType.PCS:
            from idss_agent.components.mcp_tools import search_pcs_mcp
            tools = [search_pcs_mcp]
            logger.info(f"[Product API Manager] Returning {len(tools)} PC tools")
        elif self.product_type == ProductType.ELECTRONICS:
            from idss_agent.components.mcp_tools import search_electronics_mcp
            tools = [search_electronics_mcp]
            logger.info(f"[Product API Manager] Returning {len(tools)} electronics tools")
        
        return tools


# Global instance
_api_manager = ProductAPIManager()


def get_product_api_manager() -> ProductAPIManager:
    """Get the global product API manager instance."""
    return _api_manager


def detect_and_set_product_type(user_query: str) -> ProductType:
    """Detect product type from query and set it in the manager."""
    product_type = _api_manager.detect_product_type(user_query)
    _api_manager.set_product_type(product_type.value)
    return product_type


def get_tools_for_product_type(product_type: Optional[str] = None) -> List:
    """Get tools for a specific product type."""
    if product_type:
        _api_manager.set_product_type(product_type)
    return _api_manager.get_all_tools()

