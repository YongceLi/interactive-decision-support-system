"""
HTTP client for Auto.dev APIs.
"""

import os
import httpx
from typing import Dict, Any, Optional


class AutoDevClient:
    """HTTP client for Auto.dev API endpoints."""

    def __init__(self, base_url: str = "https://auto.dev"):
        self.base_url = base_url.rstrip("/")

        # Get API key from environment
        api_key = os.getenv("AUTO_DEV_API_KEY")
        if not api_key:
            raise ValueError("AUTO_DEV_API_KEY environment variable is required")

        # Create client with authentication headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.client = httpx.Client(headers=headers)

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make GET request to Auto.dev API."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Request failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error: {str(e)}")

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()