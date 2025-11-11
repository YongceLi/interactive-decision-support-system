#!/usr/bin/env python3
"""
Standalone test script for recommendation engine.

Usage:
    python scripts/test_recommendation.py "I want a safe and stylish car for my daughter"

Output: JSON with extracted filters, SQL query, and recommended vehicles
"""

import os
import sys
import json
import logging
from pathlib import Path
from io import StringIO
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
load_dotenv(project_root / ".env")

# Import components
from idss_agent.state.schema import create_initial_state
from idss_agent.processing.semantic_parser import semantic_parser_node
from idss_agent.processing.recommendation import update_recommendation_list
from idss_agent.tools.zipcode_lookup import get_location_from_zip_or_coords
from langchain_core.messages import HumanMessage


class LogCapture(logging.Handler):
    """Custom logging handler to capture SQL queries and important logs."""

    def __init__(self):
        super().__init__()
        self.logs = []
        self.sql_query = None

    def emit(self, record):
        msg = self.format(record)
        self.logs.append({
            "level": record.levelname,
            "message": msg,
            "logger": record.name
        })

        # Capture SQL query if it appears in logs
        if "SELECT" in msg and "FROM vehicle_listings" in msg:
            self.sql_query = msg


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
    for logger_name in ['idss_agent.tools.local_vehicle_store',
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
        "location_data": None,
        "sql_query": None,
        "search_strategy": None,
        "vehicles_found": 0,
        "recommended_vehicles": [],
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
        if filters.get("zip") or state.get("user_latitude"):
            coords = get_location_from_zip_or_coords(
                zipcode=filters.get("zip"),
                latitude=state.get("user_latitude"),
                longitude=state.get("user_longitude")
            )

            result["location_data"] = {
                "zip_code": filters.get("zip"),
                "coordinates": list(coords) if coords else None,
                "search_radius": filters.get("search_radius"),
                "user_latitude": state.get("user_latitude"),
                "user_longitude": state.get("user_longitude")
            }

        # Step 4: Run recommendation engine
        try:
            state = update_recommendation_list(state)
            result["vehicles_found"] = len(state.get("recommended_vehicles", []))
            result["recommended_vehicles"] = state.get("recommended_vehicles", [])
        except Exception as e:
            result["errors"].append(f"Recommendation engine error: {str(e)}")
            return result

        # Step 5: Capture SQL query from logs
        result["sql_query"] = log_capture.sql_query

        # Step 6: Capture processing logs
        result["processing_logs"] = log_capture.logs

        # Step 7: Determine search strategy (from logs or state)
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
        for logger_name in ['idss_agent.tools.local_vehicle_store',
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
        "location_data": result["location_data"],
        "sql_query": result["sql_query"],
        "search_strategy": result["search_strategy"],
        "vehicles_found": result["vehicles_found"],
        "recommended_vehicles": result["recommended_vehicles"]
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
        print("Example: python scripts/test_recommendation.py \"I want a safe car for my daughter\"", file=sys.stderr)
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
