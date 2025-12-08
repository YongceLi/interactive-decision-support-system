"""
Knowledge Graph and Database Augmentation Utilities.

This package provides utilities for augmenting PC parts databases with
compatibility attributes extracted via web scraping and LLM extraction.
"""

from .llm_extractor import LLMExtractor, convert_to_product_attributes

__all__ = [
    "LLMExtractor",
    "convert_to_product_attributes",
]
