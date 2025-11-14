#!/usr/bin/env python3
"""
Build a Neo4j knowledge graph describing PC component compatibility.

The loader ingests product data from the local ``pc_parts.db`` SQLite database,
normalizes seller-agnostic component nodes (CPU, GPU, motherboard, PSU, case,
cooling, RAM, storage), derives attributes and explicit constraints, and writes
nodes plus typed compatibility edges into Neo4j.

Usage example:

    python scripts/build_pc_parts_kg.py \
        --db-path data/pc_parts.db \
        --neo4j-uri bolt://localhost:7687 \
        --neo4j-user neo4j \
        --neo4j-password password \
        --namespace pc_parts \
        --limit 200 \
        --purge

Environment variables ``PC_PARTS_DB``, ``NEO4J_URI``, ``NEO4J_USER``, and
``NEO4J_PASSWORD`` are respected as defaults.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import re
import sqlite3
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from dotenv import load_dotenv

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - handled at runtime
    GraphDatabase = None  # type: ignore


LOGGER = logging.getLogger("pc_parts_kg")

load_dotenv()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AttributeFact:
    kind: str
    value: str
    label: Optional[str] = None
    numeric: Optional[float] = None
    unit: Optional[str] = None
    provenance: Optional[str] = None


@dataclass
class ConstraintFact:
    kind: str
    value: float
    unit: str
    label: Optional[str] = None
    provenance: Optional[str] = None


@dataclass
class ComponentRecord:
    slug: str
    component_type: str
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    sellers: Set[str] = field(default_factory=set)
    prices: List[float] = field(default_factory=list)
    attributes: List[AttributeFact] = field(default_factory=list)
    constraints: List[ConstraintFact] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_examples: List[Dict[str, Any]] = field(default_factory=list)

    _attribute_index: Dict[Tuple[str, str], AttributeFact] = field(
        default_factory=dict, init=False, repr=False
    )
    _constraint_index: Dict[Tuple[str, float], ConstraintFact] = field(
        default_factory=dict, init=False, repr=False
    )

    def add_attribute(self, fact: AttributeFact) -> None:
        key = (fact.kind, fact.value.lower())
        existing = self._attribute_index.get(key)
        if existing:
            if existing.numeric is None and fact.numeric is not None:
                existing.numeric = fact.numeric
            if not existing.provenance and fact.provenance:
                existing.provenance = fact.provenance
            return
        self._attribute_index[key] = fact
        self.attributes.append(fact)

    def add_constraint(self, fact: ConstraintFact) -> None:
        key = (fact.kind, fact.value)
        existing = self._constraint_index.get(key)
        if existing:
            if not existing.provenance and fact.provenance:
                existing.provenance = fact.provenance
            return
        self._constraint_index[key] = fact
        self.constraints.append(fact)

    @property
    def price_summary(self) -> Dict[str, Optional[float]]:
        if not self.prices:
            return {"min": None, "max": None, "avg": None}
        return {
            "min": min(self.prices),
            "max": max(self.prices),
            "avg": round(statistics.mean(self.prices), 2),
        }

    def to_payload(self) -> Dict[str, Any]:
        stats = self.price_summary
        return {
            "slug": self.slug,
            "name": self.name,
            "type": self.component_type,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "seller_count": len(self.sellers),
            "sellers": sorted(self.sellers),
            "price_min": stats["min"],
            "price_max": stats["max"],
            "price_avg": stats["avg"],
            "attributes": [
                dataclasses.asdict(attr) for attr in self.attributes
            ],
            "constraints": [
                dataclasses.asdict(constraint) for constraint in self.constraints
            ],
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Regex helpers and heuristics
# ---------------------------------------------------------------------------


SPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
CAPACITY_GB_RE = re.compile(r"(\d+)\s*x\s*(\d+)\s*gb", re.IGNORECASE)
SINGLE_CAPACITY_GB_RE = re.compile(r"(\d{1,4})\s*gb", re.IGNORECASE)
CAPACITY_TB_RE = re.compile(r"(\d+(?:\.\d+)?)\s*tb", re.IGNORECASE)
SPEED_RE = re.compile(r"(\d{3,5})\s*(?:mhz|mt/s)", re.IGNORECASE)
WATTAGE_RE = re.compile(r"(\d{3,4})\s*(?:w|watt)", re.IGNORECASE)
SOCKET_PATTERNS = [
    re.compile(r"\b(lga)\s*-?\s*(\d{3,5})\b", re.IGNORECASE),
    re.compile(r"\b(am\d+)\b", re.IGNORECASE),
    re.compile(r"\b(strx\d|trx40|swrx8|str5|sp3)\b", re.IGNORECASE),
]
DDR_RE = re.compile(r"\b(ddr\d)\b", re.IGNORECASE)
PCIe_RE = re.compile(r"pcie?\s*(\d(?:\.\d)?)", re.IGNORECASE)

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


SELLER_KEYWORDS = {
    "amazon",
    "amazon marketplace",
    "best buy",
    "bestbuy",
    "bhphoto",
    "costco",
    "ebay",
    "newegg",
    "newegg inc.",
    "newegg marketplace",
    "target",
    "walmart",
    "walmart marketplace",
    "micro center",
    "microcenter",
    "staples",
    "office depot",
    "lenovo store",
    "dell store",
}

SELLER_DELIMS_RE = re.compile(r"\s*[-–|]\s*")


def is_retailer(token: str) -> bool:
    normalized = token.lower().strip(" .,'\"")
    if not normalized:
        return False
    if normalized in SELLER_KEYWORDS:
        return True
    # Split composite names (e.g., "walmart marketplace")
    parts = [part for part in re.split(r"\s+|&|/", normalized) if part]
    return parts and all(part in SELLER_KEYWORDS for part in parts)


def strip_seller_prefix(name: str) -> str:
    current = name.strip()
    for _ in range(4):
        split = SELLER_DELIMS_RE.split(current, maxsplit=1)
        if len(split) != 2:
            break
        prefix, rest = split[0].strip(), split[1].strip()
        if not prefix:
            break
        if is_retailer(prefix):
            current = rest
            continue
        # Handle multi-token prefixes separated with '-' (e.g., "Walmart - Newegg Inc.")
        sub_parts = [part.strip() for part in prefix.split("-") if part.strip()]
        if sub_parts and all(is_retailer(part) for part in sub_parts):
            current = rest
            continue
        break
    return current or name


def guess_brand(name: str) -> Optional[str]:
    tokens = re.split(r"\s+", name)
    if not tokens:
        return None
    candidate = tokens[0].strip("()[]{}")
    if not candidate or is_retailer(candidate):
        return None
    if candidate.isupper():
        return candidate
    return candidate.title()


def clean_manufacturer(name: Optional[str], fallback: Optional[str]) -> Optional[str]:
    if not name:
        return fallback
    candidate = name.strip()
    if not candidate:
        return fallback
    if is_retailer(candidate):
        return fallback
    segments = [seg.strip() for seg in re.split(r"[-/|]", candidate) if seg.strip()]
    if segments and all(is_retailer(seg) for seg in segments):
        return fallback
    return candidate


def build_display_name(base_name: str, component_type: str) -> str:
    type_token = component_type.upper()
    if base_name.upper().endswith(f"({type_token})"):
        return base_name
    return f"{base_name} ({type_token})"


def normalize_whitespace(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def slugify(value: str) -> str:
    cleaned = NON_ALNUM_RE.sub("-", value.lower()).strip("-")
    return cleaned or "component"


def extract_socket(text: str) -> Optional[str]:
    for pattern in SOCKET_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = [g for g in match.groups() if g]
            joined = " ".join(group.upper() for group in groups)
            return joined or match.group(0).upper()
    return None


def extract_ram_standard(text: str) -> Optional[str]:
    matches = DDR_RE.findall(text)
    return max((match.upper() for match in matches), default=None)


def extract_form_factors(text: str) -> Set[str]:
    found: Set[str] = set()
    for token, label in FORM_FACTOR_MAP.items():
        if token in text:
            found.add(label)
    return found


def extract_capacity_gb(name: str) -> Optional[float]:
    combo = CAPACITY_GB_RE.search(name)
    if combo:
        return float(int(combo.group(1)) * int(combo.group(2)))
    tb_match = CAPACITY_TB_RE.search(name)
    if tb_match:
        return float(tb_match.group(1)) * 1024
    single = SINGLE_CAPACITY_GB_RE.findall(name)
    if single:
        numeric = max(int(value) for value in single)
        return float(numeric)
    return None


def extract_speed_mhz(name: str) -> Optional[float]:
    speed = SPEED_RE.search(name)
    if speed:
        return float(speed.group(1))
    dash_speed = re.search(r"ddr\d[-\s]*(\d{3,5})", name, re.IGNORECASE)
    if dash_speed:
        return float(dash_speed.group(1))
    return None


def extract_radiator_size(name: str) -> Optional[int]:
    match = re.search(r"(\d{3})\s*mm", name)
    if match:
        return int(match.group(1))
    multi_match = re.findall(r"(\d{2})\s*cm", name)
    if multi_match:
        largest = max(int(size) for size in multi_match)
        return largest * 10
    return None


GPU_SERIES_METADATA: Sequence[Tuple[re.Pattern[str], Dict[str, Any]]] = [
    (re.compile(r"rtx\s*4090", re.IGNORECASE), {"series": "RTX 4090", "vendor": "NVIDIA", "pcie": 4.0, "psu": 850, "tdp": 450}),
    (re.compile(r"rtx\s*4080\s*super", re.IGNORECASE), {"series": "RTX 4080 SUPER", "vendor": "NVIDIA", "pcie": 4.0, "psu": 850, "tdp": 320}),
    (re.compile(r"rtx\s*4080", re.IGNORECASE), {"series": "RTX 4080", "vendor": "NVIDIA", "pcie": 4.0, "psu": 750, "tdp": 320}),
    (re.compile(r"rtx\s*4070\s*ti\s*super", re.IGNORECASE), {"series": "RTX 4070 Ti SUPER", "vendor": "NVIDIA", "pcie": 4.0, "psu": 750, "tdp": 285}),
    (re.compile(r"rtx\s*4070\s*ti", re.IGNORECASE), {"series": "RTX 4070 Ti", "vendor": "NVIDIA", "pcie": 4.0, "psu": 700, "tdp": 285}),
    (re.compile(r"rtx\s*4070", re.IGNORECASE), {"series": "RTX 4070", "vendor": "NVIDIA", "pcie": 4.0, "psu": 650, "tdp": 220}),
    (re.compile(r"rtx\s*4060\s*ti", re.IGNORECASE), {"series": "RTX 4060 Ti", "vendor": "NVIDIA", "pcie": 4.0, "psu": 600, "tdp": 165}),
    (re.compile(r"rtx\s*4060", re.IGNORECASE), {"series": "RTX 4060", "vendor": "NVIDIA", "pcie": 4.0, "psu": 550, "tdp": 160}),
    (re.compile(r"rtx\s*3050", re.IGNORECASE), {"series": "RTX 3050", "vendor": "NVIDIA", "pcie": 4.0, "psu": 500, "tdp": 130}),
    (re.compile(r"rtx\s*3080", re.IGNORECASE), {"series": "RTX 3080", "vendor": "NVIDIA", "pcie": 4.0, "psu": 750, "tdp": 320}),
    (re.compile(r"rtx\s*3070", re.IGNORECASE), {"series": "RTX 3070", "vendor": "NVIDIA", "pcie": 4.0, "psu": 650, "tdp": 220}),
    (re.compile(r"rtx\s*3060", re.IGNORECASE), {"series": "RTX 3060", "vendor": "NVIDIA", "pcie": 4.0, "psu": 550, "tdp": 170}),
    (re.compile(r"gtx\s*1660", re.IGNORECASE), {"series": "GTX 1660", "vendor": "NVIDIA", "pcie": 3.0, "psu": 450, "tdp": 120}),
    (re.compile(r"gtx\s*1650", re.IGNORECASE), {"series": "GTX 1650", "vendor": "NVIDIA", "pcie": 3.0, "psu": 350, "tdp": 75}),
    (re.compile(r"rx\s*7900\s*xtx", re.IGNORECASE), {"series": "RX 7900 XTX", "vendor": "AMD", "pcie": 4.0, "psu": 850, "tdp": 355}),
    (re.compile(r"rx\s*7900\s*xt", re.IGNORECASE), {"series": "RX 7900 XT", "vendor": "AMD", "pcie": 4.0, "psu": 800, "tdp": 315}),
    (re.compile(r"rx\s*7800\s*xt", re.IGNORECASE), {"series": "RX 7800 XT", "vendor": "AMD", "pcie": 4.0, "psu": 700, "tdp": 263}),
    (re.compile(r"rx\s*7700\s*xt", re.IGNORECASE), {"series": "RX 7700 XT", "vendor": "AMD", "pcie": 4.0, "psu": 700, "tdp": 245}),
    (re.compile(r"rx\s*7600", re.IGNORECASE), {"series": "RX 7600", "vendor": "AMD", "pcie": 4.0, "psu": 550, "tdp": 165}),
    (re.compile(r"rx\s*6700", re.IGNORECASE), {"series": "RX 6700", "vendor": "AMD", "pcie": 4.0, "psu": 600, "tdp": 230}),
    (re.compile(r"rx\s*6600", re.IGNORECASE), {"series": "RX 6600", "vendor": "AMD", "pcie": 4.0, "psu": 500, "tdp": 132}),
    (re.compile(r"rx\s*580", re.IGNORECASE), {"series": "RX 580", "vendor": "AMD", "pcie": 3.0, "psu": 500, "tdp": 185}),
    (re.compile(r"arc\s*a770", re.IGNORECASE), {"series": "Arc A770", "vendor": "Intel", "pcie": 4.0, "psu": 650, "tdp": 225}),
    (re.compile(r"arc\s*a750", re.IGNORECASE), {"series": "Arc A750", "vendor": "Intel", "pcie": 4.0, "psu": 600, "tdp": 225}),
    (re.compile(r"arc\s*b580", re.IGNORECASE), {"series": "Arc B580", "vendor": "Intel", "pcie": 4.0, "psu": 550, "tdp": 185}),
]


CHIPSET_METADATA: Dict[str, Dict[str, Any]] = {
    "z890": {"socket": "LGA 1851", "pcie": 5.0, "ram": "DDR5"},
    "b850": {"socket": "LGA 1851", "pcie": 5.0, "ram": "DDR5"},
    "h870": {"socket": "LGA 1851", "pcie": 5.0, "ram": "DDR5"},
    "z790": {"socket": "LGA 1700", "pcie": 5.0, "ram": "DDR5"},
    "z690": {"socket": "LGA 1700", "pcie": 5.0, "ram": "DDR5"},
    "b760": {"socket": "LGA 1700", "pcie": 5.0, "ram": "DDR5"},
    "b660": {"socket": "LGA 1700", "pcie": 4.0, "ram": "DDR4"},
    "h610": {"socket": "LGA 1700", "pcie": 3.0, "ram": "DDR4"},
    "x870e": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "x870": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "b850m": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "b650": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "b650e": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "a620": {"socket": "AM5", "pcie": 4.0, "ram": "DDR5"},
    "x670": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "x670e": {"socket": "AM5", "pcie": 5.0, "ram": "DDR5"},
    "x570": {"socket": "AM4", "pcie": 4.0, "ram": "DDR4"},
    "b550": {"socket": "AM4", "pcie": 4.0, "ram": "DDR4"},
    "b450": {"socket": "AM4", "pcie": 3.0, "ram": "DDR4"},
    "x470": {"socket": "AM4", "pcie": 3.0, "ram": "DDR4"},
    "z490": {"socket": "LGA 1200", "pcie": 3.0, "ram": "DDR4"},
    "z390": {"socket": "LGA 1151", "pcie": 3.0, "ram": "DDR4"},
    "x299": {"socket": "LGA 2066", "pcie": 3.0, "ram": "DDR4"},
    "w790": {"socket": "LGA 4677", "pcie": 5.0, "ram": "DDR5"},
    "wrx90e": {"socket": "sTR5", "pcie": 5.0, "ram": "DDR5"},
    "trx40": {"socket": "sTRX4", "pcie": 4.0, "ram": "DDR4"},
    "wrx80": {"socket": "sWRX8", "pcie": 4.0, "ram": "DDR4"},
}


COOLER_TDP_CAPACITY = {
    120: 180.0,
    140: 200.0,
    240: 250.0,
    280: 300.0,
    360: 350.0,
    420: 400.0,
}


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------


def fetch_rows(conn: sqlite3.Connection, part_type: str, limit: Optional[int]) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            part_id,
            source,
            COALESCE(manufacturer, '') AS manufacturer,
            product_name,
            model_number,
            series,
            price,
            seller,
            COALESCE(review_count, 0) AS review_count
        FROM pc_parts
        WHERE part_type = ?
        ORDER BY
            COALESCE(review_count, 0) DESC,
            CASE WHEN price IS NULL THEN 1 ELSE 0 END,
            COALESCE(price, 0) ASC
    """
    params: List[Any] = [part_type]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(sql, params)
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    LOGGER.info("Fetched %d %s rows", len(rows), part_type)
    return rows


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


