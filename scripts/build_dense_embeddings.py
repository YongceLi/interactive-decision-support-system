#!/usr/bin/env python3
"""
Build dense embeddings for all vehicles in the database.
Run this offline whenever database is updated.

Usage:
    python scripts/build_dense_embeddings.py
    python scripts/build_dense_embeddings.py --batch-size 256 --model all-mpnet-base-v2
    python scripts/build_dense_embeddings.py --limit 100  # For testing
"""
import argparse
import json
import sqlite3
import sys
import numpy as np
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def generate_vehicle_description(vehicle: Dict[str, Any]) -> str:
    """
    Convert structured vehicle data into natural language description.
    This is what the language model embedding will encode.

    Handles both formats:
    - Unified format (flat with "build" and "dealer" objects)
    - Auto.dev format (nested with "vehicle" and "retailListing" objects)
    """
    # Check which format we have
    is_unified = "data_source" in vehicle or "build" in vehicle

    if is_unified:
        # Unified format: extract from top-level and "build" object
        build = vehicle.get("build", {})
        dealer = vehicle.get("dealer", {})

        v_year = build.get("year") or vehicle.get("year")
        v_make = build.get("make") or vehicle.get("make")
        v_model = build.get("model") or vehicle.get("model")
        v_trim = build.get("trim") or vehicle.get("trim")
        v_body_style = build.get("body_type") or vehicle.get("body_style")
        v_engine = build.get("engine") or vehicle.get("engine")
        v_fuel = build.get("fuel_type") or vehicle.get("fuel_type")
        v_drivetrain = build.get("drivetrain") or vehicle.get("drivetrain")
        v_transmission = build.get("transmission") or vehicle.get("transmission")
        v_doors = build.get("doors") or vehicle.get("doors")
        v_seats = build.get("std_seating") or vehicle.get("seats")
        v_exterior_color = vehicle.get("exterior_color")
        v_interior_color = vehicle.get("interior_color")

        r_price = vehicle.get("price")
        r_miles = vehicle.get("miles") or vehicle.get("mileage")
        r_used = vehicle.get("inventory_type") == "used"
        r_cpo = vehicle.get("is_certified") or False
        r_city = dealer.get("city")
        r_state = dealer.get("state")
    else:
        # Auto.dev format: nested structure
        v = vehicle.get("vehicle", {})
        r = vehicle.get("retailListing", {})

        v_year = v.get("year")
        v_make = v.get("make")
        v_model = v.get("model")
        v_trim = v.get("trim")
        v_body_style = v.get("bodyStyle") or v.get("style")
        v_engine = v.get("engine")
        v_fuel = v.get("fuel")
        v_drivetrain = v.get("drivetrain")
        v_transmission = v.get("transmission")
        v_doors = v.get("doors")
        v_seats = v.get("seats")
        v_exterior_color = v.get("exteriorColor")
        v_interior_color = v.get("interiorColor")

        r_price = r.get("price")
        r_miles = r.get("miles")
        r_used = r.get("used", True)
        r_cpo = r.get("cpo", False)
        r_city = r.get("city")
        r_state = r.get("state")

    # Build description parts
    parts = []

    # Core identity
    if v_year and v_make and v_model:
        identity = f"{v_year} {v_make} {v_model}"
        if v_trim:
            identity += f" {v_trim}"
        parts.append(identity)

    # Body and type
    if v_body_style:
        parts.append(f"{v_body_style} body style")

    # Powertrain
    if v_engine:
        parts.append(f"{v_engine} engine")
    if v_fuel:
        parts.append(f"{v_fuel} fuel")
    if v_drivetrain:
        parts.append(f"{v_drivetrain} drivetrain")
    if v_transmission:
        parts.append(f"{v_transmission} transmission")

    # Capacity
    if v_seats:
        parts.append(f"{v_seats} seats")
    if v_doors:
        parts.append(f"{v_doors} doors")

    # Colors
    if v_exterior_color:
        parts.append(f"{v_exterior_color} exterior")
    if v_interior_color:
        parts.append(f"{v_interior_color} interior")

    # Price and condition
    if r_price:
        parts.append(f"${r_price:,}")
    if r_miles:
        parts.append(f"{r_miles:,} miles")
    if r_used:
        parts.append("used vehicle")
    else:
        parts.append("new vehicle")
    if r_cpo:
        parts.append("certified pre-owned")

    # Location
    if r_city and r_state:
        parts.append(f"located in {r_city}, {r_state}")

    return ". ".join(parts) + "." if parts else "vehicle"


