#!/usr/bin/env python3
"""
LLM-based extraction module for parsing product specifications and compatibility data.

Uses structured output (JSON schema) to extract product attributes and compatibility
relationships from unstructured text, reducing hallucinations and improving accuracy.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
    from pydantic import BaseModel, Field
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    BaseModel = object  # type: ignore
    Field = lambda *args, **kwargs: None  # type: ignore

LOGGER = logging.getLogger("llm_extractor")


# Pydantic models for structured output
if LLM_AVAILABLE:
    class ProductAttribute(BaseModel):
        """A single product attribute."""
        attribute_type: str = Field(description="Type of attribute (e.g., 'socket', 'pcie_version', 'ram_standard', 'wattage', 'form_factor', 'brand', 'capacity')")
        attribute_value: str = Field(description="Normalized value of the attribute (e.g., 'LGA 1700', 'PCIe:5.0', 'DDR5', '850W')")
        confidence: float = Field(default=0.8, description="Confidence score 0-1 based on how explicit the information is")
    
    class CompatibilityRelationship(BaseModel):
        """A compatibility relationship between products."""
        compatible_product_name: Optional[str] = Field(default=None, description="Name of compatible product if mentioned")
        compatibility_type: str = Field(description="Type of compatibility (e.g., 'socket', 'pcie', 'ram_standard', 'psu_wattage', 'form_factor')")
        constraint_value: Optional[str] = Field(default=None, description="Specific constraint value (e.g., 'LGA 1700', 'PCIe 5.0', '850W')")
        is_compatible: bool = Field(description="Whether this indicates compatibility (true) or incompatibility (false)")
    
    class ExtractedProductData(BaseModel):
        """Structured product data extracted from text."""
        product_name: Optional[str] = Field(default=None, description="Product name if found in text")
        attributes: List[ProductAttribute] = Field(default_factory=list, description="List of product attributes found")
        compatibility_relationships: List[CompatibilityRelationship] = Field(default_factory=list, description="Compatibility relationships mentioned")
        notes: Optional[str] = Field(default=None, description="Any additional notes or context")


class LLMExtractor:
    """LLM-based extractor for product specifications and compatibility data."""
    
    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.0, use_cache: bool = True):
        """
        Initialize LLM extractor.
        
        Args:
            model_name: OpenAI model to use (default: gpt-4o-mini for cost efficiency)
            temperature: Temperature for generation (0.0 for deterministic output)
            use_cache: Whether to cache extractions to avoid redundant API calls
        """
        if not LLM_AVAILABLE:
            raise ImportError(
                "LLM libraries not available. Install with: pip install langchain-openai pydantic"
            )
        
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.use_cache = use_cache
        self.cache: Dict[str, ExtractedProductData] = {}
        
        # Create prompt template
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at extracting structured product specification and compatibility data from technical documentation.

Your task is to extract:
1. Product attributes (socket, PCIe version, RAM standard, wattage, form factor, etc.)
2. Compatibility relationships with other products

IMPORTANT RULES:
- Only extract information that is EXPLICITLY stated in the text
- Use normalized attribute values (e.g., "PCIe:5.0" not "PCIe 5.0" or "PCI Express 5.0")
- For socket: Use format like "LGA 1700", "AM5", "sTR5" (with space for LGA numbers)
- For PCIe: Use format "PCIe:5.0" or "PCIe:4.0" (with colon and one decimal)
- For RAM: Use format "DDR4" or "DDR5" (no spaces or dashes)
- For wattage: Use format "850W" (number followed by W)
- For form factor: Use format "ATX", "Micro-ATX", "Mini-ITX", "E-ATX"
- Set confidence based on how explicit the information is (0.9+ for explicit specs, 0.7-0.8 for inferred)
- Do NOT make up or infer compatibility relationships unless explicitly stated
- If compatibility is mentioned but product name is unclear, set compatible_product_name to null

Return structured JSON matching the schema exactly."""),
            ("human", """Extract product specifications and compatibility information from the following text:

{text}

Product context:
- Product name: {product_name}
- Product slug: {product_slug}
- Source: {source}

Extract all relevant attributes and compatibility relationships. Return JSON matching the schema.""")
        ])
        
        # Create output parser
        self.output_parser = PydanticOutputParser(pydantic_object=ExtractedProductData)
        # Add format instructions to the prompt
        format_instructions = self.output_parser.get_format_instructions()
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at extracting structured product specification and compatibility data from technical documentation.

