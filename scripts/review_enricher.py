#!/usr/bin/env python3
"""Convert raw electronics reviews into personas and evaluation queries."""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
from typing import Iterable, List

from review_simulation.dataset import save_enriched_reviews
from review_simulation.enrichment import enrich_row

logger = logging.getLogger("review_enricher")


def iter_review_rows(path: Path) -> Iterable[dict]:
    if path.is_file():
        yield from _read_csv(path)
    else:
        for csv_path in sorted(path.glob("*.csv")):
            yield from _read_csv(csv_path)


def _read_csv(path: Path) -> Iterable[dict]:
    logger.info("Reading reviews from %s", path)
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def build_dataset(input_path: Path, limit: int | None = None) -> List:
    reviews = []
    for row in iter_review_rows(input_path):
        reviews.append(enrich_row(row))
        if limit and len(reviews) >= limit:
            break
    if not reviews:
        raise ValueError(f"No reviews found in {input_path}")
    return reviews


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich electronics reviews with personas")
    parser.add_argument("input", type=Path, help="CSV file or directory containing review files")
    parser.add_argument("output", type=Path, help="Destination CSV for enriched dataset")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for number of rows")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    reviews = build_dataset(args.input, args.limit)
    save_enriched_reviews(reviews, args.output)
    logger.info("Wrote %s enriched reviews to %s", len(reviews), args.output)


if __name__ == "__main__":
    main()
