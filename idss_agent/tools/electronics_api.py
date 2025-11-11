"""RapidAPI product search tools for electronics recommendations.

This module mirrors the structure of ``autodev_api.py`` but targets a
general-purpose product search API so the agent can source electronics data.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests
from langchain_core.tools import tool

from idss_agent.utils.logger import get_logger


api_logger = get_logger("tools.electronics_api")


DEFAULT_HOST = os.getenv("RAPIDAPI_HOST", "product-search-api.p.rapidapi.com")
DEFAULT_BASE_URL = os.getenv("RAPIDAPI_BASE_URL", f"https://{DEFAULT_HOST}")
DEFAULT_SEARCH_PATH = os.getenv("RAPIDAPI_SEARCH_ENDPOINT", "/shopping")
DEFAULT_PRODUCT_PATH = os.getenv("RAPIDAPI_PRODUCT_ENDPOINT", "/products/{product_id}")


def _get_api_key() -> str:
    """Retrieve RapidAPI key from environment variables."""

    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        raise ValueError(
            "RAPIDAPI_KEY not found in environment variables. "
            "Set RAPIDAPI_KEY with your RapidAPI credential."
        )
    return api_key


def _build_headers() -> Dict[str, str]:
    """Return headers required by RapidAPI."""

    return {
        "X-RapidAPI-Key": _get_api_key(),
        "X-RapidAPI-Host": DEFAULT_HOST,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _make_request(
    path: str,
    payload: Dict[str, Any],
    method: str = "POST",
    timeout: int = 30,
) -> str:
    """Make a request to the RapidAPI electronics endpoint."""

    url = f"{DEFAULT_BASE_URL.rstrip('/')}{path}"
    headers = _build_headers()

    try:
        api_logger.info(
            "RapidAPI request %s %s payload=%s",
            method.upper(),
            url,
            json.dumps(payload)[:1000],
        )

        if method.upper() == "POST":
            response = requests.post(url, data=payload, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, params=payload, headers=headers, timeout=timeout)

        response.raise_for_status()
        api_logger.debug(
            "RapidAPI response status=%s body_length=%s",
            response.status_code,
            len(response.text),
        )
        return response.text
    except requests.exceptions.HTTPError as exc:  # pragma: no cover - simple wrapper
        status = exc.response.status_code if exc.response else "unknown"
        return json.dumps({
            "error": (
                "RapidAPI request failed with status "
                f"{status}. Details: {str(exc)}"
            )
        })
    except Exception as exc:  # pragma: no cover - propagated error text
        return json.dumps({"error": f"RapidAPI request failed: {str(exc)}"})


def _clean_payload(payload: Dict[str, Optional[Any]]) -> Dict[str, Any]:
    """Drop keys with ``None`` values and coerce everything to strings."""

    cleaned: Dict[str, Any] = {}
    for key, value in payload.items():
        if value in (None, ""):
            continue
        cleaned[key] = str(value)
    return cleaned


@tool
def search_products(
    query: str,
    page: int = 1,
    country: Optional[str] = "us",
    language: Optional[str] = None,
    sort_by: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    seller: Optional[str] = None,
) -> str:
    """Search electronics products via RapidAPI.

    Args:
        query: Search keywords (required by the API).
        page: Page number (1-indexed).
        country: ISO country code (defaults to ``us``).
        language: Optional locale.
        sort_by: Sorting preference accepted by the API.
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        seller: Optional seller/store filter.

    Returns:
        Raw JSON string from the API response or serialized error message.
    """

    payload = _clean_payload(
        {
            "query": query,
            "page": page,
            "country": country,
            "language": language,
            "sort_by": sort_by,
            "min_price": min_price,
            "max_price": max_price,
            "seller": seller,
        }
    )

    return _make_request(DEFAULT_SEARCH_PATH, payload, method="POST")


@tool
def get_product_details(
    product_id: str,
    country: Optional[str] = "us",
    language: Optional[str] = None,
) -> str:
    """Fetch detailed information for a single product by RapidAPI product ID."""

    path_template = DEFAULT_PRODUCT_PATH or ""
    path_template = path_template.strip()

    # Support templated REST path (/products/{product_id}) and legacy POST endpoint (/product)
    supports_rest_path = any(token in path_template for token in ("{product_id}", "{id}"))

    if supports_rest_path:
        path = path_template.format(product_id=product_id, id=product_id)
        payload = _clean_payload(
            {
                "country": country,
                "language": language,
            }
        )
        return _make_request(path, payload, method="GET")

    # Legacy behaviour: append product_id via payload and POST to default path
    payload = _clean_payload(
        {
            "product_id": product_id,
            "country": country,
            "language": language,
        }
    )

    # If the legacy path is something like "/products", append the id manually
    if path_template.rstrip("/").endswith("/products"):
        path = f"{path_template.rstrip('/')}/{product_id}"
        payload.pop("product_id", None)
        return _make_request(path, payload, method="GET")

    return _make_request(path_template or "/product", payload, method="POST")


