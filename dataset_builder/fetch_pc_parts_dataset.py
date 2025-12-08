"""Build a local SQLite database of consumer electronics products.

This script fetches product data from RapidAPI (shopping API) and stores it
in a normalized SQLite database.

The resulting database matches the normalized structure defined in
``dataset_builder/pc_parts_schema.sql`` and keeps the complete raw payload
for traceability
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Ensure project root on sys.path so shared utils are available when needed
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Load environment variables from .env if present
load_dotenv()


logger = logging.getLogger("electronics_builder")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ELECTRONICS_CATEGORIES: Dict[str, Dict[str, str]] = {
    "cpu": {"query": "cpu"},
    "gpu": {"query": "graphics card"},
    "motherboard": {"query": "motherboard"},
    "psu": {"query": "power supply"},
    "case": {"query": "pc case"},
    "cooling": {"query": "cpu cooler"},
    "ram": {"query": "ram"},
    "internal_storage": {"query": "internal ssd"},
    "external_storage": {"query": "external ssd"},
    "monitor": {"query": "computer monitor"},
    "keyboard": {"query": "mechanical keyboard"},
    "mouse": {"query": "gaming mouse"},
    "headset": {"query": "gaming headset"},
    "headphones": {"query": "wireless headphones"},
    "speakers": {"query": "bluetooth speaker"},
    "webcam": {"query": "webcam"},
    "microphone": {"query": "usb microphone"},
    "vr_headset": {"query": "vr headset"},
}

# Defaults for RapidAPI integration (can be overridden via environment)
DEFAULT_RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "product-search-api.p.rapidapi.com")
DEFAULT_RAPIDAPI_ENDPOINT = os.getenv("RAPIDAPI_ENDPOINT", "/shopping")
DEFAULT_RAPIDAPI_COUNTRY = os.getenv("RAPIDAPI_COUNTRY", "us")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

DEFAULT_TIMEOUT = (5, 25)

def _create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        try:
            cleaned = (
                value.replace("$", "")
                .replace(",", "")
                .replace("USD", "")
                .strip()
            )
            return float(cleaned) if cleaned else None
        except Exception:
            return None


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            cleaned = (
                value.replace(",", "")
                .replace("reviews", "")
                .replace("ratings", "")
                .strip()
            )
            return int(cleaned) if cleaned else None
        except Exception:
            return None


def _canonical_part_id(source: str, candidate: Optional[str], fallback_fields: Iterable[str]) -> str:
    if candidate is not None:
        candidate_str = str(candidate).strip()
        if candidate_str and candidate_str.lower() != "none":
            return f"{source}:{candidate_str}".lower()

    joined = "|".join(field for field in fallback_fields if field)
    if not joined:
        joined = f"{source}:{_now_iso()}"
    digest = sha1(joined.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"


def _extract_gpu_attributes(title: str, series: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    """Extract GPU-specific attributes: variant, interface, VRAM, memory type, cooler type.
    
    Examples:
    - "ASUS PRIME GeForce RTX 5080 16GB GDDR7" -> variant: PRIME, vram: 16GB, memory_type: GDDR7
    - "RTX 4060 VENTUS 2X" -> variant: VENTUS, cooler_type: Dual-Fan
    """
    attrs = {}
    title_upper = title.upper()
    
    # Extract variant (Gaming, Ventus, Eagle, Twin Edge, Prime, TUF, Strix, etc.)
    variant_patterns = [
        r'\b(GAMING|VENTUS|EAGLE|TWIN EDGE|PRIME|TUF|STRIX|ROG|AORUS|PHOENIX|DUAL|FOUNDERS EDITION)\b',
        r'\b(GAMING OC|GAMING X|GAMING Z|GAMING PRO)\b',
        r'\b(SUPRIM|MECH|CHALLENGER|FIGHTER|PULSE|NITRO|RED DEVIL|HELLHOUND)\b',
    ]
    for pattern in variant_patterns:
        variant_match = re.search(pattern, title_upper)
        if variant_match:
            attrs["variant"] = variant_match.group(1)
            break
    
    # Extract VRAM (2GB, 6GB, 8GB, 12GB, 16GB, 24GB, etc.)
    vram_match = re.search(r'\b(\d{1,2})\s*GB\b', title_upper)
    if vram_match:
        attrs["vram"] = f"{vram_match.group(1)}GB"
    
    # Extract memory type (GDDR3, GDDR5, GDDR6, GDDR6X, GDDR7, etc.)
    memory_type_match = re.search(r'\b(GDDR[3567X])\b', title_upper)
    if memory_type_match:
        attrs["memory_type"] = memory_type_match.group(1)
    
    # Extract interface (PCIe 4.0 x16, PCIe 5.0 x16, PCIe 3.0 x16)
    interface_match = re.search(r'\b(PCI[Ee]\s*\d\.\d\s*x\d{1,2})\b', title_upper)
    if interface_match:
        attrs["interface"] = interface_match.group(1)
    
    # Extract cooler type (Dual-Fan, dual, 2X, 3X, Triple-Fan, etc.)
    cooler_patterns = [
        r'\b(DUAL-FAN|DUAL FAN|DUAL|2X|2-FAN)\b',
        r'\b(TRIPLE-FAN|TRIPLE FAN|TRIPLE|3X|3-FAN)\b',
        r'\b(SINGLE-FAN|SINGLE FAN|SINGLE|1X|1-FAN)\b',
        r'\b(LIQUID COOLING|AIO|WATER COOLING)\b',
    ]
    for pattern in cooler_patterns:
        cooler_match = re.search(pattern, title_upper)
        if cooler_match:
            cooler_name = cooler_match.group(1)
            # Normalize cooler type
            if "DUAL" in cooler_name or "2X" in cooler_name or "2-FAN" in cooler_name:
                attrs["cooler_type"] = "Dual-Fan"
            elif "TRIPLE" in cooler_name or "3X" in cooler_name or "3-FAN" in cooler_name:
                attrs["cooler_type"] = "Triple-Fan"
            elif "SINGLE" in cooler_name or "1X" in cooler_name or "1-FAN" in cooler_name:
                attrs["cooler_type"] = "Single-Fan"
            elif "LIQUID" in cooler_name or "AIO" in cooler_name or "WATER" in cooler_name:
                attrs["cooler_type"] = "Liquid Cooling"
            else:
                attrs["cooler_type"] = cooler_match.group(1)
            break
    
    return attrs


def _extract_ram_attributes(title: str, series: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    """Extract RAM-specific attributes: ram_standard, capacity, form_factor.
    
    Examples:
    - "Synology DDR4 4GB SODIMM RAM" -> ram_standard: DDR4, capacity: 4GB, form_factor: SODIMM
    """
    attrs = {}
    title_upper = title.upper()
    
    # Extract RAM standard (DDR3, DDR4, DDR5)
    ram_standard_match = re.search(r'\b(DDR[345])\b', title_upper)
    if ram_standard_match:
        attrs["ram_standard"] = ram_standard_match.group(1)
    
    # Extract capacity (4GB, 8GB, 16GB, 32GB, 64GB, etc.)
    capacity_match = re.search(r'\b(\d{1,3})\s*GB\b', title_upper)
    if capacity_match:
        attrs["capacity"] = f"{capacity_match.group(1)}GB"
    
    # Extract form factor (SODIMM, DIMM, UDIMM, RDIMM, LRDIMM)
    form_factor_match = re.search(r'\b(SODIMM|DIMM|UDIMM|RDIMM|LRDIMM)\b', title_upper)
    if form_factor_match:
        attrs["form_factor"] = form_factor_match.group(1)
    else:
        # Default to DIMM for desktop RAM if not specified
        if "LAPTOP" not in title_upper and "NOTEBOOK" not in title_upper:
            attrs["form_factor"] = "DIMM"
    
    return attrs


def _extract_motherboard_attributes(title: str, series: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    """Extract motherboard-specific attributes: chipset, form_factor, socket.
    
    Examples:
    - "MSI MPG B550 Gaming Plus AM4 ATX" -> chipset: B550, form_factor: ATX, socket: AM4
    """
    attrs = {}
    title_upper = title.upper()
    
    # Extract chipset (B450, B550, X570, Z790, etc.)
    chipset_match = re.search(r'\b([BXZH]\d{3,4}[A-Z]?[EM]?)\b', title_upper)
    if chipset_match:
        attrs["chipset"] = chipset_match.group(1)
    
    # Extract form factor (ATX, mATX, Mini-ITX, EATX, etc.)
    form_factor_match = re.search(r'\b(ATX|MATX|MICRO-ATX|MICRO ATX|MINI-ITX|MINI ITX|EATX|EXTENDED ATX|ITX)\b', title_upper)
    if form_factor_match:
        form_factor = form_factor_match.group(1)
        # Normalize form factor names
        if "MATX" in form_factor or "MICRO" in form_factor:
            attrs["form_factor"] = "mATX"
        elif "MINI" in form_factor or "ITX" in form_factor:
            attrs["form_factor"] = "Mini-ITX"
        elif "EATX" in form_factor or "EXTENDED" in form_factor:
            attrs["form_factor"] = "EATX"
        else:
            attrs["form_factor"] = "ATX"
    else:
        # Default to ATX if not specified
        attrs["form_factor"] = "ATX"
    
    # Extract socket (AM4, AM5, LGA 1700, LGA 1200, etc.)
    socket_patterns = [
        r'\b(AM[45])\b',
        r'\b(LGA\s*\d{4,5})\b',
        r'\b(SOCKET\s*\d{3,4})\b',
    ]
    for pattern in socket_patterns:
        socket_match = re.search(pattern, title_upper)
        if socket_match:
            attrs["socket"] = socket_match.group(1).replace(" ", "")
            break
    
    return attrs


def _extract_cpu_attributes(title: str, series: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    """Extract CPU-specific attributes: core_count, base_clock, boost_clock, etc.
    
    Examples:
    - "AMD Ryzen 5 5600G 6 Core Processor" -> core_count: 6
    """
    attrs = {}
    title_upper = title.upper()
    
    # Extract core count
    core_match = re.search(r'\b(\d{1,2})\s*CORE\b', title_upper)
    if core_match:
        attrs["core_count"] = int(core_match.group(1))
    
    # Extract thread count
    thread_match = re.search(r'\b(\d{1,2})\s*THREAD\b', title_upper)
    if thread_match:
        attrs["thread_count"] = int(thread_match.group(1))
    
    # Extract base clock (GHz)
    base_clock_match = re.search(r'\b(\d+\.\d+)\s*GHZ\s*(?:BASE|@)\b', title_upper)
    if base_clock_match:
        attrs["base_clock"] = f"{base_clock_match.group(1)}GHz"
    
    # Extract boost clock (GHz)
    boost_clock_match = re.search(r'\b(\d+\.\d+)\s*GHZ\s*(?:BOOST|MAX)\b', title_upper)
    if boost_clock_match:
        attrs["boost_clock"] = f"{boost_clock_match.group(1)}GHz"
    
    # Extract TDP (W)
    tdp_match = re.search(r'\b(\d{2,3})\s*W\s*(?:TDP|THERMAL)\b', title_upper)
    if tdp_match:
        attrs["tdp"] = f"{tdp_match.group(1)}W"
    
    return attrs


def _extract_psu_attributes(title: str, series: Optional[str], model: Optional[str]) -> Dict[str, Any]:
    """Extract PSU-specific attributes: wattage, form factor, certification.
    
    Examples:
    - "RM850x" -> wattage: 850W
    - "A650BN" -> wattage: 650W, certification: 80 Plus Bronze
    - "CX750M" -> wattage: 750W
    """
    attrs = {}
    title_upper = title.upper()
    
    # Extract wattage from series name (e.g., RM850x -> 850W, A650BN -> 650W)
    wattage = None
    if series:
        # Look for 3-4 digit numbers in series name
        wattage_match = re.search(r'(\d{3,4})', series.upper())
        if wattage_match:
            wattage = int(wattage_match.group(1))
            attrs["wattage"] = f"{wattage}W"
    
    # Also check title directly if not found in series
    if not wattage:
        wattage_match = re.search(r'(\d{3,4})\s*W', title_upper)
        if wattage_match:
            wattage = int(wattage_match.group(1))
            attrs["wattage"] = f"{wattage}W"
    
    # Extract form factor (ATX, SFX, TFX, etc.)
    form_factor_match = re.search(r'\b(ATX|SFX|TFX|CFX|LFX|FLEX)\b', title_upper)
    if form_factor_match:
        attrs["form_factor"] = form_factor_match.group(1)
    else:
        # Default to ATX if not specified (most common)
        attrs["form_factor"] = "ATX"
    
    # Extract 80 Plus certification
    cert_patterns = [
        (r'\b80\s*PLUS\s*TITANIUM\b', "80 Plus Titanium"),
        (r'\b80\s*PLUS\s*PLATINUM\b', "80 Plus Platinum"),
        (r'\b80\s*PLUS\s*GOLD\b', "80 Plus Gold"),
        (r'\b80\s*PLUS\s*SILVER\b', "80 Plus Silver"),
        (r'\b80\s*PLUS\s*BRONZE\b', "80 Plus Bronze"),
        (r'\b80\s*PLUS\b', "80 Plus"),
        (r'\bPLATINUM\b', "80 Plus Platinum"),
        (r'\bGOLD\b', "80 Plus Gold"),
        (r'\bBRONZE\b', "80 Plus Bronze"),
        (r'\bSILVER\b', "80 Plus Silver"),
    ]
    
    # Check model name for certification codes (e.g., BN = Bronze, GL = Gold)
    if model:
        model_upper = model.upper()
        if "BN" in model_upper or "BRONZE" in model_upper:
            attrs["certification"] = "80 Plus Bronze"
        elif "GL" in model_upper or "GOLD" in model_upper:
            attrs["certification"] = "80 Plus Gold"
        elif "PL" in model_upper or "PLATINUM" in model_upper:
            attrs["certification"] = "80 Plus Platinum"
        elif "SL" in model_upper or "SILVER" in model_upper:
            attrs["certification"] = "80 Plus Silver"
    
    # Check title for certification
    if "certification" not in attrs:
        for pattern, cert_name in cert_patterns:
            if re.search(pattern, title_upper):
                attrs["certification"] = cert_name
                break
    
    # Extract modularity (Fully Modular, Semi-Modular, Non-Modular)
    if "FULLY MODULAR" in title_upper or "FULL MODULAR" in title_upper:
        attrs["modularity"] = "Fully Modular"
    elif "SEMI-MODULAR" in title_upper or "SEMI MODULAR" in title_upper:
        attrs["modularity"] = "Semi-Modular"
    elif "NON-MODULAR" in title_upper or "NON MODULAR" in title_upper:
        attrs["modularity"] = "Non-Modular"
    
    # Extract color (Black, Black/Silver, White, etc.)
    color_patterns = [
        r'\b(BLACK/SILVER|BLACK-SILVER|BLACK & SILVER)\b',
        r'\b(WHITE/BLACK|WHITE-BLACK|WHITE & BLACK)\b',
        r'\b(BLACK/WHITE|BLACK-WHITE|BLACK & WHITE)\b',
        r'\b(BLACK)\b',
        r'\b(WHITE)\b',
        r'\b(SILVER)\b',
        r'\b(GRAY|GREY)\b',
        r'\b(RED)\b',
        r'\b(BLUE)\b',
    ]
    for pattern in color_patterns:
        color_match = re.search(pattern, title_upper)
        if color_match:
            color_name = color_match.group(1)
            # Normalize color names
            if "/" in color_name or "-" in color_name or "&" in color_name:
                # Multi-color: normalize separators
                attrs["color"] = color_name.replace("-", "/").replace(" & ", "/")
            else:
                attrs["color"] = color_name
            break
    
    # Extract ATX version (ATX 3.1, ATX 3.0, ATX 2.0, etc.)
    atx_version_match = re.search(r'\bATX\s*(\d\.\d)\b', title_upper)
    if atx_version_match:
        attrs["atx_version"] = f"ATX {atx_version_match.group(1)}"
    elif "ATX 3" in title_upper:
        # Check for ATX 3.1 specifically (newer standard)
        if "ATX 3.1" in title_upper or "ATX3.1" in title_upper:
            attrs["atx_version"] = "ATX 3.1"
        elif "ATX 3.0" in title_upper or "ATX3.0" in title_upper:
            attrs["atx_version"] = "ATX 3.0"
        else:
            attrs["atx_version"] = "ATX 3.0"  # Default to 3.0 if just "ATX 3" mentioned
    
    # Extract noise level (Low-noise, Silent, Quiet, etc.)
    noise_patterns = [
        r'\b(LOW-NOISE|LOW NOISE|LOWNOISE)\b',
        r'\b(SILENT)\b',
        r'\b(QUIET)\b',
        r'\b(ULTRA-QUIET|ULTRA QUIET|ULTRAQUIET)\b',
        r'\b(ZERO-RPM|ZERO RPM|ZERORPM)\b',  # Fanless mode
    ]
    for pattern in noise_patterns:
        noise_match = re.search(pattern, title_upper)
        if noise_match:
            noise_name = noise_match.group(1)
            # Normalize noise level names
            if "LOW" in noise_name:
                attrs["noise_level"] = "Low-noise"
            elif "SILENT" in noise_name:
                attrs["noise_level"] = "Silent"
            elif "QUIET" in noise_name:
                if "ULTRA" in noise_name:
                    attrs["noise_level"] = "Ultra-quiet"
                else:
                    attrs["noise_level"] = "Quiet"
            elif "ZERO" in noise_name:
                attrs["noise_level"] = "Zero-RPM"
            else:
                attrs["noise_level"] = noise_name
            break
    
    # Extract PCIe 5.0 power support (12VHPWR, 12V-2×6, PCIe Gen5 Cable, PCIE5)
    pcie5_patterns = [
        r'\b12VHPWR\b',
        r'\b12V-2[×X]6\b',
        r'\bPCI[Ee]\s*GEN5\s*CABLE\b',
        r'\bPCIE5\b',
        r'\bPCI[Ee]\s*5\.0\s*POWER\b',
    ]
    attrs["supports_pcie5_power"] = 0
    for pattern in pcie5_patterns:
        if re.search(pattern, title_upper):
            attrs["supports_pcie5_power"] = 1
            break
    
    return attrs


def _parse_title_fields(title: str, product_type: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse brand, series, and model from product title.
    
    Returns: (brand, series, model)
    """
    if not title:
        return None, None, None
    
    title_upper = title.upper()
    title_lower = title.lower()
    
    # Common brands (search anywhere in title, prioritize longer matches)
    brands = ["WESTERN DIGITAL", "COOLER MASTER", "BE QUIET", "G.SKILL", "GIGABYTE", 
              "POWERCOLOR", "THERMALTAKE", "SAPPHIRE", "KINGSTON", "SAMSUNG", 
              "ASROCK", "CORSAIR", "ADATA", "CRUCIAL", "SEAGATE", "NOCTUA", 
              "ARCTIC", "DEEPCOOL", "NVIDIA", "INTEL", "AMD", "ASUS", "MSI", 
              "EVGA", "ZOTAC", "XFX", "SANDISK", "PNY", "KINGSPEC", "LEXAR", 
              "SEASONIC", "NZXT", "FSP", "SAMA", "LIAN LI", "APEVIA", "LUKYAMZN",
              "TEAM", "PATRIOT", "MICRON", "TIMETEC", "WD", "INLAND", "TEAMGROUP", 
              "EXASCEND", "SYNOLOGY", "HPE", "GAMESTOP", "LOGITECH", "RAZER", 
              "HYPERX", "STEELSERIES", "TURTLE BEACH", "JBL", "ELGATO", "INSTA360",
              "META", "SONY", "HTC", "FRACTAL DESIGN", "PHANTEKS", "HYTE", "ANTEC",
              "ROSEWILL", "ZALMAN", "MONOTECH", "DIYPCPC", "JONSBO", "DARKFLASH",
              "HAVN", "VEVOR", "GAMEMAX", "HEC", "COUGAR", "RUIX", "KEYCHRON",
              "DUCKY", "SATECHI", "GMMK", "DROP", "GLORIOUS", "REDRAGON", "RK ROYAL KLUDGE",
              "AJAZZ", "CREATIVE", "ALURATEK", "EMEET", "SANOXY", "DESTEK", "ILIVE",
              "OBJLGEV", "PIMAX", "BIGSCREEN", "DPVR", "THIRDEYE", "OCULUS"]
    
    brand = None
    # Brand aliases/normalization
    brand_aliases = {
        "WD": "WESTERN DIGITAL",
        "SANDISK": "WESTERN DIGITAL",  # SanDisk is owned by Western Digital
        "G.SKILL": "G.SKILL",
        "G SKILL": "G.SKILL",
        "GSKILL": "G.SKILL",
    }
    
    # Sort by length (longest first) to match longer brand names first
    brands_sorted = sorted(brands, key=len, reverse=True)
    for b in brands_sorted:
        if b.upper() in title_upper:
            brand = b
            break
    
    # Check for brand aliases
    if not brand:
        for alias, canonical in brand_aliases.items():
            if alias in title_upper:
                brand = canonical
                break
    
    # Special handling for brands that might appear differently
    if not brand:
        if "WESTERN DIGITAL" in title_upper or " WD " in title_upper or title_upper.startswith("WD "):
            brand = "WESTERN DIGITAL"
        elif "SANDISK" in title_upper:
            brand = "WESTERN DIGITAL"
        elif "G.SKILL" in title_upper or "G SKILL" in title_upper or "GSKILL" in title_upper:
            brand = "G.SKILL"
        elif "SEASONIC" in title_upper:
            brand = "SEASONIC"
        elif "APEVIA" in title_upper:
            brand = "APEVIA"
        elif "PNY" in title_upper:
            brand = "PNY"
        elif "KINGSPEC" in title_upper:
            brand = "KINGSPEC"
        elif "LEXAR" in title_upper:
            brand = "LEXAR"
        elif "NZXT" in title_upper:
            brand = "NZXT"
        elif "FSP" in title_upper:
            brand = "FSP"
        elif "SAMA" in title_upper:
            brand = "SAMA"
        elif "LIAN LI" in title_upper or "LIANLI" in title_upper:
            brand = "LIAN LI"
        elif "TEAM" in title_upper and "TEAMGROUP" not in title_upper:
            brand = "TEAM"
        elif "TEAMGROUP" in title_upper:
            brand = "TEAMGROUP"
        elif "PATRIOT" in title_upper:
            brand = "PATRIOT"
        elif "MICRON" in title_upper:
            brand = "MICRON"
        elif "TIMETEC" in title_upper:
            brand = "TIMETEC"
        elif "INLAND" in title_upper:
            brand = "INLAND"
        elif "SYNOLOGY" in title_upper:
            brand = "SYNOLOGY"
    
    # Parse based on product type
    series = None
    model = None
    
    if product_type == "cpu":
        # Filter out pre-built desktops and all-in-ones (these shouldn't be in CPU category)
        desktop_keywords = [
            "DESKTOP PC", "DESKTOP COMPUTER", "ALL-IN-ONE", "GAMING PC", "GAMING DESKTOP",
            "MINI PC", "SMALL DESKTOP", "FORM FACTOR PC", "SFF DESKTOP", "MICRO DESKTOP",
            "IBUYPOWER", "CYBERPOWERPC", "AVADIRECT", "BUYPOWER", "GEEKOM", "VELZTORM",
            "SKYTECH", "CLX SET", "THERMALTAKE LCGS", "HP OMEN", "HP PROONE", "HP ELITEDESK",
            "DELL OPTIPLEX", "DELL PRO", "DELL PRECISION", "MSI CODEX", "ASUS ROG G700",
            "WORKSTATION PC", "BUSINESS DESKTOP", "AI MINI PC", "INTEL NUC",
            "WINDOWS 11", "WINDOWS 10", "RAM", "SSD", "HDD", "GRAPHICS", "RTX", "GTX", "RX ",
            "LIQUID COOL", "RGB", "WIFI", "BLUETOOTH", "MONITOR", "INCH", "FHD", "HDMI",
            "USB", "ETHERNET", "KEYBOARD", "MOUSE", "SPEAKERS", "WEBCAM"
        ]
        # Check if title contains multiple desktop indicators (more than just "Desktop processor")
        desktop_indicators = sum(1 for keyword in desktop_keywords if keyword in title_upper)
        if desktop_indicators >= 2:  # If 2+ indicators, it's likely a full PC
            return None, None, None
        # Also check for specific PC brand patterns
        pc_brands = ["IBUYPOWER", "CYBERPOWERPC", "AVADIRECT", "SKYTECH", "CLX SET", "THERMALTAKE LCGS", 
                     "MSI CODEX", "ASUS ROG G700", "HP OMEN", "HP PROONE", "HP ELITEDESK", 
                     "DELL OPTIPLEX", "DELL PRO", "DELL PRECISION", "GEEKOM", "VELZTORM", 
                     "BOESIIPC", "ZHICGCP", "ICEWOLF", "HOENGAGER", "CAPTIVA PC"]
        if any(pc_brand in title_upper for pc_brand in pc_brands):
            return None, None, None
        # Check for patterns like "Gaming Desktop with..." or "Desktop Computer..."
        if re.search(r'(GAMING|BUSINESS|WORKSTATION)\s+(DESKTOP|PC|COMPUTER)', title_upper):
            return None, None, None
        
        # CPU examples: "AMD Ryzen 5 7600X 6-Core", "Intel Core i5-12400", "Intel Core i5-3330"
        if brand == "AMD":
            # Look for "Ryzen" series (handle both "Ryzen 5" and "Ryzen-5" formats)
            if "RYZEN" in title_upper:
                # Extract Ryzen series (e.g., "Ryzen 7000-series", "Ryzen 5")
                ryzen_match = None
                if "RYZEN 9" in title_upper or "RYZEN-9" in title_upper:
                    ryzen_match = "Ryzen 9"
                elif "RYZEN 7" in title_upper or "RYZEN-7" in title_upper:
                    ryzen_match = "Ryzen 7"
                elif "RYZEN 5" in title_upper or "RYZEN-5" in title_upper:
                    ryzen_match = "Ryzen 5"
                elif "RYZEN 3" in title_upper or "RYZEN-3" in title_upper:
                    ryzen_match = "Ryzen 3"
                elif "THREADRIPPER" in title_upper:
                    ryzen_match = "Threadripper"
                elif "EPYC" in title_upper:
                    ryzen_match = "EPYC"
                
                if ryzen_match:
                    series = ryzen_match
                    # Extract model number (e.g., "7600X", "7800X3D", "8500G", "9995WX", "5945WX")
                    # Look for 4-digit numbers followed by optional letters (including WX for Threadripper)
                    model_match = re.search(r'(\d{4}[A-Z0-9]*)', title_upper)
                    if model_match:
                        model = model_match.group(1)
            # Handle older AMD processors (A-series, FX-series)
            elif "FX-" in title_upper or " FX " in title_upper:
                series = "FX"
                model_match = re.search(r'FX-?(\d{4}[A-Z]*)', title_upper)
                if not model_match:
                    model_match = re.search(r'(\d{4}[A-Z]*)', title_upper)
                if model_match:
                    model = model_match.group(1)
            elif re.search(r'\bA\d{1,2}-\d{4}', title_upper):
                series = "A-Series"
                model_match = re.search(r'A\d{1,2}-(\d{4}[A-Z]*)', title_upper)
                if model_match:
                    model = model_match.group(1)
        elif brand == "INTEL":
            # Look for "Core Ultra" first (newer Intel processors)
            if "CORE ULTRA" in title_upper:
                # Extract Core Ultra series (e.g., "Core Ultra 7", "Core Ultra 5")
                ultra_match = None
                if "CORE ULTRA 9" in title_upper:
                    ultra_match = "Core Ultra 9"
                elif "CORE ULTRA 7" in title_upper:
                    ultra_match = "Core Ultra 7"
                elif "CORE ULTRA 5" in title_upper:
                    ultra_match = "Core Ultra 5"
                
                if ultra_match:
                    series = ultra_match
                    # Extract model number (e.g., "265K", "155H")
                    model_match = re.search(r'(\d{3}[A-Z]*)', title_upper)
                    if model_match:
                        model = model_match.group(1)
            # Look for Xeon processors
            elif "XEON" in title_upper:
                series = "Xeon"
                # Extract model number (e.g., "E5-2650 V2")
                model_match = re.search(r'E\d-(\d{4}[A-Z\s]*V?\d*)', title_upper)
                if not model_match:
                    # Fallback: look for any number pattern
                    model_match = re.search(r'(\d{4}[A-Z0-9\s]*)', title_upper)
                if model_match:
                    model = model_match.group(1).strip()
            # Look for Pentium processors
            elif "PENTIUM" in title_upper:
                series = "Pentium"
                # Extract model number (e.g., "G5400", "G3450")
                model_match = re.search(r'G(\d{4}[A-Z]*)', title_upper)
                if model_match:
                    model = f"G{model_match.group(1)}"
                elif not model:
                    # Fallback: look for any 4-digit number
                    model_match = re.search(r'(\d{4}[A-Z]*)', title_upper)
                    if model_match:
                        model = model_match.group(1)
            # Look for Celeron processors
            elif "CELERON" in title_upper:
                series = "Celeron"
                # Extract model number
                model_match = re.search(r'(\d{4}[A-Z]*)', title_upper)
                if model_match:
                    model = model_match.group(1)
            # Look for regular "Core" series
            elif "CORE" in title_upper:
                # Extract Core series (e.g., "Core i9", "Core i7", "Core i5", "Core i3")
                core_match = None
                if "CORE I9" in title_upper or "I9-" in title_upper:
                    core_match = "Core i9"
                elif "CORE I7" in title_upper or "I7-" in title_upper:
                    core_match = "Core i7"
                elif "CORE I5" in title_upper or "I5-" in title_upper:
                    core_match = "Core i5"
                elif "CORE I3" in title_upper or "I3-" in title_upper:
                    core_match = "Core i3"
                
                if core_match:
                    series = core_match
                    # Extract model number - handle both 4-digit (e.g., "3330", "7500") and 5-digit (e.g., "12400", "13900K")
                    # Try multiple patterns to catch different formats
                    # Pattern 1: "i5-3330" or "Core i5-3330"
                    model_match = re.search(r'I[3579]-(\d{4,5}[A-Z]*)', title_upper)
                    if not model_match:
                        # Pattern 2: "Core i5 3330" (space separated)
                        model_match = re.search(r'CORE I[3579]\s+(\d{4,5}[A-Z]*)', title_upper)
                    if not model_match:
                        # Pattern 3: Any 4-5 digit number with optional suffix (fallback)
                        model_match = re.search(r'(\d{4,5}[A-Z]*)', title_upper)
                    if model_match:
                        # Extract the captured group (model number)
                        model = model_match.group(1)
        
        # If we have brand and series but no model, try harder to find model
        if brand and series and not model:
            # For Intel Core series, try to extract model from title
            if "CORE" in series.upper():
                model_match = re.search(r'I[3579]-(\d{4,5}[A-Z]*)', title_upper)
                if not model_match:
                    model_match = re.search(r'CORE I[3579]\s+(\d{4,5}[A-Z]*)', title_upper)
                if model_match:
                    model = model_match.group(1)
            # For AMD Ryzen, try to extract model
            elif "RYZEN" in series.upper():
                model_match = re.search(r'(\d{4}[A-Z0-9]*)', title_upper)
                if model_match:
                    model = model_match.group(1)
            # Generic: try to find any model number pattern
            if not model:
                model_match = re.search(r'(\d{4,5}[A-Z]*)', title_upper)
                if model_match:
                    model = model_match.group(1)
    
    elif product_type == "gpu":
        # GPU examples: "RTX 4060 VENTUS 2X", "RX 7600 GAMING OC 8GB", "GTX 1050 Ti Phoenix", "Arc B580"
        # Handle NVIDIA Quadro/RTX A-series first (professional GPUs)
        if "QUADRO" in title_upper or "RTX A" in title_upper or re.search(r'\bRTX\s*A\d{4}\b', title_upper):
            brand = "NVIDIA"
            # Quadro RTX A6000, RTX A5000, etc.
            quadro_match = re.search(r'(?:QUADRO\s+)?RTX\s*A(\d{4})', title_upper)
            if quadro_match:
                series = f"Quadro RTX A{quadro_match.group(1)}"
                model = f"A{quadro_match.group(1)}"
            # Quadro P-series
            elif re.search(r'QUADRO\s+P\d{3,4}', title_upper):
                quadro_p_match = re.search(r'QUADRO\s+(P\d{3,4})', title_upper)
                if quadro_p_match:
                    series = f"Quadro {quadro_p_match.group(1)}"
                    model = quadro_p_match.group(1)
            # RTX A-series (without Quadro)
            elif re.search(r'\bRTX\s*A\d{4}\b', title_upper):
                rtx_a_match = re.search(r'RTX\s*A(\d{4})', title_upper)
                if rtx_a_match:
                    series = f"RTX A{rtx_a_match.group(1)}"
                    model = f"A{rtx_a_match.group(1)}"
            # NVIDIA A100, H100, A2 (datacenter GPUs)
            elif re.search(r'\bA\d{3}\b', title_upper) or re.search(r'\bH\d{3}\b', title_upper):
                datacenter_match = re.search(r'\b([AH]\d{3})\b', title_upper)
                if datacenter_match:
                    series = datacenter_match.group(1)
                    model = datacenter_match.group(1)
        elif brand == "NVIDIA" or "RTX" in title_upper or "GTX" in title_upper or "GEFORCE" in title_upper:
            brand = "NVIDIA"
            # Extract RTX/GTX series
            if "RTX" in title_upper:
                rtx_match = re.search(r'RTX\s*(\d{4}[A-Z]*)', title_upper)
                if rtx_match:
                    series = f"RTX {rtx_match.group(1)}"
                    model = rtx_match.group(1)
            elif "GTX" in title_upper:
                gtx_match = re.search(r'GTX\s*(\d{4}[A-Z]*)', title_upper)
                if gtx_match:
                    series = f"GTX {gtx_match.group(1)}"
                    model = gtx_match.group(1)
            elif "GEFORCE" in title_upper:
                # Try to extract model number after "GeForce"
                geforce_match = re.search(r'GEFORCE\s+(\d{4}[A-Z]*)', title_upper)
                if geforce_match:
                    model_num = geforce_match.group(1)
                    if model_num.startswith("RTX") or model_num.startswith("GTX"):
                        series = model_num
                        model = model_num[3:].strip()
                    else:
                        series = f"GeForce {model_num}"
                        model = model_num
        elif brand == "AMD" or "RX" in title_upper or "RADEON" in title_upper:
            brand = "AMD"
            # Extract RX series
            rx_match = re.search(r'RX\s*(\d{4}[A-Z]*)', title_upper)
            if rx_match:
                series = f"RX {rx_match.group(1)}"
                model = rx_match.group(1)
            elif "RADEON PRO" in title_upper:
                # Radeon Pro W7900, etc.
                radeon_pro_match = re.search(r'RADEON PRO\s+(?:WX\s+)?(W?\d{4}[A-Z]*)', title_upper)
                if radeon_pro_match:
                    model_num = radeon_pro_match.group(1)
                    series = f"Radeon Pro {model_num}"
                    model = model_num
                else:
                    # Fallback: just "Radeon Pro" as series
                    series = "Radeon Pro"
                    # Try to extract any model number
                    model_match = re.search(r'PRO\s+(\d{3,4}[A-Z]*)', title_upper)
                    if model_match:
                        model = model_match.group(1)
            elif "RADEON" in title_upper:
                # Try to extract model number after "Radeon"
                radeon_match = re.search(r'RADEON\s+(?:HD\s+)?(?:R\d\s+)?(\d{3,4}[A-Z]*)', title_upper)
                if radeon_match:
                    model_num = radeon_match.group(1)
                    series = f"Radeon {model_num}"
                    model = model_num
        elif brand == "INTEL" or "ARC" in title_upper:
            brand = "INTEL"
            # Extract Intel Arc series
            arc_match = re.search(r'ARC\s*([A-Z]\d{3}[A-Z]*)', title_upper)
            if arc_match:
                series = f"Arc {arc_match.group(1)}"
                model = arc_match.group(1)
            elif "INTEL ARC" in title_upper:
                arc_match = re.search(r'INTEL\s+ARC\s+([A-Z]\d{3}[A-Z]*)', title_upper)
                if arc_match:
                    series = f"Arc {arc_match.group(1)}"
                    model = arc_match.group(1)
    
    elif product_type == "motherboard":
        # Motherboard examples: "Gigabyte B550 Eagle WiFi6", "MSI MPG B550 Gaming Plus", "ASUS ROG Strix Z790-E"
        # Extract chipset first (B550, Z790, X570, etc.) - this is often the model identifier
        chipset_match = re.search(r'\b([BXZH]\d{3,4}[A-Z]?)\b', title_upper)
        if chipset_match:
            chipset = chipset_match.group(1)
            # Use chipset as model if no other model found
            if not model:
                model = chipset
        
        # Extract series first (MPG, MAG, PRO, MEG, ROG STRIX, TUF, PRIME, etc.)
        series_patterns = [
            r'\b(MPG|MAG|PRO|MEG)\b',  # MSI series
            r'\b(ROG STRIX|STRIX|TUF|PRIME|CROSSHAIR)\b',  # ASUS series
            r'\b(AORUS|EAGLE)\b',  # Gigabyte series
            r'\b(TAICHI|PHANTOM GAMING|STEEL LEGEND)\b',  # ASRock series
        ]
        for pattern in series_patterns:
            series_match = re.search(pattern, title_upper)
            if series_match:
                series = series_match.group(1)
                break
        
        # Extract chipset (B550, X870E, Z790, B650, etc.) - stored in chipset field
        chipset_match = re.search(r'\b([BXZH]\d{3,4}[A-Z]?[EM]?)\b', title_upper)
        chipset = None
        if chipset_match:
            chipset = chipset_match.group(1)
            # If no series found, use chipset as series (backward compatibility)
            if not series:
                series = chipset
        
        # Try to extract model name (product name like "Eagle", "Gaming Plus", "HERO", "TOMAHAWK")
        # Look for common motherboard model patterns
        model_patterns = [
            r'\b(ROG STRIX|STRIX|TUF|PRIME|CROSSHAIR|HERO|FORMULA|EXTREME|APEX|GENE|IMPACT)\b',
            r'\b(EAGLE|GAMING PLUS|GAMING X|PRO|PRO4|PRO5|ELITE|AORUS|TAICHI|STEEL LEGEND|PHANTOM GAMING)\b',
            r'\b(TOMAHAWK|CARBON|UNIFY|GODLIKE|MEG|MAG|MPG|PRO|A-PRO|B-PRO)\b',
            r'\b(PLUS|MAX|MINI|MICRO|ITX|ATX|EATX|WIFI|WIFI7)\b',
        ]
        for pattern in model_patterns:
            model_match = re.search(pattern, title_upper)
            if model_match:
                model = model_match.group(1)
                break
        
        # If no brand detected, try to infer from common patterns
        if not brand:
            if "ROG" in title_upper or "STRIX" in title_upper or "TUF" in title_upper or "PRIME" in title_upper or "CROSSHAIR" in title_upper:
                brand = "ASUS"
            elif "MEG" in title_upper or "MAG" in title_upper or "MPG" in title_upper:
                brand = "MSI"
            elif "AORUS" in title_upper or "EAGLE" in title_upper or "GIGABYTE" in title_upper or title_upper.startswith("GA "):
                brand = "GIGABYTE"
            elif "TAICHI" in title_upper or "PHANTOM" in title_upper or "STEEL" in title_upper or "ASROCK" in title_upper:
                brand = "ASROCK"
            elif "COLORFUL" in title_upper or "CVN" in title_upper:
                brand = "COLORFUL"
            elif "SUPERMICRO" in title_upper or "X10" in title_upper or "X11" in title_upper:
                brand = "SUPERMICRO"
            elif chipset:
                # If we have chipset but no brand, try to infer from chipset patterns
                # Most motherboards with just chipset are usually from major brands
                # But we can't be sure, so leave brand as None
                pass
    
    elif product_type == "psu":
        # PSU examples: "Thermaltake Smart BM3 750W", "SEASONIC CORE GX-750", "NZXT ATX 3.1 850W", "Apevia Venus450W"
        # "Corsair RM850x", "EVGA A650BN", "Corsair CX750M"
        # Try to extract model name first (product line like "Smart BM3", "CORE GX-750", "Toughpower GF A3", "RM850x")
        model_patterns = [
            r'\b(RM\d{3,4}[A-Z]?|CX\d{3,4}[A-Z]?|TX\d{3,4}[A-Z]?|HX\d{3,4}[A-Z]?|AX\d{3,4}[A-Z]?)\b',  # Corsair models
            r'\b(A\d{3,4}[A-Z]{2}|B\d{3,4}[A-Z]{2}|G\d{3,4}[A-Z]{2}|P\d{3,4}[A-Z]{2})\b',  # EVGA models (A650BN, B550GM, etc.)
            r'\b(SMART|TOUGHPOWER|CORE|FOCUS|PRIME|EDGE|VENUS|RAPTOR|ESSENCE|CYBERCORE|HYDRO)\b',
            r'\b([A-Z]{2,}-\d+|GX-\d+|TX-\d+|GF\s*A?\d+|BM\d+|W\d+)\b',
            r'\b(ATX\s*\d+\.\d+|80\s*PLUS|PLATINUM|GOLD|BRONZE|SILVER)\b',
        ]
        for pattern in model_patterns:
            model_match = re.search(pattern, title_upper)
            if model_match:
                model = model_match.group(1)
                break
        # Extract wattage - check model name first (e.g., RM850x -> 850W), then title
        wattage = None
        if model:
            wattage_match = re.search(r'(\d{3,4})', model)
            if wattage_match:
                wattage = wattage_match.group(1)
                series = f"{wattage}W"
        if not wattage:
            wattage_match = re.search(r'(\d{3,4})\s*W', title_upper)
            if wattage_match:
                wattage = wattage_match.group(1)
                series = f"{wattage}W"
        # If no brand detected, try to infer from product line
        if not brand:
            if "CORE" in title_upper or "FOCUS" in title_upper or "PRIME" in title_upper:
                brand = "SEASONIC"
            elif "VENUS" in title_upper or "RAPTOR" in title_upper or "ESSENCE" in title_upper:
                brand = "APEVIA"
            elif "SMART" in title_upper or "TOUGHPOWER" in title_upper:
                brand = "THERMALTAKE"
            elif "ATX" in title_upper and "3." in title_upper:
                brand = "NZXT"
            elif "HYDRO" in title_upper:
                brand = "FSP"
            elif "RM" in title_upper or "CX" in title_upper or "TX" in title_upper or "HX" in title_upper:
                brand = "CORSAIR"
            elif re.search(r'\bA\d{3,4}[A-Z]{2}\b', title_upper) or re.search(r'\bB\d{3,4}[A-Z]{2}\b', title_upper):
                brand = "EVGA"
            elif "PLATINUM" in title_upper and "SAMA" not in title_upper:
                # Could be various brands, but SAMA uses Platinum
                pass
    
    elif product_type == "ram":
        # RAM examples: "Corsair Vengeance RGB Pro DDR4", "Kingston Fury Beast DDR4", "G.Skill Trident Z Royal", "Timetec 16GB DDR3 1333MHz"
        # Extract product line as model first (Vengeance, Fury Beast, Trident Z, Ballistix, etc.)
        model_patterns = [
            r'\b(VENGEANCE|FURY BEAST|FURY|TRIDENT Z|TRIDENT|BALLISTIX|BALLISTIX ELITE|VIPER STEEL|VIPER)\b',
            r'\b(RGB PRO|LPX|DOMINATOR|TITANIUM|ROYAL|VULCAN Z|T-FORCE|VULCAN)\b',
            r'\b(PRO|ELITE|PLUS|MAX|ULTRA)\b',
        ]
        for pattern in model_patterns:
            model_match = re.search(pattern, title_upper)
            if model_match:
                model = model_match.group(1)
                break
        # Extract DDR type and speed as series
        ddr_match = re.search(r'(DDR[345])', title_upper)
        if ddr_match:
            ddr_type = ddr_match.group(1)
            # Try to extract speed
            speed_match = re.search(r'(\d{3,4})\s*MHZ', title_upper)
            if speed_match:
                series = f"{ddr_type} {speed_match.group(1)}MHz"
            else:
                series = ddr_type
        # If no brand detected, try to infer from product line
        if not brand and model:
            if "VENGEANCE" in title_upper or "DOMINATOR" in title_upper:
                brand = "CORSAIR"
            elif "FURY" in title_upper:
                brand = "KINGSTON"
            elif "TRIDENT" in title_upper or "RIPJAWS" in title_upper:
                brand = "G.SKILL"
            elif "BALLISTIX" in title_upper:
                brand = "CRUCIAL"
            elif "VIPER" in title_upper:
                brand = "PATRIOT"
            elif "T-FORCE" in title_upper or "VULCAN" in title_upper:
                brand = "TEAM"
    
    elif product_type == "internal_storage":
        # Internal storage examples: "SanDisk SN7100 SSD M.2", "Kingston A400 SSD", "WD Blue SA510 SSD", "PNY CS900 SATA III"
        # Extract product line as model first (Blue, Green, Red, Ultra, Plus, Pro, etc.)
        model_patterns = [
            r'\b(BLUE|GREEN|RED|BLACK|GOLD|ULTRA|PLUS|PRO|MAX|ELITE|PREMIUM)\b',
            r'\b(SPATIUM|VENGEANCE|FURY|BALLISTIX|VIPER)\b',
            r'\b(M\.2|NVME|SATA|PCI[Ee])\b',
        ]
        for pattern in model_patterns:
            model_match = re.search(pattern, title_upper)
            if model_match:
                model = model_match.group(1)
                break
        # Extract product line/model number as series
        # Look for model numbers like "SN7100", "A400", "SA510", "CS900", "NV3", "T700"
        model_match = re.search(r'\b([A-Z]{1,3}\d{3,5}[A-Z0-9]*)\b', title_upper)
        if model_match:
            series = model_match.group(1)
        # If no brand detected, try to infer from product line or model
        if not brand:
            if "BLUE" in title_upper or "GREEN" in title_upper or "RED" in title_upper or "BLACK" in title_upper:
                brand = "WESTERN DIGITAL"
            elif "ULTRA" in title_upper or "PLUS" in title_upper:
                if "SANDISK" in title_upper or "SN" in title_upper:
                    brand = "WESTERN DIGITAL"
            elif "A400" in title_upper or "NV3" in title_upper:
                brand = "KINGSTON"
            elif "CS" in title_upper and "PNY" not in title_upper:
                # Could be PNY or other brand, but CS series is common
                pass
            elif "SPATIUM" in title_upper:
                brand = "MSI"
            elif "P3" in title_upper or "T700" in title_upper or "BALLISTIX" in title_upper:
                brand = "CRUCIAL"
    
    elif product_type == "webcam":
        # Webcam examples: "Logitech Brio 100 Webcam", "Logitech C920S HD Pro Webcam", "Insta360 Link 2 4K Webcam"
        # Extract series/model patterns: Letter(s) + numbers (e.g., Brio 100, C920S, Link 2)
        webcam_patterns = [
            r'\b([A-Z]\d{3,4}[A-Z]?)\b',  # C920S, Brio 100, C270
            r'\b([A-Z]{2,}\s+\d{1,3})\b',  # Brio 100, Link 2
            r'\b([A-Z]{2,}\s+[A-Z]{1,2}\s+\d{1,3})\b',  # C920S HD Pro
        ]
        for pattern in webcam_patterns:
            match = re.search(pattern, title_upper)
            if match:
                model_parts = match.group(1).split()
                if len(model_parts) >= 2:
                    series = model_parts[0]
                    model = " ".join(model_parts[1:])
                else:
                    model = match.group(1)
                break
        
        # If no brand detected, try common webcam brands
        if not brand:
            if "LOGITECH" in title_upper:
                brand = "LOGITECH"
            elif "INSTA360" in title_upper:
                brand = "INSTA360"
            elif "ELGATO" in title_upper:
                brand = "ELGATO"
            elif "CREATIVE" in title_upper:
                brand = "CREATIVE"
    
    elif product_type == "keyboard":
        # Keyboard examples: "Razer Pro Type Ultra", "HyperX Alloy Origins 65", "Logitech G G915 X"
        # Extract series/model patterns
        keyboard_patterns = [
            r'\b([A-Z]\d{3,4}[A-Z]?)\b',  # G915, K100, K3 Pro
            r'\b([A-Z]{2,}\s+\d{1,3})\b',  # Alloy Origins 65
            r'\b([A-Z]{2,}\s+[A-Z]{1,3})\b',  # Pro Type Ultra, BlackWidow V4
            r'\b([A-Z]{2,}\s+V\d+)\b',  # BlackWidow V4, Huntsman V2
        ]
        for pattern in keyboard_patterns:
            match = re.search(pattern, title_upper)
            if match:
                model_parts = match.group(1).split()
                if len(model_parts) >= 2:
                    series = model_parts[0]
                    model = " ".join(model_parts[1:])
                else:
                    model = match.group(1)
                break
        
        # Extract common keyboard series
        if not series:
            series_patterns = [
                r'\b(G\d{3,4}|K\d{3,4}|MX\s+MECHANICAL|PRO\s+TYPE|BLACKWIDOW|HUNTSMAN|APEX|ALLOY|K3|K100)\b',
            ]
            for pattern in series_patterns:
                match = re.search(pattern, title_upper)
                if match:
                    series = match.group(1)
                    break
        
        # If no brand detected, try common keyboard brands
        if not brand:
            if "LOGITECH" in title_upper or "G " in title_upper and "G915" in title_upper:
                brand = "LOGITECH"
            elif "RAZER" in title_upper:
                brand = "RAZER"
            elif "HYPERX" in title_upper:
                brand = "HYPERX"
            elif "STEELSERIES" in title_upper:
                brand = "STEELSERIES"
            elif "KEYCHRON" in title_upper:
                brand = "KEYCHRON"
            elif "DUCKY" in title_upper:
                brand = "DUCKY"
            elif "CORSAIR" in title_upper:
                brand = "CORSAIR"
    
    elif product_type == "mouse":
        # Mouse examples: "Logitech G PRO X Superlight 2 SE", "Razer Basilisk V3 Pro", "SteelSeries Rival 5"
        # Extract series/model patterns
        mouse_patterns = [
            r'\b([A-Z]\d{3,4}[A-Z]?)\b',  # G305, G502, G703
            r'\b([A-Z]{2,}\s+V\d+)\b',  # Basilisk V3, Deathadder V4
            r'\b([A-Z]{2,}\s+\d{1,2})\b',  # Rival 5, Model O3
            r'\b(MODEL\s+[A-Z]\d?)\b',  # Model O3, Model O
        ]
        for pattern in mouse_patterns:
            match = re.search(pattern, title_upper)
            if match:
                model_parts = match.group(1).split()
                if len(model_parts) >= 2:
                    series = model_parts[0]
                    model = " ".join(model_parts[1:])
                else:
                    model = match.group(1)
                break
        
        # Extract common mouse series
        if not series:
            series_patterns = [
                r'\b(G\s*PRO|G\d{3,4}|BASILISK|DEATHADDER|VIPER|COBRA|RIVAL|MODEL\s+[A-Z])\b',
            ]
            for pattern in series_patterns:
                match = re.search(pattern, title_upper)
                if match:
                    series = match.group(1)
                    break
        
        # If no brand detected, try common mouse brands
        if not brand:
            if "LOGITECH" in title_upper or "G " in title_upper:
                brand = "LOGITECH"
            elif "RAZER" in title_upper:
                brand = "RAZER"
            elif "STEELSERIES" in title_upper:
                brand = "STEELSERIES"
            elif "HYPERX" in title_upper:
                brand = "HYPERX"
            elif "GLORIOUS" in title_upper:
                brand = "GLORIOUS"
            elif "REDRAGON" in title_upper:
                brand = "REDRAGON"
    
    elif product_type == "headset":
        # Headset examples: "Logitech G432 Gaming Headset", "HyperX Cloud Stinger 2 Core", "SteelSeries Arctis Nova"
        # Extract series/model patterns
        headset_patterns = [
            r'\b([A-Z]\d{3,4})\b',  # G432
            r'\b([A-Z]{2,}\s+\d{1,2})\b',  # Cloud Stinger 2, Arctis Nova
            r'\b([A-Z]{2,}\s+[A-Z]{2,})\b',  # Cloud Alpha, Arctis Nova Pro
            r'\b(V\d+)\b',  # BlackShark V2 Pro
        ]
        for pattern in headset_patterns:
            match = re.search(pattern, title_upper)
            if match:
                model_parts = match.group(1).split()
                if len(model_parts) >= 2:
                    series = model_parts[0]
                    model = " ".join(model_parts[1:])
                else:
                    model = match.group(1)
                break
        
        # Extract common headset series
        if not series:
            series_patterns = [
                r'\b(G\d{3,4}|CLOUD|ARCTIS|BLACKSHARK|KRAKEN|VIRTUOSO|QUANTUM|RECON|STEALTH)\b',
            ]
            for pattern in series_patterns:
                match = re.search(pattern, title_upper)
                if match:
                    series = match.group(1)
                    break
        
        # If no brand detected, try common headset brands
        if not brand:
            if "LOGITECH" in title_upper:
                brand = "LOGITECH"
            elif "HYPERX" in title_upper:
                brand = "HYPERX"
            elif "STEELSERIES" in title_upper:
                brand = "STEELSERIES"
            elif "RAZER" in title_upper:
                brand = "RAZER"
            elif "TURTLE BEACH" in title_upper:
                brand = "TURTLE BEACH"
            elif "JBL" in title_upper:
                brand = "JBL"
            elif "CORSAIR" in title_upper:
                brand = "CORSAIR"
            elif "SONY" in title_upper:
                brand = "SONY"
            elif "ASTRO" in title_upper:
                brand = "ASTRO"
    
    elif product_type == "vr_headset":
        # VR Headset examples: "Meta Quest 3S", "Sony PlayStation VR2", "HTC VIVE Pro 2"
        # Extract series/model patterns
        vr_patterns = [
            r'\b(QUEST\s+\d{1,2}[A-Z]?)\b',  # Quest 3S, Quest 3
            r'\b(VR\d+)\b',  # VR2
            r'\b(VIVE\s+[A-Z]{2,}\s+\d{1,2})\b',  # VIVE Pro 2, VIVE Focus Vision
            r'\b([A-Z]{2,}\s+\d{1,2})\b',  # Crystal Light, Beyond 2
        ]
        for pattern in vr_patterns:
            match = re.search(pattern, title_upper)
            if match:
                model_parts = match.group(1).split()
                if len(model_parts) >= 2:
                    series = model_parts[0]
                    model = " ".join(model_parts[1:])
                else:
                    model = match.group(1)
                break
        
        # Extract common VR series
        if not series:
            series_patterns = [
                r'\b(QUEST|PLAYSTATION\s+VR|VIVE|CRYSTAL|BEYOND|ODyssey|FOCUS|RIFT)\b',
            ]
            for pattern in series_patterns:
                match = re.search(pattern, title_upper)
                if match:
                    series = match.group(1)
                    break
        
        # If no brand detected, try common VR brands
        if not brand:
            if "META" in title_upper or "QUEST" in title_upper or "OCULUS" in title_upper:
                brand = "META"
            elif "SONY" in title_upper or "PLAYSTATION" in title_upper:
                brand = "SONY"
            elif "HTC" in title_upper or "VIVE" in title_upper:
                brand = "HTC"
            elif "SAMSUNG" in title_upper:
                brand = "SAMSUNG"
            elif "PIMAX" in title_upper:
                brand = "PIMAX"
            elif "BIGSCREEN" in title_upper:
                brand = "BIGSCREEN"
            elif "DPVR" in title_upper:
                brand = "DPVR"
    
    elif product_type == "case":
        # Case examples: "NZXT H9 Flow RGB", "Fractal Design North XL", "Lian Li Mini ATX"
        # Extract series/model patterns
        case_patterns = [
            r'\b([A-Z]\d{1,2})\b',  # H9, H7, Y60, Y70
            r'\b([A-Z]{2,}\s+\d{1,2})\b',  # Define R5, Meshify C
            r'\b([A-Z]{2,}\s+[A-Z]{2,})\b',  # North XL, Evolv X2
        ]
        for pattern in case_patterns:
            match = re.search(pattern, title_upper)
            if match:
                model_parts = match.group(1).split()
                if len(model_parts) >= 2:
                    series = model_parts[0]
                    model = " ".join(model_parts[1:])
                else:
                    model = match.group(1)
                break
        
        # Extract common case series
        if not series:
            series_patterns = [
                r'\b(H\d{1,2}|Y\d{1,2}|DEFINE|MESHIFY|NORTH|EVOLV|LANCOOL|TERRA|CORE|V\s+SERIES)\b',
            ]
            for pattern in series_patterns:
                match = re.search(pattern, title_upper)
                if match:
                    series = match.group(1)
                    break
        
        # If no brand detected, try common case brands
        if not brand:
            if "NZXT" in title_upper:
                brand = "NZXT"
            elif "FRACTAL DESIGN" in title_upper or "FRACTAL" in title_upper:
                brand = "FRACTAL DESIGN"
            elif "LIAN LI" in title_upper or "LIANLI" in title_upper:
                brand = "LIAN LI"
            elif "PHANTEKS" in title_upper:
                brand = "PHANTEKS"
            elif "HYTE" in title_upper:
                brand = "HYTE"
            elif "ANTEC" in title_upper:
                brand = "ANTEC"
            elif "THERMALTAKE" in title_upper:
                brand = "THERMALTAKE"
            elif "ROSEWILL" in title_upper:
                brand = "ROSEWILL"
            elif "ZALMAN" in title_upper:
                brand = "ZALMAN"
            elif "MONOTECH" in title_upper:
                brand = "MONOTECH"
            elif "COUGAR" in title_upper:
                brand = "COUGAR"
    
    elif product_type in ["cooling", "external_storage", "monitor", "microphone", "speaker"]:
        # Generic parsing for other peripherals
        # Extract model numbers: Letter(s) + numbers pattern
        if not model:
            model_patterns = [
                r'\b([A-Z]\d{3,4}[A-Z]?)\b',  # Single letter + numbers
                r'\b([A-Z]{2,}\s+\d{1,3})\b',  # Words + numbers
                r'\b([A-Z]{2,}\s+[A-Z]{1,2}\s+\d{1,3})\b',  # Multiple words + numbers
            ]
            for pattern in model_patterns:
                match = re.search(pattern, title_upper)
                if match:
                    model_parts = match.group(1).split()
                    if len(model_parts) >= 2:
                        series = model_parts[0]
                        model = " ".join(model_parts[1:])
                    else:
                        model = match.group(1)
                    break
    
    # If we couldn't parse, try to extract any model numbers as fallback
    if not model and brand:
        # For Intel: try to find any 4-5 digit number that might be a model
        if brand == "INTEL":
            model_match = re.search(r'(\d{4,5}[A-Z]*)', title_upper)
            if model_match:
                model = model_match.group(1)
        # For AMD: try to find 4-digit numbers
        elif brand == "AMD":
            model_match = re.search(r'(\d{4}[A-Z0-9]*)', title_upper)
            if model_match:
                model = model_match.group(1)
        # Generic fallback: try to find common model number patterns
        if not model:
            model_match = re.search(r'([A-Z]{2,}\s*\d{3,}[A-Z0-9]*)', title_upper)
            if model_match:
                potential_model = model_match.group(1).strip()
                if not series:
                    series = potential_model
                model = potential_model.split()[-1] if " " in potential_model else potential_model
    
    return brand, series, model


