#!/usr/bin/env python3
"""Generate augmented vehicle reviews by rewriting scraper output for new make/model pairs."""
from __future__ import annotations

import argparse
import logging
import random
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("review_rewriter")


PROMPT_TEMPLATE = """
You will rewrite an automotive review so that it matches a new vehicle make and model.

Guidance:
- Preserve the original sentiment, tone, and rating context of the review.
- Keep the perspective, details, and style grounded in the provided original review.
- Only change details that must shift to fit the target make/model; otherwise keep facts consistent.
- Do not invent specs unrelated to the original content. Keep it concise and natural.

Original review metadata:
- Make: {original_make}
- Model: {original_model}
- Year: {year}
- Rating: {rating}
- Source text: {review}

Rewrite this review so it appears to be about the target vehicle while preserving the sentiment and implied rating.
Target vehicle: {target_make} {target_model}
Return only the rewritten review text without any additional commentary.
"""


def load_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding_errors="ignore")
    except TypeError:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return pd.read_csv(handle)
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return pd.read_csv(handle)


def sample_make_models(
    make_model_rows: Sequence[Tuple[str, str]], count: int, rng: random.Random
) -> List[Tuple[str, str]]:
    if not make_model_rows:
        raise ValueError("No make/model pairs available for sampling.")
    sample_size = min(count, len(make_model_rows))
    return rng.sample(list(make_model_rows), sample_size)


def rewrite_review(
    llm: ChatOpenAI,
    original_row: pd.Series,
    target_make: str,
    target_model: str,
) -> str:
    prompt = PROMPT_TEMPLATE.format(
        original_make=original_row.get("Make", ""),
        original_model=original_row.get("Model", ""),
        year=original_row.get("Year", ""),
        rating=original_row.get("ratings", ""),
        review=original_row.get("Review", ""),
        target_make=target_make,
        target_model=target_model,
    )
    response = llm.invoke(prompt)
    return response.content.strip()


def expand_reviews(
    reviews: pd.DataFrame,
    make_models: Iterable[Tuple[str, str]],
    llm: ChatOpenAI,
    variants_per_review: int,
    rng: random.Random,
) -> pd.DataFrame:
    results = []
    make_model_list = list(make_models)
    for _, row in reviews.iterrows():
        sampled_pairs = sample_make_models(make_model_list, variants_per_review, rng)
        for make, model in sampled_pairs:
            logger.info(
                "Rewriting review for %s %s -> %s %s", row.get("Make"), row.get("Model"), make, model
            )
            rewritten = rewrite_review(llm, row, make, model)
            results.append(
                {
                    "Make": make,
                    "Model": model,
                    "Year": row.get("Year"),
                    "Review": rewritten,
                    "ratings": row.get("ratings"),
                    "date": row.get("date"),
                    "source": "LLM",
                    "source_url": "LLM",
                }
            )
    return pd.DataFrame(results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reviews",
        type=Path,
        default=Path("data") / "review_scraper_output.csv",
        help="Path to the original scraper output CSV",
    )
    parser.add_argument(
        "--make-models",
        type=Path,
        default=Path("data") / "top_100_make_model.csv",
        help="Path to CSV containing top make/model pairs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "review_scraper_augmented.csv",
        help="Destination CSV for the rewritten reviews",
    )
    parser.add_argument(
        "--variants-per-review",
        type=int,
        default=5,
        help="Number of make/model rewrites to generate for each original review",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Chat model identifier for the LLM rewrite",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible sampling",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    logger.info("Loading reviews from %s", args.reviews)
    reviews = load_csv(args.reviews)
    logger.info("Loading make/model pairs from %s", args.make_models)
    make_models_df = load_csv(args.make_models)
    make_models = make_models_df[["make", "model"]].dropna().itertuples(index=False, name=None)

    llm = ChatOpenAI(model=args.model, temperature=0.4)
    augmented = expand_reviews(
        reviews=reviews,
        make_models=make_models,
        llm=llm,
        variants_per_review=args.variants_per_review,
        rng=rng,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    augmented.to_csv(args.output, index=False)
    logger.info("Saved augmented reviews to %s", args.output)


if __name__ == "__main__":
    main()
