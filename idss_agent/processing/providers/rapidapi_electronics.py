"""
RapidAPI-backed electronics search provider.
"""
from __future__ import annotations

from typing import Dict, Any

from idss_agent.tools.electronics_api import search_products
from idss_agent.utils.logger import get_logger

logger = get_logger("providers.rapidapi")


class RapidApiElectronicsProvider:
    """
    Thin wrapper around the existing RapidAPI integration so it can be swapped out.
    """

    def search(self, params: Dict[str, Any]) -> str:
        logger.debug("RapidAPI provider invoked with params: %s", params)
        return search_products.invoke(params)





