#!/usr/bin/env python3
"""
Standalone test script for the electronics recommendation engine.

Usage:
    python scripts/test_recommendation.py "I'm shopping for a mid-range gaming laptop"

Output: JSON with extracted filters, search payloads, and recommended products.
"""

import json
import logging
import os
import sys
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
from langchain_core.messages import HumanMessage
from idss_agent.processing.recommendation import update_recommendation_list


class LogCapture(logging.Handler):
    """Custom logging handler to capture API payloads and important logs."""

    def __init__(self):
        super().__init__()
        self.logs = []
        self.search_payload = None

    def emit(self, record):
        msg = self.format(record)
        self.logs.append({
            "level": record.levelname,
            "message": msg,
            "logger": record.name
        })

        # Capture database search payloads for debugging
        if "Electronics search SQL" in msg or "Local database search" in msg:
            self.search_payload = msg


def test_recommendation_pipeline(user_query: str) -> dict:
    """
    Test the recommendation pipeline with a user query.

    Args:
        user_query: Natural language query from user

    Returns:
        Dictionary with all intermediate outputs and results
    """

    # Set up log capture
    log_capture = LogCapture()
    log_capture.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_capture.setFormatter(formatter)

    # Add handler to relevant loggers
    for logger_name in ['idss_agent.tools.local_electronics_store',
                        'idss_agent.processing.recommendation',
                        'idss_agent.processing.semantic_parser']:
        logger = logging.getLogger(logger_name)
        logger.addHandler(log_capture)
        logger.setLevel(logging.DEBUG)

    # Initialize result dictionary
    result = {
        "user_query": user_query,
        "extracted_filters": None,
        "implicit_preferences": None,
        "search_payload": None,
        "search_strategy": None,
        "products_found": 0,
        "recommended_products": [],
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

        # Step 3: Run recommendation engine
        try:
            state = update_recommendation_list(state)
            result["products_found"] = len(state.get("recommended_products", []))
            result["recommended_products"] = state.get("recommended_products", [])
        except Exception as e:
            result["errors"].append(f"Recommendation engine error: {str(e)}")
            return result
        # Step 4: Capture API payloads from logs
        result["search_payload"] = log_capture.search_payload

        # Step 5: Capture processing logs
        result["processing_logs"] = log_capture.logs

        # Step 6: Determine search strategy (from logs or state)
        for log in log_capture.logs:
            if "Search strategy" in log["message"] or "fallback" in log["message"].lower():
                result["search_strategy"] = log["message"]
                break

    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")
        import traceback
        result["errors"].append(traceback.format_exc())

    finally:
        # Clean up log handlers
        for logger_name in ['idss_agent.tools.local_electronics_store',
                            'idss_agent.processing.recommendation',
                            'idss_agent.processing.semantic_parser']:
            logger = logging.getLogger(logger_name)
            logger.removeHandler(log_capture)

    return result


def format_output(result: dict, verbose: bool = False) -> str:
    """
    Format the result as JSON output.

    Args:
        result: Result dictionary from test_recommendation_pipeline
        verbose: If True, include processing logs

    Returns:
        Formatted JSON string
    """
    # Create a clean output structure
    output = {
        "user_query": result["user_query"],
        "extracted_filters": result["extracted_filters"],
        "implicit_preferences": result["implicit_preferences"],
        "search_payload": result["search_payload"],
        "search_strategy": result["search_strategy"],
        "products_found": result["products_found"],
        "recommended_products": result["recommended_products"]
    }

    # Add logs if verbose
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
        print("Usage: python scripts/test_recommendation.py \"USER QUERY\"", file=sys.stderr)
        print("Example: python scripts/test_recommendation.py \"I'm looking for a quiet mechanical keyboard under $150\"", file=sys.stderr)
        sys.exit(1)

    user_query = sys.argv[1]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Run the test
    result = test_recommendation_pipeline(user_query)

    # Output the result as JSON
    print(format_output(result, verbose=verbose))

    # Exit with error code if there were errors
    if result["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
