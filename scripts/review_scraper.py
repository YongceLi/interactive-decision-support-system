#!/usr/bin/env python3
"""Fetch top make/model pairs from the unified vehicle database and scrape reviews.

This utility performs two major steps:

1. Query the local ``uni_vehicles.db`` database to find the ``k`` most common
   ``(make, model)`` combinations.
2. For each pair, download consumer reviews from Edmunds and save them into a
   CSV file so they can be analysed later by LLM-powered personas.

The scraper is intentionally conservative and resilient to failures — any
network or parsing error is logged and skipped so that partially successful
runs still produce a dataset.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("review_scraper")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


DEFAULT_DB_PATH = Path("data") / "car_dataset_idss" / "uni_vehicles.db"
DEFAULT_OUTPUT_PATH = Path("data") / "review_scraper_output.csv"


@dataclass
class MakeModel:
    """Simple container describing a make/model pair."""

    make: str
    model: str
    count: int


@dataclass
class ReviewRecord:
    """Normalized review payload ready for CSV export."""

    make: str
    model: str
    review: str
    rating: Optional[float]
    date: Optional[str]
    source: str
    source_url: str


class EdmundsConsumerReviewScraper:
    """Scrape consumer reviews for a given make/model from Edmunds."""

    BASE_URL_TEMPLATE = "https://www.edmunds.com/{make_slug}/{model_slug}/consumer-reviews/"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/119.0.0.0 Safari/537.36",
        )

    @staticmethod
    def _slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-")

    def build_url(self, make: str, model: str) -> str:
        return self.BASE_URL_TEMPLATE.format(
            make_slug=self._slugify(make), model_slug=self._slugify(model)
        )

    def fetch_reviews(self, make: str, model: str, limit: int = 20) -> List[ReviewRecord]:
        url = self.build_url(make, model)
        logger.info("Fetching reviews for %s %s from %s", make, model, url)
        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        reviews: List[ReviewRecord] = []

        for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(node.string or "{}")
            except json.JSONDecodeError:
                continue

            # Edmunds nests reviews under the product entry.
            potential_reviews: Sequence[dict]
            if isinstance(data, dict) and data.get("@type") == "Product":
                potential_reviews = data.get("review", []) or []
            elif isinstance(data, list):
                potential_reviews = []
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Review":
                        potential_reviews.append(item)
            else:
                continue

            for raw_review in potential_reviews:
                if len(reviews) >= limit:
                    break
                if not isinstance(raw_review, dict):
                    continue
                body = raw_review.get("reviewBody") or raw_review.get("description")
                if not body:
                    continue
                rating = None
                rating_info = raw_review.get("reviewRating") or {}
                if isinstance(rating_info, dict):
                    rating_value = rating_info.get("ratingValue")
                    try:
                        rating = float(rating_value)
                    except (TypeError, ValueError):
                        rating = None
                date_published = raw_review.get("datePublished")
                reviews.append(
                    ReviewRecord(
                        make=make,
                        model=model,
                        review=body.strip(),
                        rating=rating,
                        date=date_published,
                        source="edmunds",
                        source_url=url,
                    )
                )
            if len(reviews) >= limit:
                break

        if not reviews:
            logger.warning("No structured reviews found for %s %s", make, model)

        return reviews


def fetch_top_make_model_pairs(db_path: Path, top_k: int) -> List[MakeModel]:
    """Query the SQLite database for the most common make/model pairs."""

    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found at {db_path}. Ensure uni_vehicles.db is available."
        )

    logger.info("Querying top %d make/model pairs from %s", top_k, db_path)
    sql = (
        "SELECT make, model, COUNT(*) as cnt "
        "FROM unified_vehicle_listings "
        "WHERE make IS NOT NULL AND model IS NOT NULL "
        "GROUP BY make, model "
        "ORDER BY cnt DESC "
        "LIMIT ?"
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, (top_k,)).fetchall()

    return [MakeModel(row["make"], row["model"], int(row["cnt"])) for row in rows]


def write_reviews_to_csv(reviews: Iterable[ReviewRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Make", "Model", "Review", "ratings", "date", "source", "source_url"]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in reviews:
            writer.writerow(
                {
                    "Make": record.make,
                    "Model": record.model,
                    "Review": record.review,
                    "ratings": record.rating,
                    "date": record.date,
                    "source": record.source,
                    "source_url": record.source_url,
                }
            )
    logger.info("Wrote %s", output_path)


def run(db_path: Path, top_k: int, output_path: Path, reviews_per_pair: int) -> None:
    pairs = fetch_top_make_model_pairs(db_path, top_k)
    scraper = EdmundsConsumerReviewScraper()

    all_reviews: List[ReviewRecord] = []
    for pair in pairs:
        scraped = scraper.fetch_reviews(pair.make, pair.model, limit=reviews_per_pair)
        if scraped:
            all_reviews.extend(scraped)
        else:
            logger.info("Skipping %s %s due to missing reviews", pair.make, pair.model)

    if not all_reviews:
        logger.warning("No reviews collected. Check network access or Edmunds markup.")
    write_reviews_to_csv(all_reviews, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to uni_vehicles.db (default: data/car_dataset_idss/uni_vehicles.db)",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of make/model pairs to fetch")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output CSV file for scraped reviews",
    )
    parser.add_argument(
        "--reviews-per-pair",
        type=int,
        default=20,
        help="Maximum number of reviews to retain per make/model pair",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.db, args.top_k, args.output, args.reviews_per_pair)