def build_embeddings(
    db_path: Path,
    model_name: str = "all-MiniLM-L6-v2",
    batch_size: int = 256,
    version: str = "v1",
    limit: int = None
):
    """
    Generate dense embeddings for all vehicles.

    Args:
        db_path: Path to vehicle database
        model_name: Sentence transformer model name
        batch_size: Number of vehicles to process at once
        version: Embedding version identifier
        limit: Optional limit for testing (processes first N vehicles)
    """
    try:
        from sentence_transformers import SentenceTransformer
        from tqdm import tqdm
    except ImportError:
        print("ERROR: Required packages not installed")
        print("Please run: pip install sentence-transformers tqdm")
        sys.exit(1)

    # Load model
    print(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)
    print(f"✓ Model loaded (dimension: {model.get_sentence_embedding_dimension()})")

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get vehicle count
    cursor.execute("SELECT COUNT(*) as cnt FROM unified_vehicle_listings")
    total = cursor.fetchone()["cnt"]

    if limit:
        total = min(total, limit)
        print(f"Processing {total} vehicles (limited for testing)")
    else:
        print(f"Processing {total} vehicles")

    # Fetch vehicles
    if limit:
        rows = conn.execute(f"SELECT vin, raw_json FROM unified_vehicle_listings LIMIT {limit}").fetchall()
    else:
        rows = conn.execute("SELECT vin, raw_json FROM unified_vehicle_listings").fetchall()

    # Process in batches
    batch_vins = []
    batch_texts = []
    inserted = 0
    errors = 0

    pbar = tqdm(total=total, desc="Generating embeddings")

    for row in rows:
        vin = row["vin"]

        try:
            vehicle_data = json.loads(row["raw_json"])

            # Generate description
            description = generate_vehicle_description(vehicle_data)

            batch_vins.append(vin)
            batch_texts.append(description)

            # Process batch
            if len(batch_texts) >= batch_size:
                # Filter out any None or empty texts
                valid_indices = [i for i, text in enumerate(batch_texts) if text and isinstance(text, str) and text.strip()]
                valid_texts = [batch_texts[i] for i in valid_indices]
                valid_vins = [batch_vins[i] for i in valid_indices]

                if valid_texts:
                    embeddings = model.encode(valid_texts, show_progress_bar=False, convert_to_numpy=True)

                    # Insert into database
                    for vin, text, embedding in zip(valid_vins, valid_texts, embeddings):
                        embedding_blob = embedding.astype(np.float32).tobytes()

                        conn.execute("""
                            INSERT OR REPLACE INTO vehicle_dense_embeddings
                            (vin, embedding, embedding_model, embedding_version, description_text)
                            VALUES (?, ?, ?, ?, ?)
                        """, (vin, embedding_blob, model_name, version, text))

                    inserted += len(valid_vins)
                    conn.commit()

                batch_vins = []
                batch_texts = []
                pbar.update(batch_size)

        except Exception as e:
            errors += 1
            if errors < 10:  # Only print first 10 errors
                print(f"\nWarning: Failed to process VIN {vin}: {e}")
            pbar.update(1)
            continue

    # Process remaining batch
    if batch_texts:
        try:
            print(f"\nProcessing final batch of {len(batch_texts)} vehicles...")

            # Debug: Check for None or invalid values
            for i, text in enumerate(batch_texts):
                if text is None:
                    print(f"  ERROR: batch_texts[{i}] is None!")
                elif not isinstance(text, str):
                    print(f"  ERROR: batch_texts[{i}] is not a string: {type(text)}")
                elif not text.strip():
                    print(f"  WARNING: batch_texts[{i}] is empty")

            # Filter out any None or empty texts
            valid_indices = [i for i, text in enumerate(batch_texts) if text and isinstance(text, str) and text.strip()]
            valid_texts = [batch_texts[i] for i in valid_indices]
            valid_vins = [batch_vins[i] for i in valid_indices]

            if not valid_texts:
                print("  ERROR: No valid texts to encode!")
                return

            print(f"  Encoding {len(valid_texts)} valid texts...")
            embeddings = model.encode(valid_texts, show_progress_bar=False, convert_to_numpy=True)
            print(f"  Embeddings shape: {embeddings.shape}")

            for i, (vin, text, embedding) in enumerate(zip(valid_vins, valid_texts, embeddings)):
                embedding_blob = embedding.astype(np.float32).tobytes()
                conn.execute("""
                    INSERT OR REPLACE INTO vehicle_dense_embeddings
                    (vin, embedding, embedding_model, embedding_version, description_text)
                    VALUES (?, ?, ?, ?, ?)
                """, (vin, embedding_blob, model_name, version, text))
            inserted += len(valid_vins)
            conn.commit()
            pbar.update(len(valid_vins))
        except Exception as e:
            import traceback
            print(f"\nError processing final batch: {e}")
            print(f"Traceback: {traceback.format_exc()}")

    pbar.close()

    print(f"\n✓ Successfully generated {inserted} embeddings")
    if errors > 0:
        print(f"⚠ Encountered {errors} errors")

    # Show sample
    cursor.execute("""
        SELECT vin, description_text
        FROM vehicle_dense_embeddings
        LIMIT 3
    """)
    print("\nSample descriptions:")
    for row in cursor:
        print(f"  VIN {row['vin'][:10]}...: {row['description_text'][:100]}...")

    conn.close()
    print(f"\n✓ Embeddings saved to {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Build dense embeddings for vehicles")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/car_dataset_idss/uni_vehicles.db"),
        help="Path to vehicle database"
    )
    parser.add_argument(
        "--model",
        default="all-MiniLM-L6-v2",
        help="Sentence transformer model name (default: all-MiniLM-L6-v2)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Batch size for embedding generation (default: 256)"
    )
    parser.add_argument(
        "--version",
        default="v1",
        help="Embedding version identifier (default: v1)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of vehicles for testing (default: process all)"
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found at {args.db_path}")
        sys.exit(1)

    build_embeddings(
        args.db_path,
        model_name=args.model,
        batch_size=args.batch_size,
        version=args.version,
        limit=args.limit
    )


if __name__ == "__main__":
    main()
