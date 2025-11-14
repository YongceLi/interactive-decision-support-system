#!/usr/bin/env python3
"""Test Wikipedia scraping to see what attributes are available."""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import directly to avoid __init__.py dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "normalize_attributes",
    PROJECT_ROOT / "scripts" / "kg" / "normalize_attributes.py"
)
normalize_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalize_module)
normalize_attribute_value = normalize_module.normalize_attribute_value

# Test cases from actual Wikipedia logs
test_cases = [
    ('codename', 'AD10x'),
    ('architecture', 'Ada Lovelace'),
    ('codename', 'GA10x'),
    ('architecture', 'Ampere'),
    ('interface', 'PCIe 4.0'),
    ('bus interface', 'PCIe 4.0 x16'),
    ('memory type', 'GDDR6'),
    ('memory bus', '128-bit'),
    ('tdp', '115W'),
    ('power consumption', '115W'),
    ('manufactured by', 'TSMC'),
    ('designed by', 'Nvidia'),
]

print('=== TESTING NORMALIZATION FUNCTION ===\n')
for key, value in test_cases:
    result = normalize_attribute_value(key, value)
    if result:
        print(f'✓ {key:25} = {value:40} → {result[0]}: {result[1]}')
    else:
        print(f'✗ {key:25} = {value:40} → (not recognized)')

print('\n=== CHECKING REGEX PATTERNS ===\n')
import re

# Test codename pattern
codename_tests = ['AD10x', 'GA10x', 'Polaris', 'GA107']
print('Codename pattern: r"([A-Z][A-Z0-9]+[a-z0-9]*)"')
for test in codename_tests:
    match = re.search(r"([A-Z][A-Z0-9]+[a-z0-9]*)", test)
    if match:
        print(f'  ✓ "{test}" → {match.group(1)}')
    else:
        print(f'  ✗ "{test}" → (no match)')

# Test architecture pattern
arch_tests = ['Ada Lovelace', 'Ampere', 'RDNA 2']
print('\nArchitecture pattern: r"([A-Z][a-z]+(?:\\s+[A-Z]?[a-z]+)?)"')
for test in arch_tests:
    match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)?)", test)
    if match:
        print(f'  ✓ "{test}" → {match.group(1)}')
    else:
        print(f'  ✗ "{test}" → (no match)')
