"""Web research tools for enriching vehicle recommendations with market insights."""

import os
from typing import Optional
from langchain_core.tools import tool

try:
    from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
except ImportError:
    # Fallback if tavily is not installed
    TavilySearchAPIWrapper = None


@tool
def research_vehicle_recommendations(query: str) -> str:
    """Search the web for vehicle recommendations and market insights.

    Use this when the user has implicit preferences that need research, such as:
    - "Best family SUV 2024"
    - "Most reliable trucks under 30k"
    - "Best fuel efficient sedans"
    - "Top rated safety vehicles for new drivers"
    - "Best vehicles for dog owners"
    - "Most reliable used cars for commuting"

    This helps translate lifestyle needs into specific vehicle recommendations
    that can then be searched in the Auto.dev API.

    Args:
        query: Search query about vehicle recommendations or market insights

    Returns:
        Summary of web search results with vehicle recommendations and insights

    Example:
        >>> research_vehicle_recommendations("best family SUV with 3 rows under 35k")
    """
    try:
        if TavilySearchAPIWrapper is None:
            return '{"error": "Tavily search is not available. Install with: pip install langchain-community tavily-python"}'

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return '{"error": "TAVILY_API_KEY not found in environment variables. Web research is not available."}'

        search = TavilySearchAPIWrapper(tavily_api_key=api_key)

        # Perform search with focus on vehicle recommendations
        results = search.results(
            query=query,
            max_results=5,
            search_depth="advanced",
            include_answer=True
        )

        # Format results
        if not results:
            return '{"error": "No results found for the query."}'

        # Build a summary
        summary_parts = []

        # Add the AI-generated answer if available
        if isinstance(results, dict) and results.get("answer"):
            summary_parts.append(f"Summary: {results['answer']}\n")

        # Add top results
        result_list = results if isinstance(results, list) else results.get("results", [])

        if result_list:
            summary_parts.append("Top recommendations from web research:")
            for i, result in enumerate(result_list[:5], 1):
                title = result.get("title", "No title")
                content = result.get("content", "")
                url = result.get("url", "")

                summary_parts.append(f"\n{i}. {title}")
                if content:
                    # Truncate long content
                    content_preview = content[:300] + "..." if len(content) > 300 else content
                    summary_parts.append(f"   {content_preview}")
                if url:
                    summary_parts.append(f"   Source: {url}")

        return "\n".join(summary_parts)

    except Exception as e:
        return f'{{"error": "Error performing web research: {str(e)}"}}'


@tool
def research_vehicle_comparison(vehicle_options: str) -> str:
    """Search the web for comparisons between specific vehicles.

    Use this when you need to compare specific makes/models to help
    the user decide, such as:
    - "Honda CR-V vs Toyota RAV4 2024"
    - "Jeep Wrangler vs Ford Bronco reliability"
    - "Subaru Outback vs Forester family use"

    Args:
        vehicle_options: Vehicles to compare (e.g., "Honda CR-V vs Toyota RAV4")

    Returns:
        Summary of comparison results from the web

    Example:
        >>> research_vehicle_comparison("Honda CR-V vs Toyota RAV4 reliability and safety")
    """
    try:
        if TavilySearchAPIWrapper is None:
            return '{"error": "Tavily search is not available. Install with: pip install langchain-community tavily-python"}'

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return '{"error": "TAVILY_API_KEY not found in environment variables. Web research is not available."}'

        search = TavilySearchAPIWrapper(tavily_api_key=api_key)

        # Add comparison keywords
        query = f"{vehicle_options} comparison review"

        results = search.results(
            query=query,
            max_results=4,
            search_depth="advanced",
            include_answer=True
        )

        # Format results
        if not results:
            return '{"error": "No comparison results found."}'

        summary_parts = []

        # Add the AI-generated answer if available
        if isinstance(results, dict) and results.get("answer"):
            summary_parts.append(f"Comparison Summary: {results['answer']}\n")

        # Add top comparison results
        result_list = results if isinstance(results, list) else results.get("results", [])

        if result_list:
            summary_parts.append("Detailed comparisons from automotive sources:")
            for i, result in enumerate(result_list[:4], 1):
                title = result.get("title", "No title")
                content = result.get("content", "")
                url = result.get("url", "")

                summary_parts.append(f"\n{i}. {title}")
                if content:
                    content_preview = content[:300] + "..." if len(content) > 300 else content
                    summary_parts.append(f"   {content_preview}")
                if url:
                    summary_parts.append(f"   Source: {url}")

        return "\n".join(summary_parts)

    except Exception as e:
        return f'{{"error": "Error performing comparison research: {str(e)}"}}'
