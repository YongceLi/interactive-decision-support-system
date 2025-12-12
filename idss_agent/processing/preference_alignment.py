"""
Preference Alignment Scoring for Method 3: Coverage-Risk Optimization.

Implements Pos_j(v) and Neg_j(v) alignment scores as defined in METHOD3_DESIGN.md:
- Pos_j(v) = Σ_{k: pros} max(0, cosine(preference_j, phrase_k))
- Neg_j(v) = Σ_{k: cons} max(0, cosine(preference_j, phrase_k))

These scores measure how well vehicle v aligns with user preference j
by summing similarities across individual phrases.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from idss_agent.processing.phrase_store import PhraseStore, VehiclePhrases
from idss_agent.state.schema import ImplicitPreferences
from idss_agent.utils.logger import get_logger

logger = get_logger("processing.preference_alignment")


def compute_alignment_scores(
    vehicle_phrases: VehiclePhrases,
    liked_embeddings: np.ndarray,
    disliked_embeddings: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute Pos and Neg alignment scores for a vehicle.

    Args:
        vehicle_phrases: Pre-computed phrase embeddings for vehicle
        liked_embeddings: Embeddings for user's liked features (M, D)
        disliked_embeddings: Embeddings for user's disliked features (N, D)

    Returns:
        Tuple of (pos_scores, neg_scores):
        - pos_scores: (M,) array of Pos_j(v) for each liked feature j
        - neg_scores: (N,) array of Neg_j(v) for each disliked feature j
    """
    # Compute Pos_j(v) = max_{k: pros} cosine(u_j, z_vk)
    # Shape: (M liked, K pros) - similarity of each liked feature to each pros phrase
    pros_similarities = liked_embeddings @ vehicle_phrases.pros_embeddings.T

    # Take max similarity (best match) across pros phrases for each liked feature
    # Hybrid approach: max per preference, sum across preferences in greedy selection
    pos_scores = np.max(pros_similarities, axis=1)

    # Compute Neg_j(v) = max_{k: cons} cosine(u_j, z_vk)
    # Shape: (N disliked, K cons) - similarity of each disliked feature to each cons phrase
    cons_similarities = disliked_embeddings @ vehicle_phrases.cons_embeddings.T

    # Take max similarity (best match) across cons phrases for each disliked feature
    neg_scores = np.max(cons_similarities, axis=1)

    return pos_scores, neg_scores


def compute_alignment_matrix(
    vehicles: List[Dict],
    phrase_store: PhraseStore,
    implicit_preferences: ImplicitPreferences
) -> Tuple[np.ndarray, np.ndarray, List[str], List[str]]:
    """
    Compute Pos and Neg alignment matrices for a set of vehicles.

    Args:
        vehicles: List of vehicle dicts with make, model, year
        phrase_store: Pre-loaded phrase store
        implicit_preferences: User's implicit preferences

    Returns:
        Tuple of (Pos, Neg, liked_features, disliked_features):
        - Pos: (V vehicles, M liked) matrix of Pos_j(v) scores
        - Neg: (V vehicles, N disliked) matrix of Neg_j(v) scores
        - liked_features: List of M liked feature strings
        - disliked_features: List of N disliked feature strings
    """
    # Extract preferences
    liked_features = implicit_preferences.get("liked_features", [])
    disliked_features = implicit_preferences.get("disliked_features", [])

    if not liked_features and not disliked_features:
        logger.warning("No implicit preferences provided - returning zero scores")
        return np.zeros((len(vehicles), 0)), np.zeros((len(vehicles), 0)), [], []

    # Encode user preferences
    liked_embeddings = phrase_store.encode_batch(liked_features) if liked_features else np.array([])
    disliked_embeddings = phrase_store.encode_batch(disliked_features) if disliked_features else np.array([])

    # Compute scores for each vehicle
    pos_matrix = []
    neg_matrix = []

    for vehicle in vehicles:
        # Get phrase embeddings for this vehicle
        vehicle_phrases = phrase_store.get_phrases(
            vehicle["make"],
            vehicle["model"],
            vehicle["year"]
        )

        if vehicle_phrases is None:
            # No phrases available - use zeros
            pos_scores = np.zeros(len(liked_features)) if liked_features else np.array([])
            neg_scores = np.zeros(len(disliked_features)) if disliked_features else np.array([])
        else:
            # Compute alignment scores
            pos_scores, neg_scores = compute_alignment_scores(
                vehicle_phrases,
                liked_embeddings,
                disliked_embeddings
            )

        pos_matrix.append(pos_scores)
        neg_matrix.append(neg_scores)

    # Stack into matrices
    Pos = np.array(pos_matrix) if pos_matrix else np.zeros((len(vehicles), 0))
    Neg = np.array(neg_matrix) if neg_matrix else np.zeros((len(vehicles), 0))

    logger.info(f"Computed alignment matrix: {Pos.shape[0]} vehicles × "
                f"({Pos.shape[1]} liked + {Neg.shape[1]} disliked) preferences")

    return Pos, Neg, liked_features, disliked_features


