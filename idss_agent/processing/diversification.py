"""
Diversification utilities for recommendation ranking.

Implements Maximal Marginal Relevance (MMR) for diverse top-k selection.
"""
from typing import Dict, Any, List, Tuple

from idss_agent.utils.logger import get_logger

logger = get_logger("processing.diversification")


def compute_vehicle_similarity(v1: Dict[str, Any], v2: Dict[str, Any]) -> float:
    """
    Compute similarity between two vehicles (0.0 = diverse, 1.0 = identical).

    Similarity is based on make, model, and body_style overlap.

    Args:
        v1, v2: Vehicle dictionaries

    Returns:
        Similarity score between 0.0 (completely different) and 1.0 (same vehicle)
    """
    vehicle1 = v1.get("vehicle", {})
    vehicle2 = v2.get("vehicle", {})

    make1 = str(vehicle1.get("make", "")).lower()
    make2 = str(vehicle2.get("make", "")).lower()
    model1 = str(vehicle1.get("model", "")).lower()
    model2 = str(vehicle2.get("model", "")).lower()
    body1 = str(vehicle1.get("bodyStyle", "") or v1.get("body_style", "")).lower()
    body2 = str(vehicle2.get("bodyStyle", "") or v2.get("body_style", "")).lower()

    # Same make and model = very similar
    if make1 == make2 and model1 == model2:
        return 0.9

    # Same make, different model = moderately similar
    if make1 == make2:
        # Further penalize if same body style
        if body1 == body2 and body1:
            return 0.7
        return 0.6

    # Different make, same body style = somewhat similar
    if body1 == body2 and body1:  # body1 not empty
        return 0.4

    # Completely different
    return 0.0


def diversify_with_mmr(
    scored_vehicles: List[Tuple[float, Dict[str, Any]]],
    top_k: int = 20,
    lambda_param: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Apply Maximal Marginal Relevance (MMR) to select diverse top-k vehicles.

    MMR balances relevance (vector similarity score) with diversity
    (dissimilarity to already-selected vehicles).

    Args:
        scored_vehicles: List of (relevance_score, vehicle_dict) tuples,
                        sorted by relevance descending
        top_k: Number of vehicles to select
        lambda_param: Trade-off between relevance and diversity
                     - 1.0 = pure relevance (no diversity)
                     - 0.5 = equal weight
                     - 0.0 = pure diversity (ignores relevance)
                     - Recommended: 0.6-0.8

    Returns:
        List of top_k vehicles selected via MMR
    """
    if len(scored_vehicles) <= top_k:
        return [vehicle for _, vehicle in scored_vehicles]

    # Start with the highest-scoring vehicle
    selected: List[Tuple[float, Dict[str, Any]]] = [scored_vehicles[0]]
    remaining = list(scored_vehicles[1:])

    while len(selected) < top_k and remaining:
        best_mmr_score = -float('inf')
        best_idx = 0

        for idx, (relevance, candidate) in enumerate(remaining):
            # Compute maximum similarity to any already-selected vehicle
            max_similarity = max(
                compute_vehicle_similarity(candidate, selected_vehicle)
                for _, selected_vehicle in selected
            )

            # MMR formula: balance relevance and diversity
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_similarity

            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_idx = idx

        # Add best MMR candidate to selected list
        selected.append(remaining.pop(best_idx))

    logger.info(f"MMR diversification: selected {len(selected)} from {len(scored_vehicles)} candidates (lambda={lambda_param})")

    return [vehicle for _, vehicle in selected]


def diversify_with_clustered_mmr(
    scored_vehicles: List[Tuple[float, Dict[str, Any]]],
    top_k: int = 20,
    cluster_size: int = 3,
    lambda_param: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Apply MMR in clusters to balance diversity and similarity.

    Instead of maximizing diversity across all top_k vehicles, this creates
    clusters of similar vehicles, allowing users to compare similar options.

    Example with top_k=20, cluster_size=3:
    - Cluster 1 (vehicles 1-3): Similar vehicles (e.g., all Ford Rangers)
    - Cluster 2 (vehicles 4-6): Different cluster (e.g., all Chevy Silverados)
    - Cluster 3 (vehicles 7-9): Another cluster (e.g., all Toyota Tacomas)
    - etc.

    Args:
        scored_vehicles: List of (relevance_score, vehicle_dict) tuples,
                        sorted by relevance descending
        top_k: Total number of vehicles to select
        cluster_size: Number of vehicles per cluster (default: 3)
        lambda_param: Trade-off between relevance and diversity within each cluster
                     - 1.0 = pure relevance (no diversity within cluster)
                     - 0.5 = equal weight
                     - 0.0 = pure diversity (ignores relevance)
                     - Recommended: 0.6-0.8

    Returns:
        List of top_k vehicles organized in clusters
    """
    if len(scored_vehicles) <= top_k:
        return [vehicle for _, vehicle in scored_vehicles]

    selected: List[Tuple[float, Dict[str, Any]]] = []
    remaining = list(scored_vehicles)

    num_clusters = (top_k + cluster_size - 1) // cluster_size  # Ceiling division

    for cluster_idx in range(num_clusters):
        if not remaining:
            break

        # Determine how many vehicles to select in this cluster
        vehicles_needed = min(cluster_size, top_k - len(selected))
        if vehicles_needed <= 0:
            break

        # Run MMR for this cluster only
        cluster = []

        # Start with highest-scoring remaining vehicle
        cluster.append(remaining.pop(0))

        # Select rest of cluster using MMR (within cluster)
        for _ in range(vehicles_needed - 1):
            if not remaining:
                break

            best_mmr_score = -float('inf')
            best_idx = 0

            for idx, (relevance, candidate) in enumerate(remaining):
                # Compute max similarity to vehicles in CURRENT cluster only
                max_similarity = max(
                    compute_vehicle_similarity(candidate, cluster_vehicle)
                    for _, cluster_vehicle in cluster
                )

                # MMR formula
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_similarity

                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx

            # Add to current cluster
            cluster.append(remaining.pop(best_idx))

        # Add entire cluster to selected list
        selected.extend(cluster)

        logger.info(f"Cluster {cluster_idx + 1}: selected {len(cluster)} vehicles")

    logger.info(f"Clustered MMR: selected {len(selected)} vehicles in {num_clusters} clusters (cluster_size={cluster_size}, lambda={lambda_param})")

    return [vehicle for _, vehicle in selected]


__all__ = [
    "compute_vehicle_similarity",
    "diversify_with_mmr",
    "diversify_with_clustered_mmr",
]
