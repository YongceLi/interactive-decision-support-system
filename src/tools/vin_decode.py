"""
VIN Decode tool for Auto.dev API.
"""

from typing import Dict, Any
from .base import BaseTool, ToolResult
from .autodev_client import AutoDevClient


class VinDecodeTool(BaseTool):
    """Tool for decoding Vehicle Identification Numbers using Auto.dev API."""

    def __init__(self):
        super().__init__("vin_decode")
        self.client = AutoDevClient()

    def execute(self, vin: str, **kwargs) -> ToolResult:
        """
        Decode a VIN to get vehicle specifications.

        Args:
            vin: Vehicle Identification Number (17 characters)

        Returns:
            ToolResult with decoded vehicle information
        """
        if not vin or len(vin) != 17:
            return ToolResult(
                success=False,
                error="VIN must be exactly 17 characters",
                tool_name=self.name
            )

        try:
            # Call Auto.dev VIN decode API
            response_data = self.client.get(f"/api/vin/{vin}")

            # Extract relevant vehicle information
            vehicle_data = {
                "vin": vin,
                "make": response_data.get("make"),
                "model": response_data.get("model"),
                "year": response_data.get("year"),
                "body_style": response_data.get("body_style"),
                "engine": response_data.get("engine"),
                "transmission": response_data.get("transmission"),
                "drivetrain": response_data.get("drivetrain"),
                "fuel_type": response_data.get("fuel_type"),
                "trim": response_data.get("trim"),
                "series": response_data.get("series"),
                "plant": response_data.get("plant"),
                "raw_response": response_data  # Keep full response for debugging
            }

            return ToolResult(
                success=True,
                data=vehicle_data,
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to decode VIN: {str(e)}",
                tool_name=self.name
            )

    def get_description(self) -> str:
        """Get description of the VIN decode tool."""
        return "Decode a Vehicle Identification Number (VIN) to get detailed vehicle specifications including make, model, year, engine, and other technical details."

    def get_required_params(self) -> list[str]:
        """Get required parameters for VIN decode."""
        return ["vin"]

    def get_optional_params(self) -> list[str]:
        """Get optional parameters for VIN decode."""
        return []