#!/usr/bin/env python3
"""
Attribute normalization utilities.

Normalizes product attributes from various sources to canonical forms.
Examples:
- PCIE_5, PCIE5, pcie-v5 → PCIe:5.0
- DDR4, ddr4, DDR-4 → DDR4
- LGA1700, LGA 1700, lga-1700 → LGA 1700
"""

import re
from typing import Optional, Tuple

# PCIe normalization patterns
PCIE_PATTERNS = [
    (re.compile(r"pcie?\s*[:\-]?\s*(\d(?:\.\d)?)", re.IGNORECASE), "pcie_version"),
    (re.compile(r"pci\s*express\s*(\d(?:\.\d)?)", re.IGNORECASE), "pcie_version"),
    (re.compile(r"gen\s*(\d)", re.IGNORECASE), "pcie_version"),  # Often used for PCIe gen
]

# Socket normalization patterns
SOCKET_PATTERNS = [
    (re.compile(r"\b(lga)\s*[:\-]?\s*(\d{3,5})\b", re.IGNORECASE), "socket"),
    (re.compile(r"\b(am\d+)\b", re.IGNORECASE), "socket"),
    (re.compile(r"\b(strx\d|trx40|swrx8|str5|sp3)\b", re.IGNORECASE), "socket"),
]

# RAM standard normalization
RAM_PATTERNS = [
    (re.compile(r"\b(ddr\d)\b", re.IGNORECASE), "ram_standard"),
    (re.compile(r"\b(ddr\s*[:\-]?\s*\d)\b", re.IGNORECASE), "ram_standard"),
]

# Form factor normalization
FORM_FACTOR_MAP = {
    "e-atx": "E-ATX",
    "eatx": "E-ATX",
    "atx": "ATX",
    "micro-atx": "Micro-ATX",
    "micro atx": "Micro-ATX",
    "m-atx": "Micro-ATX",
    "matx": "Micro-ATX",
    "mini-itx": "Mini-ITX",
    "mini itx": "Mini-ITX",
    "mitx": "Mini-ITX",
    "nano-itx": "Nano-ITX",
}

# Brand normalization (common variations)
BRAND_MAP = {
    "nvidia": "NVIDIA",
    "amd": "AMD",
    "intel": "Intel",
    "corsair": "Corsair",
    "g.skill": "G.Skill",
    "gskill": "G.Skill",
    "kingston": "Kingston",
    "samsung": "Samsung",
    "crucial": "Crucial",
    "evga": "EVGA",
    "msi": "MSI",
    "asus": "ASUS",
    "gigabyte": "Gigabyte",
    "asrock": "ASRock",
}


def normalize_pcie(value: str) -> Optional[str]:
    """Normalize PCIe version to canonical form: PCIe:5.0"""
    for pattern, _ in PCIE_PATTERNS:
        match = pattern.search(value)
        if match:
            version = match.group(1)
            try:
                version_float = float(version)
                return f"PCIe:{version_float:.1f}"
            except ValueError:
                pass
    return None


def normalize_socket(value: str) -> Optional[str]:
    """Normalize socket to canonical form."""
    for pattern, _ in SOCKET_PATTERNS:
        match = pattern.search(value)
        if match:
            groups = [g for g in match.groups() if g]
            if len(groups) == 2:
                # LGA format
                return f"{groups[0].upper()} {groups[1]}"
            else:
                return match.group(0).upper()
    return None


def normalize_ram_standard(value: str) -> Optional[str]:
    """Normalize RAM standard to canonical form: DDR4, DDR5, etc."""
    for pattern, _ in RAM_PATTERNS:
        match = pattern.search(value)
        if match:
            ram = match.group(1).upper()
            # Clean up separators
            ram = re.sub(r"[:\-\s]+", "", ram)
            return ram
    return None


def normalize_form_factor(value: str) -> Optional[str]:
    """Normalize form factor to canonical form."""
    value_lower = value.lower().strip()
    for key, canonical in FORM_FACTOR_MAP.items():
        if key in value_lower:
            return canonical
    return None


def normalize_brand(value: str) -> Optional[str]:
    """Normalize brand name to canonical form."""
    value_lower = value.lower().strip()
    return BRAND_MAP.get(value_lower, value.title() if value else None)


def normalize_wattage(value: str) -> Optional[str]:
    """Normalize wattage to canonical form: 850W"""
    match = re.search(r"(\d{3,4})\s*(?:w|watt)", value, re.IGNORECASE)
    if match:
        return f"{match.group(1)}W"
    return None


def normalize_capacity(value: str) -> Optional[str]:
    """Normalize capacity to canonical form: 16GB, 1TB, etc."""
    # GB
    gb_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|gigabyte)", value, re.IGNORECASE)
    if gb_match:
        return f"{gb_match.group(1)}GB"
    
    # TB
    tb_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:tb|terabyte)", value, re.IGNORECASE)
    if tb_match:
        return f"{tb_match.group(1)}TB"
    
    return None


