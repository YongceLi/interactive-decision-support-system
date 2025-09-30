"""
Vehicle Listings Search tool for Auto.dev API.
"""

from typing import Dict, Any, Optional
from .base import BaseTool, ToolResult
from .autodev_client import AutoDevClient


class VehicleListingsTool(BaseTool):
    """Tool for searching vehicle listings using Auto.dev API."""

    def __init__(self):
        super().__init__("search_vehicle_listings")
        self.client = AutoDevClient()

    def execute(self, **kwargs) -> ToolResult:
        """
        Search for vehicle listings with various filters.

        Args:
            **kwargs: Search parameters including:
                - make: Vehicle make (e.g., "Toyota", "Honda")
                - model: Vehicle model (e.g., "Camry", "Accord")
                - year_min: Minimum year
                - year_max: Maximum year
                - price_min: Minimum price
                - price_max: Maximum price
                - mileage_max: Maximum mileage
                - zip_code: Location zip code
                - radius: Search radius in miles
                - body_style: Body style (e.g., "sedan", "suv")
                - fuel_type: Fuel type (e.g., "gasoline", "hybrid", "electric")
                - transmission: Transmission type
                - limit: Maximum number of results (default 20)

        Returns:
            ToolResult with list of matching vehicles
        """
        try:
            # Build query parameters
            params = {}

            # Direct mapping parameters
            direct_params = [
                "make", "model", "year_min", "year_max", "price_min", "price_max",
                "mileage_max", "zip_code", "radius", "body_style", "fuel_type",
                "transmission", "limit"
            ]

            for param in direct_params:
                if param in kwargs and kwargs[param] is not None:
                    params[param] = kwargs[param]

            # Set default limit if not provided
            if "limit" not in params:
                params["limit"] = 20

            # Call Auto.dev vehicle listings API
            response_data = self.client.get("/api/listings", params=params)

            # Extract and format vehicle listings
            listings = response_data.get("listings", [])
            formatted_listings = []

            for listing in listings:
                formatted_listing = {
                    "id": listing.get("id"),
                    "vin": listing.get("vin"),
                    "make": listing.get("make"),
                    "model": listing.get("model"),
                    "year": listing.get("year"),
                    "trim": listing.get("trim"),
                    "body_style": listing.get("body_style"),
                    "price": listing.get("price"),
                    "mileage": listing.get("mileage"),
                    "fuel_type": listing.get("fuel_type"),
                    "transmission": listing.get("transmission"),
                    "drivetrain": listing.get("drivetrain"),
                    "exterior_color": listing.get("exterior_color"),
                    "interior_color": listing.get("interior_color"),
                    "dealer": listing.get("dealer"),
                    "location": listing.get("location"),
                    "distance": listing.get("distance"),
                    "stock_number": listing.get("stock_number"),
                    "description": listing.get("description"),
                    "url": listing.get("url"),
                    "images": listing.get("images", [])
                }
                formatted_listings.append(formatted_listing)

            result_data = {
                "listings": formatted_listings,
                "total_count": response_data.get("total_count", len(formatted_listings)),
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
                error=f"Failed to search vehicle listings: {str(e)}",
                tool_name=self.name
            )

    def get_description(self) -> str:
        """Get description of the vehicle listings search tool."""
        return "Search for vehicle listings based on various criteria including make, model, year, price range, location, and other filters. Returns detailed information about available vehicles."

    def get_required_params(self) -> list[str]:
        """Get required parameters for vehicle listings search."""
        return []  # No required params - can search with any combination

    def get_optional_params(self) -> list[str]:
        """Get optional parameters for vehicle listings search."""
        return [
            "make", "model", "year_min", "year_max", "price_min", "price_max",
            "mileage_max", "zip_code", "radius", "body_style", "fuel_type",
            "transmission", "limit"
        ]