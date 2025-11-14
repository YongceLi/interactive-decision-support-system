#!/usr/bin/env python3
"""
Build FAISS index from dense embeddings in database.
Run this after build_dense_embeddings.py completes.

Usage:
    python scripts/build_faiss_index.py
    python scripts/build_faiss_index.py --index-type IVF --nlist 100
"""
import argparse
import pickle
import sqlite3
import sys
import numpy as np
from pathlib import Path
from typing import List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_embeddings_from_db(
    db_path: Path,
    model_name: str = "all-mpnet-base-v2",
    version: str = "v1"
) -> Tuple[np.ndarray, List[str]]:
    """
    Load all embeddings and VINs from database.

    Args:
        db_path: Path to vehicle database
        model_name: Embedding model name to filter by
        version: Embedding version to filter by

    Returns:
        Tuple of (embeddings array, list of VINs)
    """
    print(f"Loading embeddings from {db_path}")
    print(f"  Model: {model_name}")
    print(f"  Version: {version}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count total
    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM vehicle_dense_embeddings
        WHERE embedding_model = ? AND embedding_version = ?
    """, (model_name, version))
    total = cursor.fetchone()[0]
    print(f"  Found {total:,} embeddings")

    if total == 0:
        print("ERROR: No embeddings found. Run build_dense_embeddings.py first.")
        sys.exit(1)

    # Load all embeddings
    cursor.execute("""
        SELECT vin, embedding
        FROM vehicle_dense_embeddings
        WHERE embedding_model = ? AND embedding_version = ?
        ORDER BY vin
    """, (model_name, version))

    vins = []
    embeddings_list = []

    print("  Loading embeddings into memory...")
    for row in cursor:
        vin = row[0]
        embedding_blob = row[1]

        # Convert BLOB back to numpy array
        embedding = np.frombuffer(embedding_blob, dtype=np.float32)

        vins.append(vin)
        embeddings_list.append(embedding)

    conn.close()

    # Stack into single array
    embeddings = np.vstack(embeddings_list)
    print(f"✓ Loaded embeddings with shape: {embeddings.shape}")

    return embeddings, vins


def build_flat_index(embeddings: np.ndarray, vins: List[str]) -> Tuple[object, List[str]]:
    """
    Build a simple flat (brute-force) FAISS index.
    Best for smaller datasets or when accuracy is critical.

    Args:
        embeddings: Numpy array of embeddings (N x D)
        vins: List of VINs corresponding to embeddings

    Returns:
        Tuple of (FAISS index, VIN list)
    """
    try:
        import faiss
    except ImportError:
        print("ERROR: faiss-cpu not installed")
        print("Please run: pip install faiss-cpu")
        sys.exit(1)

    print(f"\nBuilding Flat index...")
    dimension = embeddings.shape[1]

    # Create flat L2 index
    index = faiss.IndexFlatL2(dimension)

    # Add embeddings
    print(f"  Adding {len(embeddings):,} vectors...")
    index.add(embeddings)

    print(f"✓ Flat index built with {index.ntotal:,} vectors")
    return index, vins


def build_ivf_index(
    embeddings: np.ndarray,
    vins: List[str],
    nlist: int = 100,
    nprobe: int = 10
) -> Tuple[object, List[str]]:
    """
    Build an IVF (Inverted File) FAISS index for faster search.
    Uses clustering to speed up nearest neighbor search.

    Args:
        embeddings: Numpy array of embeddings (N x D)
        vins: List of VINs corresponding to embeddings
        nlist: Number of clusters (higher = more accurate but slower)
        nprobe: Number of clusters to search (higher = more accurate)

    Returns:
        Tuple of (FAISS index, VIN list)
    """
    try:
        import faiss
    except ImportError:
        print("ERROR: faiss-cpu not installed")
        print("Please run: pip install faiss-cpu")
        sys.exit(1)

    print(f"\nBuilding IVF index with {nlist} clusters...")
    dimension = embeddings.shape[1]

    # Create quantizer (used for clustering)
    quantizer = faiss.IndexFlatL2(dimension)

    # Create IVF index
    index = faiss.IndexIVFFlat(quantizer, dimension, nlist)

    # Train the index on the data
    print(f"  Training index on {len(embeddings):,} vectors...")
    index.train(embeddings)

    # Add embeddings
    print(f"  Adding vectors to index...")
    index.add(embeddings)

    # Set search parameters
    index.nprobe = nprobe

    print(f"✓ IVF index built with {index.ntotal:,} vectors")
    print(f"  nlist={nlist}, nprobe={nprobe}")
    return index, vins


def save_index(
    index: object,
    vins: List[str],
    output_dir: Path,
    model_name: str,
    version: str,
    index_type: str
):
    """
    Save FAISS index and VIN mapping to disk.

    Args:
        index: FAISS index object
        vins: List of VINs
        output_dir: Directory to save files
        model_name: Model name for filename
        version: Version for filename
        index_type: Index type for filename
    """
    try:
        import faiss
    except ImportError:
        print("ERROR: faiss-cpu not installed")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize model name for filename
    model_slug = model_name.replace("/", "_").replace("-", "_")

    # Save FAISS index
    index_path = output_dir / f"faiss_{index_type.lower()}_{model_slug}_{version}.index"
    print(f"\nSaving FAISS index to {index_path}")
    faiss.write_index(index, str(index_path))
    print(f"✓ Index saved ({index_path.stat().st_size / (1024*1024):.1f} MB)")

    # Save VIN mapping
    vins_path = output_dir / f"vins_{index_type.lower()}_{model_slug}_{version}.pkl"
    print(f"Saving VIN mapping to {vins_path}")
    with open(vins_path, 'wb') as f:
        pickle.dump(vins, f)
    print(f"✓ VINs saved ({vins_path.stat().st_size / 1024:.1f} KB)")

    # Save metadata
    metadata = {
        'model_name': model_name,
        'version': version,
        'index_type': index_type,
        'num_vectors': index.ntotal,
        'dimension': index.d,
    }
    metadata_path = output_dir / f"metadata_{index_type.lower()}_{model_slug}_{version}.pkl"
    with open(metadata_path, 'wb') as f:
        pickle.dump(metadata, f)
    print(f"✓ Metadata saved")


def main():
    parser = argparse.ArgumentParser(description="Build FAISS index from dense embeddings")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/car_dataset_idss/uni_vehicles.db"),
        help="Path to vehicle database (default: data/car_dataset_idss/uni_vehicles.db)"
    )
    parser.add_argument(
        "--model",
        default="all-mpnet-base-v2",
        help="Embedding model name (default: all-mpnet-base-v2)"
    )
    parser.add_argument(
        "--version",
        default="v1",
        help="Embedding version (default: v1)"
    )
    parser.add_argument(
        "--index-type",
        choices=["Flat", "IVF"],
        default="Flat",
        help="Index type: Flat (exact) or IVF (approximate, faster) (default: Flat)"
    )
    parser.add_argument(
        "--nlist",
        type=int,
        default=100,
        help="Number of clusters for IVF index (default: 100)"
    )
    parser.add_argument(
        "--nprobe",
        type=int,
        default=10,
        help="Number of clusters to search in IVF index (default: 10)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/car_dataset_idss/faiss_indices"),
        help="Output directory for index files (default: data/car_dataset_idss/faiss_indices)"
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found at {args.db_path}")
        sys.exit(1)

    print("=" * 80)
    print("FAISS Index Builder")
    print("=" * 80)

    # Load embeddings
    embeddings, vins = load_embeddings_from_db(
        args.db_path,
        args.model,
        args.version
    )

    # Build index
    if args.index_type == "Flat":
        index, vins = build_flat_index(embeddings, vins)
    elif args.index_type == "IVF":
        index, vins = build_ivf_index(embeddings, vins, args.nlist, args.nprobe)

    # Save index
    save_index(
        index,
        vins,
        args.output_dir,
        args.model,
        args.version,
        args.index_type
    )

    print("\n" + "=" * 80)
    print("✓ FAISS index build complete!")
    print("=" * 80)
    print(f"\nTo use this index in your application:")
    print(f"  1. Load index: faiss.read_index('{args.output_dir}/faiss_...index')")
    print(f"  2. Load VINs: pickle.load(open('{args.output_dir}/vins_...pkl', 'rb'))")
    print(f"  3. Search: distances, indices = index.search(query_embedding, k=20)")
    print(f"  4. Map indices to VINs: vins[idx] for idx in indices[0]")


if __name__ == "__main__":
    main()
