"""Fill missing normalized body type and fuel type values.

This script backfills ``norm_body_type`` and ``norm_fuel_type`` in the
``unified_vehicle_listings`` table using two strategies:

1. If other rows with the same ``make`` and ``model`` already have normalized
   values, the most common values for that pair are used.
2. If no normalized values exist for the pair, an LLM (``gpt-4o-mini``) is
   asked to suggest likely values. The response is cached per make/model so
   each pair only requires one LLM call.

Set ``OPENAI_API_KEY`` in your ``.env`` file to enable the LLM fallback.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

LOGGER = logging.getLogger(__name__)

DEFAULT_DB = Path("data/car_dataset_idss/uni_vehicles.db")


@dataclass(frozen=True)
class MakeModel:
    make: str
    model: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing norm_body_type and norm_fuel_type values using"
            " existing data or an LLM fallback."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to the SQLite database with unified_vehicle_listings.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model to query when a make/model pair lacks normalized data.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (e.g. DEBUG, INFO, WARNING).",
    )
    return parser.parse_args()


def most_common_value(
    connection: sqlite3.Connection, column: str, make: str, model: str
) -> Optional[str]:
    cursor = connection.execute(
        f"""
        SELECT {column}, COUNT(*) AS cnt
        FROM unified_vehicle_listings
        WHERE make = ? AND model = ? AND {column} IS NOT NULL
        GROUP BY {column}
        ORDER BY cnt DESC, {column} ASC
        LIMIT 1
        """,
        (make, model),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def fetch_pairs_with_missing(connection: sqlite3.Connection) -> Iterable[MakeModel]:
    cursor = connection.execute(
        """
        SELECT DISTINCT make, model
        FROM unified_vehicle_listings
        WHERE norm_body_type IS NULL OR norm_fuel_type IS NULL
        """
    )
    for make, model in cursor.fetchall():
        if make is None or model is None:
            continue
        yield MakeModel(make, model)


def update_missing_values(
    connection: sqlite3.Connection,
    pair: MakeModel,
    body_type: Optional[str],
    fuel_type: Optional[str],
) -> int:
    cursor = connection.execute(
        """
        UPDATE unified_vehicle_listings
        SET
            norm_body_type = CASE
                WHEN norm_body_type IS NULL AND :body_type IS NOT NULL THEN :body_type
                ELSE norm_body_type
            END,
            norm_fuel_type = CASE
                WHEN norm_fuel_type IS NULL AND :fuel_type IS NOT NULL THEN :fuel_type
                ELSE norm_fuel_type
            END
        WHERE make = :make
          AND model = :model
          AND (norm_body_type IS NULL OR norm_fuel_type IS NULL)
        """,
        {
            "body_type": body_type,
            "fuel_type": fuel_type,
            "make": pair.make,
            "model": pair.model,
        },
    )
    return cursor.rowcount


def infer_with_llm(
    client: OpenAI, model: str, pair: MakeModel
) -> Tuple[Optional[str], Optional[str]]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are predicting vehicle attributes. Return a JSON object"
                " with keys 'body_type' and 'fuel_type'. Body type should be a"
                " simple category such as sedan, SUV, pickup, coupe, wagon,"
                " hatchback, minivan, or convertible. Fuel type should be one"
                " of gasoline, diesel, hybrid, plug-in hybrid, or electric."
            ),
        },
        {
            "role": "user",
            "content": (
                "Provide the typical body type and fuel type for this vehicle."
                f"\nMake: {pair.make}\nModel: {pair.model}\n"
                "Respond with JSON only."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    body_type = payload.get("body_type")
    fuel_type = payload.get("fuel_type")
    LOGGER.debug(
        "LLM suggestion for %s %s: body=%s fuel=%s",
        pair.make,
        pair.model,
        body_type,
        fuel_type,
    )
    return body_type, fuel_type


def ensure_llm_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required to use the LLM fallback")
    return OpenAI(api_key=api_key)


def main() -> None:
    load_dotenv()
    args = parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(message)s")

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    llm_cache: Dict[MakeModel, Tuple[Optional[str], Optional[str]]] = {}
    client: Optional[OpenAI] = None

    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        pairs = list(fetch_pairs_with_missing(connection))
        if not pairs:
            LOGGER.info("No rows require backfilling")
            return

        updates_by_pair: Dict[MakeModel, int] = defaultdict(int)

        for pair in pairs:
            body_type = most_common_value(connection, "norm_body_type", pair.make, pair.model)
            fuel_type = most_common_value(connection, "norm_fuel_type", pair.make, pair.model)

            if body_type is None or fuel_type is None:
                if pair not in llm_cache:
                    if client is None:
                        client = ensure_llm_client()
                    llm_cache[pair] = infer_with_llm(client, args.model, pair)
                llm_body, llm_fuel = llm_cache[pair]
                body_type = body_type or llm_body
                fuel_type = fuel_type or llm_fuel

            if body_type is None and fuel_type is None:
                LOGGER.warning("Skipping %s %s; no values available", pair.make, pair.model)
                continue

            with connection:
                updated = update_missing_values(connection, pair, body_type, fuel_type)
                updates_by_pair[pair] = updated

        total_updates = sum(updates_by_pair.values())
        LOGGER.info("Backfilled %d rows across %d make/model pairs", total_updates, len(updates_by_pair))


if __name__ == "__main__":
    main()
