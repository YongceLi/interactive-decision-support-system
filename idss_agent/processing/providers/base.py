"""
Abstractions for product search providers.
"""
from __future__ import annotations

from typing import Protocol, Dict, Any


class ProductSearchProvider(Protocol):
    """
    Protocol for search providers used by the recommendation pipeline.
    """

    def search(self, params: Dict[str, Any]) -> str:
        """
        Execute a search request and return the raw response payload as text.

        Args:
            params: Provider-specific search parameters

        Returns:
            Raw text payload (JSON string or similar) containing search results
        """






