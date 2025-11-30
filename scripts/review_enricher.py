#!/usr/bin/env python3
"""Enrich raw electronics (GPU) reviews with persona insights via GPT-4o-mini."""
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


class ProductPreference(BaseModel):
    """Structured affinity toward a specific GPU/product configuration."""

    product_brand: Optional[str] = Field(
        None, description="Brand the reviewer is drawn to (e.g., NVIDIA, ASUS)"
    )
    product_name: Optional[str] = Field(
        None, description="Full product/model name the reviewer mentions"
    )
    normalize_product_name: Optional[str] = Field(
        None, description="Normalized root product family (e.g., RTX 5070 Ti)"
    )
    rationale: str = Field(..., description="Short explanation referencing the review text")


class PersonaSignals(BaseModel):
    """Aggregated shopping preferences inferred from the review."""

    mentioned_product_brands: List[str] = Field(
        default_factory=list,
        description="Distinct product brands explicitly referenced in the review.",
    )
    mentioned_product_names: List[str] = Field(
        default_factory=list,
        description="Distinct product names explicitly referenced in the review.",
    )
    mentioned_normalize_product_names: List[str] = Field(
        default_factory=list,
        description="Normalized product families referenced in the review.",
    )
    performance_tier: Optional[str] = Field(
        None,
        description="Performance expectation (high-end, mid-range, or low-end) implied by the review.",
    )
    newness_preference_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1 (older generation acceptable) to 10 (must be the latest) scale.",
    )
    newness_preference_notes: str = Field(
        ...,
        description="Short explanation of the newness preference scale selection.",
    )
    price_range: Optional[str] = Field(
        None,
        description="Budget range or willingness to pay implied by the review.",
    )
    openness_to_alternatives: int = Field(
        ...,
        ge=1,
        le=10,
        description="1 (not open) to 10 (very open) scale describing willingness to consider alternative brands/models.",
    )
    misc_notes: str = Field(
        ...,
        description="Catch-all notes such as use cases (gaming, AI), noise, thermals, or installation constraints.",
    )


class ReviewInference(BaseModel):
    """LLM-derived persona summary for a single review."""

    likes: List[ProductPreference] = Field(
        ..., description="Products or configurations the reviewer strongly prefers"
    )
    dislikes: List[ProductPreference] = Field(
        ..., description="Products or configurations the reviewer wants to avoid"
    )
    intention: str = Field(..., description="What the reviewer would hope to achieve with a recommender")
    persona_signals: PersonaSignals = Field(
        ..., description="Aggregated search preferences to guide persona/query generation."
    )


PROMPT_TEMPLATE = """
You are analysing a consumer-written GPU review. Extract concrete buying signals.

The incoming data columns mean:
- Review: free-form text written by the buyer.
- Rating: numeric score from 1 (most negative) to 5 (most positive).
- Brand: product brand discussed in the review.
- Product: full product/model name discussed in the review.
- Norm_Product: normalized product family (e.g., RTX 5070 Ti).
- Date: publication date of the review.
- like_option: product variants explicitly praised in the review.
- dislike_option: product variants explicitly criticised in the review.
- user_intention: what the shopper is trying to achieve.

Review metadata:
- Brand: {brand}
- Product: {product}
- Norm_Product: {norm_product}
- Rating: {rating}
- Date: {date}

Review text:
{review}

Return JSON with keys "likes", "dislikes", "intention", and "persona_signals". First, determine the product_brand/product_name/normalize_product_name preferences implied by the review. Then, bucket the brands/names into their respective categories. Finally, summarize the reviewer's intention when interacting with a GPU recommendation agent and capture high-level search signals.
- likes: Products/configurations the reviewer prefers. Each entry must specify product_brand/product_name/normalize_product_name when implied.
- dislikes: Products/configurations the reviewer avoids. Each entry must specify product_brand/product_name/normalize_product_name when implied.
- intention: One or two sentences about their goal when interacting with a GPU recommendation agent.
- persona_signals: Object describing aggregated search preferences with these keys:
  * mentioned_product_brands (list of strings)
  * mentioned_product_names (list of strings)
  * mentioned_normalize_product_names (list of strings; omit if none)
  * performance_tier (high-end, mid-range, or low-end if implied; otherwise null)
  * newness_preference_score (integer 1-10 where 1=older generation acceptable, 10=latest only)
  * newness_preference_notes (sentence explaining the score)
  * price_range (budget range implied by the review; null if unstated)
  * openness_to_alternatives (integer 1-10 where 1=refuses alternatives, 10=fully open)
  * misc_notes (sentence covering other priorities such as thermals, acoustics, use case, or installation constraints)

Focus only on signals grounded in the review; never hallucinate brands or specs not implied.
"""


def enrich_reviews(df: pd.DataFrame, model_name: str) -> pd.DataFrame:
    llm = ChatOpenAI(model=model_name, temperature=0.1)
    structured_llm = llm.with_structured_output(ReviewInference)

    enriched_rows = []
    for _, row in df.iterrows():
        prompt = PROMPT_TEMPLATE.format(
            brand=row.get("Brand", ""),
            product=row.get("Product", ""),
            norm_product=row.get("Norm_Product", ""),
            rating=row.get("Rating", ""),
            date=row.get("Date", ""),
            review=row.get("Review", ""),
        )
        logger.info("Deriving preferences for %s %s", row.get("Brand"), row.get("Product"))
        inference = structured_llm.invoke(prompt)
        enriched_rows.append(
            {
                "Brand": row.get("Brand"),
                "Product": row.get("Product"),
                "Norm_Product": row.get("Norm_Product"),
                "Review": row.get("Review"),
                "ratings": row.get("Rating"),
                "Rating": row.get("Rating"),
                "date": row.get("Date"),
                "liked_options": json.dumps([pref.model_dump() for pref in inference.likes]),
                "disliked_options": json.dumps([pref.model_dump() for pref in inference.dislikes]),
                "like_option": json.dumps([pref.model_dump() for pref in inference.likes]),
                "dislike_option": json.dumps([pref.model_dump() for pref in inference.dislikes]),
                "user_intention": inference.intention,
                "mentioned_product_brands": json.dumps(
                    inference.persona_signals.mentioned_product_brands
                ),
                "mentioned_product_names": json.dumps(
                    inference.persona_signals.mentioned_product_names
                ),
                "mentioned_normalize_product_names": json.dumps(
                    inference.persona_signals.mentioned_normalize_product_names
                ),
                "performance_tier": inference.persona_signals.performance_tier,
                "newness_preference_score": inference.persona_signals.newness_preference_score,
                "newness_preference_notes": inference.persona_signals.newness_preference_notes,
                "price_range": inference.persona_signals.price_range,
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
