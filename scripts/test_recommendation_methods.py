#!/usr/bin/env python3
"""
Standalone test script for new recommendation methods (Method 1 & Method 2).

Usage:
    python scripts/test_recommendation_methods.py "I want a gaming laptop under $1500"
    python scripts/test_recommendation_methods.py "I want a gaming laptop under $1500" --method 1
    python scripts/test_recommendation_methods.py "I want a gaming laptop under $1500" --method 2

Output: JSON with extracted filters, recommended products, and diversity stats
"""

import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
load_dotenv(project_root / ".env")

# Import components
from idss_agent.state.schema import create_initial_state
from idss_agent.processing.semantic_parser import semantic_parser_node
from idss_agent.processing.recommendation_method1 import recommend_method1
from idss_agent.processing.recommendation_method2 import recommend_method2
from langchain_core.messages import HumanMessage


class LogCapture(logging.Handler):
    """Custom logging handler to capture important logs."""

    def __init__(self):
        super().__init__()
        self.logs = []

    def emit(self, record):
        msg = self.format(record)
        self.logs.append({
            "level": record.levelname,
            "message": msg,
            "logger": record.name
        })


def test_method1_pipeline(user_query: str) -> dict:
    """
    Test Method 1 (Local database search + Vector ranking + MMR diversification) with a user query.

    Args:
        user_query: Natural language query from user

    Returns:
        Dictionary with all intermediate outputs and results
    """

    # Set up log capture
    log_capture = LogCapture()
    log_capture.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_capture.setFormatter(formatter)

    # Add handler to relevant loggers
    for logger_name in ['processing.method1', 'processing.diversification',
                        'processing.vector_ranker', 'tools.local_electronics_store',
                        'idss_agent.processing.semantic_parser']:
        logger = logging.getLogger(logger_name)
        logger.addHandler(log_capture)
        logger.setLevel(logging.INFO)

    # Initialize result dictionary
    result = {
        "method": "Method 1: Local database search + Vector ranking + MMR diversification",
        "user_query": user_query,
        "extracted_filters": None,
        "implicit_preferences": None,
        "location_data": None,
        "products_found": 0,
        "recommended_products": [],
        "diversity_stats": {},
        "processing_logs": [],
        "errors": []
    }

    try:
        # Step 1: Create initial state
        state = create_initial_state()
        state["conversation_history"].append(HumanMessage(content=user_query))

        # Step 2: Run semantic parser to extract filters
        try:
            state = semantic_parser_node(state)
            result["extracted_filters"] = dict(state["explicit_filters"])
            result["implicit_preferences"] = dict(state["implicit_preferences"])
        except Exception as e:
            result["errors"].append(f"Semantic parser error: {str(e)}")
            return result

        # Step 3: Extract location data if present
        filters = state["explicit_filters"]
        user_lat, user_lon, coords = None, None, None

        result["location_data"] = {
            "zip_code": filters.get("zip"),
            "coordinates": [user_lat, user_lon] if coords else None,
            "search_radius": filters.get("search_radius"),
            "user_latitude": state.get("user_latitude"),
            "user_longitude": state.get("user_longitude")
        }

        # Step 4: Run Method 1
        try:
            products = recommend_method1(
                explicit_filters=state["explicit_filters"],
                implicit_preferences=state["implicit_preferences"],
                top_k=20,
                lambda_param=0.7
            )
            result["products_found"] = len(products)
            result["recommended_products"] = products

            # Calculate diversity stats
            if products:
                # Electronics products use 'brand' and 'title' fields
                brands = [
                    p.get("brand") or p.get("make") or p.get("product", {}).get("brand") or ""
                    for p in products
                ]
                titles = [
                    p.get("title") or p.get("product_name") or p.get("product", {}).get("title") or ""
                    for p in products
                ]
                brand_titles = [
                    f"{p.get('brand') or p.get('make') or p.get('product', {}).get('brand') or ''} {p.get('title') or p.get('product_name') or p.get('product', {}).get('title') or ''}"
                    for p in products
                ]
                from collections import Counter
                brand_counts = Counter(brands)
                title_counts = Counter(titles)
                brand_title_counts = Counter(brand_titles)

                result["diversity_stats"] = {
                    "unique_brands": len(set(brands)),
                    "unique_titles": len(set(titles)),
                    "unique_brand_titles": len(set(brand_titles)),
                    "brand_distribution": dict(brand_counts),
                    "title_distribution": dict(title_counts),
                    "brand_title_distribution": dict(brand_title_counts)
                }

        except Exception as e:
            result["errors"].append(f"Method 1 error: {str(e)}")
            import traceback
            result["errors"].append(traceback.format_exc())
            return result

        # Step 5: Capture processing logs
        result["processing_logs"] = log_capture.logs

    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")
        import traceback
        result["errors"].append(traceback.format_exc())

    finally:
        # Clean up log handlers
        for logger_name in ['processing.method1', 'processing.diversification',
                            'processing.vector_ranker', 'tools.local_electronics_store',
                            'idss_agent.processing.semantic_parser']:
            logger = logging.getLogger(logger_name)
            logger.removeHandler(log_capture)

    return result