Your task is to extract:
1. Product attributes (socket, PCIe version, RAM standard, wattage, form factor, etc.)
2. Compatibility relationships with other products

IMPORTANT RULES:
- Only extract information that is EXPLICITLY stated in the text
- Use normalized attribute values (e.g., "PCIe:5.0" not "PCIe 5.0" or "PCI Express 5.0")
- For socket: Use format like "LGA 1700", "AM5", "sTR5" (with space for LGA numbers)
- For PCIe: Use format "PCIe:5.0" or "PCIe:4.0" (with colon and one decimal)
- For RAM: Use format "DDR4" or "DDR5" (no spaces or dashes)
- For wattage: Use format "850W" (number followed by W)
- For form factor: Use format "ATX", "Micro-ATX", "Mini-ITX", "E-ATX"
- Set confidence based on how explicit the information is (0.9+ for explicit specs, 0.7-0.8 for inferred)
- Do NOT make up or infer compatibility relationships unless explicitly stated
- If compatibility is mentioned but product name is unclear, set compatible_product_name to null

{format_instructions}"""),
            ("human", """Extract product specifications and compatibility information from the following text:

{text}

Product context:
- Product name: {product_name}
- Product slug: {product_slug}
- Source: {source}

Extract all relevant attributes and compatibility relationships. Return JSON matching the schema.""")
        ]).partial(format_instructions=format_instructions)
    
    def extract_from_text(
        self,
        text: str,
        product_name: str,
        product_slug: str,
        source: str = "unknown"
    ) -> ExtractedProductData:
        """
        Extract structured data from text using LLM.
        
        Args:
            text: Text to extract from (HTML content, PDF text, etc.)
            product_name: Product name for context
            product_slug: Product slug identifier
            source: Source of the text (e.g., "newegg", "manufacturer_pdf")
        
        Returns:
            ExtractedProductData with attributes and compatibility relationships
        """
        # Check cache
        cache_key = f"{product_slug}:{hash(text[:500])}"
        if self.use_cache and cache_key in self.cache:
            LOGGER.debug("Using cached extraction for %s", product_slug)
            return self.cache[cache_key]
        
        # Truncate text if too long (to avoid token limits)
        max_chars = 8000  # Conservative limit for gpt-4o-mini
        if len(text) > max_chars:
            LOGGER.warning("Text too long (%d chars), truncating to %d", len(text), max_chars)
            # Try to keep beginning and end (where specs often are)
            text = text[:max_chars//2] + "\n... [truncated] ...\n" + text[-max_chars//2:]
        
        try:
            # Format prompt
            messages = self.prompt_template.format_messages(
                text=text,
                product_name=product_name,
                product_slug=product_slug,
                source=source
            )
            
            # Call LLM
            response = self.llm.invoke(messages)
            
            # Parse response
            parsed = self.output_parser.parse(response.content)
            
            # Cache result
            if self.use_cache:
                self.cache[cache_key] = parsed
            
            LOGGER.info("Extracted %d attributes and %d compatibility relationships using LLM",
                       len(parsed.attributes), len(parsed.compatibility_relationships))
            
            return parsed
            
        except Exception as e:
            LOGGER.error("Error extracting with LLM: %s", e)
            # Return empty result on error
            return ExtractedProductData()
    
    def extract_from_html(
        self,
        html_content: str,
        product_name: str,
        product_slug: str,
        source: str = "unknown"
    ) -> ExtractedProductData:
        """
        Extract from HTML content by converting to text first.
        
        Args:
            html_content: HTML content to extract from
            product_name: Product name for context
            product_slug: Product slug identifier
            source: Source of the HTML
        
        Returns:
            ExtractedProductData
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text(separator='\n', strip=True)
            
            # Clean up whitespace
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            text = '\n'.join(lines)
            
            return self.extract_from_text(text, product_name, product_slug, source)
            
        except Exception as e:
            LOGGER.error("Error extracting from HTML: %s", e)
            return ExtractedProductData()
    
    def extract_from_pdf_text(
        self,
        pdf_text: str,
        product_name: str,
        product_slug: str,
        source: str = "pdf"
    ) -> ExtractedProductData:
        """
        Extract from PDF text content.
        
        Args:
            pdf_text: Text extracted from PDF
            product_name: Product name for context
            product_slug: Product slug identifier
            source: Source identifier
        
        Returns:
            ExtractedProductData
        """
        return self.extract_from_text(pdf_text, product_name, product_slug, source)


