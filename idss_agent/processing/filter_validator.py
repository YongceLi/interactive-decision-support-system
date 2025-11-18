"""
Filter validation and correction using LLM.

Validates categorical filter values against database schema and uses
LLM to correct invalid values (e.g., "truck" → "pickup").
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from langchain_openai import ChatOpenAI
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.filter_validator")

# Categorical fields that require validation
CATEGORICAL_FIELDS = {
    "body_style": "vehicle body type",
    "fuel_type": "fuel/energy type",
    "drivetrain": "drivetrain system",
    "transmission": "transmission type",
}

# Load valid values from JSON file (pre-generated from database)
_VALID_VALUES_CACHE: Optional[Dict[str, List[str]]] = None


def _load_valid_values() -> Dict[str, List[str]]:
    """
    Load valid filter values from JSON file.

    Returns:
        Dictionary mapping field names to lists of valid values
    """
    global _VALID_VALUES_CACHE

    if _VALID_VALUES_CACHE is not None:
        return _VALID_VALUES_CACHE

    # Path to valid values JSON
    config_path = Path(__file__).parent.parent.parent / "config" / "valid_filter_values.json"

    try:
        with open(config_path, 'r') as f:
            _VALID_VALUES_CACHE = json.load(f)

        logger.info(f"Loaded valid values for {len(_VALID_VALUES_CACHE)} categorical fields")
        return _VALID_VALUES_CACHE

    except FileNotFoundError:
        logger.error(f"Valid values file not found: {config_path}")
        logger.error("Run 'python scripts/extract_valid_filter_values.py' to generate it")
        return {}

    except Exception as e:
        logger.error(f"Error loading valid values: {e}")
        return {}


def _format_correction_prompt(
    field: str,
    invalid_value: str,
    valid_values: List[str],
    field_description: str
) -> str:
    """
    Format LLM prompt for value correction.

    Args:
        field: Field name (e.g., "body_style")
        invalid_value: User's input value
        valid_values: List of valid values from database
        field_description: Human-readable field description

    Returns:
        Formatted prompt string
    """
    return f"""You are a vehicle database value normalizer.

User said: "{invalid_value}"
Field: {field} ({field_description})

Valid values in database:
{chr(10).join(f"- {v}" for v in valid_values)}

Task: Find the best matching valid value, or return "SKIP" if no good match exists.

Rules:
1. Return ONLY the exact valid value (match case from list above)
2. If user's value is a synonym or similar concept, return the matching valid value
3. If no reasonable match exists, return exactly "SKIP"
4. Do not explain or add commentary

Examples:
- User: "truck" → "pickup" (if pickup is valid)
- User: "ev" → "electric" (if electric is valid)
- User: "4wd" → "4wd" (if 4wd is valid)
- User: "banana" → "SKIP" (not a vehicle attribute)

Your response (one word only):"""


def _correct_with_llm(
    field: str,
    invalid_value: str,
    valid_values: List[str],
    field_description: str
) -> Optional[str]:
    """
    Use small LLM to correct invalid categorical value.

    Args:
        field: Field name
        invalid_value: User's invalid input
        valid_values: List of valid values
        field_description: Human-readable description

    Returns:
        Corrected value from valid_values, or None if no match
    """
    try:
        # Use small model for cost efficiency
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0  # Deterministic
        )

        prompt = _format_correction_prompt(
            field=field,
            invalid_value=invalid_value,
            valid_values=valid_values,
            field_description=field_description
        )

        response = llm.invoke(prompt)
        corrected = response.content.strip()

        # Check if LLM wants to skip
        if corrected.upper() == "SKIP":
            return None

        # Validate LLM response (case-insensitive match)
        for valid_val in valid_values:
            if corrected.lower() == valid_val.lower():
                return valid_val

        # LLM returned invalid value (shouldn't happen, but handle gracefully)
        logger.warning(f"LLM returned invalid value '{corrected}' for {field}, skipping")
        return None

    except Exception as e:
        logger.error(f"LLM correction failed for {field}='{invalid_value}': {e}")
        return None


def validate_and_correct_filters(explicit_filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and correct categorical filter values.

    Checks each categorical filter against valid values from database.
    Uses LLM to correct invalid values (e.g., "truck" → "pickup").
    Skips filters that cannot be corrected.

    Args:
        explicit_filters: Raw filters from semantic parser

    Returns:
        Corrected filters with invalid values fixed or removed

    Example:
        >>> filters = {"body_style": "truck", "fuel_type": "ev", "price": "20000-30000"}
        >>> corrected = validate_and_correct_filters(filters)
        >>> print(corrected)
        {"body_style": "pickup", "fuel_type": "electric", "price": "20000-30000"}
    """
    # Load valid values
    valid_values_cache = _load_valid_values()

    if not valid_values_cache:
        logger.warning("No valid values loaded, skipping validation")
        return explicit_filters

    corrected_filters = {}

    for field, value in explicit_filters.items():
        # Skip non-categorical fields
        if field not in CATEGORICAL_FIELDS:
            corrected_filters[field] = value
            continue

        # Skip if no validation data available
        valid_values = valid_values_cache.get(field, [])
        if not valid_values:
            logger.warning(f"No valid values for {field}, skipping validation")
            corrected_filters[field] = value
            continue

        # Check if value is already valid (case-insensitive)
        value_lower = str(value).lower().strip()
        if value_lower in [v.lower() for v in valid_values]:
            corrected_filters[field] = value  # Already valid
            continue

        # Invalid value detected - attempt LLM correction
        logger.warning(f"Invalid {field}='{value}', attempting LLM correction...")

        corrected_value = _correct_with_llm(
            field=field,
            invalid_value=value,
            valid_values=valid_values,
            field_description=CATEGORICAL_FIELDS[field]
        )

        if corrected_value:
            logger.info(f"✓ Corrected {field}: '{value}' → '{corrected_value}'")
            corrected_filters[field] = corrected_value
        else:
            logger.warning(f"✗ Could not correct {field}='{value}', skipping filter")
            # Skip this filter (don't add to corrected_filters)

    return corrected_filters


__all__ = [
    "validate_and_correct_filters",
]