def _generate_slug(brand: Optional[str], series: Optional[str], model: Optional[str]) -> str:
    """Generate slug from brand + series + model."""
    parts = []
    if brand:
        parts.append(str(brand).strip())
    if series:
        parts.append(str(series).strip())
    if model:
        parts.append(str(model).strip())
    return " ".join(parts).lower().replace(" ", "-") if parts else ""


def _is_parseable(record: "PCPartRecord") -> bool:
    """Check if a record has all required fields (brand, series, model) for parsing."""
    return bool(record.brand and record.series and record.model)


def _export_unparseable_to_csv(records: List["PCPartRecord"], csv_path: Path) -> int:
    """Export unparseable records to CSV for manual editing.
    
    Returns: number of records exported
    """
    unparseable = [r for r in records if not _is_parseable(r)]
    if not unparseable:
        return 0
    
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file exists to append or create
    file_exists = csv_path.exists()
    
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "product_id", "product_type", "raw_name", "brand", "series", "model",
            "price", "seller", "rating", "rating_count", "size", "color", "year",
            "created_at",
            # CPU Attributes
            "socket", "architecture", "pcie_version", "ram_standard", "tdp",
            # GPU Attributes
            "vram", "memory_type", "cooler_type", "variant", "is_oc", "revision", "interface", "power_connector",
            # Motherboard Attributes
            "chipset", "form_factor",
            # PSU Attributes
            "wattage", "certification", "modularity", "atx_version", "noise", "supports_pcie5_power",
            # Case Attributes
            "storage", "capacity", "storage_type",
            # Cooling Attributes
            "cooling_type", "tdp_support"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        for record in unparseable:
            row = record.to_row()
            csv_row = {
                "product_id": row["product_id"],
                "product_type": row["product_type"],
                "raw_name": row["raw_name"],
                "brand": row.get("brand") or "",
                "series": row.get("series") or "",
                "model": row.get("model") or "",
                "price": row.get("price") or "",
                "seller": row.get("seller") or "",
                "rating": row.get("rating") or "",
                "rating_count": row.get("rating_count") or "",
                "size": row.get("size") or "",
                "color": row.get("color") or "",
                "year": row.get("year") or "",
                "created_at": row.get("created_at") or "",
                # CPU Attributes
                "socket": row.get("socket") or "",
                "architecture": row.get("architecture") or "",
                "pcie_version": row.get("pcie_version") or "",
                "ram_standard": row.get("ram_standard") or "",
                "tdp": row.get("tdp") or "",
                # GPU Attributes
                "vram": row.get("vram") or "",
                "memory_type": row.get("memory_type") or "",
                "cooler_type": row.get("cooler_type") or "",
                "variant": row.get("variant") or "",
                "is_oc": row.get("is_oc") or "",
                "revision": row.get("revision") or "",
                "interface": row.get("interface") or "",
                "power_connector": row.get("power_connector") or "",
                # Motherboard Attributes
                "chipset": row.get("chipset") or "",
                "form_factor": row.get("form_factor") or "",
                # PSU Attributes
                "wattage": row.get("wattage") or "",
                "certification": row.get("certification") or "",
                "modularity": row.get("modularity") or "",
                "atx_version": row.get("atx_version") or "",
                "noise": row.get("noise") or "",
                "supports_pcie5_power": row.get("supports_pcie5_power") or "",
                # Case Attributes
                "storage": row.get("storage") or "",
                "capacity": row.get("capacity") or "",
                "storage_type": row.get("storage_type") or "",
                # Cooling Attributes
                "cooling_type": row.get("cooling_type") or "",
                "tdp_support": row.get("tdp_support") or "",
            }
            writer.writerow(csv_row)
    
    logger.info("Exported %d unparseable records to %s", len(unparseable), csv_path)
    return len(unparseable)


