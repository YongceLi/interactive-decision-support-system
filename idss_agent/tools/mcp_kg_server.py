"""
MCP Server Wrapper for Knowledge Graph Compatibility Queries.

This module wraps domain-specific knowledge graph queries in an MCP (Model Context Protocol) server,
allowing LLM agents to query PC part compatibility without domain-specific code.

The MCP server exposes:
- check_compatibility: Check if two parts are compatible
- find_compatible_parts: Find compatible parts for a given product
- build_pc_configuration: Build complete PC configurations
"""
import os
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from idss_agent.tools.kg_compatibility import get_compatibility_tool, PART_COMPATIBILITY_MAP
from idss_agent.tools.pc_build import get_pc_build_tool
from idss_agent.utils.logger import get_logger

logger = get_logger("tools.mcp_kg_server")


class MCPKGServer:
    """
    MCP Server wrapper for Knowledge Graph compatibility queries.
    
    This server exposes domain-specific PC part compatibility knowledge
    through a standardized interface, allowing LLM agents to query
    compatibility without embedding domain logic.
    """
    
    def __init__(self):
        """Initialize MCP KG server with compatibility and build tools."""
        self.compatibility_tool = get_compatibility_tool()
        self.build_tool = get_pc_build_tool()
        logger.info("MCP KG Server initialized")
    
    def check_compatibility(
        self,
        part1_name: str,
        part2_name: str,
        compatibility_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Check if two PC parts are compatible.
        
        Args:
            part1_name: Name or slug of first product
            part2_name: Name or slug of second product
            compatibility_types: Optional list of compatibility types to check
        
        Returns:
            Dict with compatibility result
        """
        if not self.compatibility_tool.is_available():
            return {
                "compatible": False,
                "error": "Knowledge graph unavailable",
                "message": "The compatibility checking system is temporarily unavailable."
            }
        
        # Find products in KG
        product1 = self.compatibility_tool.find_product_by_name(part1_name)
        product2 = self.compatibility_tool.find_product_by_name(part2_name)
        
        if not product1:
            return {
                "compatible": False,
                "error": "Product not found",
                "message": f"Could not find '{part1_name}' in the knowledge graph."
            }
        
        if not product2:
            return {
                "compatible": False,
                "error": "Product not found",
                "message": f"Could not find '{part2_name}' in the knowledge graph."
            }
        
        # Check compatibility
        result = self.compatibility_tool.check_compatibility(
            product1.get("slug"),
            product2.get("slug"),
            compatibility_types
        )
        
        return result
    
    def find_compatible_parts(
        self,
        source_product_name: str,
        target_part_type: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Find compatible parts for a given product.
        
        Args:
            source_product_name: Name or slug of source product
            target_part_type: Type of part to find (e.g., "gpu", "cpu", "ram")
            limit: Maximum number of results
        
        Returns:
            Dict with list of compatible products
        """
        if not self.compatibility_tool.is_available():
            return {
                "error": "Knowledge graph unavailable",
                "message": "The compatibility checking system is temporarily unavailable.",
                "compatible_parts": []
            }
        
        # Normalize target part type
        target_part_type = target_part_type.lower().strip()
        
        # Find source product
        source_product = self.compatibility_tool.find_product_by_name(source_product_name)
        if not source_product:
            return {
                "error": "Product not found",
                "message": f"Could not find '{source_product_name}' in the knowledge graph.",
                "compatible_parts": []
            }
        
        # Find compatible parts
        compatible_parts = self.compatibility_tool.find_compatible_parts(
            source_product.get("slug"),
            target_part_type,
            limit=limit
        )
        
        return {
            "source_product": source_product.get("name"),
            "source_slug": source_product.get("slug"),
            "target_type": target_part_type,
            "compatible_parts": [
                {
                    "name": part.get("name"),
                    "slug": part.get("slug"),
                    "brand": part.get("brand"),
                    "price_avg": part.get("price_avg"),
                    "price_min": part.get("price_min"),
                    "product_type": part.get("product_type"),
                }
                for part in compatible_parts
            ]
        }
    
    def build_pc_configuration(
        self,
        budget: float,
        use_case: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build a complete PC configuration with compatible parts.
        
        Args:
            budget: Total budget in USD
            use_case: Optional use case (e.g., "gaming", "workstation", "budget")
        
        Returns:
            Dict with complete PC build configuration
        """
        build_result = self.build_tool.build_pc_configuration(
            budget=budget,
            use_case=use_case,
            preferences=None
        )
        
        # Format for MCP response
        parts_formatted = {}
        for part_type, part_data in build_result.get('parts', {}).items():
            parts_formatted[part_type] = {
                "name": part_data.get("name") or part_data.get("title", part_type),
                "slug": part_data.get("slug"),
                "brand": part_data.get("brand"),
                "price_avg": part_data.get("price_avg"),
                "price_min": part_data.get("price_min"),
                "price": part_data.get("price"),
            }
        
        return {
            "budget": budget,
            "use_case": use_case,
            "parts": parts_formatted,
            "total_price": build_result.get('total_price', 0),
            "budget_remaining": build_result.get('budget_remaining', 0),
            "complete": build_result.get('complete', False),
            "reasoning": build_result.get('reasoning', [])
        }
    
    def get_supported_compatibility_types(self) -> Dict[str, List[str]]:
        """
        Get supported compatibility relationship types.
        
        Returns:
            Dict mapping part type pairs to compatibility types
        """
        return {
            str(key): value
            for key, value in PART_COMPATIBILITY_MAP.items()
        }
    
    def is_available(self) -> bool:
        """Check if the MCP server is available."""
        return self.compatibility_tool.is_available()


# Global instance
_mcp_kg_server: Optional[MCPKGServer] = None


def get_mcp_kg_server() -> MCPKGServer:
    """Get or create the global MCP KG server instance."""
    global _mcp_kg_server
    if _mcp_kg_server is None:
        _mcp_kg_server = MCPKGServer()
    return _mcp_kg_server


# MCP Tool Definitions (for LLM agent integration)
MCP_TOOLS = [
    {
        "name": "check_pc_parts_compatibility",
        "description": "Check if two PC parts are compatible using the knowledge graph",
        "parameters": {
            "type": "object",
            "properties": {
                "part1_name": {
                    "type": "string",
                    "description": "Name or slug of first PC part"
                },
                "part2_name": {
                    "type": "string",
                    "description": "Name or slug of second PC part"
                }
            },
            "required": ["part1_name", "part2_name"]
        }
    },
    {
        "name": "find_compatible_pc_parts",
        "description": "Find compatible PC parts for a given product using the knowledge graph",
        "parameters": {
            "type": "object",
            "properties": {
                "source_product_name": {
                    "type": "string",
                    "description": "Name or slug of source product"
                },
                "target_part_type": {
                    "type": "string",
                    "description": "Type of part to find (e.g., 'gpu', 'cpu', 'ram', 'psu', 'motherboard')",
                    "enum": ["cpu", "gpu", "ram", "psu", "motherboard", "case", "cooler", "storage"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10
                }
            },
            "required": ["source_product_name", "target_part_type"]
        }
    },
    {
        "name": "build_pc_configuration",
        "description": "Build a complete PC configuration with compatible parts within a budget",
        "parameters": {
            "type": "object",
            "properties": {
                "budget": {
                    "type": "number",
                    "description": "Total budget in USD"
                },
                "use_case": {
                    "type": "string",
                    "description": "Use case (e.g., 'gaming', 'workstation', 'budget', '1440p gaming')",
                    "default": ""
                }
            },
            "required": ["budget"]
        }
    }
]

