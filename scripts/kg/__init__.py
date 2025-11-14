"""
Knowledge Graph module for PC component compatibility.

This module contains tools for building and maintaining a Neo4j knowledge graph
of PC component compatibility relationships.
"""

from .scrape_compatibility_data import CompatibilityScraper, ProductAttribute, CompatibilityFact
from .normalize_attributes import normalize_attribute_value, normalize_all_attributes

__all__ = [
    "CompatibilityScraper",
    "ProductAttribute",
    "CompatibilityFact",
    "normalize_attribute_value",
    "normalize_all_attributes",
]

