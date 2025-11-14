#!/usr/bin/env python3
"""Test actual Wikipedia scraping to see what attributes are available."""

import sys
import re
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "normalize_attributes",
    PROJECT_ROOT / "scripts" / "kg" / "normalize_attributes.py"
)
normalize_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalize_module)
normalize_attribute_value = normalize_module.normalize_attribute_value

# Test with actual Wikipedia page HTML (simulated)
# Based on RTX 4060 Wikipedia page structure
test_infobox_data = [
    ("Release date", "October 12, 2022; 3 years ago(2022-10-12)"),
    ("Manufactured by", "TSMC"),
    ("Designed by", "Nvidia"),
    ("Marketed by", "Nvidia"),
    ("Codename", "AD10x"),
    ("Architecture", "Ada Lovelace"),
    ("Models", "GeForce RTX series"),
    ("Transistors", "18.9B (AD107)"),
    ("Fabrication process", "TSMC 4N"),
    ("Interface", "PCIe 4.0"),
    ("Memory type", "GDDR6"),
    ("Memory bus", "128-bit"),
    ("TDP", "115W"),
    ("Power consumption", "115W"),
]

print("=== TESTING WIKIPEDIA INFOBOX ATTRIBUTES ===\n")
print("Simulating Wikipedia infobox extraction:\n")

extracted = []
for key, value in test_infobox_data:
    result = normalize_attribute_value(key, value)
    if result:
        attr_type, attr_value = result
        extracted.append((attr_type, attr_value))
        print(f"✓ {key:25} = {value:50} → {attr_type}: {attr_value}")
    else:
        print(f"✗ {key:25} = {value:50} → (not recognized)")

print(f"\n=== SUMMARY ===")
print(f"Total attributes tested: {len(test_infobox_data)}")
print(f"Successfully extracted: {len(extracted)}")
print(f"\nExtracted attributes:")
for attr_type, attr_value in extracted:
    print(f"  - {attr_type}: {attr_value}")

print("\n=== RECOMMENDATION ===")
if len(extracted) < len(test_infobox_data) * 0.5:
    print("Less than 50% extraction rate. LLM extraction would help!")
    print("LLM can extract structured data even from unstructured text.")
else:
    print("Good extraction rate. LLM could still help with edge cases.")

