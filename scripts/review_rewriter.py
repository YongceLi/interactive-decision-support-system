#!/usr/bin/env python3
"""Generate augmented GPU reviews by rewriting scraper output for new brand/product pairs."""
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
You will rewrite a GPU/electronics review so that it matches a new brand and product name.

Guidance:
- Preserve the original sentiment, tone, and rating context of the review.
- Keep the perspective, details, and style grounded in the provided original review.
- Only change details that must shift to fit the target brand/product; otherwise keep facts consistent.
- Do not invent specs unrelated to the original content. Keep it concise and natural.

Original review metadata:
- Brand: {original_brand}
- Product: {original_product}
- Normalized product family: {norm_product}
- Rating: {rating}
- Source text: {review}

Rewrite this review so it appears to be about the target product while preserving the sentiment and implied rating.
Target product: {target_brand} {target_product}
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
    target_brand: str,
    target_product: str,
) -> str:
    prompt = PROMPT_TEMPLATE.format(
        original_brand=original_row.get("Brand", ""),
        original_product=original_row.get("Product", ""),
        norm_product=original_row.get("Norm_Product", ""),
        rating=original_row.get("Rating", ""),
        review=original_row.get("Review", ""),
        target_brand=target_brand,
        target_product=target_product,
    )
    response = llm.invoke(prompt)
    return response.content.strip()


def expand_reviews(
    reviews: pd.DataFrame,
    brand_products: Iterable[Tuple[str, str]],
    llm: ChatOpenAI,
    variants_per_review: int,
    rng: random.Random,
) -> pd.DataFrame:
    results = []
    brand_product_list = list(brand_products)
    for _, row in reviews.iterrows():
        sampled_pairs = sample_make_models(brand_product_list, variants_per_review, rng)
        for brand, product in sampled_pairs:
            logger.info(
                "Rewriting review for %s %s -> %s %s",
                row.get("Brand"),
                row.get("Product"),
                brand,
                product,
            )
            rewritten = rewrite_review(llm, row, brand, product)
            results.append(
                {
                    "Brand": brand,
                    "Product": product,
                    "Norm_Product": row.get("Norm_Product"),
                    "Review": rewritten,
                    "ratings": row.get("Rating"),
                    "Rating": row.get("Rating"),
                    "date": row.get("Date"),
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
        default=Path("data") / "review_electronics_gpu.csv",
        help="Path to the original scraper output CSV",
    )
    parser.add_argument(
        "--make-models",
        type=Path,
        default=Path("data") / "review_electronics_gpu.csv",
        help="Path to CSV containing target brand/product pairs",
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
    make_models = make_models_df[["Brand", "Product"]].dropna().itertuples(index=False, name=None)

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
