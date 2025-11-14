"""
Provider registry for recommendation search backends.
"""
from __future__ import annotations

from importlib import import_module
from typing import Dict, Type

from .base import ProductSearchProvider

_REGISTRY: Dict[str, str] = {
    "rapidapi": "idss_agent.processing.providers.rapidapi_electronics:RapidApiElectronicsProvider",
}


def get_provider(name: str) -> ProductSearchProvider:
    """
    Resolve and instantiate a search provider by name.
    """
    if name not in _REGISTRY:
        raise ValueError(f"Unknown search provider '{name}'. Available providers: {list(_REGISTRY.keys())}")

    module_path, class_name = _REGISTRY[name].split(":")
    module = import_module(module_path)
    provider_cls: Type[ProductSearchProvider] = getattr(module, class_name)
    return provider_cls()






