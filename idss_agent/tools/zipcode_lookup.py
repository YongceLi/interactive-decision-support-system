"""
ZIP code to lat/long lookup utility.

Provides fast ZIP → coordinates conversion for users who don't share browser location.
Uses an in-memory dictionary for instant O(1) lookups.
"""
import csv
from pathlib import Path
from typing import Optional, Tuple, Dict
from idss_agent.utils.logger import get_logger

logger = get_logger("tools.zipcode_lookup")

# Global cache for ZIP code data - loads ONCE per application lifecycle
_ZIPCODE_DICT: Optional[Dict[str, Tuple[float, float, str, str]]] = None


def _load_zipcode_data() -> Dict[str, Tuple[float, float, str, str]]:
    """
    Load ZIP code data from CSV into memory dictionary.

    Returns:
        Dictionary mapping ZIP → (latitude, longitude, city, state)
    """
    csv_path = Path(__file__).resolve().parent.parent.parent / "data" / "zip_code_database.csv"

    if not csv_path.exists():
        logger.error(f"ZIP code database not found at {csv_path}")
        return {}

    zipcode_dict = {}

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                zip_code = row['zip']

                # Skip if missing critical data or decommissioned
                if not zip_code or not row['latitude'] or not row['longitude']:
                    continue

                if row.get('decommissioned', '0') == '1':
                    continue

                try:
                    latitude = float(row['latitude'])
                    longitude = float(row['longitude'])
                    city = row.get('primary_city', 'Unknown')
                    state = row.get('state', 'Unknown')

                    zipcode_dict[zip_code] = (latitude, longitude, city, state)

                except (ValueError, KeyError):
                    continue

        logger.info(f"Loaded {len(zipcode_dict)} ZIP codes into memory (~{len(zipcode_dict) * 70 / 1024:.1f} KB)")

    except Exception as e:
        logger.error(f"Failed to load ZIP code data: {e}")
        return {}

    return zipcode_dict


def _get_zipcode_dict() -> Dict[str, Tuple[float, float, str, str]]:
    """Get or initialize the ZIP code dictionary (loads CSV only once)."""
    global _ZIPCODE_DICT

    if _ZIPCODE_DICT is None:
        _ZIPCODE_DICT = _load_zipcode_data()

    return _ZIPCODE_DICT


def lookup_zipcode_coordinates(zipcode: str) -> Optional[Tuple[float, float, str, str]]:
    """
    Look up latitude/longitude for a given ZIP code.

    Args:
        zipcode: 5-digit US ZIP code (e.g., "94043")

    Returns:
        Tuple of (latitude, longitude, city, state) if found, None otherwise
    """
    # Validate ZIP code format
    if not zipcode or not isinstance(zipcode, str):
        logger.warning(f"Invalid ZIP code format: {zipcode}")
        return None

    # Normalize: remove spaces, take first 5 digits
    clean_zip = zipcode.strip().replace(" ", "")[:5]

    if not clean_zip.isdigit() or len(clean_zip) != 5:
        logger.warning(f"ZIP code must be 5 digits: {zipcode}")
        return None

    # Lookup in dictionary
    zipcode_dict = _get_zipcode_dict()
    result = zipcode_dict.get(clean_zip)

    if result:
        latitude, longitude, city, state = result
        logger.debug(f"ZIP {clean_zip} → {city}, {state} ({latitude}, {longitude})")
        return result
    else:
        logger.info(f"ZIP code not found in database: {clean_zip}")
        return None


def get_location_from_zip_or_coords(
    zipcode: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None
) -> Optional[Tuple[float, float]]:
    """
    Get user location coordinates from either ZIP code or direct coordinates.

    Priority:
    1. If latitude/longitude provided → use directly
    2. Else if zipcode provided → lookup coordinates
    3. Else → return None

    Args:
        zipcode: Optional 5-digit ZIP code
        latitude: Optional latitude from browser geolocation
        longitude: Optional longitude from browser geolocation

    Returns:
        Tuple of (latitude, longitude) if available, None otherwise
    """
    # Priority 1: Direct coordinates (browser geolocation)
    if latitude is not None and longitude is not None:
        logger.debug(f"Using browser location: ({latitude}, {longitude})")
        return (latitude, longitude)

    # Priority 2: ZIP code lookup
    if zipcode:
        logger.info(f"Browser location not available, using ZIP code: {zipcode}")
        result = lookup_zipcode_coordinates(zipcode)
        if result:
            return (result[0], result[1])  # Return (lat, lon) tuple
        else:
            logger.warning(f"Could not find coordinates for ZIP: {zipcode}")
            return None

    # No location info available
    logger.debug("No location information provided (no ZIP or coordinates)")
    return None
