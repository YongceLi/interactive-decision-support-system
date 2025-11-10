"""Summaries for the unified_vehicle_listings table."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

DEFAULT_DB = Path("data/uni_vehicles.db")


def fetch_one(conn: sqlite3.Connection, query: str, params: Iterable = ()) -> int:
    cursor = conn.execute(query, params)
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def fetch_pairs(
    conn: sqlite3.Connection, query: str, params: Iterable = (), limit: int | None = None
) -> List[Tuple[str, int]]:
    sql = query + (f" LIMIT {int(limit)}" if limit else "")
    cursor = conn.execute(sql, params)
    results: List[Tuple[str, int]] = []
    for row in cursor.fetchall():
        key = row[0] if row[0] not in (None, "") else "(unknown)"
        results.append((key, int(row[1])))
    return results


def percentage(part: int, total: int) -> float:
    return (part / total * 100.0) if total else 0.0


def print_table(title: str, rows: List[Tuple[str, int]], total: int, max_rows: int = 20) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for label, count in rows[:max_rows]:
        pct = percentage(count, total)
        print(f"{label:<25} {count:>8}  ({pct:5.1f}%)")


def top_models_by_make(conn: sqlite3.Connection, top_makes: List[Tuple[str, int]], total: int) -> None:
    print("\nTop models within each of the top makes")
    print("--------------------------------------")
    for make, make_count in top_makes:
        cursor = conn.execute(
            """
            SELECT COALESCE(model, '(unknown)'), COUNT(*)
            FROM unified_vehicle_listings
            WHERE make = ?
            GROUP BY model
            ORDER BY COUNT(*) DESC
            LIMIT 10
            """,
            (make,),
        )
        models = cursor.fetchall()
        print(f"\n{make} ({percentage(make_count, total):.1f}% of fleet)")
        for model, model_count in models:
            model_label = model if model not in (None, "") else "(unknown)"
            pct = percentage(model_count, make_count)
            print(f"  {model_label:<25} {model_count:>6} ({pct:5.1f}%)")


def price_distribution(conn: sqlite3.Connection, total: int) -> None:
    buckets: List[Tuple[str, Tuple[Optional[int], Optional[int]]]] = [
        ("< $10k", (None, 10000)),
        ("$10k - $20k", (10000, 20000)),
        ("$20k - $30k", (20000, 30000)),
        ("$30k - $40k", (30000, 40000)),
        ("$40k - $50k", (40000, 50000)),
        ("$50k - $75k", (50000, 75000)),
        ("$75k - $100k", (75000, 100000)),
        ("$100k+", (100000, None)),
    ]

    print("\nPrice distribution")
    print("------------------")
    for label, (low, high) in buckets:
        if low is None:
            query = "SELECT COUNT(*) FROM unified_vehicle_listings WHERE price IS NOT NULL AND price < ?"
            count = fetch_one(conn, query, (high,))
        elif high is None:
            query = "SELECT COUNT(*) FROM unified_vehicle_listings WHERE price IS NOT NULL AND price >= ?"
            count = fetch_one(conn, query, (low,))
        else:
            query = "SELECT COUNT(*) FROM unified_vehicle_listings WHERE price IS NOT NULL AND price >= ? AND price < ?"
            count = fetch_one(conn, query, (low, high))
        print(f"{label:<15} {count:>8} ({percentage(count, total):5.1f}%)")

    unknown = fetch_one(conn, "SELECT COUNT(*) FROM unified_vehicle_listings WHERE price IS NULL")
    print(f"{'Unknown price':<15} {unknown:>8} ({percentage(unknown, total):5.1f}%)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Display statistics for unified_vehicle_listings")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to the SQLite database with unified_vehicle_listings",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        raise FileNotFoundError(f"Database not found: {args.db}")

    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        total = fetch_one(conn, "SELECT COUNT(*) FROM unified_vehicle_listings")
        distinct_vins = fetch_one(conn, "SELECT COUNT(DISTINCT vin) FROM unified_vehicle_listings")
        print(f"Total listings: {total:,}")
        print(f"Total distinct VINs: {distinct_vins:,}")
        if not total:
            print("No records in unified_vehicle_listings")
            return

        top_makes = fetch_pairs(
            conn,
            """
            SELECT make, COUNT(*)
            FROM unified_vehicle_listings
            GROUP BY make
            ORDER BY COUNT(*) DESC
            """,
            limit=20,
        )
        print_table("Top 20 makes", top_makes, total)
        top_models_by_make(conn, top_makes, total)

        inventory = fetch_pairs(
            conn,
            """
            SELECT is_used, COUNT(*)
            FROM unified_vehicle_listings
            GROUP BY is_used
            ORDER BY COUNT(*) DESC
            """,
        )
        print_table("Inventory type mix", inventory, total)

        price_distribution(conn, total)

        states = fetch_pairs(
            conn,
            """
            SELECT dealer_state, COUNT(*)
            FROM unified_vehicle_listings
            GROUP BY dealer_state
            ORDER BY COUNT(*) DESC
            """,
            limit=20,
        )
        print_table("Top dealer states", states, total)

        cities = fetch_pairs(
            conn,
            """
            SELECT dealer_city, COUNT(*)
            FROM unified_vehicle_listings
            GROUP BY dealer_city
            ORDER BY COUNT(*) DESC
            """,
            limit=20,
        )
        print_table("Top dealer cities", cities, total)

        zips = fetch_pairs(
            conn,
            """
            SELECT dealer_zip, COUNT(*)
            FROM unified_vehicle_listings
            GROUP BY dealer_zip
            ORDER BY COUNT(*) DESC
            """,
            limit=20,
        )
        print_table("Top dealer ZIP codes", zips, total)


if __name__ == "__main__":
    main()