def test_method2_pipeline(user_query: str) -> dict:
    """
    Test Method 2 (Web Search + Parallel local database queries) with a user query.

    Args:
        user_query: Natural language query from user

    Returns:
        Dictionary with all intermediate outputs and results
    """

    # Set up log capture
    log_capture = LogCapture()
    log_capture.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_capture.setFormatter(formatter)

    # Add handler to relevant loggers
    for logger_name in ['processing.method2', 'processing.vector_ranker',
                        'tools.local_electronics_store',
                        'idss_agent.processing.semantic_parser']:
        logger = logging.getLogger(logger_name)
        logger.addHandler(log_capture)
        logger.setLevel(logging.INFO)

    # Initialize result dictionary
    result = {
        "method": "Method 2: Web Search + Parallel local database queries",
        "user_query": user_query,
        "extracted_filters": None,
        "implicit_preferences": None,
        "location_data": None,
        "llm_reasoning": None,
        "suggested_brands": None,
        "products_found": 0,
        "recommended_products": [],
        "diversity_stats": {},
        "processing_logs": [],
        "errors": []
    }

    try:
        # Step 1: Create initial state
        state = create_initial_state()
        state["conversation_history"].append(HumanMessage(content=user_query))

        # Step 2: Run semantic parser to extract filters
        try:
            state = semantic_parser_node(state)
            result["extracted_filters"] = dict(state["explicit_filters"])
            result["implicit_preferences"] = dict(state["implicit_preferences"])
        except Exception as e:
            result["errors"].append(f"Semantic parser error: {str(e)}")
            return result

        # Step 3: Extract location data if present
        filters = state["explicit_filters"]
        user_lat, user_lon, coords = None, None, None
        result["location_data"] = {
            "zip_code": filters.get("zip"),
            "coordinates": [user_lat, user_lon] if coords else None,
            "search_radius": filters.get("search_radius"),
            "user_latitude": state.get("user_latitude"),
            "user_longitude": state.get("user_longitude")
        }

        # Step 4: Run Method 2
        try:
            products, reasoning = recommend_method2(
                explicit_filters=state["explicit_filters"],
                implicit_preferences=state["implicit_preferences"],
                top_k=20,
                num_brands=4
            )
            result["products_found"] = len(products)
            result["recommended_products"] = products
            result["llm_reasoning"] = reasoning

            # Calculate diversity stats
            if products:
                # Electronics products use 'brand' and 'title' fields
                brands = [
                    p.get("brand") or p.get("make") or p.get("product", {}).get("brand") or ""
                    for p in products
                ]
                titles = [
                    p.get("title") or p.get("product_name") or p.get("product", {}).get("title") or ""
                    for p in products
                ]
                brand_titles = [
                    f"{p.get('brand') or p.get('make') or p.get('product', {}).get('brand') or ''} {p.get('title') or p.get('product_name') or p.get('product', {}).get('title') or ''}"
                    for p in products
                ]
                from collections import Counter
                brand_counts = Counter(brands)
                title_counts = Counter(titles)
                brand_title_counts = Counter(brand_titles)

                result["diversity_stats"] = {
                    "unique_brands": len(set(brands)),
                    "unique_titles": len(set(titles)),
                    "unique_brand_titles": len(set(brand_titles)),
                    "brand_distribution": dict(brand_counts),
                    "title_distribution": dict(title_counts),
                    "brand_title_distribution": dict(brand_title_counts)
                }
                result["suggested_brands"] = list(brand_counts.keys())

        except Exception as e:
            result["errors"].append(f"Method 2 error: {str(e)}")
            import traceback
            result["errors"].append(traceback.format_exc())
            return result

        # Step 5: Capture processing logs
        result["processing_logs"] = log_capture.logs

    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")
        import traceback
        result["errors"].append(traceback.format_exc())

    finally:
        # Clean up log handlers
        for logger_name in ['processing.method2', 'processing.vector_ranker',
                            'tools.local_electronics_store',
                            'idss_agent.processing.semantic_parser']:
            logger = logging.getLogger(logger_name)
            logger.removeHandler(log_capture)

    return result


