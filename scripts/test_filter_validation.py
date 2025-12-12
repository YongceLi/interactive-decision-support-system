#!/usr/bin/env python3
"""
Test filter validation and correction.

Usage:
    python scripts/test_filter_validation.py
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

from idss_agent.processing.filter_validator import validate_and_correct_filters


def print_separator(char="=", length=80):
    """Print a separator line."""
    print(char * length)


def test_validation(test_name: str, filters: dict):
    """Run a validation test and display results."""
    print()
    print_separator("-")
    print(f"TEST: {test_name}")
    print_separator("-")
    print(f"Input filters:  {filters}")

    corrected = validate_and_correct_filters(filters)

    print(f"Output filters: {corrected}")

    # Show what changed
    changes = []
    for key in filters:
        if key not in corrected:
            changes.append(f"  ✗ Removed: {key}='{filters[key]}'")
        elif filters[key] != corrected[key]:
            changes.append(f"  ✓ Corrected: {key}: '{filters[key]}' → '{corrected[key]}'")
        else:
            changes.append(f"  ✓ Valid: {key}='{filters[key]}'")

    if changes:
        print("Changes:")
        for change in changes:
            print(change)

    return corrected


def main():
    """Run filter validation tests."""
    print_separator()
    print("FILTER VALIDATION TESTS")
    print_separator()
    print()
    print("This will test LLM-based filter correction.")
    print("Valid values will pass through without LLM calls.")
    print("Invalid values will be corrected using gpt-4o-mini.")
    print()

    # Test 1: Valid values (no LLM calls)
    test_validation(
        "Valid values (no LLM correction needed)",
        {
            "body_style": "sedan",
            "fuel_type": "gasoline",
            "drivetrain": "awd",
            "price": "20000-30000",  # Non-categorical, passed through
        }
    )

    # Test 2: Case variations (no LLM calls, just normalization)
    test_validation(
        "Case variations (no LLM correction needed)",
        {
            "body_style": "SEDAN",
            "fuel_type": "Electric",
            "transmission": "Automatic",
        }
    )

    # Test 3: Invalid values that can be corrected (LLM calls)
    test_validation(
        "Invalid values requiring LLM correction",
        {
            "body_style": "truck",  # Should correct to "pickup"
            "fuel_type": "ev",      # Should correct to "electric"
            "drivetrain": "4x4",    # Should correct to "4wd"
        }
    )

    # Test 4: Invalid values that cannot be corrected
    test_validation(
        "Invalid values that cannot be corrected",
        {
            "body_style": "banana",  # No valid match - should skip
            "fuel_type": "gasoline",  # Valid - should keep
            "price": "25000",        # Non-categorical - should keep
        }
    )

    # Test 5: Mixed valid and invalid
    test_validation(
        "Mixed valid and invalid values",
        {
            "body_style": "SUV",       # Valid (case variation)
            "fuel_type": "hybrid",     # Invalid - might correct
            "drivetrain": "all-wheel", # Invalid - should correct to "awd"
            "transmission": "auto",    # Invalid - should correct to "automatic"
            "price": "30000-40000",    # Non-categorical - pass through
            "make": "Toyota",          # Non-categorical - pass through
        }
    )

    print()
    print_separator()
    print("✓ All tests completed!")
    print_separator()
    print()


if __name__ == "__main__":
    main()