def _wrap_edge(from_slug: str, to_slug: str, props: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"from": from_slug, "to": to_slug, "props": props or {}}


def parse_gpu(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    metadata = next((meta for pattern, meta in GPU_SERIES_METADATA if pattern.search(lower_name)), None)
    series = metadata["series"] if metadata else None
    vendor = metadata.get("vendor") if metadata else None
    pcie_version = metadata.get("pcie", 4.0) if metadata else 4.0
    recommended_psu = metadata.get("psu", 550) if metadata else 550
    tdp = metadata.get("tdp", 200) if metadata else 200

    memory_gb = extract_capacity_gb(lower_name)

    model = series or product_name
    vendor_name = manufacturer or vendor or brand_guess or "Generic"
    slug = slugify(f"{vendor_name} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer or vendor or brand_guess,
        model=model,
        metadata={
            "pcie_requirement": pcie_version,
            "tdp_watts": tdp,
            "recommended_psu_watts": recommended_psu,
            "series_source": metadata["series"] if metadata else "name_inferred",
            "base_name": product_name,
        },
    )

    component.add_attribute(
        AttributeFact(
            kind="interface",
            value=f"PCIe {pcie_version:.1f} x16",
            label="PCIe Interface",
            numeric=pcie_version,
            provenance="heuristic_series_mapping",
        )
    )
    if memory_gb:
        component.add_attribute(
            AttributeFact(
                kind="vram",
                value=f"{int(memory_gb)} GB",
                label="Video Memory",
                numeric=float(memory_gb),
                unit="GB",
                provenance="product_name_parse",
            )
        )

    component.add_constraint(
        ConstraintFact(
            kind="psu_requirement",
            value=float(recommended_psu),
            unit="W",
            label="Recommended PSU Wattage",
            provenance="heuristic_series_mapping",
        )
    )
    return component


def parse_psu(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    wattage_match = WATTAGE_RE.search(lower_name)
    wattage = int(wattage_match.group(1)) if wattage_match else None

    efficiency_match = re.search(r"80\s*\+\s*(platinum|gold|silver|bronze|titanium|white)", lower_name)
    efficiency = efficiency_match.group(1).title() if efficiency_match else None

    form_factor = None
    for token, label in FORM_FACTOR_MAP.items():
        if token in lower_name:
            form_factor = label
            break

    model_tokens = []
    if wattage:
        model_tokens.append(f"{wattage}W")
    if efficiency:
        model_tokens.append(f"80+ {efficiency}")
    if form_factor:
        model_tokens.append(form_factor)
    base_model = " ".join(model_tokens) or product_name

    brand = manufacturer or brand_guess or "Generic"
    slug = slugify(f"{brand} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        model=base_model,
        metadata={
            "wattage": wattage,
            "efficiency": efficiency,
            "form_factor": form_factor,
            "base_name": product_name,
        },
    )

    if wattage:
        component.add_attribute(
            AttributeFact(
                kind="wattage",
                value=f"{wattage} W",
                label="Total Wattage",
                numeric=float(wattage),
                unit="W",
                provenance="product_name_parse",
            )
        )
    if efficiency:
        component.add_attribute(
            AttributeFact(
                kind="efficiency",
                value=f"80+ {efficiency}",
                label="Efficiency Rating",
                provenance="product_name_parse",
            )
        )
    if form_factor:
        component.add_attribute(
            AttributeFact(
                kind="form_factor",
                value=form_factor,
                label="PSU Form Factor",
                provenance="product_name_parse",
            )
        )

    return component


def parse_motherboard(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    socket = extract_socket(lower_name)

    chipset_match = re.search(r"\b([a-z]\d{3,4}[a-z]?|[abwz]\d{3}|wrx90e|trx40|wrx80)\b", lower_name)
    chipset = chipset_match.group(1).upper() if chipset_match else None

    chipset_meta = CHIPSET_METADATA.get(chipset.lower()) if chipset else None
    if chipset_meta and not socket:
        socket = chipset_meta.get("socket")

    ram_standard = extract_ram_standard(lower_name) or (chipset_meta.get("ram") if chipset_meta else None)
    form_factors = extract_form_factors(lower_name)
    form_factor = next(iter(form_factors)) if form_factors else None

    explicit_pcie = None
    pcie_match = PCIe_RE.search(lower_name)
    if pcie_match:
        try:
            explicit_pcie = float(pcie_match.group(1))
        except ValueError:
            explicit_pcie = None
    pcie_version = explicit_pcie or (chipset_meta["pcie"] if chipset_meta else 4.0)

    model_tokens = [token for token in [chipset, form_factor, socket] if token]
    model = " ".join(model_tokens) or product_name

    brand = manufacturer or brand_guess or "Generic"
    slug = slugify(f"{brand} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        model=model,
        metadata={
            "chipset": chipset,
            "socket": socket,
            "pcie_version": pcie_version,
            "ram_standard": ram_standard,
            "form_factor": form_factor,
            "base_name": product_name,
        },
    )

    if socket:
        component.add_attribute(
            AttributeFact(
                kind="socket",
                value=socket,
                label="CPU Socket",
                provenance="product_name_parse",
            )
        )
    if chipset:
        component.add_attribute(
            AttributeFact(
                kind="chipset",
                value=chipset,
                label="Chipset",
                provenance="product_name_parse",
            )
        )
    if ram_standard:
        component.add_attribute(
            AttributeFact(
                kind="ram_standard",
                value=ram_standard,
                label="Memory Support",
                provenance="product_name_parse",
            )
        )
    if form_factor:
        component.add_attribute(
            AttributeFact(
                kind="form_factor",
                value=form_factor,
                label="Motherboard Form Factor",
                provenance="product_name_parse",
            )
        )
    component.add_attribute(
        AttributeFact(
            kind="pcie_version",
            value=f"PCIe {pcie_version:.1f}",
            label="PCIe Version",
            numeric=pcie_version,
            provenance="chipset_mapping" if chipset_meta else "default_assumption",
        )
    )

    return component


def _amd_cpu_metadata(lower_name: str) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[str]]:
    match = re.search(r"ryzen\s+(\d)\s+(\d{4,5})", lower_name)
    tier = int(match.group(1)) if match else None
    digits = match.group(2) if match else ""
    generation = int(digits[0]) if digits else None
    socket = None
    ram = None
    pcie = None
    tdp = None
    arch = "AMD Ryzen"

    if "threadripper" in lower_name:
        socket = "sTR5" if "79" in digits or "7980" in lower_name else "sTRX4"
        ram = "DDR5" if socket == "sTR5" else "DDR4"
        pcie = 5.0 if socket == "sTR5" else 4.0
        tdp = 350.0 if socket == "sTR5" else 280.0
        arch = "AMD Threadripper"
        return socket, ram, pcie, tdp, arch

    if generation and generation >= 7:
        socket = "AM5"
        ram = "DDR5"
        pcie = 5.0
    elif generation and generation >= 5:
        socket = "AM4"
        ram = "DDR4"
        pcie = 4.0

    if tier == 9:
        tdp = 170.0 if generation and generation >= 7 else 105.0
    elif tier == 7:
        tdp = 120.0 if generation and generation >= 7 else 95.0
    elif tier == 5:
        tdp = 105.0 if generation and generation >= 7 else 65.0
    elif tier == 3:
        tdp = 65.0

    return socket, ram, pcie, tdp, arch


def _intel_cpu_metadata(lower_name: str) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[str]]:
    match = re.search(r"core\s+i(\d)\s*[- ]?(\d{3,4,5})", lower_name)
    tier = int(match.group(1)) if match else None
    digits = match.group(2) if match else ""
    socket = None
    ram = None
    pcie = None
    tdp = None
    arch = "Intel Core"

    if "xeon" in lower_name:
        socket = extract_socket(lower_name) or "LGA 4677"
        ram = "DDR5" if "sapphire rapids" in lower_name or socket == "LGA 4677" else None
        pcie = 5.0 if socket in {"LGA 4677"} else 4.0
        tdp = 270.0 if "w9" in lower_name else 165.0
        arch = "Intel Xeon"
        return socket, ram, pcie, tdp, arch

    if digits.startswith(("14", "13")):
        socket = "LGA 1700"
        ram = "DDR5"
        pcie = 5.0
    elif digits.startswith("12"):
        socket = "LGA 1700"
        ram = "DDR4"
        pcie = 4.0
    elif digits.startswith(("11", "10")):
        socket = "LGA 1200"
        ram = "DDR4"
        pcie = 3.0

    base_tdp = 125.0 if match and ("k" in lower_name or "kf" in lower_name) else 65.0
    if tier == 9:
        tdp = base_tdp
    elif tier == 7:
        tdp = base_tdp - 10.0
    elif tier == 5:
        tdp = base_tdp - 15.0
    elif tier == 3:
        tdp = base_tdp - 20.0

    return socket, ram, pcie, tdp, arch


def parse_cpu(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    if not any(keyword in lower_name for keyword in ("ryzen", "core", "xeon", "threadripper", "pentium")):
        return None
    if "desktop computer" in lower_name and "processor" not in lower_name and "cpu" not in lower_name:
        return None

    socket = extract_socket(lower_name)
    ram_standard = extract_ram_standard(lower_name)
    pcie_version = None
    tdp = None
    architecture = None

    if "ryzen" in lower_name or "threadripper" in lower_name:
        sock, ram, pcie, tdp_val, arch = _amd_cpu_metadata(lower_name)
    else:
        sock, ram, pcie, tdp_val, arch = _intel_cpu_metadata(lower_name)

    socket = socket or sock
    ram_standard = ram_standard or ram
    pcie_version = pcie or 4.0
    tdp = tdp_val or 95.0
    architecture = arch or manufacturer or "CPU"

    brand_for_identity = manufacturer or sock or brand_guess or "Generic"
    slug = slugify(f"{brand_for_identity} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        model=row.get("model_number") or product_name,
        metadata={
            "socket": socket,
            "ram_standard": ram_standard,
            "pcie_version": pcie_version,
            "tdp": tdp,
            "architecture": architecture,
            "base_name": product_name,
        },
    )

    if socket:
        component.add_attribute(
            AttributeFact(
                kind="socket",
                value=socket,
                label="CPU Socket",
                provenance="heuristic_series_mapping",
            )
        )
    if ram_standard:
        component.add_attribute(
            AttributeFact(
                kind="ram_standard",
                value=ram_standard,
                label="Supported Memory",
                provenance="heuristic_series_mapping",
            )
        )
    component.add_attribute(
        AttributeFact(
            kind="pcie_version",
            value=f"PCIe {pcie_version:.1f}",
            label="PCIe Version",
            numeric=pcie_version,
            provenance="heuristic_series_mapping",
        )
    )
    component.add_attribute(
        AttributeFact(
            kind="tdp",
            value=f"{tdp:.0f} W",
            label="Thermal Design Power",
            numeric=tdp,
            unit="W",
            provenance="heuristic_series_mapping",
        )
    )
    component.add_attribute(
        AttributeFact(
            kind="architecture",
            value=architecture,
            label="Architecture",
            provenance="heuristic_series_mapping",
        )
    )

    component.add_constraint(
        ConstraintFact(
            kind="thermal_requirement",
            value=tdp,
            unit="W",
            label="CPU Thermal Requirement",
            provenance="heuristic_series_mapping",
        )
    )
    return component


def parse_case(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    form_factors = extract_form_factors(lower_name)
    case_type = None
    if "mid tower" in lower_name:
        case_type = "Mid Tower"
    elif "full tower" in lower_name:
        case_type = "Full Tower"
    elif "mini tower" in lower_name or "mini-itx" in lower_name:
        case_type = "Mini Tower"

    max_gpu = None
    length_match = re.search(r"(\d{2,3})\s*mm\s*(?:gpu|graphics)", lower_name)
    if length_match:
        max_gpu = float(length_match.group(1))

    brand = manufacturer or brand_guess or "Generic"
    slug = slugify(f"{brand} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        metadata={
            "supported_form_factors": sorted(form_factors),
            "case_type": case_type,
            "max_gpu_length_mm": max_gpu,
            "base_name": product_name,
        },
    )

    if case_type:
        component.add_attribute(
            AttributeFact(
                kind="case_type",
                value=case_type,
                label="Case Type",
                provenance="product_name_parse",
            )
        )
    for ff in sorted(form_factors):
        component.add_attribute(
            AttributeFact(
                kind="supports_form_factor",
                value=ff,
                label="Supports Form Factor",
                provenance="product_name_parse",
            )
        )
    if max_gpu:
        component.add_attribute(
            AttributeFact(
                kind="gpu_clearance",
                value=f"{max_gpu:.0f} mm",
                label="GPU Clearance",
                numeric=max_gpu,
                unit="mm",
                provenance="product_name_parse",
            )
        )
    return component


def parse_cooling(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    cooling_type = "liquid" if any(keyword in lower_name for keyword in ("aio", "liquid", "water", "all-in-one")) else "air"
    radiator_size = extract_radiator_size(lower_name) if cooling_type == "liquid" else None
    tdp_support = None
    if cooling_type == "liquid":
        tdp_support = COOLER_TDP_CAPACITY.get(radiator_size, 220.0)
    else:
        tdp_support = 200.0 if "dual tower" in lower_name or "twin fan" in lower_name else 160.0

    socket_support: Set[str] = set()
    for pattern in SOCKET_PATTERNS:
        socket_support.update(match.group(0).upper() for match in pattern.finditer(lower_name))
    if "am5" in lower_name:
        socket_support.add("AM5")
    if "lga1700" in lower_name or "lga 1700" in lower_name:
        socket_support.add("LGA 1700")

    brand = manufacturer or brand_guess or "Generic"
    slug = slugify(f"{brand} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        metadata={
            "cooling_type": cooling_type,
            "radiator_size_mm": radiator_size,
            "tdp_support": tdp_support,
            "socket_support": sorted(socket_support),
            "base_name": product_name,
        },
    )

    component.add_attribute(
        AttributeFact(
            kind="cooling_type",
            value=cooling_type,
            label="Cooling Type",
            provenance="product_name_parse",
        )
    )
    if radiator_size:
        component.add_attribute(
            AttributeFact(
                kind="radiator_size",
                value=f"{radiator_size} mm",
                label="Radiator Size",
                numeric=float(radiator_size),
                unit="mm",
                provenance="product_name_parse",
            )
        )
    component.add_attribute(
        AttributeFact(
            kind="tdp_support",
            value=f"{tdp_support:.0f} W",
            label="Cooling Capacity",
            numeric=tdp_support,
            unit="W",
            provenance="heuristic_mapping",
        )
    )
    for socket in sorted(socket_support):
        component.add_attribute(
            AttributeFact(
                kind="socket_support",
                value=socket,
                label="Socket Support",
                provenance="product_name_parse",
            )
        )
    return component


def parse_ram(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    ram_standard = extract_ram_standard(lower_name)
    capacity_gb = extract_capacity_gb(lower_name)
    speed_mhz = extract_speed_mhz(lower_name)

    if not ram_standard and not capacity_gb:
        return None

    brand = manufacturer or brand_guess or "Generic"
    slug = slugify(f"{brand} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        metadata={
            "ram_standard": ram_standard,
            "capacity_gb": capacity_gb,
            "speed_mhz": speed_mhz,
            "base_name": product_name,
        },
    )

    if ram_standard:
        component.add_attribute(
            AttributeFact(
                kind="ram_standard",
                value=ram_standard,
                label="Memory Standard",
                provenance="product_name_parse",
            )
        )
    if capacity_gb:
        component.add_attribute(
            AttributeFact(
                kind="capacity",
                value=f"{capacity_gb:.0f} GB",
                label="Capacity",
                numeric=capacity_gb,
                unit="GB",
                provenance="product_name_parse",
            )
        )
    if speed_mhz:
        component.add_attribute(
            AttributeFact(
                kind="speed",
                value=f"{speed_mhz:.0f} MHz",
                label="Speed",
                numeric=speed_mhz,
                unit="MHz",
                provenance="product_name_parse",
            )
        )
    return component


def parse_storage(row: Dict[str, Any], canonical_type: str) -> Optional[ComponentRecord]:
    raw_name = normalize_whitespace(row["product_name"])
    product_name = strip_seller_prefix(raw_name)
    brand_guess = guess_brand(product_name)
    manufacturer = normalize_whitespace(row["manufacturer"]).title() or None
    manufacturer = clean_manufacturer(manufacturer, brand_guess)
    lower_name = product_name.lower()

    capacity_gb = extract_capacity_gb(lower_name)
    if not capacity_gb:
        return None

    storage_type = "SSD" if "ssd" in lower_name or "nvme" in lower_name else "HDD"
    interface = None
    if "nvme" in lower_name or "m.2" in lower_name:
        interface = "NVMe"
    elif "sata" in lower_name:
        interface = "SATA"
    elif "usb" in lower_name:
        interface = "USB"

    pcie_requirement = None
    if interface == "NVMe":
        gen_match = re.search(r"gen\s*(\d)", lower_name)
        if gen_match:
            pcie_requirement = float(gen_match.group(1))
        elif "gen4" in lower_name or "pcie4" in lower_name:
            pcie_requirement = 4.0
        elif "gen3" in lower_name or "pcie3" in lower_name:
            pcie_requirement = 3.0

    form_factor = None
    if "m.2" in lower_name or "m2" in lower_name:
        form_factor = "M.2"
    elif '2.5"' in product_name or "2.5 inch" in lower_name:
        form_factor = '2.5"'

    brand = manufacturer or brand_guess or "Generic"
    slug = slugify(f"{brand} {product_name}")
    display_name = build_display_name(product_name, canonical_type)

    component = ComponentRecord(
        slug=slug,
        component_type=canonical_type,
        name=display_name,
        manufacturer=manufacturer,
        metadata={
            "storage_type": storage_type,
            "capacity_gb": capacity_gb,
            "interface": interface,
            "pcie_requirement": pcie_requirement,
            "form_factor": form_factor,
            "base_name": product_name,
        },
    )

    component.add_attribute(
        AttributeFact(
            kind="storage_type",
            value=storage_type,
            label="Storage Type",
            provenance="product_name_parse",
        )
    )
    component.add_attribute(
        AttributeFact(
            kind="capacity",
            value=f"{capacity_gb:.0f} GB",
            label="Capacity",
            numeric=capacity_gb,
            unit="GB",
            provenance="product_name_parse",
        )
    )
    if interface:
        component.add_attribute(
            AttributeFact(
                kind="interface",
                value=interface,
                label="Interface",
                provenance="product_name_parse",
            )
        )
    if form_factor:
        component.add_attribute(
            AttributeFact(
                kind="form_factor",
                value=form_factor,
                label="Form Factor",
                provenance="product_name_parse",
            )
        )
    if pcie_requirement:
        component.add_attribute(
            AttributeFact(
                kind="pcie_requirement",
                value=f"PCIe {pcie_requirement:.1f}",
                label="PCIe Requirement",
                numeric=pcie_requirement,
                provenance="product_name_parse",
            )
        )
    return component


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


ParserFn = Callable[[Dict[str, Any], str], Optional[ComponentRecord]]

PART_CONFIG: Dict[str, Tuple[str, ParserFn]] = {
    "gpu": ("gpu", parse_gpu),
    "psu": ("psu", parse_psu),
    "motherboard": ("motherboard", parse_motherboard),
    "cpu": ("cpu", parse_cpu),
    "case": ("case", parse_case),
    "cooling": ("cooling", parse_cooling),
    "ram": ("ram", parse_ram),
    "internal_storage": ("storage", parse_storage),
    "storage": ("storage", parse_storage),
}


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------


def merge_component_records(target: ComponentRecord, source: ComponentRecord) -> None:
    for attr in source.attributes:
        target.add_attribute(attr)
    for constraint in source.constraints:
        target.add_constraint(constraint)
    target.metadata.update({k: v for k, v in source.metadata.items() if v is not None})
    target.sellers.update(source.sellers)
    target.prices.extend(source.prices)
    target.raw_examples.extend(source.raw_examples)


def consolidate_components(
    rows: Iterable[Dict[str, Any]],
    parser: ParserFn,
    canonical_type: str,
) -> List[ComponentRecord]:
    components: Dict[str, ComponentRecord] = {}
    for row in rows:
        component = parser(row, canonical_type)
        if component is None:
            continue
        price = row.get("price")
        if isinstance(price, (int, float)):
            component.prices.append(float(price))
        seller = row.get("seller") or row.get("source")
        if seller:
            component.sellers.add(normalize_whitespace(str(seller)))
        component.raw_examples.append(
            {
                "part_id": row.get("part_id"),
                "source": row.get("source"),
                "product_name": row.get("product_name"),
                "price": row.get("price"),
                "seller": row.get("seller"),
            }
        )

        existing = components.get(component.slug)
        if existing:
            merge_component_records(existing, component)
        else:
            components[component.slug] = component

    LOGGER.info("Consolidated %d %s components", len(components), canonical_type)
    return list(components.values())


def load_components(conn: sqlite3.Connection, limit: Optional[int]) -> Dict[str, List[ComponentRecord]]:
    result: Dict[str, Dict[str, ComponentRecord]] = {}
    for db_part_type, (canonical, parser) in PART_CONFIG.items():
        rows = fetch_rows(conn, db_part_type, limit)
        consolidated = consolidate_components(rows, parser, canonical)
        bucket = result.setdefault(canonical, {})
        for component in consolidated:
            if component.slug in bucket:
                merge_component_records(bucket[component.slug], component)
            else:
                bucket[component.slug] = component

    return {ctype: list(bucket.values()) for ctype, bucket in result.items()}


def summarize_components(components: Dict[str, List[ComponentRecord]]) -> None:
    for comp_type, records in components.items():
        LOGGER.info(
            "%s: %d nodes | price coverage: %d with price data",
            comp_type.upper(),
            len(records),
            sum(1 for record in records if record.prices),
        )
        for record in records[:5]:
            LOGGER.debug(
                "%s example: %s sellers=%d attrs=%d constraints=%d",
                comp_type,
                record.name,
                len(record.sellers),
                len(record.attributes),
                len(record.constraints),
            )


# ---------------------------------------------------------------------------
# Compatibility derivation
# ---------------------------------------------------------------------------


def build_electrical_edges(psus: Sequence[ComponentRecord], gpus: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for psu in psus:
        watt_attr = psu.metadata.get("wattage")
        if not watt_attr:
            continue
        for gpu in gpus:
            requirement = gpu.metadata.get("recommended_psu_watts")
            if not requirement:
                continue
            margin = float(watt_attr) - float(requirement)
            if margin < 0:
                continue
            edges.append(
                _wrap_edge(
                    psu.slug,
                    gpu.slug,
                    {
                        "margin_watts": round(margin, 1),
                        "psu_watts": float(watt_attr),
                        "required_watts": float(requirement),
                    },
                )
            )
    LOGGER.info("Derived %d PSU -> GPU electrical compatibility edges", len(edges))
    return edges


def build_interface_edges(motherboards: Sequence[ComponentRecord], gpus: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for board in motherboards:
        board_pcie = board.metadata.get("pcie_version")
        if not board_pcie:
            continue
        for gpu in gpus:
            gpu_pcie = gpu.metadata.get("pcie_requirement")
            if not gpu_pcie:
                continue
            if float(board_pcie) + 1e-3 >= float(gpu_pcie):
                edges.append(
                    _wrap_edge(
                        board.slug,
                        gpu.slug,
                        {
                            "board_pcie": float(board_pcie),
                            "gpu_requirement": float(gpu_pcie),
                        },
                    )
                )
    LOGGER.info("Derived %d motherboard -> GPU interface edges", len(edges))
    return edges


def build_socket_edges(cpus: Sequence[ComponentRecord], motherboards: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for cpu in cpus:
        cpu_socket = cpu.metadata.get("socket")
        if not cpu_socket:
            continue
        for board in motherboards:
            board_socket = board.metadata.get("socket")
            if not board_socket:
                continue
            if cpu_socket.lower() == board_socket.lower():
                edges.append(
                    _wrap_edge(
                        cpu.slug,
                        board.slug,
                        {"socket": cpu_socket},
                    )
                )
    LOGGER.info("Derived %d CPU -> motherboard socket edges", len(edges))
    return edges


def build_ram_edges(rams: Sequence[ComponentRecord], motherboards: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for ram in rams:
        ram_standard = ram.metadata.get("ram_standard")
        if not ram_standard:
            continue
        for board in motherboards:
            board_ram = board.metadata.get("ram_standard")
            if not board_ram:
                continue
            if ram_standard.lower() == board_ram.lower():
                edges.append(
                    _wrap_edge(
                        ram.slug,
                        board.slug,
                        {"ram_standard": ram_standard},
                    )
                )
    LOGGER.info("Derived %d RAM -> motherboard compatibility edges", len(edges))
    return edges


def build_case_motherboard_edges(cases: Sequence[ComponentRecord], motherboards: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for case in cases:
        supported = case.metadata.get("supported_form_factors") or []
        if not supported:
            continue
        supported_lower = {ff.lower() for ff in supported}
        for board in motherboards:
            board_form_factor = board.metadata.get("form_factor")
            if not board_form_factor:
                continue
            if board_form_factor.lower() in supported_lower:
                edges.append(
                    _wrap_edge(
                        case.slug,
                        board.slug,
                        {"form_factor": board_form_factor},
                    )
                )
    LOGGER.info("Derived %d case -> motherboard form factor edges", len(edges))
    return edges


def build_cpu_ram_edges(cpus: Sequence[ComponentRecord], rams: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for cpu in cpus:
        cpu_ram = cpu.metadata.get("ram_standard")
        if not cpu_ram:
            continue
        for ram in rams:
            ram_standard = ram.metadata.get("ram_standard")
            if not ram_standard:
                continue
            if cpu_ram.lower() == ram_standard.lower():
                edges.append(
                    _wrap_edge(
                        ram.slug,
                        cpu.slug,
                        {"ram_standard": ram_standard},
                    )
                )
    LOGGER.info("Derived %d RAM -> CPU compatibility edges", len(edges))
    return edges


def build_cooling_edges(coolers: Sequence[ComponentRecord], cpus: Sequence[ComponentRecord]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    for cooler in coolers:
        support = cooler.metadata.get("tdp_support")
        if not support:
            continue
        sockets = {sock.lower() for sock in cooler.metadata.get("socket_support", [])}
        for cpu in cpus:
            required = cpu.metadata.get("tdp")
            if not required:
                continue
            cpu_socket = cpu.metadata.get("socket")
            if cpu_socket and sockets and cpu_socket.lower() not in sockets:
                continue
            margin = support - float(required)
            if margin < 0:
                continue
            edges.append(
                _wrap_edge(
                    cooler.slug,
                    cpu.slug,
                    {
                        "cooler_support_watts": support,
                        "cpu_requirement_watts": float(required),
                        "margin_watts": round(margin, 1),
                    },
                )
            )
    LOGGER.info("Derived %d cooling -> CPU thermal edges", len(edges))
    return edges


# ---------------------------------------------------------------------------
# Neo4j persistence
# ---------------------------------------------------------------------------


def ensure_driver(uri: str, user: str, password: str):
    if GraphDatabase is None:  # pragma: no cover - runtime guard
        raise RuntimeError(
            "neo4j python driver is not installed. "
            "Install it with `pip install neo4j` before running the loader."
        )
    return GraphDatabase.driver(uri, auth=(user, password))


def purge_namespace(driver, namespace: str) -> None:
    with driver.session() as session:
        session.execute_write(
            lambda tx: tx.run(
                """
                MATCH (n {namespace: $namespace})
                DETACH DELETE n
                """,
                namespace=namespace,
            )
        )
    LOGGER.info("Purged existing nodes for namespace '%s'", namespace)


def upsert_components(driver, namespace: str, components: Sequence[ComponentRecord]) -> None:
    payloads = [component.to_payload() for component in components]
    if not payloads:
        LOGGER.warning("No component payloads to upsert")
        return

    with driver.session() as session:
        session.execute_write(
            lambda tx, rows: tx.run(
                """
                UNWIND $rows AS row
                MERGE (c:Component:PCComponent {slug: row.slug, namespace: $namespace})
                SET
                    c.name = row.name,
                    c.type = row.type,
                    c.manufacturer = row.manufacturer,
                    c.model = row.model,
                    c.seller_count = row.seller_count,
                    c.sellers = row.sellers,
                    c.price_min = row.price_min,
                    c.price_max = row.price_max,
                    c.price_avg = row.price_avg,
                    c.updated_at = timestamp()
                """,
                rows=rows,
                namespace=namespace,
            ),
            payloads,
        )
    LOGGER.info("Upserted %d components", len(payloads))


def upsert_attributes(driver, namespace: str, components: Sequence[ComponentRecord]) -> None:
    attribute_rows: List[Dict[str, Any]] = []
    for component in components:
        if not component.attributes:
            continue
        attribute_rows.append(
            {
                "component_slug": component.slug,
                "attributes": [
                    {
                        "kind": attr.kind,
                        "value": attr.value,
                        "label": attr.label,
                        "numeric": attr.numeric,
                        "unit": attr.unit,
                        "provenance": attr.provenance,
                    }
                    for attr in component.attributes
                ],
            }
        )
    if not attribute_rows:
        LOGGER.warning("No attribute facts to store")
        return

    with driver.session() as session:
        session.execute_write(
            lambda tx, rows: tx.run(
                """
                UNWIND $rows AS row
                MATCH (c:PCComponent {slug: row.component_slug, namespace: $namespace})
                UNWIND row.attributes AS attr
                MERGE (a:Attribute:PCAttribute {namespace: $namespace, kind: attr.kind, value: attr.value})
                SET
                    a.label = COALESCE(attr.label, a.label),
                    a.numeric = COALESCE(attr.numeric, a.numeric),
                    a.unit = COALESCE(attr.unit, a.unit),
                    a.provenance = COALESCE(attr.provenance, a.provenance)
                MERGE (c)-[:HAS_ATTRIBUTE]->(a)
                """,
                rows=rows,
                namespace=namespace,
            ),
            attribute_rows,
        )
    LOGGER.info("Linked attributes for %d components", len(attribute_rows))


def upsert_constraints(driver, namespace: str, components: Sequence[ComponentRecord]) -> None:
    constraint_rows: List[Dict[str, Any]] = []
    for component in components:
        if not component.constraints:
            continue
        constraint_rows.append(
            {
                "component_slug": component.slug,
                "constraints": [
                    {
                        "kind": constraint.kind,
                        "value": constraint.value,
                        "unit": constraint.unit,
                        "label": constraint.label,
                        "provenance": constraint.provenance,
                    }
                    for constraint in component.constraints
                ],
            }
        )
    if not constraint_rows:
        LOGGER.info("No constraints to persist")
        return

    with driver.session() as session:
        session.execute_write(
            lambda tx, rows: tx.run(
                """
                UNWIND $rows AS row
                MATCH (c:PCComponent {slug: row.component_slug, namespace: $namespace})
                UNWIND row.constraints AS constraint
                MERGE (k:Constraint:PCConstraint {namespace: $namespace, kind: constraint.kind, value: constraint.value, unit: constraint.unit})
                SET
                    k.label = COALESCE(constraint.label, k.label),
                    k.provenance = COALESCE(constraint.provenance, k.provenance)
                MERGE (c)-[:REQUIRES]->(k)
                """,
                rows=rows,
                namespace=namespace,
            ),
            constraint_rows,
        )
    LOGGER.info("Linked constraints for %d components", len(constraint_rows))


def gather_constraints(components: Sequence[ComponentRecord], kind: str) -> List[ConstraintFact]:
    constraints: List[ConstraintFact] = []
    for component in components:
        constraints.extend([constraint for constraint in component.constraints if constraint.kind == kind])
    return constraints


def upsert_constraint_satisfaction(
    driver,
    namespace: str,
    providers: Sequence[ComponentRecord],
    provider_metric_key: str,
    constraint_kind: str,
    requirements: Sequence[ConstraintFact],
) -> None:
    rows: List[Dict[str, Any]] = []
    for provider in providers:
        metric = provider.metadata.get(provider_metric_key)
        if metric is None:
            continue
        rows.append(
            {
                "component_slug": provider.slug,
                "metric": float(metric),
            }
        )
    if not rows or not requirements:
        LOGGER.info(
            "No providers or requirements for %s satisfaction (providers=%d requirements=%d)",
            constraint_kind,
            len(rows),
            len(requirements),
        )
        return

    requirement_values = sorted({constraint.value for constraint in requirements})

    with driver.session() as session:
        session.execute_write(
            lambda tx, provider_rows, required_values: tx.run(
                f"""
                UNWIND $provider_rows AS row
                MATCH (p:PCComponent {{slug: row.component_slug, namespace: $namespace}})
                UNWIND $required_values AS required_value
                MATCH (req:PCConstraint {{namespace: $namespace, kind: $constraint_kind, value: required_value}})
                WHERE row.metric >= required_value
                MERGE (p)-[rel:SATISFIES {{namespace: $namespace, kind: $constraint_kind}}]->(req)
                SET
                    rel.available = row.metric,
                    rel.required = required_value,
                    rel.margin = row.metric - required_value,
                    rel.updated_at = timestamp()
                """,
                provider_rows=provider_rows,
                required_values=required_values,
                namespace=namespace,
                constraint_kind=constraint_kind,
            ),
            rows,
            requirement_values,
        )
    LOGGER.info("Created SATISFIES edges for constraint kind '%s'", constraint_kind)


def upsert_compatibility_edges(driver, namespace: str, edge_specs: Sequence[Dict[str, Any]]) -> None:
    with driver.session() as session:
        for spec in edge_specs:
            relation_type: str = spec["type"]
            label: str = spec["label"]
            edges: List[Dict[str, Any]] = spec["edges"]
            if not edges:
                continue
            query = f"""
                UNWIND $rows AS row
                MATCH (a:PCComponent {{slug: row.from, namespace: $namespace}})
                MATCH (b:PCComponent {{slug: row.to, namespace: $namespace}})
                MERGE (a)-[rel:{relation_type} {{namespace: $namespace}}]->(b)
                SET
                    rel.label = $label,
                    rel.updated_at = timestamp()
                SET rel += row.props
            """
            session.execute_write(
                lambda tx, rows: tx.run(
                    query,
                    rows=rows,
                    namespace=namespace,
                    label=label,
                ),
                edges,
            )
            LOGGER.info("Upserted %d %s edges", len(edges), relation_type)


# ---------------------------------------------------------------------------
# CLI + main flow
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Neo4j knowledge graph for PC components.")
    parser.add_argument("--db-path", default=os.getenv("PC_PARTS_DB", "data/pc_parts.db"), help="Path to pc_parts SQLite database.")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"), help="Neo4j connection URI.")
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"), help="Neo4j username.")
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", ""), help="Neo4j password.")
    parser.add_argument("--namespace", default="pc_parts", help="Namespace tag applied to created nodes/edges.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum rows to pull per component type (0 for all).")
    parser.add_argument("--purge", action="store_true", help="Delete existing nodes for the namespace before loading.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to Neo4j.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level (default: INFO).")
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    )


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    configure_logging(args.log_level)

    limit = args.limit or None
    LOGGER.info("Loading components from %s (limit=%s)", args.db_path, limit or "all")
    conn = sqlite3.connect(args.db_path)

    try:
        components = load_components(conn, limit)
    finally:
        conn.close()

    summarize_components(components)

    gpus = components.get("gpu", [])
    psus = components.get("psu", [])
    motherboards = components.get("motherboard", [])
    cpus = components.get("cpu", [])
    cases = components.get("case", [])
    coolers = components.get("cooling", [])
    rams = components.get("ram", [])

    electrical_edges = build_electrical_edges(psus, gpus)
    interface_edges = build_interface_edges(motherboards, gpus)
    socket_edges = build_socket_edges(cpus, motherboards)
    ram_board_edges = build_ram_edges(rams, motherboards)
    case_board_edges = build_case_motherboard_edges(cases, motherboards)
    ram_cpu_edges = build_cpu_ram_edges(cpus, rams)
    cooling_edges = build_cooling_edges(coolers, cpus)

    if args.dry_run:
        LOGGER.info("Dry run complete. Skipping Neo4j persistence.")
        LOGGER.info(
            "Summary: %d GPUs, %d PSUs, %d motherboards, %d CPUs, %d cases, %d coolers, %d RAM modules",
            len(gpus),
            len(psus),
            len(motherboards),
            len(cpus),
            len(cases),
            len(coolers),
            len(rams),
        )
        LOGGER.info(
            "Edges: electrical=%d interface=%d socket=%d ram_board=%d case_board=%d ram_cpu=%d cooling=%d",
            len(electrical_edges),
            len(interface_edges),
            len(socket_edges),
            len(ram_board_edges),
            len(case_board_edges),
            len(ram_cpu_edges),
            len(cooling_edges),
        )
        return

    driver = ensure_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_password)

    if args.purge:
        purge_namespace(driver, args.namespace)

    all_components = [comp for comp_list in components.values() for comp in comp_list]
    upsert_components(driver, args.namespace, all_components)
    upsert_attributes(driver, args.namespace, all_components)
    upsert_constraints(driver, args.namespace, gpus + cpus)

    gpu_constraints = gather_constraints(gpus, "psu_requirement")
    if gpu_constraints:
        upsert_constraint_satisfaction(driver, args.namespace, psus, "wattage", "psu_requirement", gpu_constraints)

    cpu_constraints = gather_constraints(cpus, "thermal_requirement")
    if cpu_constraints:
        upsert_constraint_satisfaction(
            driver,
            args.namespace,
            coolers,
            "tdp_support",
            "thermal_requirement",
            cpu_constraints,
        )

    edge_specs = [
        {"type": "ELECTRICAL_COMPATIBLE_WITH", "label": "electrical-compatible-with", "edges": electrical_edges},
        {"type": "INTERFACE_COMPATIBLE_WITH", "label": "interface-compatible-with", "edges": interface_edges},
        {"type": "SOCKET_COMPATIBLE_WITH", "label": "socket-compatible-with", "edges": socket_edges},
        {"type": "RAM_COMPATIBLE_WITH", "label": "ram-compatible-with", "edges": ram_board_edges},
        {"type": "FORM_FACTOR_COMPATIBLE_WITH", "label": "form-factor-compatible-with", "edges": case_board_edges},
        {"type": "MEMORY_COMPATIBLE_WITH", "label": "memory-compatible-with", "edges": ram_cpu_edges},
        {"type": "THERMAL_COMPATIBLE_WITH", "label": "thermal-compatible-with", "edges": cooling_edges},
    ]
    upsert_compatibility_edges(driver, args.namespace, edge_specs)

    driver.close()
    LOGGER.info("Knowledge graph load completed successfully.")


if __name__ == "__main__":
    main()

