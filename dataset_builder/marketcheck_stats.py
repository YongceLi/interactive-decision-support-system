"""Generate summary statistics for the Marketcheck dataset."""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Iterable, List, Tuple


def _fetchall(cursor: sqlite3.Cursor, query: str, params: Tuple = ()) -> List[Tuple]:
    cursor.execute(query, params)
    return cursor.fetchall()


def _print_table(title: str, rows: Iterable[Tuple[str, int]]) -> None:
    rows = list(rows)
    if not rows:
        return
    print(f"\n{title}")
    print("-" * len(title))
    for label, count in rows:
        print(f"{label:<25} {count:>8}")


def price_buckets(prices: Iterable[float]) -> List[Tuple[str, int]]:
    ranges = [
        (0, 10000, "$0k-$10k"),
        (10000, 20000, "$10k-$20k"),
        (20000, 30000, "$20k-$30k"),
        (30000, 40000, "$30k-$40k"),
        (40000, 50000, "$40k-$50k"),
        (50000, 75000, "$50k-$75k"),
        (75000, 100000, "$75k-$100k"),
        (100000, None, ">= $100k"),
    ]
    bucket_counts: Counter[str] = Counter()

    for price in prices:
        if price is None:
            continue
        for lower, upper, label in ranges:
            if upper is None and price >= lower:
                bucket_counts[label] += 1
                break
            if lower <= price < upper:
                bucket_counts[label] += 1
                break

    return [(label, bucket_counts[label]) for _, _, label in ranges if bucket_counts[label]]


def new_vs_used(cursor: sqlite3.Cursor) -> None:
    rows = _fetchall(
        cursor,
        """
        SELECT COALESCE(inventory_type, 'unknown') AS type, COUNT(*)
        FROM marketcheck_listings
        GROUP BY COALESCE(inventory_type, 'unknown')
        ORDER BY COUNT(*) DESC
        """,
    )
    _print_table("Inventory Type Distribution", rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate statistics for Marketcheck dataset")
    parser.add_argument(
        "--db-path",
        default="data/marketcheck_vehicles.db",
        help="SQLite database path",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        total = _fetchall(cursor, "SELECT COUNT(*) FROM marketcheck_listings")[0][0]
        unique_vins = _fetchall(cursor, "SELECT COUNT(DISTINCT vin) FROM marketcheck_listings")[0][0]
        print(f"Total listings: {total:,}")
        print(f"Unique VINs: {unique_vins:,}")

        top_makes = _fetchall(
            cursor,
            """
            SELECT COALESCE(build_make, 'Unknown') AS make, COUNT(*)
            FROM marketcheck_listings
            GROUP BY COALESCE(build_make, 'Unknown')
            ORDER BY COUNT(*) DESC
            LIMIT 15
            """,
        )
        _print_table("Top Makes", top_makes)

        top_models = _fetchall(
            cursor,
            """
            SELECT COALESCE(build_model, 'Unknown') AS model, COUNT(*)
            FROM marketcheck_listings
            GROUP BY COALESCE(build_model, 'Unknown')
            ORDER BY COUNT(*) DESC
            LIMIT 15
            """,
        )
        _print_table("Top Models", top_models)

        price_rows = _fetchall(cursor, "SELECT price FROM marketcheck_listings WHERE price IS NOT NULL")
        prices = [row[0] for row in price_rows if isinstance(row[0], (int, float))]
        price_distribution = price_buckets(prices)
        if price_distribution:
            _print_table("Price Distribution", price_distribution)

        new_vs_used(cursor)

        state_rows = _fetchall(
            cursor,
            """
            SELECT COALESCE(dealer_state, 'Unknown') AS state, COUNT(*)
            FROM marketcheck_listings
            GROUP BY COALESCE(dealer_state, 'Unknown')
            ORDER BY COUNT(*) DESC
            LIMIT 10
            """,
        )
        _print_table("Top Dealer States", state_rows)

        avg_price_rows = _fetchall(
            cursor,
            """
            SELECT build_make, AVG(price)
            FROM marketcheck_listings
            WHERE price IS NOT NULL AND build_make IS NOT NULL
            GROUP BY build_make
            ORDER BY AVG(price) DESC
            LIMIT 10
            """,
        )
        if avg_price_rows:
            print("\nAverage Price by Make (Top 10)")
            print("------------------------------")
            for make, avg_price in avg_price_rows:
                print(f"{make:<15} ${avg_price:,.0f}")


if __name__ == "__main__":
    main()
