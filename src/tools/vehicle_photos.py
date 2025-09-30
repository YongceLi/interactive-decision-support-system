"""
Vehicle Photos tool for Auto.dev API.
"""

from typing import Dict, Any
from .base import BaseTool, ToolResult
from .autodev_client import AutoDevClient


class VehiclePhotosTool(BaseTool):
    """Tool for retrieving vehicle photos using Auto.dev API."""

    def __init__(self):
        super().__init__("get_vehicle_photos")
        self.client = AutoDevClient()

    def execute(self, vin: str, **kwargs) -> ToolResult:
        """
        Get photos for a specific vehicle by VIN.

        Args:
            vin: Vehicle Identification Number (17 characters)
            **kwargs: Optional parameters:
                - angle: Specific angle/view ("front", "rear", "side", "interior")
                - limit: Maximum number of photos to return
                - resolution: Image resolution preference ("thumbnail", "medium", "high")

        Returns:
            ToolResult with vehicle photo URLs and metadata
        """
        if not vin or len(vin) != 17:
            return ToolResult(
                success=False,
                error="VIN must be exactly 17 characters",
                tool_name=self.name
            )

        try:
            # Build query parameters
            params = {"vin": vin}

            # Optional parameters
            if "angle" in kwargs and kwargs["angle"]:
                params["angle"] = kwargs["angle"]
            if "limit" in kwargs and kwargs["limit"]:
                params["limit"] = kwargs["limit"]
            if "resolution" in kwargs and kwargs["resolution"]:
                params["resolution"] = kwargs["resolution"]

            # Call Auto.dev vehicle photos API
            response_data = self.client.get(f"/api/photos/{vin}", params=params)

            # Extract and format photo information
            photos = response_data.get("photos", [])
            formatted_photos = []

            for photo in photos:
                formatted_photo = {
                    "url": photo.get("url"),
                    "thumbnail_url": photo.get("thumbnail_url"),
                    "angle": photo.get("angle"),
                    "resolution": photo.get("resolution"),
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "file_size": photo.get("file_size"),
                    "format": photo.get("format"),
                    "caption": photo.get("caption"),
                    "sequence": photo.get("sequence")
                }
                formatted_photos.append(formatted_photo)

            result_data = {
                "vin": vin,
                "photos": formatted_photos,
                "total_count": response_data.get("total_count", len(formatted_photos)),
                "vehicle_info": response_data.get("vehicle_info", {}),
                "search_params": params,
                "raw_response": response_data  # Keep full response for debugging
            }

            return ToolResult(
                success=True,
                data=result_data,
                tool_name=self.name
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to get vehicle photos: {str(e)}",
                tool_name=self.name
            )

    def get_description(self) -> str:
        """Get description of the vehicle photos tool."""
        return "Retrieve photos and images for a specific vehicle using its VIN. Can filter by angle/view, resolution, and limit the number of results."

    def get_required_params(self) -> list[str]:
        """Get required parameters for vehicle photos."""
        return ["vin"]

    def get_optional_params(self) -> list[str]:
        """Get optional parameters for vehicle photos."""
        return ["angle", "limit", "resolution"]