def _import_from_csv(csv_path: Path) -> List["PCPartRecord"]:
    """Import records from manually edited CSV file.
    
    CSV should have columns: product_id, product_type, raw_name, brand, series, model,
    price, seller, rating, rating_count, size, color, year, created_at,
    and all attribute columns (socket, architecture, etc.)
    """
    if not csv_path.exists():
        logger.warning("CSV file not found: %s", csv_path)
        return []
    
    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Parse numeric fields
                price = _safe_float(row.get("price")) if row.get("price") else None
                rating = _safe_float(row.get("rating")) if row.get("rating") else None
                rating_count = _safe_int(row.get("rating_count")) if row.get("rating_count") else None
                year = _safe_int(row.get("year")) if row.get("year") else None
                
                # Get brand, series, model (required for parseable records)
                brand = row.get("brand") or None
                series = row.get("series") or None
                model = row.get("model") or None
                
                # Helper to get attribute value (empty string becomes None)
                def get_attr(key):
                    val = row.get(key)
                    return val if val else None
                
                record = PCPartRecord(
                    product_id=row["product_id"],
                    product_type=row["product_type"],
                    created_at=row.get("created_at") or _now_iso(),
                    brand=brand if brand else None,
                    series=series if series else None,
                    model=model if model else None,
                    size=row.get("size") or None,
                    color=row.get("color") or None,
                    price=price,
                    year=year,
                    seller=row.get("seller") or None,
                    rating=rating,
                    rating_count=rating_count,
                    raw_name=row.get("raw_name") or row.get("title") or "",
                    # CPU Attributes
                    socket=get_attr("socket"),
                    architecture=get_attr("architecture"),
                    pcie_version=get_attr("pcie_version"),
                    ram_standard=get_attr("ram_standard"),
                    tdp=get_attr("tdp"),
                    # GPU Attributes
                    vram=get_attr("vram"),
                    memory_type=get_attr("memory_type"),
                    cooler_type=get_attr("cooler_type"),
                    variant=get_attr("variant"),
                    is_oc=get_attr("is_oc"),
                    revision=get_attr("revision"),
                    interface=get_attr("interface"),
                    power_connector=get_attr("power_connector"),
                    # Motherboard Attributes
                    chipset=get_attr("chipset"),
                    form_factor=get_attr("form_factor"),
                    # PSU Attributes
                    wattage=get_attr("wattage"),
                    certification=get_attr("certification"),
                    modularity=get_attr("modularity"),
                    atx_version=get_attr("atx_version"),
                    noise=get_attr("noise"),
                    supports_pcie5_power=get_attr("supports_pcie5_power"),
                    # Case Attributes
                    storage=get_attr("storage"),
                    capacity=get_attr("capacity"),
                    storage_type=get_attr("storage_type"),
                    # Cooling Attributes
                    cooling_type=get_attr("cooling_type"),
                    tdp_support=get_attr("tdp_support"),
                )
                records.append(record)
            except Exception as exc:
                logger.error("Error importing CSV row: %s - %s", row, exc)
                continue
    
    logger.info("Imported %d records from CSV %s", len(records), csv_path)
    return records