def format_output(result: dict, verbose: bool = False) -> str:
    """
    Format the result as JSON output.

    Args:
        result: Result dictionary from test pipeline
        verbose: If True, include processing logs

    Returns:
        Formatted JSON string
    """
    # Create a clean output structure
    output = {
        "method": result["method"],
        "user_query": result["user_query"],
        "extracted_filters": result["extracted_filters"],
        "implicit_preferences": result["implicit_preferences"],
        "location_data": result["location_data"],
        "products_found": result["products_found"]
    }

    # Add method-specific fields
    if "llm_reasoning" in result and result["llm_reasoning"]:
        output["llm_reasoning"] = result["llm_reasoning"]
    if "suggested_brands" in result and result["suggested_brands"]:
        output["suggested_brands"] = result["suggested_brands"]

    # Always add full product list (like test_recommendation.py)
    output["recommended_products"] = result["recommended_products"]

    # Add diversity stats AFTER products
    output["diversity_stats"] = result["diversity_stats"]

    # Add processing logs if verbose
    if verbose:
        output["processing_logs"] = result["processing_logs"]

    # Add errors if any
    if result["errors"]:
        output["errors"] = result["errors"]

    return json.dumps(output, indent=2, default=str)


def main():
    """Main entry point for the test script."""

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        print("Please set it with: export OPENAI_API_KEY='sk-...'", file=sys.stderr)
        sys.exit(1)

    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_recommendation_methods.py \"USER QUERY\" [--method 1|2] [--verbose]", file=sys.stderr)
        print("Examples:", file=sys.stderr)
        print("  python scripts/test_recommendation_methods.py \"I want a gaming laptop under $1500\"", file=sys.stderr)
        print("  python scripts/test_recommendation_methods.py \"I want a gaming laptop under $1500\" --method 1", file=sys.stderr)
        print("  python scripts/test_recommendation_methods.py \"I want a gaming laptop under $1500\" --method 2", file=sys.stderr)
        print("  python scripts/test_recommendation_methods.py \"I want a gaming laptop under $1500\" --verbose", file=sys.stderr)
        sys.exit(1)

    user_query = sys.argv[1]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Determine which method to use
    method = None
    if "--method" in sys.argv:
        method_idx = sys.argv.index("--method")
        if method_idx + 1 < len(sys.argv):
            method = sys.argv[method_idx + 1]

    # Run the test
    if method == "2":
        print("Running Method 2: Web Search + Parallel local database queries", file=sys.stderr)
        result = test_method2_pipeline(user_query)
    else:
        # Default to Method 1
        print("Running Method 1: Local database search + Vector ranking + MMR diversification", file=sys.stderr)
        result = test_method1_pipeline(user_query)

    # Output the result as JSON
    print(format_output(result, verbose=verbose))

    # Exit with error code if there were errors
    if result["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
