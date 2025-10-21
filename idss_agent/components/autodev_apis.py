"""AutoDev API tools for vehicle information.
"""

import os
import requests
from typing import Optional, Dict, Any
from langchain_core.tools import tool


def _get_api_key() -> str:
    """Get AutoDev API key from environment variables.

    Returns:
        API key string

    Raises:
        ValueError: If API key is not found
    """
    api_key = os.getenv("AUTODEV_API_KEY")
    if not api_key:
        raise ValueError("AUTODEV_API_KEY not found in environment variables")
    return api_key


def _make_request(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Make authenticated request to Auto.dev API.

    Args:
        url: Full API endpoint URL
        params: Optional query parameters

    Returns:
        JSON response as string

    Raises:
        requests.exceptions.RequestException: If request fails
    """
    api_key = _get_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


@tool
def search_vehicle_listings(
    # Vehicle filters
    vehicle_make: Optional[str] = None,
    vehicle_model: Optional[str] = None,
    vehicle_year: Optional[str] = None,
    vehicle_trim: Optional[str] = None,
    vehicle_body_style: Optional[str] = None,
    vehicle_engine: Optional[str] = None,
    vehicle_transmission: Optional[str] = None,
    vehicle_exterior_color: Optional[str] = None,
    vehicle_interior_color: Optional[str] = None,
    vehicle_doors: Optional[int] = None,
    vehicle_squish_vin: Optional[str] = None,
    # Retail listing filters
    retail_price: Optional[str] = None,
    retail_state: Optional[str] = None,
    retail_miles: Optional[str] = None,
    # Wholesale listing filters
    wholesale_buy_now_price: Optional[str] = None,
    wholesale_state: Optional[str] = None,
    wholesale_miles: Optional[str] = None,
    # Location filters
    zip: Optional[str] = None,
    distance: Optional[int] = None,
    # Pagination
    page: Optional[int] = 1,
    limit: Optional[int] = 10,
) -> str:
    """Search for vehicle listings with comprehensive filtering options.

    Search through millions of active vehicle listings from U.S. physical and online
    dealers. Returns detailed vehicle information, dealership data, specifications,
    and market pricing.

    Args:
        vehicle_make: Vehicle manufacturer (e.g., "Ford", "Toyota"). Use comma for multiple: "Ford,Chevrolet"
        vehicle_model: Vehicle model (e.g., "F-150", "Camry"). Use comma for multiple
        vehicle_year: Vehicle year. Use specific year (2018) or range (2018-2020)
        vehicle_trim: Trim level (e.g., "XLT", "LT"). Use comma for multiple
        vehicle_body_style: Body style (e.g., "sedan", "suv"). Use comma for multiple
        vehicle_engine: Engine size (e.g., "2.0L", "3.5L"). Use comma for multiple
        vehicle_transmission: Transmission type (e.g., "automatic", "manual"). Use comma for multiple
        vehicle_exterior_color: Exterior color (e.g., "white", "black"). Use comma for multiple
        vehicle_interior_color: Interior color (e.g., "black", "gray"). Use comma for multiple
        vehicle_doors: Number of doors (2, 4, 5)
        vehicle_squish_vin: WMI and VDS section of VIN (first 11 chars minus check digit)
        retail_price: Price filter (use range: "10000-20000")
        retail_state: State where vehicle is located (e.g., "CA", "NY")
        retail_miles: Mileage filter (use range: "10000-20000")
        wholesale_buy_now_price: Wholesale price filter (use range: "10000-20000")
        wholesale_state: Wholesale listing state (e.g., "CA")
        wholesale_miles: Wholesale mileage filter (use range: "10000-20000")
        zip: 5-digit ZIP code to center the search around
        distance: Radius in miles from ZIP code (default: 50)
        page: Page number to retrieve (starting from 1, default: 1)
        limit: Number of listings per page (1-100, default: 100)

    Returns:
        JSON string containing an array of vehicle listings with detailed information
        including vehicle specs, dealership details, pricing, and photos.

    Example:
        >>> search_vehicle_listings(vehicle_make="Toyota", vehicle_model="Camry", retail_price="1-30000", retail_state="CA")
    """
    try:
        url = "https://api.auto.dev/listings"
        params = {}

        # Vehicle filters (ensure proper formatting with spaces after commas)
        if vehicle_make:
            params["vehicle.make"] = vehicle_make.replace(",", ", ") if "," in vehicle_make else vehicle_make
        if vehicle_model:
            params["vehicle.model"] = vehicle_model.replace(",", ", ") if "," in vehicle_model else vehicle_model
        if vehicle_year:
            params["vehicle.year"] = vehicle_year
        if vehicle_trim:
            params["vehicle.trim"] = vehicle_trim.replace(",", ", ") if "," in vehicle_trim else vehicle_trim
        if vehicle_body_style:
            params["vehicle.bodyStyle"] = vehicle_body_style.replace(",", ", ") if "," in vehicle_body_style else vehicle_body_style
        if vehicle_engine:
            params["vehicle.engine"] = vehicle_engine
        if vehicle_transmission:
            params["vehicle.transmission"] = vehicle_transmission
        if vehicle_exterior_color:
            params["vehicle.exteriorColor"] = vehicle_exterior_color
        if vehicle_interior_color:
            params["vehicle.interiorColor"] = vehicle_interior_color
        if vehicle_doors:
            params["vehicle.doors"] = vehicle_doors
        if vehicle_squish_vin:
            params["vehicle.squishVin"] = vehicle_squish_vin

        # Retail listing filters
        if retail_price:
            params["retailListing.price"] = retail_price
        if retail_state:
            params["retailListing.state"] = retail_state
        if retail_miles:
            params["retailListing.miles"] = retail_miles

        # Wholesale listing filters
        if wholesale_buy_now_price:
            params["wholesaleListing.buyNowPrice"] = wholesale_buy_now_price
        if wholesale_state:
            params["wholesaleListing.state"] = wholesale_state
        if wholesale_miles:
            params["wholesaleListing.miles"] = wholesale_miles

        # Location filters
        if zip:
            params["zip"] = zip
        if distance:
            params["distance"] = distance

        # Pagination
        if page:
            params["page"] = page
        if limit:
            params["limit"] = limit

        return _make_request(url, params)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 500:
            return f'{{"error": "Auto.dev API server error (500). This might be due to invalid parameter combinations. Try simplifying your search (fewer filters, single make/bodyStyle, or broader price range). Original error: {str(e)}"}}'
        return f'{{"error": "Error searching vehicle listings: {str(e)}"}}'
    except Exception as e:
        return f'{{"error": "Error searching vehicle listings: {str(e)}"}}'


@tool
def get_vehicle_listing_by_vin(vin: str) -> str:
    """Get detailed vehicle listing information for a specific VIN.

    Retrieve comprehensive listing data for a specific vehicle including dealer
    information, pricing, specifications, and availability.

    Args:
        vin: 17-character Vehicle Identification Number

    Returns:
        JSON string containing detailed listing information including:
        - vehicle: Complete vehicle specifications
        - retailListing: Dealer information, pricing, location
        - wholesaleListing: Wholesale/auction data if available
        - history: Vehicle history information if available

    Example:
        >>> get_vehicle_listing_by_vin("1HGBH41JXMN109186")
    """
    if not vin or len(vin) != 17:
        return '{"error": "VIN must be exactly 17 characters"}'

    try:
        url = f"https://api.auto.dev/listings/{vin}"
        return _make_request(url)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f'{{"error": "Listing not found for VIN {vin}. This vehicle may not be currently available or listed."}}'
        elif e.response.status_code == 500:
            return f'{{"error": "Detailed listing not available for VIN {vin}. The listing data may be incomplete in the database."}}'
        return f'{{"error": "Error getting vehicle listing: {str(e)}"}}'
    except Exception as e:
        return f'{{"error": "Error getting vehicle listing: {str(e)}"}}'


@tool
def get_vehicle_photos_by_vin(vin: str) -> str:
    """Get high-quality photos for a vehicle by VIN.

    Retrieve a collection of professional retail images including exterior shots,
    interior views, engine bay photos, and detail shots from dealer listings.

    Args:
        vin: 17-character Vehicle Identification Number

    Returns:
        JSON string containing arrays of photo URLs:
        - retail: Array of retail/dealer photo URLs

        Returns empty arrays if no photos are available (not an error).

    Example:
        >>> get_vehicle_photos_by_vin("1HGBH41JXMN109186")
    """
    if not vin or len(vin) != 17:
        return '{"error": "VIN must be exactly 17 characters"}'

    try:
        url = f"https://api.auto.dev/photos/{vin}"
        return _make_request(url)
    except Exception as e:
        return f'{{"error": "Error getting vehicle photos: {str(e)}"}}'
