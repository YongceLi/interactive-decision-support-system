"""
MCP Server for product-agnostic API access.

This server exposes tools for searching different product types (vehicles, PCs, electronics)
following the Model Context Protocol specification.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field
import requests


# Request/Response models
class SearchVehiclesRequest(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[str] = "2022-2026"
    price: Optional[str] = None
    state: Optional[str] = None
    miles: Optional[str] = "0-50000"
    page: int = 1
    limit: int = 20


class SearchPCsRequest(BaseModel):
    cpu: Optional[str] = None
    gpu: Optional[str] = None
    ram: Optional[str] = None
    storage: Optional[str] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    page: int = 1
    limit: int = 20


# Initialize MCP server
server = Server("product-search-mcp")


def _get_autodev_api_key() -> str:
    """Get AutoDev API key from environment."""
    api_key = os.getenv("AUTODEV_API_KEY")
    if not api_key:
        raise ValueError("AUTODEV_API_KEY not found in environment variables")
    return api_key


async def search_vehicles(
    make: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[str] = "2022-2026",
    price: Optional[str] = None,
    state: Optional[str] = None,
    miles: Optional[str] = "0-50000",
    page: int = 1,
    limit: int = 20
) -> str:
    """Search for vehicle listings using AutoDev API."""
    try:
        api_key = _get_autodev_api_key()
        url = "https://api.auto.dev/listings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        params = {}
        if make:
            params["vehicle.make"] = make
        if model:
            params["vehicle.model"] = model
        if year:
            params["vehicle.year"] = year
        if price:
            params["retailListing.price"] = price
        if state:
            params["retailListing.state"] = state
        if miles:
            params["retailListing.miles"] = miles
        params["page"] = page
        params["limit"] = limit
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)})


async def search_pcs(
    cpu: Optional[str] = None,
    gpu: Optional[str] = None,
    ram: Optional[str] = None,
    storage: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    page: int = 1,
    limit: int = 20
) -> str:
    """Search for PC listings (placeholder for future PC API integration)."""
    # TODO: Implement PC API when available
    return json.dumps({
        "error": "PC API not yet implemented. Please provide the PC API endpoint."
    })


async def search_electronics(
    category: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    title: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> str:
    """Search for electronics products using Platzi Fake Store API."""
    try:
        base_url = "https://api.escuelajs.co/api/v1"
        url = f"{base_url}/products"
        
        params = {
            "limit": limit,
            "offset": offset
        }
        
        if category:
            params["categoryId"] = category
        if price_min is not None:
            params["price_min"] = price_min
        if price_max is not None:
            params["price_max"] = price_max
        if title:
            params["title"] = title
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return json.dumps({"error": str(e)})


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="search_vehicles",
            description="Search for vehicle listings with comprehensive filtering options",
            inputSchema={
                "type": "object",
                "properties": {
                    "make": {"type": "string", "description": "Vehicle manufacturer (e.g., 'Toyota', 'Ford')"},
                    "model": {"type": "string", "description": "Vehicle model (e.g., 'Camry', 'F-150')"},
                    "year": {"type": "string", "description": "Vehicle year or range (e.g., '2022-2026')"},
                    "price": {"type": "string", "description": "Price range (e.g., '10000-30000')"},
                    "state": {"type": "string", "description": "State code (e.g., 'CA', 'NY')"},
                    "miles": {"type": "string", "description": "Mileage range (e.g., '0-50000')"},
                    "page": {"type": "integer", "description": "Page number (default: 1)"},
                    "limit": {"type": "integer", "description": "Results per page (default: 20)"}
                }
            }
        ),
        Tool(
            name="search_pcs",
            description="Search for PC listings (currently placeholder - needs PC API)",
            inputSchema={
                "type": "object",
                "properties": {
                    "cpu": {"type": "string", "description": "CPU specification"},
                    "gpu": {"type": "string", "description": "GPU specification"},
                    "ram": {"type": "string", "description": "RAM specification"},
                    "storage": {"type": "string", "description": "Storage specification"},
                    "price_min": {"type": "integer", "description": "Minimum price"},
                    "price_max": {"type": "integer", "description": "Maximum price"},
                    "page": {"type": "integer", "description": "Page number (default: 1)"},
                    "limit": {"type": "integer", "description": "Results per page (default: 20)"}
                }
            }
        ),
        Tool(
            name="search_electronics",
            description="Search for electronics products using Platzi Fake Store API",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Product category"},
                    "price_min": {"type": "number", "description": "Minimum price"},
                    "price_max": {"type": "number", "description": "Maximum price"},
                    "title": {"type": "string", "description": "Search by product title/keywords"},
                    "limit": {"type": "integer", "description": "Results per page (default: 20)"},
                    "offset": {"type": "integer", "description": "Pagination offset (default: 0)"}
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    if name == "search_vehicles":
        result = await search_vehicles(**arguments)
        return [TextContent(type="text", text=result)]
    
    elif name == "search_pcs":
        result = await search_pcs(**arguments)
        return [TextContent(type="text", text=result)]
    
    elif name == "search_electronics":
        result = await search_electronics(**arguments)
        return [TextContent(type="text", text=result)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

