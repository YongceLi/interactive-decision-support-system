"""
MCP-based tools for the agent to use.

These tools wrap MCP server calls and can be used by the agent
as regular LangChain tools.
"""

import json
import os
from typing import Optional, Dict, Any
from langchain_core.tools import tool
from idss_agent.logger import get_logger

logger = get_logger("components.mcp_tools")


def _call_mcp_server_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Call appropriate API directly based on tool name."""
    try:
        logger.info(f"[API] Calling tool: {tool_name} with arguments: {arguments}")
        
        # Direct API calls - no MCP server needed for internal agent use
        if tool_name == "search_vehicles":
            from idss_agent.components.autodev_apis import search_vehicle_listings
            result = search_vehicle_listings.invoke(arguments)
            logger.info(f"[API] Tool {tool_name} completed successfully")
            return result
        elif tool_name == "search_pcs":
            logger.info("[API] PC API not yet implemented")
            return json.dumps({"error": "PC API not yet implemented"})
        elif tool_name == "search_electronics":
            from idss_agent.components.electronics_apis import search_electronics_listings
            result = search_electronics_listings.invoke(arguments)
            logger.info(f"[API] Tool {tool_name} completed successfully")
            return result
        else:
            logger.error(f"[API] Unknown tool: {tool_name}")
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
            
    except Exception as e:
        logger.error(f"[API] Error calling tool {tool_name}: {e}")
        return json.dumps({"error": str(e)})


@tool
def search_vehicles_mcp(
    vehicle_make: Optional[str] = None,
    vehicle_model: Optional[str] = None,
    vehicle_year: Optional[str] = "2022-2026",
    vehicle_body_style: Optional[str] = None,
    vehicle_engine: Optional[str] = None,
    vehicle_transmission: Optional[str] = None,
    vehicle_exterior_color: Optional[str] = None,
    vehicle_interior_color: Optional[str] = None,
    vehicle_doors: Optional[int] = 4,
    retail_price: Optional[str] = None,
    retail_state: Optional[str] = None,
    retail_miles: Optional[str] = "0-50000",
    zip: Optional[str] = None,
    distance: Optional[int] = None,
    page: Optional[int] = 1,
    limit: Optional[int] = 20,
) -> str:
    """Search for vehicle listings using the MCP server.
    
    This tool connects to the MCP server to search for vehicles,
    enabling product-agnostic API access.
    
    Args:
        vehicle_make: Vehicle manufacturer (e.g., "Toyota", "Ford")
        vehicle_model: Vehicle model (e.g., "Camry", "F-150")
        vehicle_year: Vehicle year or range (e.g., "2022-2026")
        vehicle_body_style: Body style (e.g., "sedan", "suv")
        vehicle_engine: Engine size (e.g., "2.0L")
        vehicle_transmission: Transmission type (e.g., "automatic")
        vehicle_exterior_color: Exterior color (e.g., "white")
        vehicle_interior_color: Interior color (e.g., "black")
        vehicle_doors: Number of doors (2, 4, 5)
        retail_price: Price range (e.g., "10000-30000")
        retail_state: State code (e.g., "CA", "NY")
        retail_miles: Mileage range (e.g., "0-50000")
        zip: 5-digit ZIP code
        distance: Radius in miles from ZIP code
        page: Page number (default: 1)
        limit: Results per page (default: 20)
    
    Returns:
        JSON string containing vehicle listings
    """
    try:
        # Prepare arguments for MCP server
        arguments = {
            "make": vehicle_make,
            "model": vehicle_model,
            "year": vehicle_year,
            "price": retail_price,
            "state": retail_state,
            "miles": retail_miles,
            "page": page,
            "limit": limit
        }
        
        # Remove None values
        arguments = {k: v for k, v in arguments.items() if v is not None}
        
        # Call MCP server
        result = _call_mcp_server_tool("search_vehicles", arguments)
        return result
        
    except Exception as e:
        logger.error(f"Error in search_vehicles_mcp: {e}")
        return json.dumps({"error": str(e)})


@tool
def search_pcs_mcp(
    cpu: Optional[str] = None,
    gpu: Optional[str] = None,
    ram: Optional[str] = None,
    storage: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    page: Optional[int] = 1,
    limit: Optional[int] = 20,
) -> str:
    """Search for PC listings using the MCP server.
    
    This tool connects to the MCP server to search for PCs.
    Currently a placeholder until PC API is implemented.
    
    Args:
        cpu: CPU specification
        gpu: GPU specification
        ram: RAM specification
        storage: Storage specification
        price_min: Minimum price
        price_max: Maximum price
        page: Page number (default: 1)
        limit: Results per page (default: 20)
    
    Returns:
        JSON string containing PC listings
    """
    try:
        arguments = {
            "cpu": cpu,
            "gpu": gpu,
            "ram": ram,
            "storage": storage,
            "price_min": price_min,
            "price_max": price_max,
            "page": page,
            "limit": limit
        }
        
        # Remove None values
        arguments = {k: v for k, v in arguments.items() if v is not None}
        
        # Call MCP server
        result = _call_mcp_server_tool("search_pcs", arguments)
        return result
        
    except Exception as e:
        logger.error(f"Error in search_pcs_mcp: {e}")
        return json.dumps({"error": str(e)})


@tool
def search_electronics_mcp(
    category: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    title: Optional[str] = None,
    limit: Optional[int] = 20,
    offset: Optional[int] = 0,
) -> str:
    """Search for electronics products using the MCP server.
    
    This tool connects to the MCP server to search for electronics
    using the Platzi Fake Store API.
    
    Args:
        category: Product category
        price_min: Minimum price
        price_max: Maximum price
        title: Search by product title/keywords
        limit: Results per page (default: 20)
        offset: Pagination offset (default: 0)
    
    Returns:
        JSON string containing electronics listings
    """
    try:
        arguments = {
            "category": category,
            "price_min": price_min,
            "price_max": price_max,
            "title": title,
            "limit": limit,
            "offset": offset
        }
        
        # Remove None values
        arguments = {k: v for k, v in arguments.items() if v is not None}
        
        # Call MCP server
        result = _call_mcp_server_tool("search_electronics", arguments)
        return result
        
    except Exception as e:
        logger.error(f"Error in search_electronics_mcp: {e}")
        return json.dumps({"error": str(e)})

