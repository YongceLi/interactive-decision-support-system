#!/usr/bin/env python3
"""Entry point for the review-driven single-turn simulation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import pandas as pd
from langchain_openai import ChatOpenAI

from review_simulation.persona import ReviewPersona, VehicleAffinity, load_personas
from review_simulation.simulation import SimulationResult, VehicleJudgement, run_simulation
from review_simulation.ui import render_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV produced by review_enricher.py")
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Chat model to use for persona synthesis and evaluation",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of recommended vehicles to inspect",
    )
    parser.add_argument(
        "--metric-k",
        type=int,
        default=20,
        help="k value for precision/recall reporting (defaults to limit)",
    )
    parser.add_argument(
        "--method",
        type=int,
        choices=[1, 2],
        default=1,
        help="Recommendation method to evaluate (1 = SQL + Vector + MMR, 2 = Web Search + Parallel SQL)",
    )
    parser.add_argument(
        "--max-personas",
        type=int,
        default=None,
        help="Optional cap on number of personas processed",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="Optional CSV path to store generated persona queries and metadata",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    personas: List[ReviewPersona] = load_personas(args.input)
    if args.max_personas is not None:
        personas = personas[: args.max_personas]

    llm = ChatOpenAI(model=args.model, temperature=0.4)

    results: List[SimulationResult] = []
    for persona in personas:
        results.append(
            run_simulation(
                persona,
                llm,
                recommendation_limit=args.limit,
                metric_k=args.metric_k,
                recommendation_method=args.method,
            )
        )

    render_results(results, args.metric_k)

    if args.export is not None:
        export_results(results, args.export)


def export_results(results: List[SimulationResult], output_path: Path) -> None:
    """Persist persona prompts and structured preferences for downstream evaluation."""

    rows = [
        _result_to_row(result)
        for result in results
    ]
    if not rows:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_path, index=False)
        return

    frame = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)


def _serialize_affinities(affinities: List[VehicleAffinity]) -> str:
    return json.dumps(
        [
            {
                "make": affinity.make,
                "model": affinity.model,
                "year": affinity.year,
                "condition": affinity.condition,
                "rationale": affinity.rationale,
            }
            for affinity in affinities
        ]
    )


def _serialize_vehicle_judgements(judgements: List[VehicleJudgement]) -> str:
    return json.dumps(
        [
            {
                "index": item.index,
                "make": item.make,
                "model": item.model,
                "year": item.year,
                "condition": item.condition,
                "location": item.location,
                "vin": item.vin,
                "satisfied": item.satisfied,
                "rationale": item.rationale,
            }
            for item in judgements
        ]
    )


def _result_to_row(result: SimulationResult) -> dict:
    persona = result.persona
    turn = result.persona_turn
    metrics = result.metrics

    return {
        "Make": persona.make,
        "Model": persona.model,
        "Review": persona.review,
        "ratings": persona.rating,
        "Rating": persona.rating,
        "date": persona.date,
        "like_option": _serialize_affinities(persona.liked),
        "dislike_option": _serialize_affinities(persona.disliked),
        "liked_options": _serialize_affinities(persona.liked),
        "disliked_options": _serialize_affinities(persona.disliked),
        "user_intention": persona.intention,
        "mentioned_makes": json.dumps(persona.mentioned_makes),
        "mentioned_models": json.dumps(persona.mentioned_models),
        "mentioned_years": json.dumps(persona.mentioned_years),
        "preferred_condition": persona.preferred_condition,
        "newness_preference_score": persona.newness_preference_score,
        "newness_preference_notes": persona.newness_preference_notes,
        "preferred_vehicle_type": persona.preferred_vehicle_type,
        "preferred_fuel_type": persona.preferred_fuel_type,
        "openness_to_alternatives": persona.alternative_openness,
        "misc_notes": persona.misc_notes,
        "persona_writing_style": turn.writing_style,
        "persona_interaction_style": turn.interaction_style,
        "persona_family_background": turn.family_background,
        "persona_goal_summary": turn.goal_summary,
        "persona_query": turn.message,
        "precision_at_k": metrics.precision_at_k,
        "recall_at_k": metrics.recall_at_k,
        "satisfied_in_top_k": metrics.satisfied_count,
        "vehicle_judgements": _serialize_vehicle_judgements(result.vehicles),
    }


if __name__ == "__main__":
    main()
