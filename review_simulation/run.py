#!/usr/bin/env python3
"""Entry point for evaluating review-driven personas against recommendations."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from langchain_openai import ChatOpenAI

from review_simulation.exporter import RESULT_EXPORT_COLUMNS, result_to_row
from review_simulation.persona import ReviewPersona, load_personas_from_frame
from review_simulation.simulation import (
    PersonaTurn,
    SimulationResult,
    evaluate_persona,
)
from review_simulation.ui import render_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="CSV produced by generate_persona_queries.py",
    )
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
        "--confidence-threshold",
        type=float,
        default=0.5,
        help="Minimum average confidence required to accept an assessment without retrying",
    )
    parser.add_argument(
        "--max-assessment-attempts",
        type=int,
        default=3,
        help="Maximum number of assessment passes to run when confidence is low",
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
    persona_pairs = _load_personas_and_turns(args.input)
    if args.max_personas is not None:
        persona_pairs = persona_pairs[: args.max_personas]

    llm = ChatOpenAI(model=args.model, temperature=0.4)

    results: List[SimulationResult] = []
    for persona, turn in persona_pairs:
        results.append(
            evaluate_persona(
                persona,
                turn,
                llm,
                recommendation_limit=args.limit,
                metric_k=args.metric_k,
                recommendation_method=args.method,
                confidence_threshold=args.confidence_threshold,
                max_assessment_attempts=args.max_assessment_attempts,
            )
        )

    render_results(results, args.metric_k)

    if args.export is not None:
        export_results(results, args.export)


def export_results(results: List[SimulationResult], output_path: Path) -> None:
    """Persist persona prompts and structured preferences for downstream evaluation."""

    rows = [
        result_to_row(result)
        for result in results
    ]
    if not rows:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_path, index=False)
        return

    frame = pd.DataFrame(rows, columns=RESULT_EXPORT_COLUMNS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)


def _load_personas_and_turns(csv_path: Path) -> List[Tuple[ReviewPersona, PersonaTurn]]:
    frame = pd.read_csv(csv_path)
    personas = load_personas_from_frame(frame)
    turns: List[PersonaTurn] = []

    for _, row in frame.iterrows():
        turns.append(
            PersonaTurn(
                message=str(row.get("persona_query", "")),
                writing_style=str(row.get("persona_writing_style", "")),
                interaction_style=str(row.get("persona_interaction_style", "")),
                family_background=str(row.get("persona_family_background", "")),
                goal_summary=str(row.get("persona_goal_summary", "")),
                upper_price_limit=row.get("persona_upper_price_limit"),
            )
        )

    if len(personas) != len(turns):
        raise ValueError(
            "Persona preference data and persona queries are misaligned in the provided CSV."
        )

    return list(zip(personas, turns))


if __name__ == "__main__":
    main()
