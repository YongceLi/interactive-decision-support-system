#!/usr/bin/env python3
"""Enrich raw vehicle reviews with persona insights via GPT-4o-mini."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("review_enricher")


class VehiclePreference(BaseModel):
    """Structured affinity toward a specific vehicle configuration."""

    make: Optional[str] = Field(None, description="Vehicle make the reviewer is drawn to")
    model: Optional[str] = Field(None, description="Vehicle model the reviewer mentions")
    year: Optional[int] = Field(None, description="Model year preference if stated")
    condition: str = Field(
        ...,
        description="One of 'new', 'used', 'either', or 'unspecified' depending on review context",
    )
    rationale: str = Field(..., description="Short explanation referencing the review text")


class ReviewInference(BaseModel):
    """LLM-derived persona summary for a single review."""

    likes: List[VehiclePreference] = Field(
        ..., description="Vehicles or configurations the reviewer strongly prefers"
    )
    dislikes: List[VehiclePreference] = Field(
        ..., description="Vehicles or configurations the reviewer wants to avoid"
    )
    intention: str = Field(..., description="What the reviewer would hope to achieve with a recommender")


PROMPT_TEMPLATE = """
You are analysing a consumer-written vehicle review. Extract concrete buying signals.

Review metadata:
- Make: {make}
- Model: {model}
- Rating: {rating}
- Date: {date}

Review text:
"""
{review}
"""

Return JSON with keys "likes", "dislikes", and "intention".
- likes: 1-3 entries. Each entry must specify make/model/year/condition when the review implies it. Condition must be one of: new, used, either, unspecified.
- dislikes: 0-3 entries with the same schema describing what they want to avoid.
- intention: One or two sentences about their goal when interacting with a car recommendation agent.

Focus only on signals grounded in the review; never hallucinate brands not implied.
"""


def enrich_reviews(df: pd.DataFrame, model_name: str) -> pd.DataFrame:
    llm = ChatOpenAI(model=model_name, temperature=0.1)
    structured_llm = llm.with_structured_output(ReviewInference)

    enriched_rows = []
    for _, row in df.iterrows():
        prompt = PROMPT_TEMPLATE.format(
            make=row.get("Make", ""),
            model=row.get("Model", ""),
            rating=row.get("ratings", ""),
            date=row.get("date", ""),
            review=row.get("Review", ""),
        )
        logger.info("Deriving preferences for %s %s", row.get("Make"), row.get("Model"))
        inference = structured_llm.invoke(prompt)
        enriched_rows.append(
            {
                "Make": row.get("Make"),
                "Model": row.get("Model"),
                "Review": row.get("Review"),
                "ratings": row.get("ratings"),
                "date": row.get("date"),
                "liked_options": json.dumps([pref.model_dump() for pref in inference.likes]),
                "disliked_options": json.dumps([pref.model_dump() for pref in inference.dislikes]),
                "user_intention": inference.intention,
            }
        )

    return pd.DataFrame(enriched_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV produced by review_scraper.py")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "review_personas.csv",
        help="Destination CSV with LLM-enriched metadata",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Chat model identifier (default: gpt-4o-mini)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.input)
    enriched = enrich_reviews(df, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(args.output, index=False)
    logger.info("Saved enriched reviews to %s", args.output)


if __name__ == "__main__":
    main()
