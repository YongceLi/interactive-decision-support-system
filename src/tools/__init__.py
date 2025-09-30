"""
Tool registry and base classes for Interactive Decision Support System.

This module provides the foundation for integrating external APIs and tools
into the IDSS execution engine.
"""

from .base import BaseTool, ToolResult
from .registry import ToolRegistry
from .vin_decode import VinDecodeTool
from .vehicle_listings import VehicleListingsTool
from .vehicle_photos import VehiclePhotosTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "VinDecodeTool",
    "VehicleListingsTool",
    "VehiclePhotosTool"
]