"""Read/write helpers for enriched review datasets."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

from .models import EnrichedReview, PersonaProfile, PreferenceBundle, QueryBundle


def _safe_json_load(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    value = value.strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def save_enriched_reviews(reviews: Iterable[EnrichedReview], path: Path | str) -> None:
    """Persist enriched reviews to CSV (JSON-encoding nested objects)."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [review.to_row() for review in reviews]
    if not rows:
        raise ValueError("No reviews to write")

    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            serialized = row.copy()
            serialized["explicit_preferences"] = json.dumps(row["explicit_preferences"], ensure_ascii=False)
            serialized["implicit_preferences"] = json.dumps(row["implicit_preferences"], ensure_ascii=False)
            serialized["persona"] = json.dumps(row["persona"], ensure_ascii=False)
            serialized["queries"] = json.dumps(row["queries"], ensure_ascii=False)
            writer.writerow(serialized)


def load_enriched_reviews(path: Path | str) -> List[EnrichedReview]:
    """Load enriched reviews from CSV."""

    reviews: List[EnrichedReview] = []
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    with input_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            explicit = _safe_json_load(row.get("explicit_preferences")) or {}
            implicit = _safe_json_load(row.get("implicit_preferences")) or {}
            persona_data = _safe_json_load(row.get("persona")) or {}
            queries = _safe_json_load(row.get("queries")) or {}

            preferences = PreferenceBundle(
                explicit=explicit,
                implicit=implicit,
                mentioned_like=[p.strip() for p in (row.get("mentioned_like") or "").split(",") if p.strip()],
                mentioned_dislike=[p.strip() for p in (row.get("mentioned_dislike") or "").split(",") if p.strip()],
                mentioned_setup=(row.get("mentioned_setup") or "").strip() or None,
                performance=row.get("performance") or "mid-range",
                newness=int(row.get("newness") or 5),
                price_range=row.get("price_range") or "mid-range",
                openness_to_alternative=int(row.get("openness_to_alternative") or 5),
            )

            persona = PersonaProfile(
                summary=persona_data.get("summary", ""),
                review_date=persona_data.get("review_date", row.get("date", "")),
                source=persona_data.get("source", row.get("source", "")),
                rating=float(persona_data.get("rating") or row.get("rating") or 0),
                brand=persona_data.get("brand", row.get("brand", "")),
                product=persona_data.get("product", row.get("product", "")),
                norm_product=persona_data.get("norm_product", row.get("norm_product", "")),
                performance=persona_data.get("performance", preferences.performance),
                newness=int(persona_data.get("newness") or preferences.newness),
                price_range=persona_data.get("price_range", preferences.price_range),
                openness_to_alternative=int(
                    persona_data.get("openness_to_alternative")
                    or preferences.openness_to_alternative
                ),
                likes=persona_data.get("likes", preferences.mentioned_like),
                dislikes=persona_data.get("dislikes", preferences.mentioned_dislike),
                setup_notes=persona_data.get("setup_notes") or preferences.mentioned_setup,
                extra_context=persona_data.get("extra_context", {}),
            )

            query_bundle = QueryBundle(
                primary=queries.get("primary", ""),
                alternates=queries.get("alternates", []),
            )

            reviews.append(
                EnrichedReview(
                    review_id=row.get("review_id", str(len(reviews))),
                    brand=row.get("brand", ""),
                    product=row.get("product", ""),
                    norm_product=row.get("norm_product", ""),
                    review=row.get("review", ""),
                    rating=float(row.get("rating") or 0),
                    date=row.get("date", ""),
                    source=row.get("source", ""),
                    preferences=preferences,
                    persona=persona,
                    queries=query_bundle,
                )
            )

    return reviews