def compute_coverage_risk_score(
    selected_indices: List[int],
    candidate_idx: int,
    Pos: np.ndarray,
    Neg: np.ndarray,
    lambda_risk: float = 0.5,
    min_similarity: float = 0.5
) -> float:
    """
    Compute marginal gain of adding candidate to selected set.

    Implements the greedy coverage-risk objective:
    f(S ∪ {v}) - f(S) = Coverage_gain - λ × Risk_gain

    Only counts alignment scores > min_similarity (default 0.5) to filter out weak matches.

    Args:
        selected_indices: Indices of already-selected vehicles
        candidate_idx: Index of candidate vehicle to add
        Pos: (V, M) matrix of Pos_j(v) scores
        Neg: (V, N) matrix of Neg_j(v) scores
        lambda_risk: Risk penalty weight (default 0.5)
        min_similarity: Minimum similarity threshold (default 0.5)

    Returns:
        Marginal gain score
    """
    M = Pos.shape[1]  # Number of liked features
    N = Neg.shape[1]  # Number of disliked features

    # Filter scores: only count > min_similarity
    Pos_filtered = np.where(Pos > min_similarity, Pos, 0.0)
    Neg_filtered = np.where(Neg > min_similarity, Neg, 0.0)

    # Current coverage and risk
    if selected_indices:
        current_coverage = np.sum(np.max(Pos_filtered[selected_indices, :], axis=0))
        current_risk = np.sum(np.max(Neg_filtered[selected_indices, :], axis=0))
    else:
        current_coverage = 0.0
        current_risk = 0.0

    # Coverage and risk with candidate added
    new_selected = selected_indices + [candidate_idx]
    new_coverage = np.sum(np.max(Pos_filtered[new_selected, :], axis=0))
    new_risk = np.sum(np.max(Neg_filtered[new_selected, :], axis=0))

    # Marginal gain
    coverage_gain = new_coverage - current_coverage
    risk_gain = new_risk - current_risk
    marginal_gain = coverage_gain - lambda_risk * risk_gain

    return marginal_gain


def greedy_select_vehicles(
    Pos: np.ndarray,
    Neg: np.ndarray,
    k: int = 20,
    lambda_risk: float = 0.5,
    min_similarity: float = 0.5
) -> List[int]:
    """
    Greedy algorithm for coverage-risk optimization.

    Implements Algorithm 1 from METHOD3_DESIGN.md:
    - Iteratively select vehicle with highest marginal gain
    - Marginal gain = Coverage_gain - λ × Risk_gain
    - Only counts alignment scores > min_similarity

    Args:
        Pos: (V, M) matrix of Pos_j(v) scores
        Neg: (V, N) matrix of Neg_j(v) scores
        k: Number of vehicles to select (default 20)
        lambda_risk: Risk penalty weight (default 0.5)
        min_similarity: Minimum similarity threshold (default 0.5)

    Returns:
        List of k selected vehicle indices
    """
    V = Pos.shape[0]  # Total number of vehicles
    selected_indices = []
    remaining_indices = list(range(V))

    logger.info(f"Starting greedy selection: selecting {k} from {V} vehicles")
    logger.info(f"Pos matrix: {Pos.shape}, Neg matrix: {Neg.shape}, λ={lambda_risk}, min_sim={min_similarity}")

    for iteration in range(min(k, V)):
        # Compute marginal gain for each remaining vehicle
        marginal_gains = []
        for idx in remaining_indices:
            gain = compute_coverage_risk_score(
                selected_indices,
                idx,
                Pos,
                Neg,
                lambda_risk,
                min_similarity
            )
            marginal_gains.append((idx, gain))

        # Select vehicle with highest marginal gain
        best_idx, best_gain = max(marginal_gains, key=lambda x: x[1])

        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)

        logger.debug(f"Iteration {iteration + 1}/{k}: selected vehicle {best_idx} "
                    f"(gain={best_gain:.3f})")

    logger.info(f"✓ Greedy selection complete: selected {len(selected_indices)} vehicles")

    return selected_indices


