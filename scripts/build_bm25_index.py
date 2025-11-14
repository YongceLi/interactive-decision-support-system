#!/usr/bin/env python3
"""
Build BM25 index for sparse keyword-based vehicle search.

This script:
1. Loads all vehicles from the database
2. Creates text documents from vehicle attributes
3. Builds BM25 index using rank-bm25
4. Saves index and VIN list to pickle files

Usage:
    python scripts/build_bm25_index.py
    python scripts/build_bm25_index.py --db data/california_vehicles.db
"""
import argparse
import pickle
import sqlite3
from pathlib import Path
from typing import Dict, Any, List
from rank_bm25 import BM25Okapi

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from idss_agent.utils.logger import get_logger
from idss_agent.utils.config import get_config

logger = get_logger("scripts.build_bm25_index")


def build_vehicle_document(vehicle: Dict[str, Any]) -> str:
    """
    Build searchable text document from vehicle attributes.

    This creates a keyword-rich text representation that BM25 can search.

    Args:
        vehicle: Vehicle dictionary from database

    Returns:
        Space-separated text document
    """
    parts = []

    # Core identity (most important for matching)
    if vehicle.get("make"):
        parts.append(vehicle["make"])
    if vehicle.get("model"):
        parts.append(vehicle["model"])
    if vehicle.get("trim"):
        parts.append(vehicle["trim"])

    # Year
    if vehicle.get("year"):
        parts.append(str(vehicle["year"]))

    # Body style
    if vehicle.get("body_style"):
        parts.append(vehicle["body_style"])

    # Colors
    if vehicle.get("exterior_color"):
        parts.append(vehicle["exterior_color"])
    if vehicle.get("interior_color"):
        parts.append(vehicle["interior_color"])

    # Powertrain
    if vehicle.get("engine"):
        parts.append(vehicle["engine"])
    if vehicle.get("drivetrain"):
        parts.append(vehicle["drivetrain"])
    if vehicle.get("fuel_type"):
        parts.append(vehicle["fuel_type"])
    if vehicle.get("transmission"):
        parts.append(vehicle["transmission"])

    # Physical attributes
    if vehicle.get("doors"):
        parts.append(f"{vehicle['doors']}door")
    if vehicle.get("seats"):
        parts.append(f"{vehicle['seats']}seater")

    # Condition keywords
    if vehicle.get("is_cpo"):
        parts.extend(["certified", "pre-owned", "cpo"])
    if vehicle.get("is_used") is False:
        parts.append("new")
    elif vehicle.get("is_used"):
        parts.append("used")

    return " ".join(str(p) for p in parts if p).lower()


def load_vehicles_from_db(db_path: Path) -> List[Dict[str, Any]]:
    """
    Load all vehicles from SQLite database.

    Args:
        db_path: Path to SQLite database

    Returns:
        List of vehicle dictionaries
    """
    logger.info(f"Loading vehicles from {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query all vehicles with required fields
    cursor.execute("""
        SELECT
            vin, make, model, trim, year, body_style,
            exterior_color, interior_color, engine, drivetrain,
            fuel_type, transmission, doors, seats, is_used, is_cpo
        FROM unified_vehicle_listings
        WHERE vin IS NOT NULL
    """)

    vehicles = []
    for row in cursor.fetchall():
        vehicles.append(dict(row))

    conn.close()

    logger.info(f"✓ Loaded {len(vehicles)} vehicles")
    return vehicles


def build_bm25_index(vehicles: List[Dict[str, Any]]) -> tuple:
    """
    Build BM25 index from vehicles.

    Args:
        vehicles: List of vehicle dictionaries

    Returns:
        Tuple of (BM25Okapi index, list of VINs)
    """
    logger.info("Building BM25 index...")

    # Build corpus (tokenized documents)
    corpus = []
    vins = []

    for vehicle in vehicles:
        doc = build_vehicle_document(vehicle)
        tokens = doc.split()  # Simple whitespace tokenization
        corpus.append(tokens)
        vins.append(vehicle["vin"])

    # Build BM25 index
    bm25 = BM25Okapi(corpus)

    logger.info(f"✓ Built BM25 index with {len(vins)} documents")

    return bm25, vins


def main():
    parser = argparse.ArgumentParser(description="Build BM25 index for vehicle search")
    parser.add_argument(
        "--db",
        type=str,
        help="Path to vehicle database (default: from config)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for index files (default: data/car_dataset_idss)",
    )

    args = parser.parse_args()

    # Get paths from arguments or use defaults
    if args.db:
        db_path = Path(args.db)
    else:
        db_path = Path('data/car_dataset_idss/uni_vehicles.db')

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path('data/car_dataset_idss')

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("BM25 INDEX BUILDER")
    logger.info("=" * 60)
    logger.info(f"Database: {db_path}")
    logger.info(f"Output directory: {output_dir}")

    # Step 1: Load vehicles
    vehicles = load_vehicles_from_db(db_path)

    # Step 2: Build BM25 index
    bm25, vins = build_bm25_index(vehicles)

    # Step 3: Save index
    index_path = output_dir / "bm25_index.pkl"
    vins_path = output_dir / "bm25_vins.pkl"

    logger.info(f"Saving BM25 index to {index_path}")
    with open(index_path, "wb") as f:
        pickle.dump(bm25, f)

    logger.info(f"Saving VIN list to {vins_path}")
    with open(vins_path, "wb") as f:
        pickle.dump(vins, f)

    logger.info("=" * 60)
    logger.info("✓ BM25 INDEX BUILD COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Index: {index_path}")
    logger.info(f"VINs: {vins_path}")
    logger.info(f"Total vehicles: {len(vins)}")

    # Test query
    logger.info("\nTesting index with sample query...")
    test_query = "honda accord red"
    test_tokens = test_query.split()
    scores = bm25.get_scores(test_tokens)
    top_idx = scores.argmax()
    logger.info(f"Query: '{test_query}'")
    logger.info(f"Top match: VIN {vins[top_idx]} (score: {scores[top_idx]:.3f})")
    logger.info(f"Vehicle: {build_vehicle_document(vehicles[top_idx])}")


if __name__ == "__main__":
    main()