@dataclass
class PCPartRecord:
    product_id: str
    product_type: str
    created_at: str

    slug: Optional[str] = None
    series: Optional[str] = None
    model: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    price: Optional[float] = None  # Minimum price (best deal)
    year: Optional[int] = None
    seller: Optional[str] = None  # Seller with minimum price (best deal)
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    updated_at: Optional[str] = None
    raw_name: Optional[str] = None
    
    # CPU Attributes
    socket: Optional[str] = None
    architecture: Optional[str] = None
    pcie_version: Optional[str] = None
    ram_standard: Optional[str] = None
    tdp: Optional[str] = None
    
    # GPU Attributes
    vram: Optional[str] = None
    memory_type: Optional[str] = None
    cooler_type: Optional[str] = None
    variant: Optional[str] = None
    is_oc: Optional[str] = None
    revision: Optional[str] = None
    interface: Optional[str] = None
    power_connector: Optional[str] = None
    
    # Motherboard Attributes
    chipset: Optional[str] = None
    form_factor: Optional[str] = None
    
    # PSU Attributes
    wattage: Optional[str] = None
    certification: Optional[str] = None
    modularity: Optional[str] = None
    atx_version: Optional[str] = None
    noise: Optional[str] = None
    supports_pcie5_power: Optional[str] = None
    
    # Case Attributes
    storage: Optional[str] = None
    capacity: Optional[str] = None
    storage_type: Optional[str] = None
    
    # Cooling Attributes
    cooling_type: Optional[str] = None
    tdp_support: Optional[str] = None

    def to_row(self) -> Dict[str, Any]:
        # Generate slug if not provided, fallback to product_id if brand/series/model are all None
        slug = self.slug or _generate_slug(self.brand, self.series, self.model)
        if not slug:
            # Use product_id as fallback to ensure slug is never empty (required by schema)
            slug = self.product_id.replace(":", "-").lower()
        
        return {
            "product_id": self.product_id,
            "slug": slug,
            "product_type": self.product_type,
            "series": self.series,
            "model": self.model,
            "brand": self.brand,
            "size": self.size,
            "color": self.color,
            "price": self.price,
            "year": self.year,
            "seller": self.seller,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "raw_name": self.raw_name,
            # CPU Attributes
            "socket": self.socket,
            "architecture": self.architecture,
            "pcie_version": self.pcie_version,
            "ram_standard": self.ram_standard,
            "tdp": self.tdp,
            # GPU Attributes
            "vram": self.vram,
            "memory_type": self.memory_type,
            "cooler_type": self.cooler_type,
            "variant": self.variant,
            "is_oc": self.is_oc,
            "revision": self.revision,
            "interface": self.interface,
            "power_connector": self.power_connector,
            # Motherboard Attributes
            "chipset": self.chipset,
            "form_factor": self.form_factor,
            # PSU Attributes
            "wattage": self.wattage,
            "certification": self.certification,
            "modularity": self.modularity,
            "atx_version": self.atx_version,
            "noise": self.noise,
            "supports_pcie5_power": self.supports_pcie5_power,
            # Case Attributes
            "storage": self.storage,
            "capacity": self.capacity,
            "storage_type": self.storage_type,
            # Cooling Attributes
            "cooling_type": self.cooling_type,
            "tdp_support": self.tdp_support,
        }