def rank_vehicles_by_alignment(
    vehicles: List[Dict],
    phrase_store: PhraseStore,
    implicit_preferences: ImplicitPreferences,
    k: int = 20,
    lambda_risk: float = 0.5,
    min_similarity: float = 0.5
) -> List[Dict]:
    """
    Rank vehicles using Method 3: Coverage-Risk Optimization.

    Args:
        vehicles: List of vehicle dicts (must pass explicit filters)
        phrase_store: Pre-loaded phrase store
        implicit_preferences: User's implicit preferences
        k: Number of vehicles to recommend (default 20)
        lambda_risk: Risk penalty weight (default 0.5)
        min_similarity: Minimum similarity threshold (default 0.5)

    Returns:
        List of top-k ranked vehicles (same dicts, reordered)
    """
    if not vehicles:
        logger.warning("No vehicles to rank")
        return []

    if not implicit_preferences.get("liked_features") and not implicit_preferences.get("disliked_features"):
        logger.warning("No implicit preferences - returning vehicles in original order")
        return vehicles[:k]

    # Step 1: Compute alignment matrices
    logger.info(f"Computing alignment scores for {len(vehicles)} vehicles...")
    Pos, Neg, liked_features, disliked_features = compute_alignment_matrix(
        vehicles,
        phrase_store,
        implicit_preferences
    )

    # Step 2: Greedy selection
    logger.info(f"Running greedy coverage-risk optimization (k={k}, λ={lambda_risk}, min_sim={min_similarity})...")
    selected_indices = greedy_select_vehicles(Pos, Neg, k, lambda_risk, min_similarity)

    # Step 3: Reorder vehicles by selection order
    ranked_vehicles = [vehicles[idx] for idx in selected_indices]

    # Step 4: Log detailed alignment for top vehicles
    logger.info("=" * 70)
    logger.info("FEATURE ALIGNMENT DETAILS (Top 5)")
    logger.info("=" * 70)

    for rank, (idx, vehicle) in enumerate(zip(selected_indices[:5], ranked_vehicles[:5]), 1):
        logger.info(f"\n#{rank}: {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')}")

        # Get vehicle phrases
        vehicle_phrases = phrase_store.get_phrases(
            vehicle["make"],
            vehicle["model"],
            vehicle["year"]
        )

        if vehicle_phrases is None:
            logger.info("  (no review data available)")
            continue

        # Debug: log phrase counts
        logger.debug(f"  Vehicle has {len(vehicle_phrases.pros_phrases)} pros phrases, {len(vehicle_phrases.cons_phrases)} cons phrases")
        logger.debug(f"  Pros embeddings shape: {vehicle_phrases.pros_embeddings.shape}, Cons embeddings shape: {vehicle_phrases.cons_embeddings.shape}")

        # Show liked feature matches
        if liked_features:
            logger.info("  LIKED FEATURES:")
            liked_embeddings = phrase_store.encode_batch(liked_features)

            for j, liked_feature in enumerate(liked_features):
                pos_score = Pos[idx, j]

                # Check if we have any pros phrases
                if len(vehicle_phrases.pros_phrases) == 0 or vehicle_phrases.pros_embeddings.shape[0] == 0:
                    logger.info(f"    '{liked_feature}' (score: {pos_score:.2f}) → (no phrases available)")
                    continue

                # Find the single best matching pros phrase (max similarity)
                pros_similarities = liked_embeddings[j] @ vehicle_phrases.pros_embeddings.T
                best_idx = int(np.argmax(pros_similarities))
                best_sim = float(pros_similarities[best_idx])
                best_phrase = vehicle_phrases.pros_phrases[best_idx]

                logger.info(f"    '{liked_feature}' (score: {pos_score:.2f}) → \"{best_phrase}\" (sim: {best_sim:.2f})")

        # Show disliked feature matches
        if disliked_features:
            logger.info("  DISLIKED FEATURES:")
            disliked_embeddings = phrase_store.encode_batch(disliked_features)

            for j, disliked_feature in enumerate(disliked_features):
                neg_score = Neg[idx, j]

                # Check if we have any cons phrases
                if len(vehicle_phrases.cons_phrases) == 0 or vehicle_phrases.cons_embeddings.shape[0] == 0:
                    logger.info(f"    '{disliked_feature}' (score: {neg_score:.2f}) → (no phrases available)")
                    continue

                # Find the single best matching cons phrase (max similarity)
                cons_similarities = disliked_embeddings[j] @ vehicle_phrases.cons_embeddings.T
                best_idx = int(np.argmax(cons_similarities))
                best_sim = float(cons_similarities[best_idx])
                best_phrase = vehicle_phrases.cons_phrases[best_idx]

                logger.info(f"    '{disliked_feature}' (score: {neg_score:.2f}) → \"{best_phrase}\" (sim: {best_sim:.2f})")

    logger.info("=" * 70)
    logger.info(f"✓ Ranked {len(ranked_vehicles)} vehicles by alignment")

    return ranked_vehicles
