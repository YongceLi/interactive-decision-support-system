#!/usr/bin/env python3
"""
Test embedding similarity for vehicle variants.

Usage:
    python scripts/test_embedding_similarity.py "I want an affordable sedan" data/test_price_variants.csv
    python scripts/test_embedding_similarity.py "I want a hybrid" data/test_fuel_variants.csv
    python scripts/test_embedding_similarity.py "I want a luxury car" data/test_make_variants.csv

CSV Format:
    year,make,model,trim,body_style,engine,fuel_type,drivetrain,transmission,
    doors,seats,exterior_color,interior_color,price,mileage,is_used,is_cpo,city,state

Output:
    Table showing: vehicle info, similarity score, sorted by similarity (highest first)
"""
import argparse
import csv
import sys
import os
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env")


def parse_user_query(user_query: str) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Parse user query using semantic parser to extract structured filters.
    Then build query text from filters (same as recommendation system).

    Args:
        user_query: Raw user query string

    Returns:
        Tuple of (explicit_filters, implicit_preferences, query_text)
    """
    try:
        from idss_agent.state.schema import create_initial_state
        from idss_agent.processing.semantic_parser import semantic_parser_node
        from idss_agent.processing.dense_ranker import build_query_text
        from langchain_core.messages import HumanMessage
    except ImportError as e:
        print(f"ERROR: Failed to import required modules: {e}")
        print("Please ensure the IDSS agent modules are available")
        sys.exit(1)

    # Create initial state
    state = create_initial_state()
    state["conversation_history"].append(HumanMessage(content=user_query))

    # Run semantic parser
    try:
        state = semantic_parser_node(state)
    except Exception as e:
        print(f"ERROR: Semantic parser failed: {e}")
        print("Please ensure OPENAI_API_KEY is set")
        sys.exit(1)

    explicit_filters = dict(state["explicit_filters"])
    implicit_preferences = dict(state["implicit_preferences"])

    # Build query text from filters (same as recommendation system)
    query_text = build_query_text(explicit_filters, implicit_preferences)

    return explicit_filters, implicit_preferences, query_text


def load_vehicles_from_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """
    Load vehicles from CSV file.

    Args:
        csv_path: Path to CSV file

    Returns:
        List of vehicle dictionaries
    """
    vehicles = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert types
            vehicle = {}
            for key, value in row.items():
                # Skip empty values
                if value.strip() == '':
                    vehicle[key] = None
                    continue

                # Convert numeric fields
                if key in ['year', 'doors', 'seats']:
                    vehicle[key] = int(value) if value else None
                elif key in ['price', 'mileage']:
                    vehicle[key] = float(value) if value else None
                elif key in ['is_used', 'is_cpo']:
                    vehicle[key] = value.lower() in ['true', '1', 'yes'] if value else None
                else:
                    vehicle[key] = value

            vehicles.append(vehicle)

    return vehicles


def generate_vehicle_description(vehicle: Dict[str, Any]) -> str:
    """
    Convert structured vehicle data into natural language description.
    Same logic as build_dense_embeddings.py

    Args:
        vehicle: Vehicle dictionary (CSV row)

    Returns:
        Natural language description
    """
    parts = []

    # Core identity (exclude year - numeric)
    v_make = vehicle.get("make")
    v_model = vehicle.get("model")
    v_trim = vehicle.get("trim")

    if v_make and v_model:
        identity = f"{v_make} {v_model}"
        if v_trim:
            identity += f" {v_trim}"
        parts.append(identity)

    # Body and type
    v_body_style = vehicle.get("body_style")
    if v_body_style:
        parts.append(f"{v_body_style} body style")

    # Powertrain
    v_engine = vehicle.get("engine")
    if v_engine:
        parts.append(f"{v_engine} engine")

    v_fuel = vehicle.get("fuel_type")
    if v_fuel:
        parts.append(f"{v_fuel} fuel")

    v_drivetrain = vehicle.get("drivetrain")
    if v_drivetrain:
        parts.append(f"{v_drivetrain} drivetrain")

    v_transmission = vehicle.get("transmission")
    if v_transmission:
        parts.append(f"{v_transmission} transmission")

    # Capacity - REMOVED (numeric: doors, seats)
    # v_seats = vehicle.get("seats")
    # if v_seats:
    #     parts.append(f"{v_seats} seats")
    # v_doors = vehicle.get("doors")
    # if v_doors:
    #     parts.append(f"{v_doors} doors")

    # Colors
    v_exterior_color = vehicle.get("exterior_color")
    if v_exterior_color:
        parts.append(f"{v_exterior_color} exterior")

    v_interior_color = vehicle.get("interior_color")
    if v_interior_color:
        parts.append(f"{v_interior_color} interior")

    # Price and condition - REMOVED price and mileage (numeric)
    # r_price = vehicle.get("price")
    # if r_price:
    #     parts.append(f"${r_price:,.0f}")
    # r_miles = vehicle.get("mileage")
    # if r_miles:
    #     parts.append(f"{r_miles:,.0f} miles")

    r_used = vehicle.get("is_used")
    if r_used:
        parts.append("used vehicle")
    else:
        parts.append("new vehicle")

    r_cpo = vehicle.get("is_cpo")
    if r_cpo:
        parts.append("certified pre-owned")

    # Location
    r_city = vehicle.get("city")
    r_state = vehicle.get("state")
    if r_city and r_state:
        parts.append(f"located in {r_city}, {r_state}")

    return ". ".join(parts) + "." if parts else "vehicle"


def extract_vehicle_features(vehicle: Dict[str, Any]) -> List[str]:
    """
    Extract individual features from vehicle as separate strings.
    Each feature will be embedded separately for sum-based embedding.

    Args:
        vehicle: Vehicle dictionary

    Returns:
        List of feature strings
    """
    features = []

    # Core identity
    v_make = vehicle.get("make")
    v_model = vehicle.get("model")
    v_trim = vehicle.get("trim")
    if v_make and v_model:
        identity = f"{v_make} {v_model}"
        if v_trim:
            identity += f" {v_trim}"
        features.append(identity)

    # Body style
    v_body_style = vehicle.get("body_style")
    if v_body_style:
        features.append(f"{v_body_style} body style")

    # Engine
    v_engine = vehicle.get("engine")
    if v_engine:
        features.append(f"{v_engine} engine")

    # Fuel type
    v_fuel = vehicle.get("fuel_type")
    if v_fuel:
        features.append(f"{v_fuel} fuel")

    # Drivetrain
    v_drivetrain = vehicle.get("drivetrain")
    if v_drivetrain:
        features.append(f"{v_drivetrain} drivetrain")

    # Transmission
    v_transmission = vehicle.get("transmission")
    if v_transmission:
        features.append(f"{v_transmission} transmission")

    # Colors
    v_exterior_color = vehicle.get("exterior_color")
    if v_exterior_color:
        features.append(f"{v_exterior_color} exterior")

    v_interior_color = vehicle.get("interior_color")
    if v_interior_color:
        features.append(f"{v_interior_color} interior")

    # Condition
    r_used = vehicle.get("is_used")
    if r_used:
        features.append("used vehicle")
    else:
        features.append("new vehicle")

    r_cpo = vehicle.get("is_cpo")
    if r_cpo:
        features.append("certified pre-owned")

    # Location
    r_city = vehicle.get("city")
    r_state = vehicle.get("state")
    if r_city and r_state:
        features.append(f"located in {r_city}, {r_state}")

    return features


def extract_query_features(
    explicit_filters: Dict[str, Any],
    implicit_preferences: Dict[str, Any]
) -> List[str]:
    """
    Extract individual features from query filters/preferences as separate strings.
    Each feature will be embedded separately for sum-based embedding.

    Args:
        explicit_filters: Explicit user filters
        implicit_preferences: Implicit user preferences

    Returns:
        List of feature strings
    """
    features = []

    # Vehicle identity
    if explicit_filters.get("make"):
        features.append(f"{explicit_filters['make']}")
    if explicit_filters.get("model"):
        features.append(f"{explicit_filters['model']}")
    if explicit_filters.get("trim"):
        features.append(f"{explicit_filters['trim']}")

    # Body style
    if explicit_filters.get("body_style"):
        features.append(f"{explicit_filters['body_style']} body style")

    # Powertrain
    if explicit_filters.get("engine"):
        features.append(f"{explicit_filters['engine']} engine")
    if explicit_filters.get("fuel_type"):
        features.append(f"{explicit_filters['fuel_type']} fuel")
    if explicit_filters.get("drivetrain"):
        features.append(f"{explicit_filters['drivetrain']} drivetrain")
    if explicit_filters.get("transmission"):
        features.append(f"{explicit_filters['transmission']} transmission")

    # Colors
    if explicit_filters.get("exterior_color"):
        features.append(f"{explicit_filters['exterior_color']} exterior")
    if explicit_filters.get("interior_color"):
        features.append(f"{explicit_filters['interior_color']} interior")

    # Condition
    if explicit_filters.get("is_used") is False:
        features.append("new vehicle")
    elif explicit_filters.get("is_used") is True:
        features.append("used vehicle")
    if explicit_filters.get("is_cpo"):
        features.append("certified pre-owned")

    # Implicit preferences
    priorities = implicit_preferences.get("priorities", []) or []
    for priority in priorities:
        features.append(str(priority))

    if implicit_preferences.get("usage_patterns"):
        features.append(f"{implicit_preferences['usage_patterns']}")

    if implicit_preferences.get("lifestyle"):
        features.append(f"{implicit_preferences['lifestyle']}")

    concerns = implicit_preferences.get("concerns", []) or []
    for concern in concerns:
        features.append(str(concern))

    if implicit_preferences.get("brand_affinity"):
        features.append(f"{implicit_preferences['brand_affinity']}")

    if implicit_preferences.get("budget_sensitivity"):
        features.append(f"{implicit_preferences['budget_sensitivity']}")

    if implicit_preferences.get("notes"):
        features.append(f"{implicit_preferences['notes']}")

    return features


def embed_texts(texts: List[str], model_name: str = "all-mpnet-base-v2") -> np.ndarray:
    """
    Embed texts using sentence transformer model.

    Args:
        texts: List of text strings to embed
        model_name: Sentence transformer model name

    Returns:
        Numpy array of embeddings (shape: [len(texts), embedding_dim])
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed")
        print("Please run: pip install sentence-transformers")
        sys.exit(1)

    try:
        from tqdm import tqdm
    except ImportError:
        print("WARNING: tqdm not installed, no progress bar will be shown")
        print("Install with: pip install tqdm")
        model = SentenceTransformer(model_name)
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return embeddings

    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    return embeddings