# ---------------------------------------------------------------------------
# Source-specific collectors
# ---------------------------------------------------------------------------


class RapidAPISource:
    """Fetch PC part listings via RapidAPI."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        host: str = DEFAULT_RAPIDAPI_HOST,
        endpoint: str = DEFAULT_RAPIDAPI_ENDPOINT,
        country: str = DEFAULT_RAPIDAPI_COUNTRY,
    ) -> None:
        self.session = session or _create_session()
        self.host = host
        self.endpoint = endpoint
        self.country = country
        self.api_key = RAPIDAPI_KEY

    def fetch(self, category: str, query: str, limit: Optional[int] = 40) -> List[PCPartRecord]:
        if not self.api_key:
            logger.warning("Skipping RapidAPI for %s: RAPIDAPI_KEY not configured", category)
            return []

        logger.info(
            "Fetching RapidAPI data for %s (host=%s, endpoint=%s, limit=%s)",
            category,
            self.host,
            self.endpoint,
            limit if limit is not None else "unlimited",
        )

        records: List[PCPartRecord] = []
        url = f"https://{self.host}{self.endpoint}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.host,
        }

        page = 1
        seen_ids: Set[str] = set()

        while True:
            if limit is not None and len(records) >= limit:
                break

            payload = {
                "query": query,
                "page": str(page),
                "country": self.country,
            }

            try:
                response = self.session.post(
                    url,
                    data=payload,
                    headers=headers,
                    timeout=DEFAULT_TIMEOUT,
                )
                response.raise_for_status()
                payload_json = response.json()
            except requests.HTTPError as exc:
                logger.error("RapidAPI request failed (%s): %s", category, exc)
                break
            except Exception as exc:
                logger.error("RapidAPI unexpected error for %s: %s", category, exc)
                break

            products = self._extract_products(payload_json)
            if not products:
                logger.info("RapidAPI %s page %d returned no products", category, page)
                break

            new_records = 0
            for product in products:
                # Extract productId directly from "productId" field
                product_id_raw = product.get("productId")
                if not product_id_raw:
                    # Fallback to other fields if productId not available
                    product_id_raw = (
                        product.get("product_id")
                        or product.get("item_number")
                        or product.get("sku")
                        or product.get("id")
                    )
                
                if not product_id_raw:
                    continue
                
                # Use productId directly, prefix with source for uniqueness
                product_id = f"rapidapi:{str(product_id_raw)}"

                if product_id in seen_ids:
                    continue

                # Extract title (raw_name)
                title = product.get("title") or product.get("name") or product.get("product_title")
                if not title:
                    continue

                # Parse brand, series, model from title
                brand, series, model = _parse_title_fields(title, category)
                
                # Extract fields as specified
                seller = product.get("source")
                price_value = product.get("price")
                rating_value = product.get("rating")
                rating_count_value = product.get("ratingCount") or product.get("rating_count")
                
                # Extract year if available
                year = None
                year_str = product.get("year") or product.get("releaseYear") or product.get("modelYear")
                if year_str:
                    year = _safe_int(str(year_str))
                
                # Extract size and color if available
                size = product.get("size") or product.get("dimensions")
                color = product.get("color") or product.get("colour")
                
                # Extract attributes
                all_attrs = product.get("specs") or product.get("attributes") or {}
                base_attrs = {}
                
                # Try to extract common base attributes
                if isinstance(all_attrs, dict):
                    base_attrs = all_attrs
                
                # Extract product-type-specific attributes
                if category == "psu":
                    psu_attrs = _extract_psu_attributes(title, series, model)
                    base_attrs.update(psu_attrs)
                elif category == "gpu":
                    gpu_attrs = _extract_gpu_attributes(title, series, model)
                    base_attrs.update(gpu_attrs)
                elif category == "ram":
                    ram_attrs = _extract_ram_attributes(title, series, model)
                    base_attrs.update(ram_attrs)
                elif category == "motherboard":
                    mb_attrs = _extract_motherboard_attributes(title, series, model)
                    base_attrs.update(mb_attrs)
                elif category == "cpu":
                    cpu_attrs = _extract_cpu_attributes(title, series, model)
                    base_attrs.update(cpu_attrs)
                
                # Extract price (this will be the minimum/best deal price)
                price_float = _safe_float(str(price_value) if price_value is not None else None)
                
                # Map attributes from dict to individual fields
                # Convert values to strings as per schema (all attributes stored as TEXT)
                def attr_str(value):
                    if value is None:
                        return None
                    if isinstance(value, bool):
                        return "true" if value else "false"
                    if isinstance(value, (int, float)):
                        return str(value)
                    return str(value) if value else None
                
                record = PCPartRecord(
                    product_id=product_id,
                    product_type=category,
                    created_at=_now_iso(),
                    series=series,
                    model=model,
                    brand=brand,
                    size=size,
                    color=color,
                    price=price_float,  # Minimum price (best deal)
                    year=year,
                    seller=seller,  # Seller with minimum price (best deal)
                    rating=_safe_float(str(rating_value) if rating_value is not None else None),
                    rating_count=_safe_int(str(rating_count_value) if rating_count_value is not None else None),
                    raw_name=title,
                    # CPU Attributes
                    socket=attr_str(base_attrs.get("socket")),
                    architecture=attr_str(base_attrs.get("architecture")),
                    pcie_version=attr_str(base_attrs.get("pcie_version")),
                    ram_standard=attr_str(base_attrs.get("ram_standard")),
                    tdp=attr_str(base_attrs.get("tdp")),
                    # GPU Attributes
                    vram=attr_str(base_attrs.get("vram")),
                    memory_type=attr_str(base_attrs.get("memory_type")),
                    cooler_type=attr_str(base_attrs.get("cooler_type")),
                    variant=attr_str(base_attrs.get("variant")),
                    is_oc=attr_str(base_attrs.get("is_oc")),
                    revision=attr_str(base_attrs.get("revision")),
                    interface=attr_str(base_attrs.get("interface")),
                    power_connector=attr_str(base_attrs.get("power_connector")),
                    # Motherboard Attributes
                    chipset=attr_str(base_attrs.get("chipset")),
                    form_factor=attr_str(base_attrs.get("form_factor")),
                    # PSU Attributes
                    wattage=attr_str(base_attrs.get("wattage")),
                    certification=attr_str(base_attrs.get("certification")),
                    modularity=attr_str(base_attrs.get("modularity")),
                    atx_version=attr_str(base_attrs.get("atx_version")),
                    noise=attr_str(base_attrs.get("noise")),
                    supports_pcie5_power=attr_str(base_attrs.get("supports_pcie5_power")),
                    # Case Attributes
                    storage=attr_str(base_attrs.get("storage")),
                    capacity=attr_str(base_attrs.get("capacity")),
                    storage_type=attr_str(base_attrs.get("storage_type")),
                    # Cooling Attributes
                    cooling_type=attr_str(base_attrs.get("cooling_type")),
                    tdp_support=attr_str(base_attrs.get("tdp_support")),
                )
                records.append(record)
                seen_ids.add(product_id)
                new_records += 1

                if limit is not None and len(records) >= limit:
                    break

            if new_records == 0:
                logger.info("RapidAPI %s page %d produced only duplicates", category, page)
                break

            page += 1
            time.sleep(0.5)

        logger.info("RapidAPI %s: collected %d records", category, len(records))
        return records

    @staticmethod
    def _normalize_stock(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        lower = str(value).lower()
        if "in stock" in lower or "available" in lower:
            return "in_stock"
        if "out of stock" in lower or "unavailable" in lower or "sold out" in lower:
            return "out_of_stock"
        if "pre-order" in lower or "preorder" in lower:
            return "preorder"
        return "unknown"

    @staticmethod
    def _extract_products(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload

        for key in (
            "shopping_results",
            "products",
            "items",
            "data",
            "results",
        ):
            if key in payload and isinstance(payload[key], list):
                return payload[key]

        if "main_item" in payload and isinstance(payload["main_item"], dict):
            return [payload["main_item"]]

        return []


# ---------------------------------------------------------------------------
# Image URL updater
# ---------------------------------------------------------------------------


class ImageURLUpdater:
    """Update image URLs for existing database entries by querying RapidAPI and matching products."""

    def __init__(
        self,
        db_path: str = "data/pc_parts.db",
        session: Optional[requests.Session] = None,
        host: str = DEFAULT_RAPIDAPI_HOST,
        endpoint: str = DEFAULT_RAPIDAPI_ENDPOINT,
        country: str = DEFAULT_RAPIDAPI_COUNTRY,
    ) -> None:
        self.db_path = Path(db_path)
        self.session = session or _create_session()
        self.host = host
        self.endpoint = endpoint
        self.country = country
        self.api_key = RAPIDAPI_KEY
        self._ensure_imageurl_column()

    def _ensure_imageurl_column(self) -> None:
        """Ensure the imageurl column exists in the database."""
        if not self.db_path.exists():
            logger.warning("Database does not exist: %s", self.db_path)
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Check if column exists
            cursor.execute("PRAGMA table_info(pc_parts)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "imageurl" not in columns:
                logger.info("Adding imageurl column to pc_parts table")
                cursor.execute("ALTER TABLE pc_parts ADD COLUMN imageurl TEXT")
                conn.commit()
                logger.info("Successfully added imageurl column")

    def _normalize_name(self, name: str) -> str:
        """Normalize product name for matching (lowercase, remove extra spaces)."""
        if not name:
            return ""
        # Convert to lowercase and remove extra whitespace
        normalized = " ".join(name.lower().split())
        return normalized

    def _extract_image_url(self, product: Dict[str, Any]) -> Optional[str]:
        """Extract image URL from RapidAPI product response."""
        # Try common image URL fields
        image_fields = [
            "image",
            "imageUrl",
            "image_url",
            "thumbnail",
            "thumbnailUrl",
            "thumbnail_url",
            "photo",
            "photoUrl",
            "photo_url",
            "imageLink",
            "image_link",
        ]
        
        for field in image_fields:
            value = product.get(field)
            if value and isinstance(value, str) and value.strip():
                return value.strip()
        
        # Check if there's an images array
        images = product.get("images") or product.get("photos")
        if isinstance(images, list) and len(images) > 0:
            first_image = images[0]
            if isinstance(first_image, str):
                return first_image.strip()
            elif isinstance(first_image, dict):
                url = first_image.get("url") or first_image.get("image") or first_image.get("src")
                if url and isinstance(url, str):
                    return url.strip()
        
        return None

    def _query_rapidapi(self, query: str, page: int = 1) -> List[Dict[str, Any]]:
        """Query RapidAPI for products matching the given query."""
        if not self.api_key:
            logger.warning("Skipping RapidAPI query: RAPIDAPI_KEY not configured")
            return []

        url = f"https://{self.host}{self.endpoint}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.host,
        }

        payload = {
            "query": query,
            "page": str(page),
            "country": self.country,
        }

        try:
            response = self.session.post(
                url,
                data=payload,
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            payload_json = response.json()
            products = RapidAPISource._extract_products(payload_json)
            return products
        except requests.HTTPError as exc:
            logger.error("RapidAPI request failed for query '%s': %s", query, exc)
            return []
        except Exception as exc:
            logger.error("RapidAPI unexpected error for query '%s': %s", query, exc)
            return []

    def update_image_urls(self, limit_per_category: Optional[int] = None) -> Dict[str, int]:
        """Update image URLs for all products in the database.
        
        Args:
            limit_per_category: Maximum number of RapidAPI results to process per category.
                               If None, processes all pages until no more results.
        
        Returns:
            Dictionary mapping category names to number of products updated.
        """
        if not self.api_key:
            logger.warning("Cannot update image URLs: RAPIDAPI_KEY not configured")
            return {}

        if not self.db_path.exists():
            logger.error("Database does not exist: %s", self.db_path)
            return {}

        # Load all existing products from database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT product_id, raw_name, product_type FROM pc_parts WHERE imageurl IS NULL OR imageurl = ''")
            existing_products = cursor.fetchall()

        logger.info("Found %d products without image URLs", len(existing_products))

        # Group products by category
        products_by_category: Dict[str, List[Tuple[str, str, str]]] = {}
        for product_id, raw_name, product_type in existing_products:
            if product_type not in products_by_category:
                products_by_category[product_type] = []
            products_by_category[product_type].append((product_id, raw_name, product_type))

        # Normalize existing product names for matching
        normalized_db_names: Dict[str, Dict[str, str]] = {}
        for category, products in products_by_category.items():
            normalized_db_names[category] = {}
            for product_id, raw_name, _ in products:
                if raw_name:
                    normalized = self._normalize_name(raw_name)
                    if normalized:
                        normalized_db_names[category][product_id] = normalized

        updates_by_category: Dict[str, int] = {}

        # Process each category
        for category, config in ELECTRONICS_CATEGORIES.items():
            query = config["query"]
            logger.info("Processing category '%s' with query '%s'", category, query)

            if category not in products_by_category:
                logger.info("No products without image URLs for category '%s'", category)
                updates_by_category[category] = 0
                continue

            category_products = products_by_category[category]
            category_normalized = normalized_db_names[category]
            logger.info("Searching for %d products in category '%s'", len(category_products), category)

            # Query RapidAPI and match products
            page = 1
            matched_count = 0
            processed_count = 0

            while True:
                if limit_per_category is not None and processed_count >= limit_per_category:
                    break

                products = self._query_rapidapi(query, page)
                if not products:
                    logger.info("No more products for category '%s' at page %d", category, page)
                    break

                # Match products
                for product in products:
                    if limit_per_category is not None and processed_count >= limit_per_category:
                        break

                    processed_count += 1
                    
                    # Extract product name from RapidAPI response
                    product_name = product.get("name") or product.get("title") or product.get("product_title")
                    if not product_name:
                        continue

                    normalized_product_name = self._normalize_name(product_name)

                    # Try to find matching product in database
                    matched_product_id = None
                    best_match_score = 0.0

                    for db_product_id, normalized_db_name in category_normalized.items():
                        # Exact match
                        if normalized_product_name == normalized_db_name:
                            matched_product_id = db_product_id
                            best_match_score = 1.0
                            break
                        
                        # Partial match (check if one contains the other or vice versa)
                        if normalized_db_name in normalized_product_name or normalized_product_name in normalized_db_name:
                            # Calculate a simple similarity score
                            shorter = min(len(normalized_db_name), len(normalized_product_name))
                            longer = max(len(normalized_db_name), len(normalized_product_name))
                            if shorter > 0:
                                similarity = shorter / longer
                                if similarity > best_match_score and similarity >= 0.7:  # 70% similarity threshold
                                    matched_product_id = db_product_id
                                    best_match_score = similarity

                    if matched_product_id and best_match_score >= 0.7:
                        # Extract image URL
                        image_url = self._extract_image_url(product)
                        if image_url:
                            # Update database
                            with sqlite3.connect(self.db_path) as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE pc_parts SET imageurl = ? WHERE product_id = ?",
                                    (image_url, matched_product_id)
                                )
                                conn.commit()
                            
                            matched_count += 1
                            logger.debug(
                                "Matched '%s' (DB: '%s') -> image URL: %s",
                                product_name,
                                category_normalized[matched_product_id],
                                image_url
                            )
                            
                            # Remove from category_normalized to avoid duplicate matches
                            if matched_product_id in category_normalized:
                                del category_normalized[matched_product_id]

                page += 1
                time.sleep(0.5)  # Rate limiting

                # If we've matched all products for this category, break
                if not category_normalized:
                    break

            updates_by_category[category] = matched_count
            logger.info(
                "Category '%s': matched %d/%d products with image URLs",
                category,
                matched_count,
                len(category_products)
            )

        total_updated = sum(updates_by_category.values())
        logger.info("Total products updated with image URLs: %d", total_updated)
        return updates_by_category


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------


class PCPartsDatasetBuilder:
    def __init__(
        self,
        db_path: str = "data/pc_parts.db",
        limit_per_source: Optional[int] = None,
        unparseable_csv_path: Optional[str] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.limit_per_source = limit_per_source if limit_per_source and limit_per_source > 0 else None
        self.unparseable_csv_path = Path(unparseable_csv_path) if unparseable_csv_path else self.db_path.parent / "unparseable_products.csv"

        self._init_database()

        shared_session = _create_session()
        self.rapidapi = RapidAPISource(session=shared_session)
        self._existing_part_ids = self._load_existing_part_ids()

    def _init_database(self) -> None:
        schema_file = PROJECT_ROOT / "dataset_builder" / "pc_parts_schema.sql"
        with sqlite3.connect(self.db_path) as conn:
            with open(schema_file, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()

    def _load_existing_part_ids(self) -> Set[str]:
        if not self.db_path.exists():
            return set()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT product_id FROM pc_parts")
                return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error:
            return set()

    def build(self) -> None:
        total_inserted = 0

        for part_type, config in ELECTRONICS_CATEGORIES.items():
            logger.info("=== Collecting data for %s ===", part_type)
            collected: List[PCPartRecord] = []

            query = config.get("query")
            if not query:
                self._mark_progress("rapidapi", part_type, 0, status="skipped", error="no_query")
                continue

            try:
                rapid_records = self.rapidapi.fetch(
                    category=part_type,
                    query=query,
                    limit=self.limit_per_source,
                )
                collected.extend(rapid_records)
                self._mark_progress("rapidapi", part_type, len(rapid_records))
            except Exception as exc:  # noqa: BLE001
                logger.exception("RapidAPI fetch failed for %s: %s", part_type, exc)
                self._mark_progress("rapidapi", part_type, 0, status="failed", error=str(exc))

            # Separate parseable and unparseable records
            parseable_records = [r for r in collected if _is_parseable(r)]
            unparseable_records = [r for r in collected if not _is_parseable(r)]
            
            # Export unparseable records to CSV for manual editing
            if unparseable_records:
                exported_count = _export_unparseable_to_csv(unparseable_records, self.unparseable_csv_path)
                logger.info("Exported %d unparseable records to %s", exported_count, self.unparseable_csv_path)
            
            # Save only parseable records
            inserted = self._save_records(parseable_records)
            total_inserted += inserted

            logger.info(
                "Finished %s: %d collected (%d parseable, %d unparseable) | %d upserted (db=%s)",
                part_type,
                len(collected),
                len(parseable_records),
                len(unparseable_records),
                inserted,
                self.db_path,
            )

        self._update_stats(total_inserted)
        logger.info("PC parts dataset build complete. Total upserted: %d", total_inserted)

    def import_from_csv(self, csv_path: Optional[str] = None) -> int:
        """Import manually edited CSV file into the database.
        
        Args:
            csv_path: Path to CSV file. If None, uses default unparseable_csv_path.
        
        Returns:
            Number of records imported.
        """
        csv_file = Path(csv_path) if csv_path else self.unparseable_csv_path
        records = _import_from_csv(csv_file)
        
        if not records:
            logger.warning("No records to import from %s", csv_file)
            return 0
        
        # Filter to only parseable records (must have brand, series, model)
        parseable_records = [r for r in records if _is_parseable(r)]
        unparseable_records = [r for r in records if not _is_parseable(r)]
        
        if unparseable_records:
            logger.warning(
                "%d records in CSV are still unparseable (missing brand, series, or model). "
                "These will be skipped. Please edit the CSV and try again.",
                len(unparseable_records)
            )
        
        if not parseable_records:
            logger.warning("No parseable records to import from %s", csv_file)
            return 0
        
        inserted = self._save_records(parseable_records)
        logger.info("Imported %d parseable records from %s", inserted, csv_file)
        
        # Optionally remove imported records from CSV (comment out if you want to keep them)
        # if inserted > 0:
        #     _remove_imported_from_csv(csv_file, parseable_records)
        
        return inserted

    def _load_existing_slugs_and_price(self) -> Dict[str, float]:
        """Load existing slugs and their prices for conflict resolution.
        
        Returns: Dict mapping slug to price (the best deal price)
        """
        if not self.db_path.exists():
            return {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT slug, price FROM pc_parts WHERE slug IS NOT NULL AND price IS NOT NULL")
                return {row[0]: row[1] for row in cursor.fetchall()}
        except sqlite3.Error:
            return {}
    
    def _load_existing_full_data_by_slug(self) -> Dict[str, Dict[str, Any]]:
        """Load full existing record data by slug for minimum price conflict resolution.
        
        Returns: Dict mapping slug to {price, seller, rating, rating_count}
        """
        if not self.db_path.exists():
            return {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT slug, price, seller, rating, rating_count 
                    FROM pc_parts 
                    WHERE slug IS NOT NULL
                """)
                result = {}
                for row in cursor.fetchall():
                    slug, price, seller, rating, rating_count = row
                    if slug:
                        result[slug] = {
                            "price": price,
                            "seller": seller,
                            "rating": rating,
                            "rating_count": rating_count,
                        }
                return result
        except sqlite3.Error:
            return {}

    def _save_records(self, records: List[PCPartRecord]) -> int:
        if not records:
            return 0

        # Load existing slugs and prices for conflict resolution (best deal approach)
        existing_slugs_price = self._load_existing_slugs_and_price()
        existing_full_data = self._load_existing_full_data_by_slug()
        
        unique_rows: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        seen_slugs: Set[str] = set()

        for record in records:
            product_id = record.product_id
            row = record.to_row()
            slug = row.get("slug")
            new_price = row.get("price")
            new_seller = row.get("seller")  # Seller with this price

            # Skip if we've already seen this product_id in this batch
            if product_id in seen_ids or product_id in self._existing_part_ids:
                logger.debug("Skipping duplicate product_id %s", product_id)
                continue

            # Handle slug conflicts: Option 2 - Minimum price approach (best deal)
            if slug and slug in existing_slugs_price:
                existing_price = existing_slugs_price[slug]
                existing_data = existing_full_data.get(slug, {})
                
                if new_price is None:
                    # Skip if no price available
                    logger.debug("Skipping slug %s: new record has no price", slug)
                    continue
                
                if existing_price is not None and new_price >= existing_price:
                    # New price is not better - skip this record (we already have a better deal)
                    logger.debug("Skipping slug %s: new price %.2f >= existing price %.2f (keeping better deal)", slug, new_price, existing_price)
                    continue
                
                    row["seller"] = new_seller
                    # Use the new record's rating and rating_count (no aggregation)
                    # rating and rating_count are already in row from record.to_row()
                
                # Set updated_at for updates
                row["updated_at"] = _now_iso()
                logger.debug("Replacing slug %s: new price %.2f < existing price %.2f (found better deal from %s)", slug, new_price, existing_price, new_seller)
            # else: new record - price and seller are already set in row from record.to_row()

            # Skip if we've already seen this slug in this batch
            if slug and slug in seen_slugs:
                logger.debug("Skipping duplicate slug %s in batch", slug)
                continue

            # For new records, ensure created_at is set and updated_at is None
            if slug not in existing_slugs_price:
                row["updated_at"] = None

            unique_rows.append(row)
            seen_ids.add(product_id)
            if slug:
                seen_slugs.add(slug)

        if not unique_rows:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Delete old records that will be replaced (we have a better deal with lower price)
            for row in unique_rows:
                slug = row.get("slug")
                if slug and slug in existing_slugs_price:
                    # Delete old record with conflicting slug (we're replacing with better deal)
                    cursor.execute("DELETE FROM pc_parts WHERE slug = ?", (slug,))
            
            # Now insert all records
            # Handle both product_id and slug conflicts
            inserted = 0
            for row in unique_rows:
                try:
                    cursor.execute(
                        """
                        INSERT INTO pc_parts (
                            product_id, slug, product_type, series, model, brand,
                            size, color, price, year, seller, rating, rating_count,
                            created_at, updated_at, raw_name,
                            socket, architecture, pcie_version, ram_standard, tdp,
                            vram, memory_type, cooler_type, variant, is_oc, revision, interface, power_connector,
                            chipset, form_factor,
                            wattage, certification, modularity, atx_version, noise, supports_pcie5_power,
                            storage, capacity, storage_type,
                            cooling_type, tdp_support
                        ) VALUES (
                            :product_id, :slug, :product_type, :series, :model, :brand,
                            :size, :color, :price, :year, :seller, :rating, :rating_count,
                            :created_at, :updated_at, :raw_name,
                            :socket, :architecture, :pcie_version, :ram_standard, :tdp,
                            :vram, :memory_type, :cooler_type, :variant, :is_oc, :revision, :interface, :power_connector,
                            :chipset, :form_factor,
                            :wattage, :certification, :modularity, :atx_version, :noise, :supports_pcie5_power,
                            :storage, :capacity, :storage_type,
                            :cooling_type, :tdp_support
                        )
                        ON CONFLICT(product_id) DO UPDATE SET
                            slug=COALESCE(excluded.slug, pc_parts.slug),
                            product_type=excluded.product_type,
                            series=COALESCE(excluded.series, pc_parts.series),
                            model=COALESCE(excluded.model, pc_parts.model),
                            brand=COALESCE(excluded.brand, pc_parts.brand),
                            size=COALESCE(excluded.size, pc_parts.size),
                            color=COALESCE(excluded.color, pc_parts.color),
                            price=COALESCE(excluded.price, pc_parts.price),
                            year=COALESCE(excluded.year, pc_parts.year),
                            seller=COALESCE(excluded.seller, pc_parts.seller),
                            rating=COALESCE(excluded.rating, pc_parts.rating),
                            rating_count=COALESCE(excluded.rating_count, pc_parts.rating_count),
                            updated_at=excluded.updated_at,
                            raw_name=COALESCE(excluded.raw_name, pc_parts.raw_name),
                            socket=COALESCE(excluded.socket, pc_parts.socket),
                            architecture=COALESCE(excluded.architecture, pc_parts.architecture),
                            pcie_version=COALESCE(excluded.pcie_version, pc_parts.pcie_version),
                            ram_standard=COALESCE(excluded.ram_standard, pc_parts.ram_standard),
                            tdp=COALESCE(excluded.tdp, pc_parts.tdp),
                            vram=COALESCE(excluded.vram, pc_parts.vram),
                            memory_type=COALESCE(excluded.memory_type, pc_parts.memory_type),
                            cooler_type=COALESCE(excluded.cooler_type, pc_parts.cooler_type),
                            variant=COALESCE(excluded.variant, pc_parts.variant),
                            is_oc=COALESCE(excluded.is_oc, pc_parts.is_oc),
                            revision=COALESCE(excluded.revision, pc_parts.revision),
                            interface=COALESCE(excluded.interface, pc_parts.interface),
                            power_connector=COALESCE(excluded.power_connector, pc_parts.power_connector),
                            chipset=COALESCE(excluded.chipset, pc_parts.chipset),
                            form_factor=COALESCE(excluded.form_factor, pc_parts.form_factor),
                            wattage=COALESCE(excluded.wattage, pc_parts.wattage),
                            certification=COALESCE(excluded.certification, pc_parts.certification),
                            modularity=COALESCE(excluded.modularity, pc_parts.modularity),
                            atx_version=COALESCE(excluded.atx_version, pc_parts.atx_version),
                            noise=COALESCE(excluded.noise, pc_parts.noise),
                            supports_pcie5_power=COALESCE(excluded.supports_pcie5_power, pc_parts.supports_pcie5_power),
                            storage=COALESCE(excluded.storage, pc_parts.storage),
                            capacity=COALESCE(excluded.capacity, pc_parts.capacity),
                            storage_type=COALESCE(excluded.storage_type, pc_parts.storage_type),
                            cooling_type=COALESCE(excluded.cooling_type, pc_parts.cooling_type),
                            tdp_support=COALESCE(excluded.tdp_support, pc_parts.tdp_support)
                        """,
                        row,
                    )
                    if cursor.rowcount > 0:
                        inserted += 1
                except sqlite3.IntegrityError as e:
                    # Handle slug conflict - delete old record and retry if price is lower
                    if "UNIQUE constraint failed: pc_parts.slug" in str(e):
                        slug = row.get("slug")
                        if slug:
                            cursor.execute("SELECT price FROM pc_parts WHERE slug = ?", (slug,))
                            result = cursor.fetchone()
                            if result and result[0] is not None:
                                existing_price = result[0]
                                new_price = row.get("price")
                                if new_price is not None and new_price < existing_price:
                                    # Delete old record and insert new one
                                    cursor.execute("DELETE FROM pc_parts WHERE slug = ?", (slug,))
                                    cursor.execute(
                                        """
                                        INSERT INTO pc_parts (
                                            product_id, slug, product_type, series, model, brand,
                                            size, color, price, year, seller, rating, rating_count,
                                            created_at, updated_at, raw_name,
                                            socket, architecture, pcie_version, ram_standard, tdp,
                                            vram, memory_type, cooler_type, variant, is_oc, revision, interface, power_connector,
                                            chipset, form_factor,
                                            wattage, certification, modularity, atx_version, noise, supports_pcie5_power,
                                            storage, capacity, storage_type,
                                            cooling_type, tdp_support
                                        ) VALUES (
                                            :product_id, :slug, :product_type, :series, :model, :brand,
                                            :size, :color, :price, :year, :seller, :rating, :rating_count,
                                            :created_at, :updated_at, :raw_name,
                                            :socket, :architecture, :pcie_version, :ram_standard, :tdp,
                                            :vram, :memory_type, :cooler_type, :variant, :is_oc, :revision, :interface, :power_connector,
                                            :chipset, :form_factor,
                                            :wattage, :certification, :modularity, :atx_version, :noise, :supports_pcie5_power,
                                            :storage, :capacity, :storage_type,
                                            :cooling_type, :tdp_support
                                        )
                                        """,
                                        row,
                                    )
                                    inserted += 1
                                else:
                                    logger.debug("Skipping slug %s: new price not lower", slug)
                            else:
                                # No existing price, delete and insert
                                cursor.execute("DELETE FROM pc_parts WHERE slug = ?", (slug,))
                                cursor.execute(
                                    """
                                    INSERT INTO pc_parts (
                                        product_id, slug, product_type, series, model, brand,
                                        size, color, price, year, seller, rating, rating_count,
                                        created_at, updated_at, raw_name,
                                        socket, architecture, pcie_version, ram_standard, tdp,
                                        vram, memory_type, cooler_type, variant, is_oc, revision, interface, power_connector,
                                        chipset, form_factor,
                                        wattage, certification, modularity, atx_version, noise, supports_pcie5_power,
                                        storage, capacity, storage_type,
                                        cooling_type, tdp_support
                                    ) VALUES (
                                        :product_id, :slug, :product_type, :series, :model, :brand,
                                        :size, :color, :price, :year, :seller, :rating, :rating_count,
                                        :created_at, :updated_at, :raw_name,
                                        :socket, :architecture, :pcie_version, :ram_standard, :tdp,
                                        :vram, :memory_type, :cooler_type, :variant, :is_oc, :revision, :interface, :power_connector,
                                        :chipset, :form_factor,
                                        :wattage, :certification, :modularity, :atx_version, :noise, :supports_pcie5_power,
                                        :storage, :capacity, :storage_type,
                                        :cooling_type, :tdp_support
                                    )
                                    """,
                                    row,
                                )
                                inserted += 1
                    else:
                        raise
            conn.commit()

        self._existing_part_ids.update(seen_ids)
        return inserted

    def _mark_progress(
        self,
        source: str,
        part_type: str,
        count: int,
        *,
        status: str = "completed",
        error: Optional[str] = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pc_parts_fetch_progress (
                    source, part_type, items_fetched, fetched_at, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    part_type,
                    count,
                    _now_iso(),
                    status,
                    error,
                ),
            )
            conn.commit()

    def _update_stats(self, total_upserted: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), COUNT(DISTINCT product_id) FROM pc_parts")
            total_records, distinct_parts = cursor.fetchone()

            stats = {
                "last_build": _now_iso(),
                "total_records": str(total_records or 0),
                "unique_parts": str(distinct_parts or 0),
                "upserted_this_run": str(total_upserted),
            }

            for key, value in stats.items():
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pc_parts_dataset_stats (key, value, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (key, value, _now_iso()),
                )

            conn.commit()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the local PC parts SQLite database")
    parser.add_argument(
        "--db-path",
        default="data/pc_parts.db",
        help="Output SQLite database path (default: data/pc_parts.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Number of records to fetch per category (default: 0 meaning unlimited)",
    )
    parser.add_argument(
        "--unparseable-csv",
        default=None,
        help="Path to CSV file for unparseable products (default: data/unparseable_products.csv)",
    )
    parser.add_argument(
        "--import-csv",
        default=None,
        help="Import from CSV file instead of fetching. Provide path to CSV file.",
    )
    parser.add_argument(
        "--update-images",
        action="store_true",
        help="Update image URLs for existing products in the database by querying RapidAPI.",
    )
    parser.add_argument(
        "--image-limit",
        type=int,
        default=None,
        help="Maximum number of RapidAPI results to process per category when updating images (default: unlimited).",
    )

    args = parser.parse_args()

    if args.update_images:
        # Update image URLs
        updater = ImageURLUpdater(db_path=args.db_path)
        results = updater.update_image_urls(limit_per_category=args.image_limit)
        print(f"Image URL update complete:")
        for category, count in results.items():
            print(f"  {category}: {count} products updated")
        total = sum(results.values())
        print(f"Total: {total} products updated with image URLs")
    else:
        builder = PCPartsDatasetBuilder(
            db_path=args.db_path,
            limit_per_source=args.limit,
            unparseable_csv_path=args.unparseable_csv,
        )
        
        if args.import_csv:
            # Import from CSV
            imported = builder.import_from_csv(args.import_csv)
            print(f"Imported {imported} records from {args.import_csv}")
        else:
            # Normal build process
            builder.build()


if __name__ == "__main__":
    main()

