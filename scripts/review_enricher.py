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
from dotenv import load_dotenv

load_dotenv()


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


class PersonaSignals(BaseModel):
    """Aggregated shopping preferences inferred from the review."""

    mentioned_makes: List[str] = Field(
        default_factory=list,
        description="Distinct vehicle makes explicitly referenced in the review.",
    )
    mentioned_models: List[str] = Field(
        default_factory=list,
        description="Distinct vehicle models explicitly referenced in the review.",
    )
    mentioned_years: List[int] = Field(
        default_factory=list,
        description="Model years or year ranges referenced in the review.",
    )
    preferred_condition: str = Field(
        ...,
        description="Whether the reviewer signals a preference for new, used, either, or leaves it unspecified.",
    )
    newness_preference_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1 (vintage only) to 10 (brand new only) scale describing freshness preference.",
    )
    newness_preference_notes: str = Field(
        ...,
        description="Short explanation of the newness preference scale selection.",
    )
    preferred_vehicle_type: Optional[str] = Field(
        None,
        description="Most likely body style (SUV, sedan, truck, etc.) inferred from the review.",
    )
    preferred_fuel_type: Optional[str] = Field(
        None,
        description="Fuel or powertrain type (EV, gas, diesel, hybrid, etc.) implied by the review.",
    )
    openness_to_alternatives: int = Field(
        ...,
        ge=1,
        le=10,
        description="1 (not open) to 10 (very open) scale describing willingness to consider alternatives.",
    )
    misc_notes: str = Field(
        ...,
        description="Catch-all notes such as safety, reliability, budget, or lifestyle considerations.",
    )


class ReviewInference(BaseModel):
    """LLM-derived persona summary for a single review."""

    likes: List[VehiclePreference] = Field(
        ..., description="Vehicles or configurations the reviewer strongly prefers"
    )
    dislikes: List[VehiclePreference] = Field(
        ..., description="Vehicles or configurations the reviewer wants to avoid"
    )
    intention: str = Field(..., description="What the reviewer would hope to achieve with a recommender")
    persona_signals: PersonaSignals = Field(
        ..., description="Aggregated search preferences to guide persona/query generation."
    )


PROMPT_TEMPLATE = """
You are analysing a consumer-written vehicle review. Extract concrete buying signals.

The incoming data columns mean:
- Review: free-form text written by the vehicle owner.
- Rating: numeric score from 1 (most negative) to 5 (most positive).
- Make: vehicle make discussed in the review.
- Model: vehicle model discussed in the review.
- Date: publication date of the review.
- like_option: vehicle options or trims explicitly praised in the review.
- dislike_option: vehicle options or trims explicitly criticised in the review.
- user_intention: what the shopper is trying to achieve.

Review metadata:
- Make: {make}
- Model: {model}
- Rating: {rating}
- Date: {date}

Review text:
{review}

Return JSON with keys "likes", "dislikes", "intention", and "persona_signals". First, determine the make/model/year/condition preferences implied by the review. Then, bucket the makes/models/years/conditions into their respective categories. Finally, summarize the reviewer's intention when interacting with a car recommendation agent and capture high-level search signals.
- likes: Vehicles/configurations the reviewer prefers. Each entry must specify make/model/year/condition when implied. Condition must be one of: new, used, either, unspecified.
- dislikes: Vehicles/configurations the reviewer avoids. Each entry must specify make/model/year/condition when implied. Condition must be one of: new, used, either, unspecified.
- intention: One or two sentences about their goal when interacting with a car recommendation agent.
- persona_signals: Object describing aggregated search preferences with these keys:
  * mentioned_makes (list of strings)
  * mentioned_models (list of strings)
  * mentioned_years (list of integers; omit if none)
  * preferred_condition (new, used, either, or unspecified)
  * newness_preference_score (integer 1-10 where 1=vintage only, 5=new-used is fine, 10=brand new only)
  * newness_preference_notes (sentence explaining the score)
  * preferred_vehicle_type (SUV, sedan, truck, wagon, etc. or null if unstated)
  * preferred_fuel_type (gas, diesel, EV, hybrid, etc. or null if unstated)
  * openness_to_alternatives (integer 1-10 where 1=refuses alternatives, 10=fully open)
  * misc_notes (sentence covering other priorities such as reliability, safety, budget, comfort)

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
                "Rating": row.get("ratings"),
                "date": row.get("date"),
                "liked_options": json.dumps([pref.model_dump() for pref in inference.likes]),
                "disliked_options": json.dumps([pref.model_dump() for pref in inference.dislikes]),
                "like_option": json.dumps([pref.model_dump() for pref in inference.likes]),
                "dislike_option": json.dumps([pref.model_dump() for pref in inference.dislikes]),
                "user_intention": inference.intention,
                "mentioned_makes": json.dumps(inference.persona_signals.mentioned_makes),
                "mentioned_models": json.dumps(inference.persona_signals.mentioned_models),
                "mentioned_years": json.dumps(inference.persona_signals.mentioned_years),
                "preferred_condition": inference.persona_signals.preferred_condition,
                "newness_preference_score": inference.persona_signals.newness_preference_score,
                "newness_preference_notes": inference.persona_signals.newness_preference_notes,
                "preferred_vehicle_type": inference.persona_signals.preferred_vehicle_type,
                "preferred_fuel_type": inference.persona_signals.preferred_fuel_type,
                "openness_to_alternatives": inference.persona_signals.openness_to_alternatives,
                "misc_notes": inference.persona_signals.misc_notes,
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
    try:
        df = pd.read_csv(args.input, encoding_errors="ignore")
    except TypeError:
        # Older pandas versions may not expose ``encoding_errors``; fall back to
        # suppressing problematic bytes via Python's CSV reader instead.
        with args.input.open("r", encoding="utf-8", errors="ignore") as handle:
            df = pd.read_csv(handle)
    except UnicodeDecodeError:
        with args.input.open("r", encoding="utf-8", errors="ignore") as handle:
            df = pd.read_csv(handle)
    enriched = enrich_reviews(df, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(args.output, index=False)
    logger.info("Saved enriched reviews to %s", args.output)


if __name__ == "__main__":
    main()