def embed_as_sum_of_features(
    feature_lists: List[List[str]],
    model_name: str = "all-mpnet-base-v2"
) -> np.ndarray:
    """
    Embed each item by embedding its individual features separately,
    then summing and normalizing the embeddings.

    Args:
        feature_lists: List of feature lists, where each inner list contains
                      the features for one item (vehicle or query)
        model_name: Sentence transformer model name

    Returns:
        Numpy array of embeddings (shape: [len(feature_lists), embedding_dim])
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed")
        print("Please run: pip install sentence-transformers")
        sys.exit(1)

    model = SentenceTransformer(model_name)

    # Flatten all features for batch encoding
    all_features = []
    feature_counts = []
    for features in feature_lists:
        all_features.extend(features)
        feature_counts.append(len(features))

    # Embed all features at once
    if not all_features:
        # Return zero vector if no features
        embedding_dim = model.get_sentence_embedding_dimension()
        return np.zeros((len(feature_lists), embedding_dim))

    all_embeddings = model.encode(all_features, show_progress_bar=True, convert_to_numpy=True)

    # Sum embeddings for each item and normalize
    result_embeddings = []
    idx = 0
    for count in feature_counts:
        if count == 0:
            # Zero vector for items with no features
            embedding_dim = model.get_sentence_embedding_dimension()
            result_embeddings.append(np.zeros(embedding_dim))
        else:
            # Sum the embeddings for this item's features
            item_embeddings = all_embeddings[idx:idx + count]
            summed = np.sum(item_embeddings, axis=0)
            # L2 normalize
            normalized = summed / (np.linalg.norm(summed) + 1e-8)
            result_embeddings.append(normalized)
        idx += count

    return np.array(result_embeddings)


def compute_similarities(query_embedding: np.ndarray, vehicle_embeddings: np.ndarray) -> List[float]:
    """
    Compute cosine similarity between query and each vehicle.

    Args:
        query_embedding: Query embedding (shape: [embedding_dim])
        vehicle_embeddings: Vehicle embeddings (shape: [num_vehicles, embedding_dim])

    Returns:
        List of similarity scores
    """
    # Normalize embeddings
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    vehicle_norms = vehicle_embeddings / np.linalg.norm(vehicle_embeddings, axis=1, keepdims=True)

    # Cosine similarity
    similarities = np.dot(vehicle_norms, query_norm)

    return similarities.tolist()


def format_output_table(
    vehicles: List[Dict[str, Any]],
    similarities: List[float],
    descriptions: List[str]
) -> str:
    """
    Format output as clean text table.

    Args:
        vehicles: List of vehicle dictionaries
        similarities: List of similarity scores
        descriptions: List of vehicle descriptions (what was embedded)

    Returns:
        Formatted table string
    """
    # Sort by similarity (descending)
    sorted_data = sorted(
        zip(vehicles, similarities, descriptions),
        key=lambda x: x[1],
        reverse=True
    )

    lines = []
    lines.append("=" * 120)
    lines.append(f"{'Rank':<6} {'Similarity':<12} {'Vehicle':<50} {'Key Attributes':<50}")
    lines.append("=" * 120)

    for rank, (vehicle, similarity, description) in enumerate(sorted_data, 1):
        # Basic identity
        year = vehicle.get("year", "?")
        make = vehicle.get("make", "?")
        model = vehicle.get("model", "?")
        trim = vehicle.get("trim", "")

        vehicle_str = f"{year} {make} {model}"
        if trim:
            vehicle_str += f" {trim}"

        # Key attributes
        attrs = []

        body_style = vehicle.get("body_style")
        if body_style:
            attrs.append(body_style)

        fuel_type = vehicle.get("fuel_type")
        if fuel_type:
            attrs.append(fuel_type)

        price = vehicle.get("price")
        if price:
            attrs.append(f"${price:,.0f}")

        mileage = vehicle.get("mileage")
        if mileage:
            attrs.append(f"{mileage:,.0f}mi")

        is_used = vehicle.get("is_used")
        if is_used is False:
            attrs.append("New")
        elif is_used is True:
            is_cpo = vehicle.get("is_cpo")
            if is_cpo:
                attrs.append("CPO")
            else:
                attrs.append("Used")

        attr_str = ", ".join(attrs)

        lines.append(f"{rank:<6} {similarity:<12.4f} {vehicle_str:<50} {attr_str:<50}")

    lines.append("=" * 120)

    # Add description samples
    lines.append("\nEmbedded Descriptions (top 3):")
    lines.append("-" * 120)
    for rank, (vehicle, similarity, description) in enumerate(sorted_data[:3], 1):
        lines.append(f"#{rank} (sim={similarity:.4f}): {description}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Test embedding similarity for vehicle variants",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_embedding_similarity.py "I want an affordable sedan" data/test_price_variants.csv
  python scripts/test_embedding_similarity.py "I want a hybrid" data/test_fuel_variants.csv
  python scripts/test_embedding_similarity.py "I want a luxury car" data/test_make_variants.csv
  python scripts/test_embedding_similarity.py "I want a modern SUV" data/test_year_variants.csv
        """
    )

    parser.add_argument("query", help="User query to test")
    parser.add_argument("csv_file", type=Path, help="CSV file with vehicle variants")
    parser.add_argument(
        "--model",
        default="all-mpnet-base-v2",
        help="Sentence transformer model name (default: all-mpnet-base-v2)"
    )
    parser.add_argument(
        "--method",
        choices=["concat", "sum"],
        default="concat",
        help="Embedding method: 'concat' = single concatenated sentence (default), 'sum' = sum of individual feature embeddings"
    )

    args = parser.parse_args()

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='sk-...'")
        sys.exit(1)

    # Validate inputs
    if not args.csv_file.exists():
        print(f"ERROR: CSV file not found: {args.csv_file}")
        sys.exit(1)

    # Parse user query to extract filters (same as recommendation system)
    print(f"Parsing user query with semantic parser...")
    explicit_filters, implicit_preferences, query_text = parse_user_query(args.query)
    print(f"✓ Query parsed")

    # Load vehicles
    print(f"Loading vehicles from {args.csv_file}...")
    vehicles = load_vehicles_from_csv(args.csv_file)
    print(f"✓ Loaded {len(vehicles)} vehicles")

    # Generate descriptions
    print("Generating vehicle descriptions...")
    descriptions = [generate_vehicle_description(v) for v in vehicles]

    # Embed query text (from semantic parser) and vehicles
    print(f"Embedding query and vehicles (model: {args.model}, method: {args.method})...")

    if args.method == "concat":
        # Method 1: Concatenated sentence embedding (original)
        all_texts = [query_text] + descriptions
        embeddings = embed_texts(all_texts, model_name=args.model)
        query_embedding = embeddings[0]
        vehicle_embeddings = embeddings[1:]

    elif args.method == "sum":
        # Method 2: Sum of individual feature embeddings
        # Extract query features
        query_features = extract_query_features(explicit_filters, implicit_preferences)

        # Extract vehicle features
        vehicle_feature_lists = [extract_vehicle_features(v) for v in vehicles]

        # Embed query
        query_embeddings = embed_as_sum_of_features([query_features], model_name=args.model)
        query_embedding = query_embeddings[0]

        # Embed vehicles
        vehicle_embeddings = embed_as_sum_of_features(vehicle_feature_lists, model_name=args.model)

    # Compute similarities
    print("Computing similarities...")
    similarities = compute_similarities(query_embedding, vehicle_embeddings)

    # Format output - show transformation pipeline
    print("\n" + "=" * 120)
    print(f"QUERY TRANSFORMATION PIPELINE (Method: {args.method})")
    print("=" * 120)
    print(f"\n[1] User Input (raw):")
    print(f"    {args.query}")
    print(f"\n[2] Semantic Parser Results:")
    print(f"    Explicit Filters:")
    for key, value in explicit_filters.items():
        if key != "must_have_filters":
            print(f"      - {key}: {value}")
    print(f"    Implicit Preferences:")
    for key, value in implicit_preferences.items():
        if value:  # Only show non-empty values
            print(f"      - {key}: {value}")

    if args.method == "concat":
        print(f"\n[3] Constructed Query Text (what gets embedded):")
        print(f"    {query_text}")
    elif args.method == "sum":
        query_features = extract_query_features(explicit_filters, implicit_preferences)
        print(f"\n[3] Extracted Query Features (each embedded separately, then summed):")
        for i, feature in enumerate(query_features, 1):
            print(f"    [{i}] {feature}")
        print(f"    Total: {len(query_features)} features")
    print("")

    # Show example vehicle transformation
    print("=" * 120)
    print(f"VEHICLE TRANSFORMATION EXAMPLE (Method: {args.method})")
    print("=" * 120)
    print(f"\n[1] Vehicle Info (CSV row):")
    example_vehicle = vehicles[0]
    for key, value in example_vehicle.items():
        if value is not None and value != "":
            print(f"      - {key}: {value}")

    if args.method == "concat":
        print(f"\n[2] Vehicle Description (what gets embedded):")
        print(f"    {descriptions[0]}")
    elif args.method == "sum":
        example_features = extract_vehicle_features(vehicles[0])
        print(f"\n[2] Extracted Vehicle Features (each embedded separately, then summed):")
        for i, feature in enumerate(example_features, 1):
            print(f"    [{i}] {feature}")
        print(f"    Total: {len(example_features)} features")
    print("")

    print("=" * 120)
    print("SIMILARITY RANKINGS")
    print("=" * 120)
    print(f"\nUser Query: \"{args.query}\"")
    print("")

    output = format_output_table(vehicles, similarities, descriptions)
    print(output)

    # Summary statistics
    print("\nSummary Statistics:")
    print(f"  Mean similarity: {np.mean(similarities):.4f}")
    print(f"  Std similarity:  {np.std(similarities):.4f}")
    print(f"  Min similarity:  {np.min(similarities):.4f}")
    print(f"  Max similarity:  {np.max(similarities):.4f}")
    print(f"  Range:           {np.max(similarities) - np.min(similarities):.4f}")
    print("")


if __name__ == "__main__":
    main()