def convert_to_product_attributes(
    extracted_data: ExtractedProductData,
    product_slug: str,
    source_url: Optional[str] = None,
    source_seller: Optional[str] = None
) -> List[Any]:  # List[ProductAttribute] but avoiding circular import
    """
    Convert ExtractedProductData to list of ProductAttribute dataclass instances.
    
    This bridges the LLM extractor with the scraping module's ProductAttribute dataclass.
    """
    from .scrape_compatibility_data import ProductAttribute
    
    attributes = []
    for attr in extracted_data.attributes:
        attributes.append(ProductAttribute(
            product_slug=product_slug,
            attribute_type=attr.attribute_type,
            attribute_value=attr.attribute_value,
            source_url=source_url,
            source_seller=source_seller or "llm_extraction",
            confidence=attr.confidence
        ))
    
    return attributes


def convert_to_compatibility_facts(
    extracted_data: ExtractedProductData,
    product_slug: str,
    source_url: Optional[str] = None,
    source_seller: Optional[str] = None
) -> List[Any]:  # List[CompatibilityFact] but avoiding circular import
    """
    Convert ExtractedProductData to list of CompatibilityFact dataclass instances.
    """
    from .scrape_compatibility_data import CompatibilityFact
    
    facts = []
    for compat in extracted_data.compatibility_relationships:
        if compat.is_compatible:  # Only include compatibility facts, not incompatibilities
            facts.append(CompatibilityFact(
                product_slug=product_slug,
                compatible_with_slug=compat.compatible_product_name or "unknown",
                compatibility_type=compat.compatibility_type,
                constraint_value=compat.constraint_value,
                source_url=source_url,
                source_seller=source_seller or "llm_extraction",
                confidence=0.85,  # High confidence for LLM-extracted relationships
                metadata={"extracted_by": "llm", "notes": extracted_data.notes}
            ))
    
    return facts


if __name__ == "__main__":
    # Test extraction
    if not LLM_AVAILABLE:
        print("LLM libraries not available. Install with: pip install langchain-openai pydantic")
        exit(1)
    
    extractor = LLMExtractor()
    
    test_text = """
    ASUS ROG Strix Z790-E Gaming WiFi Motherboard
    
    Specifications:
    - CPU Socket: LGA 1700
    - Chipset: Intel Z790
    - Memory: DDR5, up to 128GB
    - PCIe Slots: PCIe 5.0 x16, PCIe 4.0 x16
    - Form Factor: ATX
    - Power Connectors: 24-pin ATX, 8-pin + 4-pin CPU
    
    Compatibility:
    - Compatible with Intel 12th and 13th Gen processors (LGA 1700 socket)
    - Supports DDR5 memory modules
    - PCIe 5.0 graphics cards supported
    """
    
    result = extractor.extract_from_text(
        test_text,
        product_name="ASUS ROG Strix Z790-E",
        product_slug="asus-rog-strix-z790-e",
        source="test"
    )
    
    print("Extracted attributes:")
    for attr in result.attributes:
        print(f"  {attr.attribute_type}: {attr.attribute_value} (confidence: {attr.confidence})")
    
    print("\nExtracted compatibility relationships:")
    for compat in result.compatibility_relationships:
        print(f"  {compat.compatibility_type}: {compat.constraint_value} (compatible: {compat.is_compatible})")