def normalize_attribute_value(key: str, value: str) -> Optional[Tuple[str, str]]:
    """
    Normalize an attribute key-value pair to canonical form.
    
    Returns:
        Tuple of (attribute_type, normalized_value) or None if not recognized
    """
    key_lower = key.lower()
    value = value.strip()
    value_lower = value.lower()
    
    # PCIe version - check multiple key patterns and value patterns
    if ("pcie" in key_lower or "pci express" in key_lower or 
        "interface" in key_lower or "bus" in key_lower or 
        "interconnect" in key_lower):
        # Check if value contains PCIe info
        if "pci" in value_lower or "pcie" in value_lower:
            normalized = normalize_pcie(value)
            if normalized:
                return ("pcie_version", normalized)
    
    # Socket
    if "socket" in key_lower or "cpu socket" in key_lower:
        normalized = normalize_socket(value)
        if normalized:
            return ("socket", normalized)
    
    # RAM standard - check multiple key patterns
    if ("memory" in key_lower or "ram" in key_lower or "ddr" in key_lower or
        "memory type" in key_lower or "memory standard" in key_lower):
        # Check for GDDR patterns first (GPU memory)
        gddr_match = re.search(r"gddr\s*(\d+)", value_lower)
        if gddr_match:
            return ("memory_type", f"GDDR{gddr_match.group(1)}")
        # Then check for DDR patterns (system memory)
        normalized = normalize_ram_standard(value)
        if normalized:
            return ("ram_standard", normalized)
    
    # Memory bus width (e.g., "256-bit")
    if "memory bus" in key_lower or "bus width" in key_lower:
        bus_match = re.search(r"(\d+)\s*[-\s]?bit", value, re.IGNORECASE)
        if bus_match:
            return ("memory_bus_width", f"{bus_match.group(1)}-bit")
    
    # Form factor
    if "form factor" in key_lower or ("size" in key_lower and "memory" not in key_lower):
        normalized = normalize_form_factor(value)
        if normalized:
            return ("form_factor", normalized)
    
    # Wattage/TDP - check multiple key patterns
    if ("wattage" in key_lower or "power" in key_lower or "watt" in key_lower or
        "tdp" in key_lower or "thermal design power" in key_lower or
        "power consumption" in key_lower):
        normalized = normalize_wattage(value)
        if normalized:
            return ("wattage", normalized)
    
    # Capacity - check multiple key patterns
    if ("capacity" in key_lower or ("size" in key_lower and "memory" in key_lower) or 
        "storage" in key_lower or "memory size" in key_lower):
        normalized = normalize_capacity(value)
        if normalized:
            return ("capacity", normalized)
    
    # Brand/Manufacturer
    if ("brand" in key_lower or "manufacturer" in key_lower or "maker" in key_lower or
        "designed by" in key_lower or "marketed by" in key_lower or
        "manufactured by" in key_lower):
        normalized = normalize_brand(value)
        if normalized:
            return ("brand", normalized)
    
    # Architecture (useful for compatibility)
    if "architecture" in key_lower:
        # Extract architecture name (e.g., "Ampere", "Ada Lovelace", "RDNA 2")
        # Try multiple patterns to catch different formats
        # Pattern 1: "RDNA 2", "GCN 4th gen" - starts with uppercase letters/numbers
        arch_match = re.search(r"([A-Z][A-Z0-9]+(?:\s+\d+)?)", value)
        if arch_match:
            arch_name = arch_match.group(1).strip()
            if len(arch_name) >= 2:
                return ("architecture", arch_name)
        # Pattern 2: "Ada Lovelace", "Ampere" - proper names
        arch_match2 = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", value)
        if arch_match2:
            arch_name = arch_match2.group(1).strip()
            if len(arch_name) >= 3 and arch_name.lower() not in ['the', 'and', 'for', 'gen']:
                return ("architecture", arch_name)
    
    # Codename (useful for identification)
    if "codename" in key_lower:
        # Extract codename (e.g., "AD10x", "GA10x", "Polaris")
        # Pattern 1: Technical codenames like "AD10x", "GA107"
        codename_match = re.search(r"([A-Z][A-Z0-9]+[a-z0-9]*)", value)
        if codename_match:
            return ("codename", codename_match.group(1))
        # Pattern 2: Name-based codenames like "Polaris", "Navi"
        codename_match2 = re.search(r"([A-Z][a-z]+)", value)
        if codename_match2:
            codename = codename_match2.group(1)
            # Skip common words
            if codename.lower() not in ['the', 'and', 'for', 'gen', 'by']:
                return ("codename", codename)
    
    return None


def normalize_all_attributes(attributes: dict) -> dict:
    """
    Normalize all attributes in a dictionary.
    
    Args:
        attributes: Dictionary of attribute key-value pairs
    
    Returns:
        Dictionary with normalized keys and values
    """
    normalized = {}
    for key, value in attributes.items():
        result = normalize_attribute_value(key, str(value))
        if result:
            attr_type, attr_value = result
            normalized[attr_type] = attr_value
    
    return normalized


if __name__ == "__main__":
    # Test normalization
    test_cases = [
        ("PCIe Version", "PCIE_5"),
        ("PCIe Version", "pcie-v5"),
        ("PCIe Version", "PCI Express 5.0"),
        ("Socket", "LGA1700"),
        ("Socket", "lga-1700"),
        ("Memory Type", "DDR4"),
        ("Memory Type", "ddr-4"),
        ("Form Factor", "micro-atx"),
        ("Power", "850W"),
        ("Capacity", "16GB"),
    ]
    
    for key, value in test_cases:
        result = normalize_attribute_value(key, value)
        if result:
            print(f"{key}: {value} → {result[0]}: {result[1]}")
        else:
            print(f"{key}: {value} → (not recognized)")

