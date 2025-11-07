#!/usr/bin/env python3
"""Entry point for the review-driven single-turn simulation."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from langchain_openai import ChatOpenAI

from review_simulation.persona import ReviewPersona, load_personas
from review_simulation.simulation import SimulationResult, run_simulation
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
        "--max-personas",
        type=int,
        default=None,
        help="Optional cap on number of personas processed",
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
            )
        )

    render_results(results, args.metric_k)


if __name__ == "__main__":
    main()
